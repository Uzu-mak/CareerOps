"""The truth guard must keep blocked claims out of documents and out of unattended submissions."""
from types import SimpleNamespace

from careerops.agents import documents
from careerops.db.models import CandidateEvidence, CandidateProfile, JobAnalysis, JobPosting
from careerops.services import autopilot


class FakeDB:
    """Just enough of a SQLAlchemy session for document/autopilot code paths."""

    def __init__(self):
        self.added = []

    def scalars(self, *_args, **_kwargs):
        return SimpleNamespace(all=lambda: [])

    def scalar(self, *_args, **_kwargs):
        return None

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass

    def refresh(self, _obj):
        pass


def _profile():
    return CandidateProfile(
        full_name='Ada Lovelace', email='ada@example.com', skills=['Python'],
        role_families=['Applied AI Engineer'], baseline_resume_text=None,
    )


def _job():
    return JobPosting(company='Acme', title='AI Engineer', description='Python', required_skills=['Python'], preferred_skills=[])


def _analysis():
    return JobAnalysis(job_id=1, matched_skills=['Python'], partial_skills=[], gap_skills=[])


def test_blocked_claim_is_removed_from_resume(monkeypatch, tmp_path):
    good = 'Built a FastAPI service for lab workflows.'
    bad = 'Reduced latency by 90% for 1M users.'
    evidence = [CandidateEvidence(profile_id=1, category='project', title='Lab platform', summary='',
                                  bullets=[good, bad], skills=['Python'], verified_metrics={})]

    monkeypatch.setattr(documents, 'rank_evidence', lambda *a, **k: evidence)
    monkeypatch.setattr(documents, 'verify_generated_claims', lambda text, ev, base='': (False, [bad]))
    monkeypatch.setattr(documents, 'HTML', lambda string: SimpleNamespace(write_pdf=lambda path: None))
    monkeypatch.setattr(documents.settings, 'generated_dir', str(tmp_path))

    art = documents.build_resume(FakeDB(), _profile(), _job(), _analysis())

    assert good in art.content
    assert bad not in art.content
    assert art.truth_guard_passed is False
    assert art.blocked_claims == [bad]


def test_resume_headline_comes_from_profile_roles(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, 'rank_evidence', lambda *a, **k: [])
    monkeypatch.setattr(documents, 'HTML', lambda string: SimpleNamespace(write_pdf=lambda path: None))
    monkeypatch.setattr(documents.settings, 'generated_dir', str(tmp_path))

    profile = _profile()
    profile.role_families = ['Forward Deployed Engineer']
    art = documents.build_resume(FakeDB(), profile, _job(), _analysis())

    assert 'Forward Deployed Engineer targeting AI Engineer' in art.content


def test_autopilot_will_not_submit_when_claims_were_withheld(monkeypatch):
    app = SimpleNamespace(id=7, status='prepared', requires_human_review=False, human_review_reasons=[], answers={}, portal=None, mode=None)
    package = {
        'application': app,
        'resume': SimpleNamespace(truth_guard_passed=False, blocked_claims=['Reduced latency by 90%.'], file_path='r.pdf'),
        'cover_letter': SimpleNamespace(truth_guard_passed=True, blocked_claims=[], file_path='c.pdf'),
    }

    def must_not_run(*_a, **_k):
        raise AssertionError('browser must not run when the truth guard failed')

    monkeypatch.setattr(autopilot, 'eligible_for_autopilot', lambda *a: (True, 'eligible'))
    monkeypatch.setattr(autopilot, 'prepare_application', lambda db, job: package)
    monkeypatch.setattr(autopilot, 'run_generic_browser', must_not_run)

    result = autopilot.attempt_autopilot_application(FakeDB(), _profile(), SimpleNamespace(id=1, application_url='https://jobs.lever.co/acme/1', canonical_url=None), allow_enqueue=False)

    assert result['attempted'] is False
    assert app.requires_human_review is True
    assert any('truth guard' in reason for reason in app.human_review_reasons)
