from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from careerops.db.base import Base
from careerops.db.models import CandidateProfile, CandidateEvidence, CareerJournalEntry, ProfileLink, Application, JobPosting, ApplicationReviewAnswer
from careerops.services.career_memory import parse_metric_lines, evidence_from_journal
from careerops.services.fingerprint import job_fingerprint


def test_journal_projects_to_candidate_evidence():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        p=CandidateProfile(full_name='Test User',skills=['Python'])
        db.add(p); db.flush()
        entry=CareerJournalEntry(profile_id=p.id,entry_date='2026-09-12',title='CareerOps memory',project='CareerOps',what_built='Built a living career journal.',tradeoffs='More structured input for better provenance.',time_spent_hours=2.5,impact='Recent work becomes retrievable evidence.',metrics=parse_metric_lines('tests_passed: 10'),skills=['FastAPI','PostgreSQL'],links=['https://example.com'])
        db.add(entry); db.flush()
        ev=evidence_from_journal(db,p,entry)
        assert ev.category=='daily_build'
        assert ev.verified_metrics['tests_passed']=='10'
        assert 'tradeoffs' in ev.summary.lower()
        assert entry.evidence_id==ev.id


def test_profile_link_persists():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        p=CandidateProfile(full_name='Test User');db.add(p);db.flush()
        db.add(ProfileLink(profile_id=p.id,label='Portfolio',url='https://example.com',link_type='portfolio'));db.commit()
        row=db.scalar(select(ProfileLink))
        assert row.url=='https://example.com'
        assert row.include_in_applications is True
