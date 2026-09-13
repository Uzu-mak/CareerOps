from __future__ import annotations
import re
import httpx
from bs4 import BeautifulSoup
from careerops.sources.base import JobSource

class GreenhouseSource(JobSource):
    def __init__(self, board_token: str): self.board_token = board_token
    async def fetch(self) -> list[dict]:
        url = f'https://boards-api.greenhouse.io/v1/boards/{self.board_token}/jobs?content=true'
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url); r.raise_for_status(); data = r.json()
        out=[]
        for j in data.get('jobs',[]):
            text = BeautifulSoup(j.get('content',''), 'html.parser').get_text('\n', strip=True)
            locations = ', '.join(loc.get('name','') for loc in j.get('offices',[]) if loc.get('name')) or j.get('location',{}).get('name')
            out.append({'source':'greenhouse','source_job_id':str(j['id']),'ats':'greenhouse','canonical_url':j.get('absolute_url'),'application_url':j.get('absolute_url'),'company':self.board_token,'title':j.get('title',''),'location':locations,'description':text,'raw_payload':j})
        return out
