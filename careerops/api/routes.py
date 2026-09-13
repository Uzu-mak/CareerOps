from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Form, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from careerops.db.session import get_db
from careerops.db.models import CandidateProfile, JobPosting, JobAnalysis, Application, GeneratedArtifact, AgentRun, SourceConfig, RuntimeSettings, ProfileLink, CareerJournalEntry, ApplicationReviewAnswer, NotificationPreference, NotificationEvent, AlertInboxMessage
from careerops.api.schemas import ProfileUpdate, ManualJobIn
from careerops.services.ingest import upsert_job
from careerops.agents.orchestrator import analyze_job, prepare_application, latest_analysis
from careerops.agents.reporting import build_daily_report, dashboard_metrics
from careerops.agents.qa import answer_question
from careerops.sources.greenhouse import GreenhouseSource
from careerops.sources.lever import LeverSource
from careerops.sources.ashby import AshbySource
from careerops.sources.generic import GenericPageSource
from careerops.agents.browser import run_generic_browser, run_mock_browser, detect_portal
from careerops.services.audit import agent_run
from careerops.agents.account import account_plan
from careerops.workers.discovery import scan_enabled_sources
from careerops.services.aws import send_email
from careerops.core.config import settings
from careerops.services.resume_baseline import save_baseline_resume
from careerops.services.autopilot import get_runtime_settings
from careerops.services.application_tracking import record_browser_result, submission_evidence_summary, get_submission_evidence, verification_state
from careerops.services.career_memory import parse_metric_lines, evidence_from_journal
from careerops.services.notifications import get_notification_preferences, emit_notification, notify_application_event
from careerops.services.alert_inbox import store_alert_email, process_pending_alerts
from careerops.services.imap_alerts import poll_imap_alerts, imap_configured

router=APIRouter(prefix='/api')

@router.get('/health')
def health(db:Session=Depends(get_db)):
    return {'status':'ok','app':'CareerOps','environment':settings.environment,'llm_provider':settings.llm_provider,'metrics':dashboard_metrics(db)}

@router.get('/profile')
def get_profile(db:Session=Depends(get_db)):
    p=db.scalar(select(CandidateProfile).limit(1))
    if not p: raise HTTPException(404,'Profile not configured')
    return {c.name:getattr(p,c.name) for c in CandidateProfile.__table__.columns}

@router.put('/profile')
def update_profile(payload:ProfileUpdate, db:Session=Depends(get_db)):
    p=db.scalar(select(CandidateProfile).limit(1))
    if not p: p=CandidateProfile(full_name=payload.full_name); db.add(p)
    data=payload.model_dump()
    legal_keys={'authorized_to_work_us','requires_current_sponsorship','requires_future_sponsorship','work_authorization_type','work_authorization_expiration'}
    legal_touched=any(data.get(k) is not None for k in legal_keys)
    for k,v in data.items(): setattr(p,k,v)
    if legal_touched: p.legal_answers_verified_at=datetime.now(timezone.utc)
    db.commit(); db.refresh(p)
    return {'ok':True,'legal_verified':p.legal_answers_verified_at is not None}

@router.post('/profile/resume')
async def upload_baseline_resume(resume:UploadFile=File(...), db:Session=Depends(get_db)):
    p=db.scalar(select(CandidateProfile).limit(1))
    if not p: raise HTTPException(404,'Profile not configured')
    try:
        result=await save_baseline_resume(db,p,resume)
    except ValueError as e:
        raise HTTPException(400,str(e))
    return {'ok':True,**result}

@router.get('/profile/resume/download')
def download_baseline_resume(db:Session=Depends(get_db)):
    p=db.scalar(select(CandidateProfile).limit(1))
    if not p or not p.baseline_resume_path or not Path(p.baseline_resume_path).exists():
        raise HTTPException(404,'Master resume not uploaded')
    return FileResponse(p.baseline_resume_path,filename=p.baseline_resume_filename or Path(p.baseline_resume_path).name)


@router.get('/jobs')
def jobs(db:Session=Depends(get_db)):
    out=[]
    for j in db.scalars(select(JobPosting).order_by(JobPosting.first_seen_at.desc())).all():
        a=latest_analysis(db,j.id)
        out.append({'id':j.id,'company':j.company,'title':j.title,'location':j.location,'salary_min':j.salary_min,'salary_max':j.salary_max,'source':j.source,'ats':j.ats,'status':j.status,
                    'fit_score':a.fit_score if a else None,'priority':a.priority if a else None,'action':a.recommended_action if a else None,'hard_filter':a.hard_filter_status if a else None})
    return out

@router.get('/jobs/{job_id}')
def job_detail(job_id:int, db:Session=Depends(get_db)):
    j=db.get(JobPosting,job_id)
    if not j: raise HTTPException(404,'Job not found')
    a=latest_analysis(db,j.id)
    apps=db.scalars(select(Application).where(Application.job_id==j.id).order_by(Application.created_at.desc())).all()
    arts=db.scalars(select(GeneratedArtifact).where(GeneratedArtifact.job_id==j.id).order_by(GeneratedArtifact.created_at.desc())).all()
    return {'job':{c.name:getattr(j,c.name) for c in JobPosting.__table__.columns},'analysis':({c.name:getattr(a,c.name) for c in JobAnalysis.__table__.columns} if a else None),'applications':[{'id':x.id,'status':x.status,'requires_human_review':x.requires_human_review,'human_review_reasons':x.human_review_reasons} for x in apps],'artifacts':[{'id':x.id,'type':x.artifact_type,'title':x.title,'downloadable':bool(x.file_path),'truth_guard_passed':x.truth_guard_passed} for x in arts]}

@router.post('/jobs/manual')
def manual(payload:ManualJobIn, db:Session=Depends(get_db)):
    data=payload.model_dump(); data.update(source='manual',source_job_id=None,ats='generic',raw_payload={})
    j,created=upsert_job(db,data)
    return {'job_id':j.id,'created':created}

@router.post('/jobs/{job_id}/analyze')
def analyze(job_id:int, db:Session=Depends(get_db)):
    j=db.get(JobPosting,job_id)
    if not j: raise HTTPException(404,'Job not found')
    a=analyze_job(db,j)
    return {'analysis_id':a.id,'fit_score':a.fit_score,'priority':a.priority,'action':a.recommended_action,'hard_filter':a.hard_filter_status,'hard_constraints':a.hard_constraints,'matched_skills':a.matched_skills,'partial_skills':a.partial_skills,'gap_skills':a.gap_skills,'explanation':a.explanation}

@router.post('/jobs/{job_id}/prepare')
def prepare(job_id:int, db:Session=Depends(get_db)):
    j=db.get(JobPosting,job_id)
    if not j: raise HTTPException(404,'Job not found')
    p=prepare_application(db,j)
    return {'application_id':p['application'].id,'resume_artifact_id':p['resume'].id,'cover_letter_artifact_id':p['cover_letter'].id,'outreach_artifact_id':p['outreach'].id,'review_reasons':p['application'].human_review_reasons}

@router.post('/jobs/{job_id}/questions')
def question(job_id:int, question:str=Form(...), db:Session=Depends(get_db)):
    j=db.get(JobPosting,job_id); p=db.scalar(select(CandidateProfile).limit(1))
    if not j or not p: raise HTTPException(404,'Missing job/profile')
    return answer_question(p,j,question)

@router.get('/artifacts/{artifact_id}/download')
def artifact_download(artifact_id:int, db:Session=Depends(get_db)):
    art=db.get(GeneratedArtifact,artifact_id)
    if not art or not art.file_path: raise HTTPException(404,'File not found')
    return FileResponse(art.file_path,filename=Path(art.file_path).name,media_type='application/pdf')

@router.get('/artifacts/{artifact_id}')
def artifact(artifact_id:int, db:Session=Depends(get_db)):
    art=db.get(GeneratedArtifact,artifact_id)
    if not art: raise HTTPException(404,'Artifact not found')
    return {'id':art.id,'type':art.artifact_type,'title':art.title,'content':art.content,'truth_guard_passed':art.truth_guard_passed,'blocked_claims':art.blocked_claims}

async def _discover(source, db):
    fetched=await source.fetch(); created=0; ids=[]
    for data in fetched:
        j,is_new=upsert_job(db,data); created+=int(is_new); ids.append(j.id)
    return {'fetched':len(fetched),'created':created,'job_ids':ids}

@router.post('/discover/greenhouse')
async def discover_greenhouse(board_token:str=Query(...), db:Session=Depends(get_db)): return await _discover(GreenhouseSource(board_token),db)
@router.post('/discover/lever')
async def discover_lever(site:str=Query(...), db:Session=Depends(get_db)): return await _discover(LeverSource(site),db)
@router.post('/discover/ashby')
async def discover_ashby(board:str=Query(...), db:Session=Depends(get_db)): return await _discover(AshbySource(board),db)
@router.post('/discover/url')
async def discover_url(url:str=Query(...), db:Session=Depends(get_db)): return await _discover(GenericPageSource(url),db)

@router.post('/jobs/{job_id}/apply-live')
def apply_live(job_id:int, submit:bool=Query(True), db:Session=Depends(get_db)):
    j=db.get(JobPosting,job_id); p=db.scalar(select(CandidateProfile).limit(1))
    if not j or not p: raise HTTPException(404,'Missing job/profile')
    if not p.baseline_resume_path:
        raise HTTPException(409,'Upload your master resume on the Profile page before applying.')
    target=j.application_url or j.canonical_url
    if not target:
        raise HTTPException(409,'This job does not have an application URL.')
    package=prepare_application(db,j)
    analysis=package['analysis']; app=package['application']
    if analysis.hard_filter_status=='FAIL':
        raise HTTPException(409,'CareerOps blocked application because a hard eligibility/location/policy constraint failed.')
    app.portal=detect_portal(target); app.mode='AUTO' if submit else 'PREPARE'; db.add(app); db.commit(); db.refresh(app)
    with agent_run(db,'LiveBrowserApplicationAgent',job_id=job_id,application_id=app.id,input_summary=f'{app.portal} browser fill + tailored resume upload') as run:
        extra_links=[{'label':x.label,'url':x.url,'link_type':x.link_type,'include_in_applications':x.include_in_applications} for x in db.scalars(select(ProfileLink).where(ProfileLink.profile_id==p.id)).all()]
        approved_review_answers={}
        for q,plan in (app.answers or {}).items():
            if not isinstance(plan,dict): continue
            answer=plan.get('user_answer') or plan.get('answer')
            if answer is not None and (plan.get('user_resolved') or plan.get('mode') in {'AUTO_PROFILE','AUTO_RULE','AUTO_VERIFIED','USER_VERIFIED'}):
                approved_review_answers[q]=str(answer)
        for x in db.scalars(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.application_id==app.id,ApplicationReviewAnswer.resolved==True)).all():
            if x.answer: approved_review_answers[x.question]=x.answer
        result=run_generic_browser(p,j,app,target,resume_path=package['resume'].file_path,cover_letter_path=package['cover_letter'].file_path,submit=submit,extra_links=extra_links,approved_review_answers=approved_review_answers)
        run.output_summary=f"{len(result.filled_fields)} fields; {len(result.uploaded_files)} files; {result.status}"
    record_browser_result(db, app, result)
    if result.submitted:
        notify_application_event(db,'submitted',app,j,result.message)
    elif result.manual_fields:
        notify_application_event(db,'human_review',app,j,result.message)
    return {'application_id':app.id,'verification':submission_evidence_summary(app),**result.__dict__}


@router.post('/jobs/{job_id}/simulate-apply')
def simulate_apply(job_id:int, db:Session=Depends(get_db)):
    j=db.get(JobPosting,job_id); p=db.scalar(select(CandidateProfile).limit(1))
    if not j or not p: raise HTTPException(404,'Missing job/profile')
    app=db.scalar(select(Application).where(Application.job_id==job_id).order_by(Application.created_at.desc()).limit(1)) or Application(job_id=job_id,status='prepared',portal='mock')
    if app.id is None: db.add(app); db.commit(); db.refresh(app)
    target=f'{settings.base_url}/mock-ats/apply/{job_id}'
    with agent_run(db,'BrowserApplicationAgent',job_id=job_id,application_id=app.id,input_summary='Playwright fill against local mock ATS') as run:
        result=run_mock_browser(p,j,app); run.output_summary=f'{len(result.filled_fields)} fields filled; {len(result.manual_fields)} manual'
    app.status='review'; app.requires_human_review=True; app.human_review_reasons=sorted(set(app.human_review_reasons + result.manual_fields + ['final submission approval']))
    db.add(app); db.commit()
    return result.__dict__

@router.get('/reports/daily')
def daily(db:Session=Depends(get_db)): return build_daily_report(db)

@router.get('/agent-runs')
def runs(db:Session=Depends(get_db)):
    rows=db.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(100)).all()
    return [{'id':r.id,'agent':r.agent_name,'status':r.status,'job_id':r.job_id,'latency_ms':r.latency_ms,'provider':r.model_provider,'output':r.output_summary,'created_at':r.created_at} for r in rows]


@router.post('/discover/run-configured')
async def discover_configured():
    return await scan_enabled_sources(analyze_new=True, force=True, trigger='manual')

@router.get('/jobs/{job_id}/account-plan')
def get_account_plan(job_id:int, db:Session=Depends(get_db)):
    j=db.get(JobPosting,job_id); p=db.scalar(select(CandidateProfile).limit(1))
    if not j or not p: raise HTTPException(404,'Missing job/profile')
    return account_plan(db,p,j)

@router.post('/reports/daily/email')
def email_report(db:Session=Depends(get_db)):
    import json
    report=build_daily_report(db)
    return {'sent':send_email('CareerOps Daily Report',json.dumps(report,indent=2)),'report':report}


@router.get('/sources')
def list_sources(db:Session=Depends(get_db)):
    rows=db.scalars(select(SourceConfig).order_by(SourceConfig.id)).all()
    return [{'id':x.id,'source_type':x.source_type,'name':x.name,'token_or_url':x.token_or_url,'enabled':x.enabled,'scan_interval_minutes':x.scan_interval_minutes,'last_run_at':x.last_run_at,'last_status':x.last_status,'last_count':x.last_count} for x in rows]

@router.post('/sources')
def create_source(source_type:str=Form(...), name:str=Form(...), token_or_url:str=Form(...), enabled:bool=Form(True), scan_interval_minutes:int=Form(240), db:Session=Depends(get_db)):
    if source_type not in {'greenhouse','lever','ashby','generic','company_career','adzuna','usajobs','linkedin_alerts','indeed_alerts'}: raise HTTPException(400,'Unsupported source type')
    x=db.scalar(select(SourceConfig).where(SourceConfig.source_type==source_type, SourceConfig.token_or_url==token_or_url))
    if x:
        x.name=name; x.enabled=enabled; x.scan_interval_minutes=scan_interval_minutes
    else:
        x=SourceConfig(source_type=source_type,name=name,token_or_url=token_or_url,enabled=enabled,scan_interval_minutes=scan_interval_minutes); db.add(x)
    db.commit(); db.refresh(x)
    return {'id':x.id,'ok':True}

@router.patch('/sources/{source_id}')
def update_source(source_id:int, enabled:bool=Query(...), db:Session=Depends(get_db)):
    x=db.get(SourceConfig,source_id)
    if not x: raise HTTPException(404,'Source not found')
    x.enabled=enabled; db.add(x); db.commit(); return {'ok':True,'enabled':x.enabled}

@router.get('/runtime-settings')
def runtime_settings(db:Session=Depends(get_db)):
    x=get_runtime_settings(db)
    return {'auto_apply_enabled':x.auto_apply_enabled,'auto_apply_min_fit':x.auto_apply_min_fit,'max_auto_applications_per_day':x.max_auto_applications_per_day}

@router.put('/runtime-settings')
def update_runtime_settings(auto_apply_enabled:bool=Form(...), auto_apply_min_fit:int=Form(90), max_auto_applications_per_day:int=Form(5), db:Session=Depends(get_db)):
    x=get_runtime_settings(db)
    x.auto_apply_enabled=auto_apply_enabled
    x.auto_apply_min_fit=max(0,min(100,auto_apply_min_fit))
    x.max_auto_applications_per_day=max(1,min(100,max_auto_applications_per_day))
    db.add(x); db.commit(); db.refresh(x)
    return {'ok':True,'auto_apply_enabled':x.auto_apply_enabled,'auto_apply_min_fit':x.auto_apply_min_fit,'max_auto_applications_per_day':x.max_auto_applications_per_day}

@router.patch('/applications/{application_id}/status')
def update_application_status(application_id:int, status:str=Query(...), db:Session=Depends(get_db)):
    allowed={'planned','prepared','review','submitted','interview','offer','rejected','withdrawn'}
    if status not in allowed: raise HTTPException(400,'Invalid status')
    app=db.get(Application,application_id)
    if not app: raise HTTPException(404,'Application not found')
    app.status=status
    if status=='submitted': app.submitted_at=datetime.now(timezone.utc)
    db.add(app); db.commit(); return {'ok':True,'status':status}

@router.get('/applications')
def list_applications(db:Session=Depends(get_db)):
    rows=db.scalars(select(Application).order_by(Application.created_at.desc())).all()
    out=[]
    for a in rows:
        job=db.get(JobPosting,a.job_id)
        out.append({'id':a.id,'job_id':a.job_id,'company':job.company if job else None,'title':job.title if job else None,'status':a.status,'verification_state':verification_state(a),'portal':a.portal,'requires_human_review':a.requires_human_review,'review_reasons':a.human_review_reasons,'submitted_at':a.submitted_at,'confirmation':a.confirmation})
    return out

@router.get('/applications/{application_id}/verification')
def application_verification(application_id:int, db:Session=Depends(get_db)):
    app=db.get(Application,application_id)
    if not app: raise HTTPException(404,'Application not found')
    return {'application_id':app.id,'status':app.status,**submission_evidence_summary(app)}

@router.get('/applications/{application_id}/evidence/screenshot')
def application_evidence_screenshot(application_id:int, db:Session=Depends(get_db)):
    app=db.get(Application,application_id)
    if not app: raise HTTPException(404,'Application not found')
    path=(get_submission_evidence(app) or {}).get('screenshot_path')
    if not path or not Path(path).exists(): raise HTTPException(404,'No submission screenshot is available')
    return FileResponse(path,filename=Path(path).name,media_type='image/png')


@router.get('/profile/links')
def list_profile_links(db:Session=Depends(get_db)):
    p=db.scalar(select(CandidateProfile).limit(1))
    if not p: raise HTTPException(404,'Profile not configured')
    rows=db.scalars(select(ProfileLink).where(ProfileLink.profile_id==p.id).order_by(ProfileLink.id)).all()
    return [{'id':x.id,'label':x.label,'url':x.url,'link_type':x.link_type,'include_in_applications':x.include_in_applications} for x in rows]

@router.post('/profile/links')
def add_profile_link(label:str=Form(...), url:str=Form(...), link_type:str=Form('other'), include_in_applications:bool=Form(True), db:Session=Depends(get_db)):
    p=db.scalar(select(CandidateProfile).limit(1))
    if not p: raise HTTPException(404,'Profile not configured')
    if not (url.startswith('http://') or url.startswith('https://')):
        raise HTTPException(400,'Use a complete http:// or https:// URL.')
    x=ProfileLink(profile_id=p.id,label=label.strip(),url=url.strip(),link_type=link_type.strip() or 'other',include_in_applications=include_in_applications)
    db.add(x); db.commit(); db.refresh(x)
    return {'ok':True,'id':x.id}

@router.delete('/profile/links/{link_id}')
def delete_profile_link(link_id:int, db:Session=Depends(get_db)):
    x=db.get(ProfileLink,link_id)
    if not x: raise HTTPException(404,'Link not found')
    db.delete(x); db.commit(); return {'ok':True}

@router.get('/journal')
def journal_entries(db:Session=Depends(get_db)):
    p=db.scalar(select(CandidateProfile).limit(1))
    if not p: raise HTTPException(404,'Profile not configured')
    rows=db.scalars(select(CareerJournalEntry).where(CareerJournalEntry.profile_id==p.id).order_by(CareerJournalEntry.entry_date.desc(),CareerJournalEntry.id.desc())).all()
    return [{'id':x.id,'entry_date':x.entry_date,'title':x.title,'project':x.project,'what_built':x.what_built,'problem_solved':x.problem_solved,'architecture_decisions':x.architecture_decisions,'tradeoffs':x.tradeoffs,'time_spent_hours':x.time_spent_hours,'impact':x.impact,'metrics':x.metrics,'skills':x.skills,'links':x.links,'lessons':x.lessons,'evidence_id':x.evidence_id} for x in rows]

@router.post('/journal')
def create_journal_entry(
    entry_date:str=Form(...), title:str=Form(...), project:str=Form(''), what_built:str=Form(...),
    problem_solved:str=Form(''), architecture_decisions:str=Form(''), tradeoffs:str=Form(''),
    time_spent_hours:str=Form(''), impact:str=Form(''), metrics_text:str=Form(''), skills_text:str=Form(''),
    links_text:str=Form(''), lessons:str=Form(''), db:Session=Depends(get_db)
):
    p=db.scalar(select(CandidateProfile).limit(1))
    if not p: raise HTTPException(404,'Profile not configured')
    try: hours=float(time_spent_hours) if str(time_spent_hours).strip() else None
    except ValueError: raise HTTPException(400,'Time spent must be a number of hours.')
    skills=[x.strip() for raw in skills_text.replace(',', '\n').splitlines() for x in [raw] if x.strip()]
    links=[x.strip() for x in links_text.splitlines() if x.strip()]
    x=CareerJournalEntry(profile_id=p.id,entry_date=entry_date,title=title.strip(),project=project.strip() or None,
        what_built=what_built.strip(),problem_solved=problem_solved.strip() or None,architecture_decisions=architecture_decisions.strip() or None,
        tradeoffs=tradeoffs.strip() or None,time_spent_hours=hours,impact=impact.strip() or None,metrics=parse_metric_lines(metrics_text),
        skills=skills,links=links,lessons=lessons.strip() or None)
    db.add(x); db.flush(); evidence=evidence_from_journal(db,p,x)
    return {'ok':True,'id':x.id,'evidence_id':evidence.id}

@router.delete('/journal/{entry_id}')
def delete_journal_entry(entry_id:int, db:Session=Depends(get_db)):
    x=db.get(CareerJournalEntry,entry_id)
    if not x: raise HTTPException(404,'Journal entry not found')
    if x.evidence_id:
        from careerops.db.models import CandidateEvidence
        ev=db.get(CandidateEvidence,x.evidence_id)
        if ev: db.delete(ev)
    db.delete(x); db.commit(); return {'ok':True}

@router.get('/applications/{application_id}/review')
def application_review(application_id:int, db:Session=Depends(get_db)):
    app=db.get(Application,application_id)
    if not app: raise HTTPException(404,'Application not found')
    saved={r.question:r for r in db.scalars(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.application_id==application_id)).all()}
    items=[]
    reasons=list(dict.fromkeys(app.human_review_reasons or []))
    for q in reasons:
        plan=(app.answers or {}).get(q,{})
        row=saved.get(q)
        items.append({'question':q,'mode':plan.get('mode','REVIEW'),'suggested_answer':plan.get('answer'),'reason':plan.get('reason','Human review required.'),
                      'answer':row.answer if row else None,'resolved':row.resolved if row else False,'notes':row.notes if row else None})
    return {'application_id':application_id,'items':items,'remaining':sum(1 for x in items if not x['resolved'])}

@router.post('/applications/{application_id}/review-answer')
def save_application_review_answer(application_id:int, question:str=Form(...), answer:str=Form(''), notes:str=Form(''), resolved:bool=Form(True), db:Session=Depends(get_db)):
    app=db.get(Application,application_id)
    if not app: raise HTTPException(404,'Application not found')
    row=db.scalar(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.application_id==application_id,ApplicationReviewAnswer.question==question))
    if row is None:
        row=ApplicationReviewAnswer(application_id=application_id,question=question,answer=answer.strip() or None,notes=notes.strip() or None,resolved=resolved)
        db.add(row)
    else:
        row.answer=answer.strip() or None; row.notes=notes.strip() or None; row.resolved=resolved; db.add(row)
    answers=dict(app.answers or {})
    plan=dict(answers.get(question,{}) or {})
    plan.update({'user_answer':answer.strip() or None,'user_resolved':resolved,'user_notes':notes.strip() or None})
    answers[question]=plan; app.answers=answers
    if resolved:
        app.human_review_reasons=[x for x in (app.human_review_reasons or []) if x != question]
    else:
        if question not in (app.human_review_reasons or []): app.human_review_reasons=list(app.human_review_reasons or [])+[question]
    app.requires_human_review=bool(app.human_review_reasons)
    db.add(app); db.commit(); db.refresh(row); db.refresh(app)
    return {'ok':True,'resolved':row.resolved,'remaining':len(app.human_review_reasons or []),'requires_human_review':app.requires_human_review}


@router.delete('/sources/{source_id}')
def delete_source(source_id:int, db:Session=Depends(get_db)):
    x=db.get(SourceConfig,source_id)
    if not x: raise HTTPException(404,'Source not found')
    db.delete(x); db.commit(); return {'ok':True}

@router.get('/providers/status')
def provider_status(db:Session=Depends(get_db)):
    return {
        'adzuna':{'configured':bool(settings.adzuna_app_id and settings.adzuna_app_key),'required':['ADZUNA_APP_ID','ADZUNA_APP_KEY']},
        'usajobs':{'configured':bool(settings.usajobs_api_key and settings.usajobs_user_agent),'required':['USAJOBS_API_KEY','USAJOBS_USER_AGENT']},
        'alert_imap':{'configured':imap_configured(),'required':['JOB_ALERT_IMAP_HOST','JOB_ALERT_IMAP_USER','JOB_ALERT_IMAP_PASSWORD']},
        'notifications':{'ses':bool(settings.ses_from_email),'slack':bool(settings.slack_webhook_url),'discord':bool(settings.discord_webhook_url),'telegram':bool(settings.telegram_bot_token and settings.telegram_chat_id)},
    }

@router.get('/notifications/preferences')
def notification_preferences(db:Session=Depends(get_db)):
    p=get_notification_preferences(db)
    return {c.name:getattr(p,c.name) for c in NotificationPreference.__table__.columns}

@router.put('/notifications/preferences')
def update_notification_preferences(
    enabled:bool=Form(True), notify_new_match:bool=Form(True), notify_high_fit:bool=Form(True),
    notify_human_review:bool=Form(True), notify_submitted:bool=Form(True), notify_failed:bool=Form(True),
    minimum_fit_score:int=Form(75), urgent_fit_score:int=Form(90), email_enabled:bool=Form(False),
    email_to:str=Form(''), slack_enabled:bool=Form(False), slack_webhook_url:str=Form(''),
    discord_enabled:bool=Form(False), discord_webhook_url:str=Form(''), telegram_enabled:bool=Form(False),
    telegram_bot_token:str=Form(''), telegram_chat_id:str=Form(''), db:Session=Depends(get_db)
):
    p=get_notification_preferences(db)
    p.enabled=enabled; p.notify_new_match=notify_new_match; p.notify_high_fit=notify_high_fit; p.notify_human_review=notify_human_review
    p.notify_submitted=notify_submitted; p.notify_failed=notify_failed
    p.minimum_fit_score=max(0,min(100,minimum_fit_score)); p.urgent_fit_score=max(p.minimum_fit_score,min(100,urgent_fit_score))
    p.email_enabled=email_enabled; p.email_to=email_to.strip() or None
    p.slack_enabled=slack_enabled; p.slack_webhook_url=slack_webhook_url.strip() or None
    p.discord_enabled=discord_enabled; p.discord_webhook_url=discord_webhook_url.strip() or None
    p.telegram_enabled=telegram_enabled; p.telegram_bot_token=telegram_bot_token.strip() or None; p.telegram_chat_id=telegram_chat_id.strip() or None
    db.add(p); db.commit(); db.refresh(p); return {'ok':True}

@router.get('/notifications')
def list_notifications(limit:int=Query(100,ge=1,le=500), db:Session=Depends(get_db)):
    rows=db.scalars(select(NotificationEvent).order_by(NotificationEvent.created_at.desc()).limit(limit)).all()
    return [{c.name:getattr(x,c.name) for c in NotificationEvent.__table__.columns} for x in rows]

@router.patch('/notifications/{notification_id}/read')
def mark_notification_read(notification_id:int, db:Session=Depends(get_db)):
    x=db.get(NotificationEvent,notification_id)
    if not x: raise HTTPException(404,'Notification not found')
    x.read=True; db.add(x); db.commit(); return {'ok':True}

@router.post('/notifications/test')
def test_notification(db:Session=Depends(get_db)):
    x=emit_notification(db,'test','CareerOps test notification','Your CareerOps notification channels are connected.')
    return {'ok':bool(x),'event_id':x.id if x else None,'delivery_results':x.delivery_results if x else {}}

@router.get('/alerts/inbox')
def alert_inbox(db:Session=Depends(get_db)):
    rows=db.scalars(select(AlertInboxMessage).order_by(AlertInboxMessage.received_at.desc()).limit(100)).all()
    return [{c.name:getattr(x,c.name) for c in AlertInboxMessage.__table__.columns} for x in rows]

@router.post('/alerts/email')
def ingest_alert_email(
    provider:str=Form(''), sender:str=Form(''), subject:str=Form(''), text:str=Form(''), html:str=Form(''),
    raw_email:str=Form(''), token:str=Form(''), db:Session=Depends(get_db)
):
    if settings.alert_ingest_token and token != settings.alert_ingest_token:
        raise HTTPException(401,'Invalid alert-ingest token')
    if not raw_email and not (text or html): raise HTTPException(400,'Provide raw_email or text/html content')
    row=store_alert_email(db,raw_email=raw_email or None,provider=provider or None,sender=sender or None,subject=subject or None,text=text or None,html=html or None)
    return {'ok':True,'id':row.id,'provider':row.provider,'urls':row.discovered_urls}

@router.post('/alerts/poll-imap')
def poll_alert_imap(db:Session=Depends(get_db)):
    return poll_imap_alerts(db)

@router.post('/alerts/process')
async def process_alerts(db:Session=Depends(get_db)):
    p=db.scalar(select(CandidateProfile).limit(1))
    return await process_pending_alerts(db,p)
