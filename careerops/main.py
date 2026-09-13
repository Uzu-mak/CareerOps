from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from careerops.core.config import settings
from careerops.db.init import create_all, seed_demo_data
from careerops.db.session import get_db
from careerops.db.models import CandidateProfile, JobPosting, JobAnalysis, Application, AgentRun, GeneratedArtifact, SourceConfig, ProfileLink, CareerJournalEntry, ApplicationReviewAnswer, NotificationPreference, NotificationEvent, AlertInboxMessage
from careerops.agents.orchestrator import latest_analysis
from careerops.agents.reporting import dashboard_metrics, build_daily_report
from careerops.api.routes import router as api_router
from careerops.services.autopilot import get_runtime_settings
from careerops.services.application_tracking import submission_evidence_summary, verification_state
from careerops.agents.evidence import rank_evidence
from careerops.agents.account import account_plan
from careerops.services.notifications import get_notification_preferences
from careerops.services.imap_alerts import imap_configured

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all(); seed_demo_data(); yield

app=FastAPI(title='CareerOps',version='3.0.0',lifespan=lifespan)
app.include_router(api_router)
app.mount('/static',StaticFiles(directory='careerops/static'),name='static')
templates=Jinja2Templates(directory='careerops/templates')

@app.get('/',response_class=HTMLResponse)
def dashboard(request:Request, db:Session=Depends(get_db)):
    jobs=db.scalars(select(JobPosting).where(JobPosting.source != 'demo').order_by(JobPosting.first_seen_at.desc())).all()
    rows=[]
    for j in jobs:
        a=latest_analysis(db,j.id); rows.append({'job':j,'analysis':a})
    profile=db.scalar(select(CandidateProfile).limit(1)); metrics=dashboard_metrics(db); report=build_daily_report(db)
    sources=db.scalars(select(SourceConfig).order_by(SourceConfig.id)).all()
    runtime=get_runtime_settings(db)
    return templates.TemplateResponse(request,'dashboard.html',{'rows':rows,'profile':profile,'metrics':metrics,'report':report,'sources':sources,'runtime':runtime,'baseline_total':sum((profile.baseline_minutes or {}).values()) if profile else 90})

@app.get('/jobs/{job_id}',response_class=HTMLResponse)
def job_page(job_id:int, request:Request, db:Session=Depends(get_db)):
    job=db.get(JobPosting,job_id)
    if not job: return RedirectResponse('/')
    analysis=latest_analysis(db,job_id)
    app_row=db.scalar(select(Application).where(Application.job_id==job_id).order_by(Application.created_at.desc()).limit(1))
    artifacts=db.scalars(select(GeneratedArtifact).where(GeneratedArtifact.job_id==job_id).order_by(GeneratedArtifact.created_at.desc())).all()
    runs=db.scalars(select(AgentRun).where(AgentRun.job_id==job_id).order_by(AgentRun.created_at.desc()).limit(20)).all()
    profile=db.scalar(select(CandidateProfile).limit(1))
    evidence=rank_evidence(db,profile,job,limit=6) if profile else []
    acct_plan=account_plan(db,profile,job) if profile else None
    review_items=[]
    if app_row:
        saved={r.question:r for r in db.scalars(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.application_id==app_row.id)).all()}
        for q in list(dict.fromkeys(app_row.human_review_reasons or [])):
            plan=(app_row.answers or {}).get(q,{})
            row=saved.get(q)
            review_items.append({'question':q,'mode':plan.get('mode','REVIEW'),'suggested_answer':plan.get('answer'),'reason':plan.get('reason','Human review required.'),'answer':row.answer if row else None,'resolved':row.resolved if row else False,'notes':row.notes if row else None})
    return templates.TemplateResponse(request,'job.html',{'job':job,'analysis':analysis,'application':app_row,'artifacts':artifacts,'runs':runs,'review_items':review_items,'evidence':evidence,'account_plan':acct_plan})


@app.get('/applications',response_class=HTMLResponse)
def applications_page(request:Request, db:Session=Depends(get_db)):
    applications=db.scalars(select(Application).order_by(Application.created_at.desc())).all()
    rows=[]
    for application in applications:
        job=db.get(JobPosting,application.job_id)
        if not job:
            continue
        rows.append({'application':application,'job':job,'verification':submission_evidence_summary(application)})
    metrics={
        'total':len(rows),
        'confirmed':sum(1 for r in rows if r['verification']['state']=='CONFIRMED'),
        'review':sum(1 for r in rows if r['verification']['state']=='REVIEW'),
        'interviews':sum(1 for r in rows if r['application'].status=='interview'),
    }
    return templates.TemplateResponse(request,'applications.html',{'rows':rows,'metrics':metrics})

@app.get('/profile',response_class=HTMLResponse)
def profile_page(request:Request, db:Session=Depends(get_db)):
    profile=db.scalar(select(CandidateProfile).limit(1))
    links=db.scalars(select(ProfileLink).where(ProfileLink.profile_id==profile.id).order_by(ProfileLink.id)).all() if profile else []
    return templates.TemplateResponse(request,'profile.html',{'profile':profile,'links':links})

@app.get('/journal',response_class=HTMLResponse)
def journal_page(request:Request, db:Session=Depends(get_db)):
    profile=db.scalar(select(CandidateProfile).limit(1))
    entries=db.scalars(select(CareerJournalEntry).where(CareerJournalEntry.profile_id==profile.id).order_by(CareerJournalEntry.entry_date.desc(),CareerJournalEntry.id.desc())).all() if profile else []
    return templates.TemplateResponse(request,'journal.html',{'profile':profile,'entries':entries})


@app.get('/notifications',response_class=HTMLResponse)
def notifications_page(request:Request, db:Session=Depends(get_db)):
    pref=get_notification_preferences(db)
    events=db.scalars(select(NotificationEvent).order_by(NotificationEvent.created_at.desc()).limit(100)).all()
    alerts=db.scalars(select(AlertInboxMessage).order_by(AlertInboxMessage.received_at.desc()).limit(50)).all()
    unread=sum(1 for x in events if not x.read)
    return templates.TemplateResponse(request,'notifications.html',{'pref':pref,'events':events,'alerts':alerts,'unread':unread,'imap_configured':imap_configured()})

@app.get('/mock-ats/apply/{job_id}',response_class=HTMLResponse)
def mock_apply(job_id:int, request:Request, db:Session=Depends(get_db)):
    job=db.get(JobPosting,job_id)
    return templates.TemplateResponse(request,'mock_ats.html',{'job':job})

@app.post('/mock-ats/submit/{job_id}',response_class=HTMLResponse)
def mock_submit(job_id:int, request:Request, first_name:str=Form(...), last_name:str=Form(...), email:str=Form(...), phone:str=Form(''), linkedin:str=Form(''), disability:str=Form('prefer_not'), db:Session=Depends(get_db)):
    return templates.TemplateResponse(request,'mock_success.html',{'job_id':job_id,'name':f'{first_name} {last_name}'})
