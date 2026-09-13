from __future__ import annotations
import re
from sqlalchemy.orm import Session
from sqlalchemy import select
from careerops.db.models import CandidateEvidence, CandidateProfile, JobPosting


def tokens(text: str) -> set[str]:
    stop = {'and','the','with','for','from','that','this','into','using','across','work','built','build','experience','systems'}
    return {x for x in re.findall(r'[a-z0-9+#.]{2,}', text.lower()) if x not in stop}


def rank_evidence(db: Session, profile: CandidateProfile, job: JobPosting, limit: int = 4):
    items = db.scalars(select(CandidateEvidence).where(CandidateEvidence.profile_id == profile.id)).all()
    job_tokens = tokens(' '.join([job.title, job.description, ' '.join(job.required_skills or []), ' '.join(job.preferred_skills or [])]))
    scored = []
    for e in items:
        e_tokens = tokens(e.title + ' ' + e.summary + ' ' + ' '.join(e.skills or []) + ' ' + ' '.join(e.bullets or []))
        overlap = len(job_tokens & e_tokens)
        skill_overlap = len({s.lower() for s in (e.skills or [])} & {s.lower() for s in (job.required_skills or []) + (job.preferred_skills or [])})
        scored.append((overlap + skill_overlap * 3, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for score, e in scored[:limit] if score > 0] or [e for _, e in scored[:limit]]
