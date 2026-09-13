from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.orm import Session
from careerops.db.models import CandidateProfile, JobPosting, PortalAccount
from careerops.agents.browser import detect_portal


def account_plan(db: Session, profile: CandidateProfile, job: JobPosting) -> dict:
    """Plan authentication without storing a password.

    CareerOps reuses authenticated browser/session state when available. Google/OAuth,
    MFA, email verification and account ownership confirmation remain human steps.
    """
    provider = job.ats or detect_portal(job.application_url or job.canonical_url)
    company_scope = job.company if provider == 'workday' else None
    acct = db.scalar(select(PortalAccount).where(PortalAccount.provider == provider, PortalAccount.company == company_scope).limit(1))
    if acct and acct.status == 'authenticated':
        return {'provider': provider, 'action':'REUSE_SESSION', 'account_id':acct.id, 'human_required':False, 'reason':'Authenticated session exists.'}
    if provider in {'greenhouse','lever','ashby','generic'}:
        return {'provider':provider,'action':'DIRECT_APPLICATION','account_id':acct.id if acct else None,'human_required':False,'reason':'Portal commonly supports direct application; verify page at runtime.'}
    if provider == 'google':
        return {'provider':provider,'action':'HUMAN_SIGN_IN_THEN_SAVE_SESSION','account_id':acct.id if acct else None,'human_required':True,'reason':'Use existing Google identity; CareerOps does not store the Google password or bypass MFA.'}
    if provider == 'workday':
        if not acct:
            acct=PortalAccount(provider='workday',company=job.company,login_email=profile.email,auth_strategy='company_scoped_account',status='account_needed',notes='Creation may require email verification. Password belongs in an external secret manager, not the database.')
            db.add(acct); db.commit(); db.refresh(acct)
        return {'provider':provider,'action':'CREATE_OR_SIGN_IN_COMPANY_ACCOUNT','account_id':acct.id,'human_required':True,'reason':'Workday tenants may require a company-scoped account and email verification.'}
    return {'provider':provider,'action':'INSPECT_PORTAL','account_id':acct.id if acct else None,'human_required':True,'reason':'Authentication behavior is unknown.'}
