from __future__ import annotations
from urllib.parse import urlparse
import httpx
from careerops.sources.base import JobSource
from careerops.core.config import settings


class AdzunaSource(JobSource):
    """Broad-market job search driven by the candidate's configured role/location policy."""

    def __init__(self, profile, country: str = 'us', results_per_query: int = 20):
        self.profile = profile
        self.country = country or 'us'
        self.results_per_query = max(1, min(50, results_per_query))

    async def fetch(self) -> list[dict]:
        if not settings.adzuna_app_id or not settings.adzuna_app_key:
            raise RuntimeError('Adzuna credentials missing: set ADZUNA_APP_ID and ADZUNA_APP_KEY')
        roles = list(dict.fromkeys((self.profile.role_families or [])[:8])) or ['Software Engineer']
        locations = list(dict.fromkeys((self.profile.preferred_locations or [])[:5])) or [self.profile.home_location or 'Seattle, WA']
        seen: set[str] = set(); out: list[dict] = []
        async with httpx.AsyncClient(timeout=35, follow_redirects=True, headers={'User-Agent':'CareerOps/3.0'}) as client:
            for role in roles:
                for location in locations:
                    url=f'https://api.adzuna.com/v1/api/jobs/{self.country}/search/1'
                    params={
                        'app_id': settings.adzuna_app_id,
                        'app_key': settings.adzuna_app_key,
                        'results_per_page': self.results_per_query,
                        'what': role,
                        'where': location,
                        'content-type':'application/json',
                        'sort_by':'date',
                    }
                    if self.profile.minimum_salary:
                        params['salary_min']=self.profile.minimum_salary
                    r=await client.get(url,params=params); r.raise_for_status()
                    for row in r.json().get('results',[]):
                        mapped=self.map_result(row)
                        key=mapped.get('source_job_id') or mapped.get('canonical_url')
                        if key and key not in seen:
                            seen.add(key); out.append(mapped)
        return out

    @staticmethod
    def map_result(row: dict) -> dict:
        company=(row.get('company') or {}).get('display_name') or 'Unknown'
        location=(row.get('location') or {}).get('display_name')
        url=row.get('redirect_url') or row.get('url')
        rid=str(row.get('id') or url or '')
        return {
            'source':'adzuna','source_job_id':rid,'ats':'aggregator','canonical_url':url,'application_url':url,
            'company':company,'title':row.get('title') or 'Job Posting','location':location,
            'description':row.get('description') or '',
            'salary_min':int(row['salary_min']) if row.get('salary_min') is not None else None,
            'salary_max':int(row['salary_max']) if row.get('salary_max') is not None else None,
            'posted_at':row.get('created'),
            'raw_payload':row,
        }
