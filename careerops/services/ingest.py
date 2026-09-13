from __future__ import annotations
from datetime import datetime, timezone
import re
from sqlalchemy import select
from sqlalchemy.orm import Session
from careerops.db.models import JobPosting
from careerops.services.fingerprint import job_fingerprint
from careerops.agents.jd_analysis import analyze_job_text


def _norm(v: str | None) -> str:
    return re.sub(r'\s+',' ',(v or '').strip().lower())


def _source_priority(source: str | None) -> int:
    s=(source or '').lower()
    if s in {'company_career','greenhouse','lever','ashby','usajobs'}: return 5
    if s=='manual': return 4
    if s=='adzuna': return 3
    if 'alert' in s: return 2
    return 1


def _semantic_duplicate(db: Session, data: dict) -> JobPosting | None:
    company=_norm(data.get('company')); title=_norm(data.get('title')); location=_norm(data.get('location'))
    if not company or company in {'unknown','linkedin alert','indeed alert'} or not title:
        return None
    # Cross-source dedupe intentionally ignores provider IDs. Same company/title/location is treated as one opportunity.
    candidates=db.scalars(select(JobPosting).where(JobPosting.status=='open')).all()
    for row in candidates:
        if _norm(row.company)!=company or _norm(row.title)!=title: continue
        row_loc=_norm(row.location)
        if location and row_loc and location!=row_loc and not (location in row_loc or row_loc in location): continue
        return row
    return None


def _parse_dt(v):
    if not isinstance(v,str): return v
    raw=v.strip()
    try: return datetime.fromisoformat(raw.replace('Z','+00:00'))
    except ValueError:
        try: return datetime.fromisoformat(raw[:10]).replace(tzinfo=timezone.utc)
        except ValueError: return None


def upsert_job(db: Session, data: dict) -> tuple[JobPosting, bool]:
    fp = job_fingerprint(data.get('company',''), data.get('title',''), data.get('location'), data.get('source_job_id'), data.get('description',''))
    existing = db.scalar(select(JobPosting).where(JobPosting.fingerprint == fp))
    if not existing:
        existing=_semantic_duplicate(db,data)
    if existing:
        existing.last_seen_at = datetime.now(timezone.utc)
        existing.last_verified_at = datetime.now(timezone.utc)
        # Prefer the official/direct source when the same role is rediscovered through an aggregator or alert.
        if _source_priority(data.get('source')) > _source_priority(existing.source):
            for k in ['source','source_job_id','ats','canonical_url','application_url','description','raw_payload']:
                v=data.get(k)
                if v not in (None,'',{},[]): setattr(existing,k,v)
        else:
            if not existing.application_url and data.get('application_url'): existing.application_url=data['application_url']
            if not existing.canonical_url and data.get('canonical_url'): existing.canonical_url=data['canonical_url']
        db.commit(); db.refresh(existing)
        return existing, False
    filtered = {k:v for k,v in data.items() if k in {c.name for c in JobPosting.__table__.columns}}
    for dt_key in ('posted_at','deadline','last_verified_at'):
        filtered[dt_key]=_parse_dt(filtered.get(dt_key))
    filtered['fingerprint']=fp
    filtered.setdefault('raw_payload', data.get('raw_payload',{}))
    job=JobPosting(**filtered)
    db.add(job); db.flush()
    extracted=analyze_job_text(job)
    for key,val in extracted.items():
        if key=='detected_skills':
            if not job.required_skills: job.required_skills=val
        elif getattr(job,key,None) in (None, [], 'unknown') and val not in (None,[]):
            setattr(job,key,val)
    db.commit(); db.refresh(job)
    return job, True
