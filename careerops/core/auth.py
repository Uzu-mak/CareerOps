"""Login for a hosted CareerOps instance.

CareerOps holds a resume, work-authorization answers and the power to submit
applications, so a hosted copy must not be reachable by anyone with the URL.

Modes (``AUTH_MODE``):

* ``none``   - no login. Only allowed when ``ENVIRONMENT=local`` (your machine).
* ``google`` - "Sign in with Google", restricted to ``ALLOWED_EMAILS``.

In ``google`` mode an ``API_TOKEN`` can also be sent as ``Authorization: Bearer
<token>`` for scripts and the MCP server.

This is plain ASGI middleware with no extra dependencies: it handles
``/auth/login``, ``/auth/callback`` and ``/auth/logout`` itself, and requires a
valid session (an HMAC-signed cookie) for everything else except the health
check, static files and the token-protected alert-ingest endpoint.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlencode

SESSION_COOKIE = 'careerops_session'
STATE_COOKIE = 'careerops_oauth'
GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_ISSUERS = {'accounts.google.com', 'https://accounts.google.com'}
DEFAULT_SECRET = 'replace-me-in-production'


class AuthConfigError(RuntimeError):
    """The deployment's auth settings are unsafe or incomplete."""


@dataclass
class AuthConfig:
    mode: str = 'none'
    environment: str = 'local'
    secret_key: str = DEFAULT_SECRET
    base_url: str = 'http://localhost:8000'
    google_client_id: str = ''
    google_client_secret: str = ''
    allowed_emails: set[str] = field(default_factory=set)
    api_token: str = ''
    session_hours: int = 12
    alert_ingest_token: str = ''

    @classmethod
    def from_settings(cls, settings) -> 'AuthConfig':
        return cls(
            mode=(settings.auth_mode or 'none').strip().lower(),
            environment=(settings.environment or 'local').strip().lower(),
            secret_key=settings.secret_key or '',
            base_url=(settings.base_url or '').rstrip('/'),
            google_client_id=settings.google_client_id or '',
            google_client_secret=settings.google_client_secret or '',
            allowed_emails={e.strip().lower() for e in (settings.allowed_emails or '').split(',') if e.strip()},
            api_token=settings.api_token or '',
            session_hours=settings.session_hours,
            alert_ingest_token=settings.alert_ingest_token or '',
        )

    @property
    def secure_cookies(self) -> bool:
        return self.base_url.startswith('https://')

    @property
    def redirect_uri(self) -> str:
        return f'{self.base_url}/auth/callback'

    def validate(self) -> None:
        """Refuse to start a deployment that would be open to the internet."""
        if self.mode == 'none':
            if self.environment not in {'local', 'test', 'dev', 'development'}:
                raise AuthConfigError(
                    f'AUTH_MODE=none is only allowed when ENVIRONMENT=local (got ENVIRONMENT={self.environment}). '
                    'Set AUTH_MODE=google with GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and ALLOWED_EMAILS.')
            return
        if self.mode != 'google':
            raise AuthConfigError(f'Unknown AUTH_MODE={self.mode!r}; use none or google.')
        problems = []
        if not self.google_client_id or not self.google_client_secret:
            problems.append('GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are required')
        if not self.allowed_emails:
            problems.append('ALLOWED_EMAILS must list at least one email')
        if self.secret_key in {'', DEFAULT_SECRET} or len(self.secret_key) < 32:
            problems.append('SECRET_KEY must be a random value of at least 32 characters')
        if self.api_token and len(self.api_token) < 32:
            problems.append('API_TOKEN must be at least 32 characters when set')
        if not self.base_url.startswith(('https://', 'http://localhost', 'http://127.0.0.1')):
            problems.append('BASE_URL must be the public https:// URL (used for the Google redirect)')
        if problems:
            raise AuthConfigError('Auth configuration: ' + '; '.join(problems))


# --------------------------------------------------------------------------- signed values

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def sign(payload: dict, secret: str, purpose: str) -> str:
    body = _b64(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode())
    mac = hmac.new(secret.encode(), f'{purpose}.{body}'.encode(), hashlib.sha256).digest()
    return f'{body}.{_b64(mac)}'


def unsign(value: str | None, secret: str, purpose: str, now: float | None = None) -> dict | None:
    """Return the payload if the signature is valid and it has not expired."""
    if not value or value.count('.') != 1:
        return None
    body, mac = value.split('.')
    expected = hmac.new(secret.encode(), f'{purpose}.{body}'.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_unb64(mac), expected):
            return None
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or float(payload.get('exp', 0)) < (now or time.time()):
        return None
    return payload


def safe_next(path: str | None) -> str:
    """Only same-site relative paths, so /auth/login?next= cannot redirect off-site."""
    if not path or not path.startswith('/') or path.startswith('//') or '\\' in path or path.startswith('/auth/'):
        return '/'
    return path


# --------------------------------------------------------------------------- Google sign-in

def google_login_url(cfg: AuthConfig, state: str) -> str:
    return GOOGLE_AUTH_URL + '?' + urlencode({
        'client_id': cfg.google_client_id, 'redirect_uri': cfg.redirect_uri, 'response_type': 'code',
        'scope': 'openid email', 'state': state, 'prompt': 'select_account',
    })


def exchange_code(cfg: AuthConfig, code: str) -> dict:
    import httpx

    response = httpx.post(GOOGLE_TOKEN_URL, data={
        'code': code, 'client_id': cfg.google_client_id, 'client_secret': cfg.google_client_secret,
        'redirect_uri': cfg.redirect_uri, 'grant_type': 'authorization_code',
    }, timeout=15)
    response.raise_for_status()
    return response.json()


def email_from_id_token(cfg: AuthConfig, id_token: str, now: float | None = None) -> str:
    """Check the ID token's claims and return the allowed email, or raise PermissionError.

    The token comes straight from Google's token endpoint over TLS in exchange
    for our client secret, so per OpenID Connect Core 3.1.3.7 its claims can be
    trusted without re-verifying the signature.
    """
    try:
        claims = json.loads(_unb64(id_token.split('.')[1]))
    except (IndexError, ValueError, TypeError) as exc:
        raise PermissionError('malformed ID token') from exc
    if claims.get('iss') not in GOOGLE_ISSUERS:
        raise PermissionError('ID token not issued by Google')
    if claims.get('aud') != cfg.google_client_id:
        raise PermissionError('ID token is for a different client')
    if float(claims.get('exp', 0)) < (now or time.time()):
        raise PermissionError('ID token expired')
    email = str(claims.get('email') or '').lower()
    if not email or claims.get('email_verified') not in (True, 'true'):
        raise PermissionError('Google account email is not verified')
    if email not in cfg.allowed_emails:
        raise PermissionError(f'{email} is not allowed to use this CareerOps instance')
    return email


# --------------------------------------------------------------------------- access rules

def is_public(path: str, method: str, cfg: AuthConfig) -> bool:
    if path in {'/api/health', '/favicon.ico', '/auth/login', '/auth/callback', '/auth/logout'}:
        return True
    if path.startswith('/static/'):
        return True
    # Has its own shared-secret check; only public when that secret is configured.
    if path == '/api/alerts/email' and method == 'POST' and cfg.alert_ingest_token:
        return True
    return False


def authenticate(cfg: AuthConfig, cookies: dict[str, str], authorization: str | None) -> str | None:
    """Return the signed-in identity, or None."""
    if authorization and authorization.lower().startswith('bearer ') and cfg.api_token:
        if hmac.compare_digest(authorization[7:].strip().encode(), cfg.api_token.encode()):
            return 'api-token'
    session = unsign(cookies.get(SESSION_COOKIE), cfg.secret_key, 'session')
    if session and str(session.get('email', '')).lower() in cfg.allowed_emails:
        return session['email']
    return None


def _cookie(name: str, value: str, cfg: AuthConfig, max_age: int) -> str:
    parts = [f'{name}={value}', 'Path=/', 'HttpOnly', 'SameSite=Lax', f'Max-Age={max_age}']
    if cfg.secure_cookies:
        parts.append('Secure')
    return '; '.join(parts)


# --------------------------------------------------------------------------- ASGI middleware

class AuthMiddleware:
    def __init__(self, app, config: AuthConfig | None = None, token_exchange=None):
        self.app = app
        self._config = config
        self._exchange = token_exchange or exchange_code

    @property
    def cfg(self) -> AuthConfig:
        if self._config is None:
            from careerops.core.config import settings
            self._config = AuthConfig.from_settings(settings)
        return self._config

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        cfg = self.cfg
        state = dict(scope.get('state') or {})
        if cfg.mode == 'none':
            state['user'] = None
            return await self.app({**scope, 'state': state}, receive, send)

        path, method = scope.get('path', '/'), scope.get('method', 'GET')
        headers = {k.decode('latin-1').lower(): v.decode('latin-1') for k, v in scope.get('headers', [])}
        cookies = {k: m.value for k, m in SimpleCookie(headers.get('cookie', '')).items()}
        query = {k: v[0] for k, v in parse_qs(scope.get('query_string', b'').decode()).items()}

        if path == '/auth/login':
            return await self._login(send, cfg, query)
        if path == '/auth/callback':
            return await self._callback(send, cfg, query, cookies)
        if path == '/auth/logout':
            return await _respond(send, 303, [('location', '/auth/login?signed_out=1'),
                                              ('set-cookie', _cookie(SESSION_COOKIE, '', cfg, 0))])

        user = authenticate(cfg, cookies, headers.get('authorization'))
        if user is None and not is_public(path, method, cfg):
            if scope['type'] == 'websocket':
                return await send({'type': 'websocket.close', 'code': 1008})
            wants_html = method == 'GET' and not path.startswith('/api/') and 'text/html' in headers.get('accept', 'text/html')
            if wants_html:
                target = path + ('?' + scope['query_string'].decode() if scope.get('query_string') else '')
                return await _respond(send, 303, [('location', '/auth/login?' + urlencode({'next': safe_next(target)}))])
            return await _respond(send, 401, [('content-type', 'application/json'), ('www-authenticate', 'Bearer')],
                                  b'{"detail":"Sign in required"}')
        state['user'] = user
        return await self.app({**scope, 'state': state}, receive, send)

    async def _login(self, send, cfg: AuthConfig, query: dict):
        if query.get('signed_out') or query.get('error'):
            message = 'You are signed out.' if query.get('signed_out') else query['error']
            return await _respond(send, 200 if query.get('signed_out') else 403, [('content-type', 'text/html; charset=utf-8')],
                                  _page(message, '/auth/login'))
        nonce = secrets.token_urlsafe(16)
        state = sign({'n': nonce, 'next': safe_next(query.get('next')), 'exp': time.time() + 600}, cfg.secret_key, 'oauth')
        return await _respond(send, 303, [('location', google_login_url(cfg, state)),
                                          ('set-cookie', _cookie(STATE_COOKIE, state, cfg, 600))])

    async def _callback(self, send, cfg: AuthConfig, query: dict, cookies: dict):
        state = query.get('state', '')
        payload = unsign(state, cfg.secret_key, 'oauth')
        # The state must match the cookie set on this browser (login CSRF protection).
        if not payload or not hmac.compare_digest(state.encode(), cookies.get(STATE_COOKIE, '').encode()):
            return await self._deny(send, 'Sign-in expired or was started in another browser. Try again.')
        if query.get('error') or not query.get('code'):
            return await self._deny(send, 'Google sign-in was cancelled.')
        try:
            tokens = await asyncio.to_thread(self._exchange, cfg, query['code'])
            email = email_from_id_token(cfg, tokens.get('id_token', ''))
        except PermissionError as exc:
            return await self._deny(send, str(exc))
        except Exception:
            return await self._deny(send, 'Could not complete Google sign-in.')
        max_age = int(cfg.session_hours * 3600)
        session = sign({'email': email, 'exp': time.time() + max_age}, cfg.secret_key, 'session')
        return await _respond(send, 303, [('location', payload.get('next') or '/'),
                                          ('set-cookie', _cookie(SESSION_COOKIE, session, cfg, max_age)),
                                          ('set-cookie', _cookie(STATE_COOKIE, '', cfg, 0))])

    async def _deny(self, send, message: str):
        return await _respond(send, 403, [('content-type', 'text/html; charset=utf-8'),
                                          ('set-cookie', _cookie(STATE_COOKIE, '', self.cfg, 0))], _page(message, '/auth/login'))


def _page(message: str, retry: str) -> bytes:
    from html import escape
    return (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>CareerOps sign-in</title><link rel='stylesheet' href='/static/styles.css'></head>"
            f"<body><main style='max-width:420px;margin:12vh auto;padding:24px'><h1>CareerOps</h1><p>{escape(message)}</p>"
            f"<p><a class='btn' href='{escape(retry)}'>Sign in with Google</a></p></main></body></html>").encode()


async def _respond(send, status: int, headers: list[tuple[str, str]], body: bytes = b''):
    await send({'type': 'http.response.start', 'status': status,
                'headers': [(k.encode('latin-1'), v.encode('latin-1')) for k, v in headers] +
                           [(b'content-length', str(len(body)).encode()), (b'cache-control', b'no-store')]})
    await send({'type': 'http.response.body', 'body': body})
