"""Remotive public remote-jobs API (no key).

Remotive asks API users to call at most about 4 times a day, link back to the
Remotive job page and name Remotive as the source, so this source defaults to
a 12-hour interval, keeps Remotive's URL as the job link and records the source.
"""
from __future__ import annotations

import html
import re

from careerops.sources.base import JobSource

API = 'https://remotive.com/api/remote-jobs'


def _text(fragment: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment or ''))).strip()


def map_job(row: dict) -> dict:
    links = re.findall(r'href="([^"]+)"', row.get('description') or '')
    return {
        'source': 'remotive', 'source_job_id': f'remotive:{row.get("id")}', 'ats': 'aggregator',
        'canonical_url': row.get('url'), 'application_url': row.get('url'),
        'company': row.get('company_name') or 'Unknown', 'title': row.get('title') or 'Job Posting',
        'location': row.get('candidate_required_location') or 'Remote', 'workplace_type': 'remote',
        'employment_type': (row.get('job_type') or '').replace('_', '-') or None,
        'description': _text(row.get('description'))[:20000] + (f"\n\nSalary: {row['salary']}" if row.get('salary') else ''),
        'posted_at': row.get('publication_date'),
        'raw_payload': {'remotive_id': row.get('id'), 'via': 'Remotive', 'links': [html.unescape(u) for u in links[:20]]},
    }


class RemotiveSource(JobSource):
    def __init__(self, categories: list[str] | None = None, limit: int = 150):
        self.categories = categories or ['software-dev', 'data']
        self.limit = max(10, min(500, limit))

    async def fetch(self) -> list[dict]:
        import httpx

        out, seen = [], set()
        async with httpx.AsyncClient(timeout=40, headers={'User-Agent': 'CareerOps/3.2'}) as client:
            for category in self.categories[:3]:
                r = await client.get(API, params={'category': category, 'limit': self.limit})
                r.raise_for_status()
                for row in r.json().get('jobs', []):
                    if row.get('id') not in seen:
                        seen.add(row.get('id'))
                        out.append(map_job(row))
        return out
