from careerops.db.models import CandidateEvidence
from careerops.agents.truth_guard import verify_generated_claims

def test_blocks_unverified_numeric_impact():
    e=CandidateEvidence(profile_id=1,category='project',title='P',summary='Built system',bullets=['Built API'],skills=[],verified_metrics={})
    ok,blocked=verify_generated_claims('Reduced latency by 60%.',[e])
    assert not ok and blocked

def test_allows_verified_numeric_impact():
    e=CandidateEvidence(profile_id=1,category='project',title='P',summary='Built system',bullets=['Reduced latency by 60%.'],skills=[],verified_metrics={'latency_reduction':'60%'})
    ok,blocked=verify_generated_claims('Reduced latency by 60%.',[e])
    assert ok and not blocked
