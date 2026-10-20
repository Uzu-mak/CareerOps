"""Hacker News "Ask HN: Who is hiring?" — a monthly thread of mostly small companies and startups.

Uses the public Algolia HN Search API (no key). Each top-level comment is one
company's post, conventionally starting with "Company | Role | Location | ...".
"""
from __future__ import annotations

import html
import re

from careerops.sources.base import JobSource

API = 'https://hn.algolia.com/api/v1'
ROLE = re.compile(r'\b(engineer|engineering|developer|scientist|architect|designer|analyst|researcher|devops|sre|'
                  r'founding|full[- ]?stack|back[- ]?end|front[- ]?end|ml|ai|data|platform|infrastructure|product manager|'
                  r'cto|lead|head of|intern|programmer)\b', re.I)
PLACE = re.compile(r'\b(remote|onsite|on-site|hybrid|in[- ]office|usa?|united states|europe|emea|uk|canada|worldwide|anywhere|'
                   r'nyc|new york|sf|san francisco|bay area|seattle|boston|austin|london|berlin|toronto|chicago|denver|la|los angeles)\b'
                   r'|,\s*[A-Z]{2}\b', re.I)
WORKPLACE_ONLY = re.compile(r'^(?:\s|[,/&()+-]|\b(?:remote|hybrid|on-?site|in[- ]office|full[- ]?time|part[- ]?time|contract|only|ok|and|or|friendly|first)\b)+$', re.I)
TAG = re.compile(r'<[^>]+>')
HREF = re.compile(r'href="([^"]+)"')


def _text(fragment: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(TAG.sub(' ', fragment or ''))).strip()


def parse_post(hit: dict) -> dict | None:
    """Map one "Who is hiring?" comment to a job dict, or None if it isn't a hiring post."""
    raw = hit.get('comment_text') or ''
    if not raw:
        return None
    header_html = re.split(r'<p>', raw, maxsplit=1)[0]
    header = _text(header_html)
    segments = [s.strip() for s in re.split(r'\s\|\s|\s•\s|\s·\s', header) if s.strip()]
    if len(segments) < 2:
        return None
    company = re.sub(r'https?://\S+', '', segments[0]).strip(' -–:') or segments[0]
    rest = segments[1:]
    roles = [s for s in rest if ROLE.search(s) and len(s) <= 160]
    places = [s for s in rest if PLACE.search(s) and s not in roles and len(s) <= 120 and not WORKPLACE_ONLY.match(s)]
    low = header.lower()
    workplace = ('remote' if re.search(r'\bremote\b', low) and not re.search(r'\bno remote\b', low)
                 else 'hybrid' if 'hybrid' in low else 'onsite' if re.search(r'\bon-?site\b|in[- ]office', low) else None)
    links = [html.unescape(u) for u in HREF.findall(raw)]
    item_url = f'https://news.ycombinator.com/item?id={hit.get("objectID")}'
    external = [u for u in links if 'ycombinator.com' not in u]
    from careerops.services.board_discovery import ats_board_from_url
    apply = next((u for u in external if ats_board_from_url(u)), None) or (external[0] if external else item_url)
    return {
        'source': 'hn_hiring', 'source_job_id': f'hn:{hit.get("objectID")}', 'ats': 'aggregator',
        'canonical_url': item_url, 'application_url': apply,
        'company': company[:200], 'title': (', '.join(roles) or 'Engineering roles (see post)')[:300],
        'location': '; '.join(places)[:400] or None, 'workplace_type': workplace,
        'description': _text(raw.replace('<p>', '\n\n'))[:20000], 'posted_at': hit.get('created_at'),
        'raw_payload': {'hn_id': hit.get('objectID'), 'links': links[:20], 'header': header[:500]},
    }


class HNHiringSource(JobSource):
    def __init__(self, max_posts: int = 1000):
        self.max_posts = max(50, min(3000, max_posts))

    async def fetch(self) -> list[dict]:
        import httpx

        async with httpx.AsyncClient(timeout=30, headers={'User-Agent': 'CareerOps/3.2'}) as client:
            r = await client.get(f'{API}/search_by_date', params={'tags': 'story,author_whoishiring', 'hitsPerPage': 10})
            r.raise_for_status()
            thread = next((h for h in r.json().get('hits', []) if (h.get('title') or '').lower().startswith('ask hn: who is hiring')), None)
            if not thread:
                raise RuntimeError('No current "Who is hiring?" thread found')
            story = int(thread['objectID'])
            out, page = [], 0
            while len(out) < self.max_posts:
                r = await client.get(f'{API}/search_by_date', params={'tags': f'comment,story_{story}', 'hitsPerPage': 1000, 'page': page})
                r.raise_for_status()
                data = r.json()
                for hit in data.get('hits', []):
                    if hit.get('parent_id') == story:       # top-level = one company's post
                        job = parse_post(hit)
                        if job:
                            out.append(job)
                page += 1
                if page >= data.get('nbPages', 0):
                    break
        return out[: self.max_posts]
