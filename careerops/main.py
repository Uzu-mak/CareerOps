from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from careerops.core.config import settings
from careerops.db.init import create_all, seed_demo_data
from careerops.db.session import get_db
from careerops.db.models import CandidateProfile, JobPosting, JobAnalysis, Application, AgentRun, GeneratedArtifact, SourceConfig, ProfileLink, CareerJournalEntry, ApplicationReviewAnswer, NotificationPreference, NotificationEvent, AlertInboxMessage, DiscoveryRun, PortalAccount
from careerops.agents.orchestrator import latest_analysis
from careerops.agents.reporting import dashboard_metrics, build_daily_report
from careerops.api.routes import router as api_router
from careerops.services.autopilot import get_runtime_settings
from careerops.services.application_tracking import submission_evidence_summary, verification_state
from careerops.agents.evidence import rank_evidence
from careerops.agents.account import account_plan
from careerops.services.notifications import get_notification_preferences
from careerops.services.imap_alerts import imap_configured
from careerops.services.job_search import job_facets, pending_analysis_count
from careerops.services.portal_sessions import session_for
from careerops.core.ui_options import apply_mode, as_template_globals, blocker_info, detect_skills, review_input, suggest_roles
from careerops.web.view_helpers import iso, money, salary_range, setup_checklist, short_dt

from careerops.core.auth import AuthConfig, AuthMiddleware

# Fail at startup, before anything is served, if a hosted instance has no login.
AUTH_CONFIG=AuthConfig.from_settings(settings)
AUTH_CONFIG.validate()

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all(); seed_demo_data()
    # Uvicorn logs the container bind address (0.0.0.0:8000), which a browser
    # cannot open. Print the address people should actually use.
    print(f'\n  CareerOps is ready: open {settings.base_url.rstrip("/")} in your browser\n'
          f'  (the "0.0.0.0:8000" line below is the address inside the container)\n', flush=True)
    yield

app=FastAPI(title='CareerOps',version='3.2.0',lifespan=lifespan)
app.add_middleware(AuthMiddleware, config=AUTH_CONFIG)
app.include_router(api_router)
app.mount('/static',StaticFiles(directory='careerops/static'),name='static')
templates=Jinja2Templates(directory='careerops/templates')
templates.env.globals['ui']=as_template_globals()
templates.env.globals['asset_version']=app.version
templates.env.filters.update(iso=iso, short_dt=short_dt, money=money)
templates.env.globals['salary_range']=salary_range


def _profile(db: Session):
    return db.scalar(select(CandidateProfile).limit(1))


def _shell(db: Session) -> dict:
    """Counts shown in the sidebar on every page."""
    return {
        'unread': db.scalar(select(func.count(NotificationEvent.id)).where(NotificationEvent.read == False)) or 0,  # noqa: E712
        'review': db.scalar(select(func.count(Application.id)).where(Application.requires_human_review == True, Application.status == 'review')) or 0,  # noqa: E712
    }


def _render(request: Request, db: Session, template: str, **context):
    return templates.TemplateResponse(request, template, {'shell': _shell(db), 'profile': context.pop('profile', None) or _profile(db), **context})


def _notifications_configured(pref) -> bool:
    return bool(pref and pref.enabled and ((pref.email_enabled and pref.email_to) or (pref.slack_enabled and pref.slack_webhook_url)
                or (pref.discord_enabled and pref.discord_webhook_url) or (pref.telegram_enabled and pref.telegram_bot_token)))


@app.get('/',response_class=HTMLResponse)
def dashboard(request:Request, db:Session=Depends(get_db)):
    profile=_profile(db)
    sources=db.scalars(select(SourceConfig).order_by(SourceConfig.id)).all()
    pipeline=dict(db.execute(select(Application.status, func.count(Application.id)).group_by(Application.status)).all())
    review_apps=db.execute(select(Application, JobPosting).join(JobPosting, JobPosting.id==Application.job_id)
                           .where(Application.requires_human_review==True, Application.status=='review')  # noqa: E712
                           .order_by(Application.updated_at.desc()).limit(5)).all()
    links=db.scalar(select(func.count(ProfileLink.id))) or 0
    pref=get_notification_preferences(db)
    last_scan=max((s.last_run_at for s in sources if s.last_run_at), default=None)
    return _render(request, db, 'dashboard.html', profile=profile, metrics=dashboard_metrics(db), report=build_daily_report(db),
                   sources=sources, runtime=get_runtime_settings(db), pending=pending_analysis_count(db), pipeline=pipeline,
                   review_apps=review_apps, last_scan=last_scan, decisions=job_facets(db)['decisions'],
                   source_errors=sum(1 for s in sources if s.enabled and (s.last_status or '').startswith('error')),
                   events=db.scalars(select(NotificationEvent).order_by(NotificationEvent.created_at.desc()).limit(6)).all(),
                   checklist=setup_checklist(profile, links, _notifications_configured(pref)))


@app.get('/jobs',response_class=HTMLResponse)
def jobs_page(request:Request, db:Session=Depends(get_db)):
    return _render(request, db, 'jobs.html', facets=job_facets(db))


@app.get('/jobs/{job_id}',response_class=HTMLResponse)
def job_page(job_id:int, request:Request, db:Session=Depends(get_db)):
    job=db.get(JobPosting,job_id)
    if not job: return RedirectResponse('/jobs')
    analysis=latest_analysis(db,job_id)
    app_row=db.scalar(select(Application).where(Application.job_id==job_id).order_by(Application.created_at.desc()).limit(1))
    artifacts=db.scalars(select(GeneratedArtifact).where(GeneratedArtifact.job_id==job_id).order_by(GeneratedArtifact.created_at.desc())).all()
    runs=db.scalars(select(AgentRun).where(AgentRun.job_id==job_id).order_by(AgentRun.created_at.desc()).limit(20)).all()
    profile=_profile(db)
    evidence=rank_evidence(db,profile,job,limit=6) if profile else []
    acct_plan=account_plan(db,profile,job) if profile else None
    review_items=[]
    if app_row:
        saved={r.question:r for r in db.scalars(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.application_id==app_row.id)).all()}
        for q in list(dict.fromkeys(app_row.human_review_reasons or [])):
            plan=(app_row.answers or {}).get(q,{})
            row=saved.get(q)
            review_items.append({'question':q,'mode':plan.get('mode','REVIEW'),'suggested_answer':plan.get('answer'),
                                 'reason':plan.get('reason','CareerOps needs your answer before it can continue.'),
                                 'answer':row.answer if row else None,'resolved':row.resolved if row else False,
                                 'notes':row.notes if row else None,'input':review_input(q, plan),'blocker':blocker_info(q),
                                 'field_type':plan.get('field_type')})
    blockers=[x for x in review_items if x['blocker']]
    review_items=[x for x in review_items if not x['blocker']]
    # Each "Prepare documents" makes a new set; show the newest of each type.
    latest={}
    for a in artifacts:
        latest.setdefault(a.artifact_type, a)
    older_artifacts=len(artifacts)-len(latest)
    artifacts=list(latest.values())
    target=job.application_url or job.canonical_url
    mode=apply_mode(target, job.ats)
    saved=session_for(db, target) if mode=='manual' else None
    if saved: mode='session'
    auto_answers=db.scalars(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.application_id==app_row.id, ApplicationReviewAnswer.category=='auto_draft')).all() if app_row else []
    return _render(request, db, 'job.html', profile=profile, job=job, llm_enabled=(settings.llm_provider or 'local').lower()!='local', apply_mode=mode,
                   session_site=saved.company if saved else None, auto_answers=auto_answers, analysis=analysis, application=app_row, artifacts=artifacts,
                   runs=runs, review_items=review_items, blockers=blockers, older_artifacts=older_artifacts, evidence=evidence, account_plan=acct_plan,
                   verification=submission_evidence_summary(app_row) if app_row else None)


@app.get('/applications',response_class=HTMLResponse)
def applications_page(request:Request, db:Session=Depends(get_db)):
    rows=[]
    for application, job in db.execute(select(Application, JobPosting).join(JobPosting, JobPosting.id==Application.job_id)
                                       .order_by(Application.updated_at.desc())).all():
        rows.append({'application':application,'job':job,'verification':submission_evidence_summary(application)})
    metrics={
        'total':len(rows),
        'confirmed':sum(1 for r in rows if r['verification']['state']=='CONFIRMED'),
        'review':sum(1 for r in rows if r['verification']['state']=='REVIEW'),
        'interviews':sum(1 for r in rows if r['application'].status in ('interview','offer')),
    }
    return _render(request, db, 'applications.html', rows=rows, metrics=metrics)


@app.get('/profile',response_class=HTMLResponse)
def profile_page(request:Request, db:Session=Depends(get_db)):
    profile=_profile(db)
    links=db.scalars(select(ProfileLink).where(ProfileLink.profile_id==profile.id).order_by(ProfileLink.id)).all() if profile else []
    pref=get_notification_preferences(db)
    have={x.lower() for x in (profile.skills or [])} if profile else set()
    suggested=[x for x in detect_skills(profile.baseline_resume_text or '') if x.lower() not in have] if profile else []
    roles_have={x.lower() for x in (profile.role_families or [])} if profile else set()
    suggested_roles=[x for x in suggest_roles(profile.baseline_resume_text or '') if x.lower() not in roles_have] if profile else []
    return _render(request, db, 'profile.html', profile=profile, links=links, suggested_skills=suggested, suggested_roles=suggested_roles,
                   checklist=setup_checklist(profile, len(links), _notifications_configured(pref)))


@app.get('/journal',response_class=HTMLResponse)
def journal_page(request:Request, db:Session=Depends(get_db)):
    profile=_profile(db)
    entries=db.scalars(select(CareerJournalEntry).where(CareerJournalEntry.profile_id==profile.id).order_by(CareerJournalEntry.entry_date.desc(),CareerJournalEntry.id.desc())).all() if profile else []
    projects=sorted({e.project for e in entries if e.project})
    return _render(request, db, 'journal.html', profile=profile, entries=entries, projects=projects,
                   total_hours=sum(e.time_spent_hours or 0 for e in entries))


@app.get('/sources',response_class=HTMLResponse)
def sources_page(request:Request, db:Session=Depends(get_db)):
    sources=db.scalars(select(SourceConfig).order_by(SourceConfig.source_type, SourceConfig.name)).all()
    runs=db.scalars(select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(8)).all()
    providers={'adzuna':bool(settings.adzuna_app_id and settings.adzuna_app_key),
               'usajobs':bool(settings.usajobs_api_key and settings.usajobs_user_agent),
               'imap':imap_configured(), 'llm':(settings.llm_provider or 'local').lower()!='local'}
    sessions=db.scalars(select(PortalAccount).where(PortalAccount.provider=='session').order_by(PortalAccount.company)).all()
    return _render(request, db, 'sources.html', sessions=sessions, sources=sources, runtime=get_runtime_settings(db), runs=runs, providers=providers,
                   llm_provider=(settings.llm_provider or 'local').lower(), pending=pending_analysis_count(db))


@app.get('/notifications',response_class=HTMLResponse)
def notifications_page(request:Request, db:Session=Depends(get_db)):
    pref=get_notification_preferences(db)
    events=db.scalars(select(NotificationEvent).order_by(NotificationEvent.created_at.desc()).limit(100)).all()
    alerts=db.scalars(select(AlertInboxMessage).order_by(AlertInboxMessage.received_at.desc()).limit(50)).all()
    return _render(request, db, 'notifications.html', pref=pref, events=events, alerts=alerts,
                   unread=sum(1 for x in events if not x.read), imap_configured=imap_configured())

@app.get('/mock-ats/apply/{job_id}',response_class=HTMLResponse)
def mock_apply(job_id:int, request:Request, db:Session=Depends(get_db)):
    job=db.get(JobPosting,job_id)
    return templates.TemplateResponse(request,'mock_ats.html',{'job':job})

@app.post('/mock-ats/submit/{job_id}',response_class=HTMLResponse)
def mock_submit(job_id:int, request:Request, first_name:str=Form(...), last_name:str=Form(...), email:str=Form(...), phone:str=Form(''), linkedin:str=Form(''), disability:str=Form('prefer_not'), db:Session=Depends(get_db)):
    return templates.TemplateResponse(request,'mock_success.html',{'job_id':job_id,'name':f'{first_name} {last_name}'})
