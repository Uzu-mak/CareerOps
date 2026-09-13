from __future__ import annotations
import httpx
from bs4 import BeautifulSoup
from careerops.sources.base import JobSource

class GenericPageSource(JobSource):
    def __init__(self, url: str): self.url=url
    async def fetch(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={'User-Agent':'CareerOps/1.0 personal job-search assistant'}) as client:
            r=await client.get(self.url); r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser')
        title=(soup.find('h1') or soup.find('title'))
        text=soup.get_text('\n', strip=True)
        return [{'source':'generic','source_job_id':self.url,'ats':'generic','canonical_url':str(r.url),'application_url':str(r.url),'company':(soup.find('meta',{'property':'og:site_name'}) or {}).get('content','Unknown'),'title':title.get_text(' ',strip=True) if title else 'Job Posting','location':None,'description':text[:50000],'raw_payload':{'url':str(r.url)}}]
