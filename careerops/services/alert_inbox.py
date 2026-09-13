from __future__ import annotations
import re
from datetime import datetime, timezone
from email import policy
from email.parser import Parser
from urllib.parse import urlparse
from sqlalchemy import select
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup
from careerops.db.models import AlertInboxMessage, CandidateProfile
from careerops.sources.generic import GenericPageSource
from careerops.services.ingest import upsert_job
from careerops.services.search_policy import should_keep_discovered_job
from careerops.agents.orchestrator import analyze_job
from careerops.services.notifications import notify_job_match

URL_RE=re.compile(r'https?://[^\s<>"\']+')


def infer_provider(sender: str|None, subject: str|None, body: str='') -> str:
    hay=' '.join([sender or '',subject or '',body[:500]]).lower()
    if 'linkedin' in hay: return 'linkedin'
    if 'indeed' in hay: return 'indeed'
    return 'unknown'


def extract_alert_urls(text: str, html: str|None=None) -> list[str]:
    urls=[]
    if html:
        soup=BeautifulSoup(html,'html.parser')
        for a in soup.find_all('a',href=True):
            href=a['href'].strip()
            if href.startswith('http') and _likely_job_url(href,a.get_text(' ',strip=True)) and href not in urls: urls.append(href)
    for u in URL_RE.findall(text or ''):
        u=u.rstrip(').,;')
        if _likely_job_url(u,'') and u not in urls: urls.append(u)
    return urls[:80]


def extract_alert_candidates(text: str, html: str|None=None) -> list[dict]:
    candidates=[]; seen=set()
    if html:
        soup=BeautifulSoup(html,'html.parser')
        for a in soup.find_all('a',href=True):
            href=a['href'].strip(); label=a.get_text(' ',strip=True)
            if href.startswith('http') and _likely_job_url(href,label) and href not in seen:
                seen.add(href); candidates.append({'url':href,'title':label[:320] or 'Job from alert'})
    for url in extract_alert_urls(text,html):
        if url not in seen:
            seen.add(url); candidates.append({'url':url,'title':'Job from alert'})
    return candidates[:80]


def parse_rfc822(raw_email: str) -> dict:
    msg=Parser(policy=policy.default).parsestr(raw_email)
    text_parts=[]; html_parts=[]
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition()=='attachment': continue
            ctype=part.get_content_type()
            try: content=part.get_content()
            except Exception: continue
            if ctype=='text/plain': text_parts.append(str(content))
            elif ctype=='text/html': html_parts.append(str(content))
    else:
        content=str(msg.get_content())
        (html_parts if msg.get_content_type()=='text/html' else text_parts).append(content)
    text='\n'.join(text_parts); html='\n'.join(html_parts) or None
    return {'sender':str(msg.get('From') or ''),'subject':str(msg.get('Subject') or ''),'message_id':str(msg.get('Message-ID') or '') or None,'text':text,'html':html}


def store_alert_email(db: Session, *, raw_email: str|None=None, provider: str|None=None, sender: str|None=None,
                      subject: str|None=None, text: str|None=None, html: str|None=None) -> AlertInboxMessage:
    if raw_email:
        p=parse_rfc822(raw_email); sender=p['sender']; subject=p['subject']; text=p['text']; html=p['html']; mid=p['message_id']
    else: mid=None
    provider=provider or infer_provider(sender,subject,text or '')
    urls=extract_alert_urls(text or '',html)
    if mid:
        existing=db.scalar(select(AlertInboxMessage).where(AlertInboxMessage.message_id==mid))
        if existing: return existing
    row=AlertInboxMessage(provider=provider,sender=sender,subject=subject,message_id=mid,raw_text=text or '',raw_html=html,discovered_urls=urls)
    db.add(row); db.commit(); db.refresh(row); return row


async def process_pending_alerts(db: Session, profile: CandidateProfile|None) -> dict:
    rows=db.scalars(select(AlertInboxMessage).where(AlertInboxMessage.processed==False).order_by(AlertInboxMessage.received_at)).all()  # noqa: E712
    totals={'messages':0,'urls':0,'created':0,'filtered':0,'analyzed':0,'errors':[]}
    for row in rows:
        totals['messages']+=1
        try:
            candidates=extract_alert_candidates(row.raw_text,row.raw_html)
            for candidate in candidates:
                url=candidate['url']; totals['urls']+=1
                try:
                    items=[]
                    # LinkedIn/Indeed alert ingestion intentionally avoids authenticated scraping.
                    # The alert itself is authoritative for discovery; the employer/aggregator URL is retained for opening/applying.
                    if row.provider in {'linkedin','indeed'}:
                        title=candidate.get('title') or 'Job from alert'
                        items=[{'source':f'{row.provider}_alert','source_job_id':url,'ats':row.provider,'canonical_url':url,'application_url':url,
                            'company':f'{row.provider.title()} Alert','title':title,'location':None,'description':(row.raw_text or BeautifulSoup(row.raw_html or '','html.parser').get_text('\n',strip=True))[:50000],
                            'raw_payload':{'alert_message_id':row.id,'subject':row.subject,'url':url}}]
                    else:
                        items=await GenericPageSource(url).fetch()
                    for item in items:
                        item['source']=f'{row.provider}_alert'
                        if profile and not should_keep_discovered_job(profile,item): totals['filtered']+=1; continue
                        job,created=upsert_job(db,item); totals['created']+=int(created)
                        if created and profile:
                            analysis=analyze_job(db,job); totals['analyzed']+=1; notify_job_match(db,job,analysis)
                except Exception as exc:
                    totals['errors'].append({'url':url,'error':str(exc)})
            row.processed=True; row.jobs_created=totals['created']; row.processed_at=datetime.now(timezone.utc); db.add(row); db.commit()
        except Exception as exc:
            row.processing_error=str(exc); db.add(row); db.commit(); totals['errors'].append({'message_id':row.id,'error':str(exc)})
    return totals


def _likely_job_url(url: str, text: str) -> bool:
    host=urlparse(url).netloc.lower(); hay=f'{url} {text}'.lower()
    if any(x in host for x in ['linkedin.com','indeed.com']): return any(x in hay for x in ['/jobs/','viewjob','jk=','currentjobid','job'])
    return any(x in hay for x in ['job','career','position','opening','apply'])
