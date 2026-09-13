from __future__ import annotations
import asyncio, json
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from careerops.db.session import SessionLocal
from careerops.db.models import SourceConfig, CandidateProfile, DiscoveryRun
from careerops.sources.greenhouse import GreenhouseSource
from careerops.sources.lever import LeverSource
from careerops.sources.ashby import AshbySource
from careerops.sources.generic import GenericPageSource
from careerops.sources.adzuna import AdzunaSource
from careerops.sources.usajobs import USAJobsSource
from careerops.sources.company_career import CompanyCareerSource
from careerops.services.ingest import upsert_job
from careerops.agents.orchestrator import analyze_job
from careerops.services.search_policy import should_keep_discovered_job
from careerops.services.autopilot import attempt_autopilot_application
from careerops.services.notifications import notify_job_match, notify_application_event
from careerops.services.alert_inbox import process_pending_alerts
from careerops.services.imap_alerts import poll_imap_alerts


def _config_payload(cfg: SourceConfig) -> dict:
    raw=(cfg.token_or_url or '').strip()
    if raw.startswith('{'):
        try: return json.loads(raw)
        except Exception: pass
    return {'value':raw}


def make_source(cfg: SourceConfig, profile: CandidateProfile | None):
    payload=_config_payload(cfg); value=payload.get('value') or cfg.token_or_url
    if cfg.source_type == 'greenhouse': return GreenhouseSource(value)
    if cfg.source_type == 'lever': return LeverSource(value)
    if cfg.source_type == 'ashby': return AshbySource(value)
    if cfg.source_type == 'generic': return GenericPageSource(value)
    if cfg.source_type == 'company_career': return CompanyCareerSource(cfg.name,payload.get('url') or value,max_detail_pages=int(payload.get('max_detail_pages',35)))
    if cfg.source_type == 'adzuna':
        if not profile: raise RuntimeError('Candidate profile required for Adzuna search')
        return AdzunaSource(profile,country=payload.get('country','us'),results_per_query=int(payload.get('results_per_query',20)))
    if cfg.source_type == 'usajobs':
        if not profile: raise RuntimeError('Candidate profile required for USAJOBS search')
        return USAJobsSource(profile,results_per_query=int(payload.get('results_per_query',50)))
    raise ValueError(f'Unsupported source_type={cfg.source_type}')


def _due(cfg: SourceConfig, force: bool=False) -> bool:
    if force or cfg.last_run_at is None: return True
    last=cfg.last_run_at
    if last.tzinfo is None: last=last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)-last >= timedelta(minutes=max(1,cfg.scan_interval_minutes or 15))


async def scan_enabled_sources(analyze_new: bool = True, force: bool=False, trigger: str='watchtower') -> dict:
    db=SessionLocal(); run=DiscoveryRun(trigger=trigger,totals={},status='running'); db.add(run); db.commit(); db.refresh(run)
    totals={'sources':0,'sources_skipped_not_due':0,'fetched':0,'location_filtered':0,'created':0,'analyzed':0,
            'notifications':0,'autopilot_attempted':0,'autopilot_submitted':0,'alert_messages':0,'alert_jobs_created':0,'imap_imported':0,'errors':[]}
    try:
        profile=db.scalar(select(CandidateProfile).limit(1))
        imap_totals=poll_imap_alerts(db)
        totals['imap_imported']=imap_totals.get('imported',0); totals['errors'].extend([{'imap':e} for e in imap_totals.get('errors',[])])
        alert_totals=await process_pending_alerts(db,profile)
        totals['alert_messages']=alert_totals['messages']; totals['alert_jobs_created']=alert_totals['created']; totals['errors'].extend(alert_totals['errors'])
        configs=db.scalars(select(SourceConfig).where(SourceConfig.enabled == True)).all()  # noqa: E712
        for cfg in configs:
            if cfg.source_type in {'linkedin_alerts','indeed_alerts'}: continue
            if not _due(cfg,force): totals['sources_skipped_not_due']+=1; continue
            totals['sources']+=1
            try:
                fetched=await make_source(cfg,profile).fetch(); new_jobs=[]
                for item in fetched:
                    totals['fetched']+=1
                    if not item.get('company') or item.get('company')=='Unknown': item['company']=cfg.name
                    if profile and not should_keep_discovered_job(profile,item):
                        totals['location_filtered']+=1; continue
                    job,created=upsert_job(db,item); totals['created']+=int(created)
                    if created: new_jobs.append(job)
                if analyze_new and profile:
                    for job in new_jobs:
                        analysis=analyze_job(db,job); totals['analyzed']+=1
                        if notify_job_match(db,job,analysis): totals['notifications']+=1
                        result=attempt_autopilot_application(db,profile,job)
                        if result.get('attempted'):
                            totals['autopilot_attempted']+=1; totals['autopilot_submitted']+=int(bool(result.get('submitted')))
                            app_id=result.get('application_id')
                            if app_id:
                                from careerops.db.models import Application
                                app=db.get(Application,app_id)
                                if app:
                                    if result.get('submitted'): notify_application_event(db,'submitted',app,job,result.get('reason',''))
                                    elif app.requires_human_review: notify_application_event(db,'human_review',app,job,result.get('reason',''))
                cfg.last_run_at=datetime.now(timezone.utc); cfg.last_status='success'; cfg.last_count=len(fetched); db.add(cfg); db.commit()
            except Exception as exc:
                cfg.last_run_at=datetime.now(timezone.utc); cfg.last_status=f'error: {str(exc)[:220]}'; db.add(cfg); db.commit(); totals['errors'].append({'source':cfg.name,'error':str(exc)})
        run.totals=totals; run.finished_at=datetime.now(timezone.utc); run.status='success' if not totals['errors'] else 'partial'; db.add(run); db.commit()
        return totals
    except Exception as exc:
        totals['errors'].append({'run':'fatal','error':str(exc)}); run.totals=totals; run.finished_at=datetime.now(timezone.utc); run.status='error'; db.add(run); db.commit(); raise
    finally:
        db.close()


if __name__ == '__main__':
    print(asyncio.run(scan_enabled_sources()))
