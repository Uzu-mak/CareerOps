from __future__ import annotations
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from careerops.db.models import CandidateProfile, CandidateEvidence, CareerJournalEntry


def parse_metric_lines(text: str | None) -> dict:
    """Only store metrics the user explicitly typed. No inference."""
    out={}
    for raw in (text or '').splitlines():
        line=raw.strip()
        if not line:
            continue
        if ':' in line:
            key,value=line.split(':',1)
            out[key.strip()]=value.strip()
        else:
            out[f'metric_{len(out)+1}']=line
    return out


def evidence_from_journal(db: Session, profile: CandidateProfile, entry: CareerJournalEntry) -> CandidateEvidence:
    parts=[entry.what_built]
    if entry.problem_solved: parts.append(f"Problem: {entry.problem_solved}")
    if entry.architecture_decisions: parts.append(f"Architecture/decisions: {entry.architecture_decisions}")
    if entry.tradeoffs: parts.append(f"Tradeoffs: {entry.tradeoffs}")
    if entry.impact: parts.append(f"Impact: {entry.impact}")
    if entry.lessons: parts.append(f"Lessons: {entry.lessons}")
    if entry.time_spent_hours is not None: parts.append(f"Time spent: {entry.time_spent_hours:g} hours")
    if entry.links: parts.append('Links: ' + ', '.join(entry.links))

    bullets=[entry.what_built]
    for value in [entry.problem_solved, entry.architecture_decisions, entry.tradeoffs, entry.impact, entry.lessons]:
        if value:
            bullets.append(value)
    ev=db.get(CandidateEvidence, entry.evidence_id) if entry.evidence_id else None
    if ev is None:
        ev=CandidateEvidence(
            profile_id=profile.id,
            category='daily_build',
            title=entry.title,
            organization=entry.project or 'Independent build journal',
            date_range=entry.entry_date,
            summary=' '.join(parts),
            bullets=bullets,
            skills=entry.skills or [],
            verified_metrics=entry.metrics or {},
            source_note=f'career_journal:{entry.id}',
        )
        db.add(ev); db.flush(); entry.evidence_id=ev.id
    else:
        ev.title=entry.title
        ev.organization=entry.project or 'Independent build journal'
        ev.date_range=entry.entry_date
        ev.summary=' '.join(parts)
        ev.bullets=bullets
        ev.skills=entry.skills or []
        ev.verified_metrics=entry.metrics or {}
        ev.source_note=f'career_journal:{entry.id}'
        db.add(ev)
    db.add(entry); db.commit(); db.refresh(entry); db.refresh(ev)
    return ev
