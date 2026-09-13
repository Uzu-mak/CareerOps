from datetime import datetime, timezone
from careerops.db.models import CandidateProfile, JobPosting
from careerops.agents.policy import evaluate_hard_constraints, classify_application_question


def profile(**kw):
    base=dict(full_name='Test',minimum_salary=90000,target_salary=120000,years_professional_software=2,years_hands_on_software=3,remote_allowed=True,hybrid_allowed=True,onsite_allowed=True)
    base.update(kw); return CandidateProfile(**base)

def job(**kw):
    base=dict(source='test',company='X',title='Engineer',description='Python',fingerprint='x',salary_min=100000,salary_max=130000,sponsorship_policy='unknown',clearance_required=False,required_years=2)
    base.update(kw); return JobPosting(**base)

def test_legal_unverified_routes_to_review():
    r=evaluate_hard_constraints(profile(),job(sponsorship_policy='unavailable'))
    assert r['items']['work_authorization']['status']=='REVIEW'
    assert r['items']['sponsorship']['status']=='REVIEW'

def test_verified_future_sponsorship_blocks_no_sponsor_role():
    p=profile(authorized_to_work_us=True,requires_future_sponsorship=True,legal_answers_verified_at=datetime.now(timezone.utc))
    r=evaluate_hard_constraints(p,job(sponsorship_policy='unavailable'))
    assert r['items']['sponsorship']['status']=='FAIL'
    assert r['overall']=='FAIL'

def test_sensitive_questions_manual():
    assert classify_application_question('Voluntary self-identification of disability')=='MANUAL'
    assert classify_application_question('Will you require future sponsorship?')=='VERIFIED_LEGAL'
