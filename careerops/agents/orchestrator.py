from __future__ import annotations
from sqlalchemy.orm import Session
from sqlalchemy import select
from careerops.core.config import settings
from careerops.db.models import CandidateProfile, JobPosting, JobAnalysis, Application, GeneratedArtifact, ApplicationReviewAnswer
from careerops.agents.jd_analysis import analyze_job_text
from careerops.agents.fit import score_job
from careerops.agents.documents import build_resume, build_cover_letter
from careerops.agents.qa import build_standard_application_answers
from careerops.agents.outreach import draft_outreach
from careerops.services.audit import agent_run


def get_profile(db: Session) -> CandidateProfile:
    p=db.scalar(select(CandidateProfile).limit(1))
    if not p: raise ValueError('Candidate profile not configured')
    return p


def latest_analysis(db: Session, job_id: int):
    return db.scalar(select(JobAnalysis).where(JobAnalysis.job_id==job_id).order_by(JobAnalysis.created_at.desc()).limit(1))


def analyze_job(db: Session, job: JobPosting) -> JobAnalysis:
    profile=get_profile(db)
    with agent_run(db,'JDAnalysisAgent',job_id=job.id,provider=settings.llm_provider,input_summary=f'{job.company} / {job.title}') as run:
        extracted=analyze_job_text(job)
        for key,val in extracted.items():
            if key=='detected_skills':
                if not job.required_skills: job.required_skills=val
            elif val not in (None,[]) and (getattr(job,key,None) in (None,[],'unknown')):
                setattr(job,key,val)
        run.output_summary=f"skills={len(job.required_skills or [])}; sponsorship={job.sponsorship_policy}; years={job.required_years}"
        db.add(job); db.commit()
    with agent_run(db,'FitAgent',job_id=job.id,input_summary='hard constraints + explainable weighted fit') as run:
        analysis=score_job(db,profile,job); db.add(analysis); db.commit(); db.refresh(analysis)
        run.output_summary=f'{analysis.fit_score}% {analysis.priority} {analysis.recommended_action}'
    return analysis


def prepare_application(db: Session, job: JobPosting) -> dict:
    profile=get_profile(db)
    analysis=latest_analysis(db,job.id) or analyze_job(db,job)
    app=db.scalar(select(Application).where(Application.job_id==job.id).order_by(Application.created_at.desc()).limit(1))
    if not app:
        app=Application(job_id=job.id, status='prepared', portal=job.ats, mode='PREPARE'); db.add(app); db.commit(); db.refresh(app)
    with agent_run(db,'ResumeAgent',job_id=job.id,application_id=app.id,input_summary='select verified evidence + tailor emphasis') as run:
        resume=build_resume(db,profile,job,analysis,app); run.output_summary=resume.file_path
    with agent_run(db,'CoverLetterAgent',job_id=job.id,application_id=app.id,input_summary='mission-aligned cover letter from verified evidence') as run:
        letter=build_cover_letter(db,profile,job,analysis,app); run.output_summary=letter.file_path
    with agent_run(db,'ApplicationQAAgent',job_id=job.id,application_id=app.id,input_summary='profile/rule/legal answer plan') as run:
        answers=build_standard_application_answers(profile,job)
        resolved_rows=db.scalars(select(ApplicationReviewAnswer).where(ApplicationReviewAnswer.application_id==app.id, ApplicationReviewAnswer.resolved==True)).all()
        resolved={r.question:r.answer for r in resolved_rows}
        for q,answer in resolved.items():
            plan=dict(answers.get(q,{}) or {})
            plan.update({'mode':'USER_VERIFIED','answer':answer,'reason':'Explicitly provided by the user for this application.','user_resolved':True})
            answers[q]=plan
        app.answers=answers
        review=[q for q,a in answers.items() if a['mode'] in ['MANUAL','REVIEW'] and q not in resolved]
        app.human_review_reasons=review; app.requires_human_review=bool(review); db.add(app); db.commit(); run.output_summary=f'{len(answers)} answers; {len(review)} review'
    with agent_run(db,'OutreachAgent',job_id=job.id,application_id=app.id,input_summary='short recruiter outreach') as run:
        text=draft_outreach(profile,job,analysis)
        outreach=GeneratedArtifact(job_id=job.id,application_id=app.id,artifact_type='outreach',title=f'{job.company} outreach',content=text)
        db.add(outreach); db.commit(); db.refresh(outreach); run.output_summary=text[:120]
    return {'application':app,'analysis':analysis,'resume':resume,'cover_letter':letter,'outreach':outreach}
