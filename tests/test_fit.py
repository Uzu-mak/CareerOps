from careerops.db.models import CandidateProfile, JobPosting
from careerops.agents.fit import skill_match

def test_skill_match_groups():
    assert skill_match(['PostgreSQL'],'SQL') in ('MATCH','PARTIAL')
    assert skill_match(['React'],'Next.js')=='PARTIAL'
    assert skill_match(['Python'],'Palantir Foundry')=='GAP'
