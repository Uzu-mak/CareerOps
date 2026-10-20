"""Find companies, not just jobs.

When a job found anywhere (Hacker News, Remotive, Adzuna, alert emails...) links
to a Greenhouse, Lever or Ashby board, that company's whole board is added as a
source. CareerOps then sees every role the company posts, and those are the
forms the browser agent can fill. This is how small companies you have never
heard of end up being watched automatically.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

TOKEN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{1,79}$')
RESERVED = {'embed', 'v1', 'jobs', 'job', 'api', 'boards', 'careers', 'apply', 'search', 'static', 'assets'}


def ats_board_from_url(url: str | None) -> tuple[str, str] | None:
    """('greenhouse'|'lever'|'ashby', board token) for an ATS job or board URL, else None."""
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.netloc or '').lower().split(':')[0]
    parts = [p for p in parsed.path.split('/') if p]
    kind = token = None
    if host.endswith('greenhouse.io') and host.split('.')[0] in {'boards', 'job-boards', 'www', 'greenhouse'}:
        kind = 'greenhouse'
        if parts[:1] == ['embed']:
            token = (parse_qs(parsed.query).get('for') or [None])[0]
        elif parts:
            token = parts[0]
    elif host in {'jobs.lever.co', 'jobs.eu.lever.co'} and parts:
        kind, token = 'lever', parts[0]
    elif host == 'jobs.ashbyhq.com' and parts:
        kind, token = 'ashby', parts[0]
    if not kind or not token or token.lower() in RESERVED or not TOKEN.match(token):
        return None
    return kind, token.lower() if kind != 'ashby' else token


def boards_in_item(item: dict) -> list[tuple[str, str]]:
    urls = [item.get('application_url'), item.get('canonical_url')]
    urls += list((item.get('raw_payload') or {}).get('links') or [])
    found = []
    for u in urls:
        b = ats_board_from_url(u)
        if b and b not in found:
            found.append(b)
    return found


def discover_boards(db, items: list[dict], origin: str, limit: int = 15) -> list[str]:
    """Add ATS boards referenced by ``items`` as new sources. Returns the names added."""
    from sqlalchemy import select

    from careerops.db.models import SourceConfig

    existing = {(s.source_type, (s.token_or_url or '').lower()) for s in db.scalars(select(SourceConfig)).all()}
    added: list[str] = []
    for item in items:
        for kind, token in boards_in_item(item):
            if len(added) >= limit:
                return added
            if (kind, token.lower()) in existing:
                continue
            name = (item.get('company') or token).strip()[:150] or token
            db.add(SourceConfig(source_type=kind, name=name, token_or_url=token, enabled=True, scan_interval_minutes=240,
                                last_status=f'found via {origin}', discovered_from=origin[:80]))
            existing.add((kind, token.lower()))
            added.append(name)
    if added:
        db.commit()
    return added
