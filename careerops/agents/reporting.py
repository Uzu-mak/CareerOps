from __future__ import annotations
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from careerops.db.models import JobPosting, JobAnalysis, Application, AgentRun


def dashboard_metrics(db: Session) -> dict:
    jobs = db.scalar(select(func.count(JobPosting.id)).where(JobPosting.source != 'demo')) or 0
    analyzed = db.scalar(select(func.count(JobAnalysis.id))) or 0
    apps = db.scalar(select(func.count(Application.id))) or 0
    submitted = db.scalar(select(func.count(Application.id)).where(Application.status == 'submitted')) or 0
    a_jobs = db.scalar(select(func.count(JobAnalysis.id)).where(JobAnalysis.priority.in_(['A+','A']))) or 0
    runs = db.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(200)).all()
    avg_latency = round(sum(r.latency_ms for r in runs)/len(runs)) if runs else 0
    return {'jobs':jobs,'analyzed':analyzed,'high_fit':a_jobs,'applications':apps,'submitted':submitted,'agent_runs':len(runs),'avg_agent_latency_ms':avg_latency}


def build_daily_report(db: Session) -> dict:
    analyses = db.scalars(select(JobAnalysis).order_by(JobAnalysis.created_at.desc())).all()
    seen = set(); rows=[]
    for a in analyses:
        if a.job_id in seen: continue
        seen.add(a.job_id)
        job = db.get(JobPosting, a.job_id)
        if not job or job.source == 'demo':
            continue
        rows.append({'job_id':job.id,'company':job.company,'title':job.title,'location':job.location,'fit_score':a.fit_score,'priority':a.priority,'action':a.recommended_action,'hard_filter':a.hard_filter_status})
    rows.sort(key=lambda x:x['fit_score'], reverse=True)
    return {
        'summary': {'jobs_analyzed':len(rows),'apply_or_review':sum(1 for x in rows if x['action'] in ['APPLY','REVIEW']),'high_fit':sum(1 for x in rows if x['priority'] in ['A+','A']),'skipped':sum(1 for x in rows if x['action']=='SKIP')},
        'top_opportunities': rows[:10],
    }
