"""Login middleware: hosted instances are closed by default and only allowed Google accounts get in."""
import asyncio
import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest

from careerops.core.auth import (
    SESSION_COOKIE, STATE_COOKIE, AuthConfig, AuthConfigError, AuthMiddleware, email_from_id_token, safe_next, sign, unsign,
)

SECRET = 'k' * 48


def config(**overrides):
    values = dict(mode='google', environment='production', secret_key=SECRET, base_url='https://careerops.example.run.app',
                  google_client_id='client-123', google_client_secret='shh', allowed_emails={'me@example.com'},
                  api_token='t' * 40, alert_ingest_token='ingest-secret')
    values.update(overrides)
    return AuthConfig(**values)


def id_token(**claims):
    base = {'iss': 'https://accounts.google.com', 'aud': 'client-123', 'exp': time.time() + 300,
            'email': 'me@example.com', 'email_verified': True}
    base.update(claims)
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b'=').decode()
    return f'{enc({"alg": "RS256"})}.{enc(base)}.sig'


async def _app(scope, receive, send):
    body = json.dumps({'path': scope['path'], 'user': scope['state'].get('user')}).encode()
    await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'application/json')]})
    await send({'type': 'http.response.body', 'body': body})


def call(mw, path, method='GET', headers=None, query=''):
    scope = {'type': 'http', 'path': path, 'method': method, 'query_string': query.encode(),
             'headers': [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}
    sent = []

    async def receive():
        return {'type': 'http.request', 'body': b''}

    async def send(message):
        sent.append(message)

    asyncio.run(mw(scope, receive, send))
    start = sent[0]
    hdrs = [(k.decode(), v.decode()) for k, v in start['headers']]
    body = b''.join(m.get('body', b'') for m in sent[1:])
    return start['status'], hdrs, body


def header(hdrs, name):
    return [v for k, v in hdrs if k == name]


def cookie_value(hdrs, name):
    for v in header(hdrs, 'set-cookie'):
        if v.startswith(name + '='):
            return v.split(';')[0].split('=', 1)[1]
    return None


def test_hosted_instance_without_login_refuses_to_start():
    with pytest.raises(AuthConfigError, match='only allowed when ENVIRONMENT=local'):
        AuthConfig(mode='none', environment='production').validate()
    AuthConfig(mode='none', environment='local').validate()  # your own machine is fine


def test_google_mode_requires_complete_safe_settings():
    with pytest.raises(AuthConfigError, match='SECRET_KEY'):
        config(secret_key='replace-me-in-production').validate()
    with pytest.raises(AuthConfigError, match='ALLOWED_EMAILS'):
        config(allowed_emails=set()).validate()
    with pytest.raises(AuthConfigError, match='GOOGLE_CLIENT_ID'):
        config(google_client_secret='').validate()
    with pytest.raises(AuthConfigError, match='BASE_URL'):
        config(base_url='http://careerops.example.com').validate()
    config().validate()


def test_pages_redirect_to_login_and_api_returns_401():
    mw = AuthMiddleware(_app, config())
    status, hdrs, _ = call(mw, '/applications', headers={'accept': 'text/html'}, query='tab=open')
    assert status == 303
    assert header(hdrs, 'location') == ['/auth/login?next=%2Fapplications%3Ftab%3Dopen']

    status, _, body = call(mw, '/api/jobs')
    assert status == 401 and b'Sign in required' in body
    status, _, _ = call(mw, '/docs', headers={'accept': 'text/html'})
    assert status == 303


def test_public_paths_stay_open():
    mw = AuthMiddleware(_app, config())
    assert call(mw, '/api/health')[0] == 200
    assert call(mw, '/static/app.js')[0] == 200
    assert call(mw, '/api/alerts/email', method='POST')[0] == 200      # route checks its own token
    closed = AuthMiddleware(_app, config(alert_ingest_token=''))
    assert call(closed, '/api/alerts/email', method='POST')[0] == 401  # no token configured -> not public


def test_full_google_sign_in_flow_sets_session():
    exchanged = []

    def fake_exchange(cfg, code):
        exchanged.append(code)
        return {'id_token': id_token()}

    mw = AuthMiddleware(_app, config(), token_exchange=fake_exchange)
    status, hdrs, _ = call(mw, '/auth/login', query='next=/applications')
    assert status == 303
    google = urlparse(header(hdrs, 'location')[0])
    params = {k: v[0] for k, v in parse_qs(google.query).items()}
    assert google.netloc == 'accounts.google.com'
    assert params['redirect_uri'] == 'https://careerops.example.run.app/auth/callback'
    assert params['scope'] == 'openid email'
    state = cookie_value(hdrs, STATE_COOKIE)
    assert state == params['state'] and 'Secure' in header(hdrs, 'set-cookie')[0]

    status, hdrs, _ = call(mw, '/auth/callback', headers={'cookie': f'{STATE_COOKIE}={state}'},
                           query=f'state={state}&code=abc')
    assert status == 303 and header(hdrs, 'location') == ['/applications']
    assert exchanged == ['abc']
    session = cookie_value(hdrs, SESSION_COOKIE)

    status, _, body = call(mw, '/api/jobs', headers={'cookie': f'{SESSION_COOKIE}={session}'})
    assert status == 200 and json.loads(body)['user'] == 'me@example.com'


def test_callback_rejects_state_from_another_browser():
    mw = AuthMiddleware(_app, config(), token_exchange=lambda c, code: {'id_token': id_token()})
    state = sign({'n': 'x', 'next': '/', 'exp': time.time() + 60}, SECRET, 'oauth')
    status, _, body = call(mw, '/auth/callback', query=f'state={state}&code=abc')  # no matching cookie
    assert status == 403 and b'another browser' in body


def test_other_google_accounts_are_turned_away():
    mw = AuthMiddleware(_app, config(), token_exchange=lambda c, code: {'id_token': id_token(email='stranger@example.com')})
    _, hdrs, _ = call(mw, '/auth/login')
    state = cookie_value(hdrs, STATE_COOKIE)
    status, hdrs, body = call(mw, '/auth/callback', headers={'cookie': f'{STATE_COOKIE}={state}'}, query=f'state={state}&code=c')
    assert status == 403 and b'not allowed' in body
    assert cookie_value(hdrs, SESSION_COOKIE) is None


def test_id_token_claims_are_checked():
    cfg = config()
    assert email_from_id_token(cfg, id_token()) == 'me@example.com'
    for bad, reason in [({'aud': 'other'}, 'different client'), ({'iss': 'evil.com'}, 'not issued'),
                        ({'exp': time.time() - 5}, 'expired'), ({'email_verified': False}, 'not verified')]:
        with pytest.raises(PermissionError, match=reason):
            email_from_id_token(cfg, id_token(**bad))


def test_tampered_or_expired_session_is_rejected():
    mw = AuthMiddleware(_app, config())
    good = sign({'email': 'me@example.com', 'exp': time.time() + 60}, SECRET, 'session')
    forged = sign({'email': 'me@example.com', 'exp': time.time() + 60}, 'x' * 48, 'session')
    expired = sign({'email': 'me@example.com', 'exp': time.time() - 1}, SECRET, 'session')
    state_as_session = sign({'email': 'me@example.com', 'exp': time.time() + 60}, SECRET, 'oauth')
    assert call(mw, '/api/jobs', headers={'cookie': f'{SESSION_COOKIE}={good}'})[0] == 200
    for value in [forged, expired, state_as_session, good[:-2] + 'xx']:
        assert call(mw, '/api/jobs', headers={'cookie': f'{SESSION_COOKIE}={value}'})[0] == 401
    removed = sign({'email': 'old@example.com', 'exp': time.time() + 60}, SECRET, 'session')
    assert call(mw, '/api/jobs', headers={'cookie': f'{SESSION_COOKIE}={removed}'})[0] == 401  # no longer allowed


def test_api_token_for_scripts():
    mw = AuthMiddleware(_app, config())
    status, _, body = call(mw, '/api/jobs', headers={'authorization': 'Bearer ' + 't' * 40})
    assert status == 200 and json.loads(body)['user'] == 'api-token'
    assert call(mw, '/api/jobs', headers={'authorization': 'Bearer wrong'})[0] == 401


def test_local_mode_lets_everything_through():
    mw = AuthMiddleware(_app, AuthConfig(mode='none', environment='local'))
    status, _, body = call(mw, '/api/jobs')
    assert status == 200 and json.loads(body)['user'] is None


def test_logout_clears_session_and_next_cannot_leave_the_site():
    status, hdrs, _ = call(AuthMiddleware(_app, config()), '/auth/logout')
    assert status == 303 and cookie_value(hdrs, SESSION_COOKIE) == ''
    for evil in ['https://evil.com', '//evil.com', '/\\evil.com', 'evil', '/auth/callback']:
        assert safe_next(evil) == '/'
    assert safe_next('/jobs/3') == '/jobs/3'
    assert unsign('garbage', SECRET, 'session') is None
