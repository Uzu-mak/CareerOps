from __future__ import annotations
import httpx
from careerops.sources.base import JobSource

class AshbySource(JobSource):
    def __init__(self, board: str): self.board=board
    async def fetch(self) -> list[dict]:
        url=f'https://api.ashbyhq.com/posting-api/job-board/{self.board}?includeCompensation=true'
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r=await client.get(url); r.raise_for_status(); data=r.json()
        out=[]
        for j in data.get('jobs',[]):
            out.append({'source':'ashby','source_job_id':j.get('id') or j.get('jobUrl'),'ats':'ashby','canonical_url':j.get('jobUrl'),'application_url':j.get('applyUrl') or j.get('jobUrl'),'company':self.board,'title':j.get('title',''),'location':j.get('location'),'workplace_type':'remote' if j.get('isRemote') else None,'description':j.get('descriptionPlain') or j.get('descriptionHtml') or '','raw_payload':j})
        return out
