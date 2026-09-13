from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from careerops.db.base import Base
from careerops.db.models import CandidateProfile, JobPosting, PortalAccount
from careerops.agents.account import account_plan


def test_workday_account_plan_creates_company_scoped_account_without_password():
    engine=create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine)
    with Session(engine) as db:
        p=CandidateProfile(full_name='Test User',email='test@example.com')
        j=JobPosting(source='test',source_job_id='1',ats='workday',company='Example Co',title='Software Engineer',description='x',fingerprint='fp',application_url='https://example.wd5.myworkdayjobs.com/en-US/job/1')
        db.add_all([p,j]);db.commit();db.refresh(j)
        plan=account_plan(db,p,j)
        assert plan['action']=='CREATE_OR_SIGN_IN_COMPANY_ACCOUNT'
        acct=db.scalar(select(PortalAccount))
        assert acct.company=='Example Co'
        assert acct.login_email=='test@example.com'
        assert 'password' in (acct.notes or '').lower()
