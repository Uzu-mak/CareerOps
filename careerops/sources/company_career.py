from __future__ import annotations
import json
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from careerops.core.config import settings
from careerops.sources.base import JobSource

JOB_WORDS=('job','career','position','opening','opportunit','apply','role','vacanc')
KNOWN_ATS_HOST_FRAGMENTS=('greenhouse.io','lever.co','ashbyhq.com','myworkdayjobs.com','workdayjobs.com','smartrecruiters.com','icims.com')

class CompanyCareerSource(JobSource):
    """Conservative public-career-page crawler with a rendered-page fallback.

    It never logs in, defeats CAPTCHAs, or bypasses anti-bot controls. The fast path
    uses normal HTTP and schema.org JobPosting JSON-LD. If a public careers page is
    JavaScript-rendered, it may render that public page with Chromium and inspect a
    bounded number of visible job-looking links. Known public ATS hosts are allowed
    as detail-link destinations.
    """
    def __init__(self, company: str, url: str, max_detail_pages: int = 35):
        self.company=company; self.url=url; self.max_detail_pages=max(1,min(60,max_detail_pages))

    async def fetch(self) -> list[dict]:
        headers={'User-Agent':'CareerOps/3.0 personal job-search monitor (+public career pages only)'}
        async with httpx.AsyncClient(timeout=30,follow_redirects=True,headers=headers) as client:
            r=await client.get(self.url); r.raise_for_status()
            base_url=str(r.url); html=r.text
            items=self.extract_jobpostings(html,base_url,self.company)
            if items: return _dedupe(items)

            links=self._extract_links(html,base_url)
            # Many modern company career sites return a nearly empty app shell to HTTP
            # clients. Render the public page as a browser would, but never log in or
            # try to evade access controls.
            if not links:
                rendered=await self._render_public_page(base_url)
                if rendered:
                    rendered_html, rendered_url=rendered
                    items=self.extract_jobpostings(rendered_html,rendered_url,self.company)
                    if items: return _dedupe(items)
                    links=self._extract_links(rendered_html,rendered_url)
                    base_url=rendered_url

            out=[]
            for href in links[:self.max_detail_pages]:
                try:
                    d=await client.get(href); d.raise_for_status()
                    found=self.extract_jobpostings(d.text,str(d.url),self.company)
                    if found: out.extend(found)
                    else:
                        generic=self.extract_generic_detail(d.text,str(d.url),self.company)
                        if generic: out.append(generic)
                except Exception:
                    # If the detail page is also a JS shell, use one browser render.
                    try:
                        rendered=await self._render_public_page(href)
                        if not rendered: continue
                        rh,ru=rendered
                        found=self.extract_jobpostings(rh,ru,self.company)
                        if found: out.extend(found)
                        else:
                            generic=self.extract_generic_detail(rh,ru,self.company)
                            if generic: out.append(generic)
                    except Exception:
                        continue
            return _dedupe(out)

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        soup=BeautifulSoup(html,'html.parser'); base_host=urlparse(base_url).netloc.lower(); links=[]
        for a in soup.find_all('a',href=True):
            text=a.get_text(' ',strip=True); href=urljoin(base_url,a['href']); u=urlparse(href)
            if u.scheme not in {'http','https'}: continue
            if not _allowed_detail_host(base_host,u.netloc.lower()): continue
            hay=f'{text} {u.path} {u.query}'.lower()
            if any(w in hay for w in JOB_WORDS) and href not in links: links.append(href)
            if len(links)>=self.max_detail_pages: break
        return links

    async def _render_public_page(self, url: str) -> tuple[str,str] | None:
        try:
            async with async_playwright() as p:
                browser=await p.chromium.launch(headless=True,executable_path=settings.chromium_executable,args=['--no-sandbox','--disable-dev-shm-usage'])
                page=await browser.new_page(user_agent='CareerOps/3.0 personal job-search monitor')
                await page.goto(url,wait_until='domcontentloaded',timeout=45000)
                await page.wait_for_timeout(1200)
                html=await page.content(); final=page.url
                await browser.close()
                return html,final
        except Exception:
            return None

    @staticmethod
    def extract_jobpostings(html: str, url: str, company: str) -> list[dict]:
        soup=BeautifulSoup(html,'html.parser'); out=[]
        for script in soup.find_all('script',attrs={'type':'application/ld+json'}):
            try: payload=json.loads(script.string or script.get_text() or '{}')
            except Exception: continue
            candidates=payload if isinstance(payload,list) else [payload]
            expanded=[]
            for obj in candidates:
                if isinstance(obj,dict) and isinstance(obj.get('@graph'),list): expanded.extend(obj['@graph'])
                else: expanded.append(obj)
            for obj in expanded:
                if not isinstance(obj,dict) or obj.get('@type')!='JobPosting': continue
                loc=_job_location(obj.get('jobLocation'))
                org=obj.get('hiringOrganization') or {}
                salary=obj.get('baseSalary') or {}; value=salary.get('value') or {}
                identifier=obj.get('identifier')
                ident_val=identifier.get('value') if isinstance(identifier,dict) else identifier
                out.append({
                    'source':'company_career','source_job_id':str(ident_val or obj.get('url') or url),
                    'ats':'company_career','canonical_url':obj.get('url') or url,'application_url':obj.get('url') or url,
                    'company':org.get('name') or company,'title':obj.get('title') or 'Job Posting','location':loc,
                    'description':BeautifulSoup(obj.get('description') or '','html.parser').get_text('\n',strip=True),
                    'employment_type':_employment(obj.get('employmentType')),
                    'salary_min':_num(value.get('minValue')),'salary_max':_num(value.get('maxValue')),
                    'posted_at':obj.get('datePosted'),'deadline':obj.get('validThrough'),'raw_payload':obj,
                })
        return out

    @staticmethod
    def extract_generic_detail(html: str, url: str, company: str) -> dict | None:
        soup=BeautifulSoup(html,'html.parser')
        h1=soup.find('h1'); title=h1.get_text(' ',strip=True) if h1 else ''
        text=soup.get_text('\n',strip=True)
        low=f'{title} {url}'.lower()
        if not title or not any(x in low for x in ['engineer','developer','scientist','analyst','manager','architect','specialist','intern','job','career','program manager','data']):
            return None
        return {'source':'company_career','source_job_id':url,'ats':'company_career','canonical_url':url,'application_url':url,'company':company,'title':title,'location':None,'description':text[:50000],'raw_payload':{'url':url}}

def _allowed_detail_host(base_host: str, host: str) -> bool:
    return host==base_host or any(fragment in host for fragment in KNOWN_ATS_HOST_FRAGMENTS)

def _employment(v):
    if isinstance(v,list): return ', '.join(map(str,v))
    return str(v) if v else None

def _num(v):
    try: return int(float(v))
    except (TypeError,ValueError): return None

def _job_location(v):
    if not v: return None
    rows=v if isinstance(v,list) else [v]; parts=[]
    for row in rows:
        if not isinstance(row,dict): continue
        addr=row.get('address') or {}
        s=', '.join([str(addr.get(k)) for k in ['addressLocality','addressRegion','addressCountry'] if addr.get(k)])
        if s: parts.append(s)
    return '; '.join(parts) or None

def _dedupe(rows):
    out=[]; seen=set()
    for r in rows:
        key=r.get('source_job_id') or r.get('canonical_url')
        if key and key in seen: continue
        if key: seen.add(key)
        out.append(r)
    return out
