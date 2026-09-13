from __future__ import annotations
import httpx
from careerops.sources.base import JobSource
from careerops.core.config import settings


class USAJobsSource(JobSource):
    """Official USAJOBS search API adapter."""
    def __init__(self, profile, results_per_query: int = 50):
        self.profile=profile; self.results_per_query=max(1,min(100,results_per_query))

    async def fetch(self) -> list[dict]:
        if not settings.usajobs_api_key or not settings.usajobs_user_agent:
            raise RuntimeError('USAJOBS credentials missing: set USAJOBS_API_KEY and USAJOBS_USER_AGENT')
        roles=list(dict.fromkeys((self.profile.role_families or [])[:6])) or ['Software Engineer']
        locations=list(dict.fromkeys((self.profile.preferred_locations or [])[:4])) or [self.profile.home_location or 'Seattle, WA']
        headers={'Host':'data.usajobs.gov','User-Agent':settings.usajobs_user_agent,'Authorization-Key':settings.usajobs_api_key}
        seen=set(); out=[]
        async with httpx.AsyncClient(timeout=35, follow_redirects=True, headers=headers) as client:
            for role in roles:
                for location in locations:
                    params={'Keyword':role,'LocationName':location,'Radius':self.profile.search_radius_miles or 50,'DatePosted':14,'ResultsPerPage':self.results_per_query,'WhoMayApply':'public'}
                    if self.profile.minimum_salary: params['RemunerationMinimumAmount']=self.profile.minimum_salary
                    r=await client.get('https://data.usajobs.gov/api/search',params=params); r.raise_for_status()
                    items=((r.json().get('SearchResult') or {}).get('SearchResultItems') or [])
                    for item in items:
                        mapped=self.map_result(item)
                        key=mapped.get('source_job_id') or mapped.get('canonical_url')
                        if key and key not in seen: seen.add(key); out.append(mapped)
        return out

    @staticmethod
    def map_result(item: dict) -> dict:
        d=item.get('MatchedObjectDescriptor') or {}
        locations=d.get('PositionLocation') or []
        if isinstance(locations,dict): locations=[locations]
        loc='; '.join([str(x.get('LocationName')) for x in locations if x.get('LocationName')]) or None
        rem=d.get('PositionRemuneration') or []
        first=rem[0] if rem else {}
        apply_uri=d.get('ApplyURI') or []
        if isinstance(apply_uri,list): apply_uri=apply_uri[0] if apply_uri else None
        summary=(d.get('UserArea') or {}).get('Details') or {}
        desc='\n'.join(str(summary.get(k) or '') for k in ['JobSummary','MajorDuties','Requirements','Evaluations'] if summary.get(k))
        return {
            'source':'usajobs','source_job_id':str(d.get('PositionID') or item.get('MatchedObjectId') or ''),'ats':'usajobs',
            'canonical_url':d.get('PositionURI'),'application_url':apply_uri or d.get('PositionURI'),
            'company':d.get('OrganizationName') or d.get('DepartmentName') or 'US Federal Government',
            'title':d.get('PositionTitle') or 'Federal Job','location':loc,'description':desc or d.get('QualificationSummary') or '',
            'salary_min':_money(first.get('MinimumRange')),'salary_max':_money(first.get('MaximumRange')),
            'posted_at':d.get('PublicationStartDate'),'deadline':d.get('ApplicationCloseDate'),
            'raw_payload':item,
        }

def _money(v):
    try: return int(float(v))
    except (TypeError,ValueError): return None
