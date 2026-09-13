from __future__ import annotations
import httpx
from bs4 import BeautifulSoup
from careerops.sources.base import JobSource

class LeverSource(JobSource):
    def __init__(self, site: str): self.site=site
    async def fetch(self) -> list[dict]:
        url=f'https://api.lever.co/v0/postings/{self.site}?mode=json'
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r=await client.get(url); r.raise_for_status(); jobs=r.json()
        out=[]
        for j in jobs:
            parts=[j.get('descriptionPlain','')]
            for lst in j.get('lists',[]): parts.append(BeautifulSoup(lst.get('content',''),'html.parser').get_text('\n', strip=True))
            out.append({'source':'lever','source_job_id':j.get('id'),'ats':'lever','canonical_url':j.get('hostedUrl'),'application_url':j.get('applyUrl') or j.get('hostedUrl'),'company':self.site,'title':j.get('text',''),'location':j.get('categories',{}).get('location'),'workplace_type':j.get('workplaceType'),'employment_type':j.get('categories',{}).get('commitment'),'description':'\n'.join(parts),'raw_payload':j})
        return out
