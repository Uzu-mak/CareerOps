"""Saved sign-in sessions for job portals.

You sign in once yourself (scripts/signin.py opens a real browser window); the
site's cookies and local storage (Playwright "storage state") are saved and
reused by the browser agent, so it reaches the application already signed in.
CareerOps never sees or stores the password. Sessions live in the uploads folder
(your machine, or your private bucket when hosted) and can be deleted any time.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

MAX_BYTES = 3 * 1024 * 1024
PROVIDER = 'session'


def site_key(url: str | None) -> str | None:
    """The site a session belongs to: 'metacareers.com', or the full tenant host on Workday."""
    host = (urlparse(url or '').netloc or '').lower().split(':')[0]
    if not host or '.' not in host:
        return None
    if host.endswith('myworkdayjobs.com') or host.endswith('myworkdaysite.com'):
        return host                              # each company is its own Workday tenant
    parts = host.split('.')
    two_level = {'co.uk', 'com.au', 'co.in', 'com.br', 'co.jp', 'com.sg'}
    if len(parts) >= 3 and '.'.join(parts[-2:]) in two_level:
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:])


def validate_state(state) -> dict:
    if not isinstance(state, dict) or not isinstance(state.get('cookies'), list):
        raise ValueError('Not a browser session: expected {"cookies": [...], "origins": [...]}')
    if not state['cookies'] and not state.get('origins'):
        raise ValueError('The session is empty; sign in before closing the window')
    return {'cookies': state['cookies'], 'origins': state.get('origins') or []}


def _dir() -> Path:
    from careerops.core.config import settings
    d = settings.uploads_path / 'sessions'
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_session(db, url: str, state) -> dict:
    from sqlalchemy import select

    from careerops.db.models import PortalAccount

    key = site_key(url)
    if not key:
        raise ValueError('Give the address of the site you signed in to, e.g. https://www.metacareers.com')
    state = validate_state(state)
    raw = json.dumps(state)
    if len(raw) > MAX_BYTES:
        raise ValueError('Session is unexpectedly large')
    safe = re.sub(r'[^a-z0-9.-]', '_', key)
    path = _dir() / f'{safe}.json'
    path.write_text(raw, encoding='utf-8')
    try:
        path.chmod(0o600)
    except OSError:
        pass
    row = db.scalar(select(PortalAccount).where(PortalAccount.provider == PROVIDER, PortalAccount.company == key))
    if not row:
        row = PortalAccount(provider=PROVIDER, company=key, auth_strategy='saved_session')
        db.add(row)
    row.status = 'authenticated'
    row.session_state_uri = str(path)
    row.last_authenticated_at = datetime.now(timezone.utc)
    row.notes = f'{len(state["cookies"])} cookies'
    db.commit(); db.refresh(row)
    return {'id': row.id, 'site': key, 'cookies': len(state['cookies'])}


def session_for(db, url: str | None):
    """The saved, still-valid session for this URL's site, or None."""
    from sqlalchemy import select

    from careerops.db.models import PortalAccount

    key = site_key(url)
    if not key:
        return None
    row = db.scalar(select(PortalAccount).where(PortalAccount.provider == PROVIDER, PortalAccount.company == key,
                                                PortalAccount.status == 'authenticated'))
    if row and row.session_state_uri and Path(row.session_state_uri).exists():
        return row
    return None


def mark_expired(db, row) -> None:
    row.status = 'expired'
    db.add(row); db.commit()


SIGN_IN_WALLS = {'portal sign-in/session required', 'portal account password / email verification'}


def note_expired_session(db, saved, result) -> None:
    """A saved session that still lands on a sign-in wall has expired: say so instead."""
    if saved and any(m in SIGN_IN_WALLS for m in result.manual_fields):
        mark_expired(db, saved)
        result.manual_fields = ['saved sign-in expired' if m in SIGN_IN_WALLS else m for m in result.manual_fields]


def delete_session(db, row) -> None:
    if row.session_state_uri:
        Path(row.session_state_uri).unlink(missing_ok=True)
    db.delete(row); db.commit()
