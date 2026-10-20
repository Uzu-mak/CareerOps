"""Filterable, paginated job listing with each job's latest analysis in one query."""
from __future__ import annotations

from math import ceil

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from careerops.core.ui_options import apply_mode as apply_mode_for
from careerops.db.models import Application, JobAnalysis, JobPosting

PAGE_SIZE = 25


def _latest_analysis_ids():
    return (select(JobAnalysis.job_id.label('job_id'), func.max(JobAnalysis.id).label('aid'))
            .group_by(JobAnalysis.job_id).subquery())


def _latest_application_ids():
    return (select(Application.job_id.label('job_id'), func.max(Application.id).label('app_id'))
            .group_by(Application.job_id).subquery())


def _auto_apply_clause():
    from careerops.core.ui_options import AUTO_APPLY_ATS, AUTO_APPLY_HOSTS
    urls = [col.ilike(f'%{h}%') for h in AUTO_APPLY_HOSTS for col in (JobPosting.application_url, JobPosting.canonical_url)]
    return or_(JobPosting.ats.in_(sorted(AUTO_APPLY_ATS)), *urls)


def search_jobs(db: Session, q: str = '', decision: str = '', priority: str = '', workplace: str = '',
                company: str = '', min_fit: int = 0, sort: str = 'fit', page: int = 1,
                page_size: int = PAGE_SIZE, apply_mode: str = '') -> dict:
    la, lp = _latest_analysis_ids(), _latest_application_ids()

    def filtered(*columns):
        stmt = (select(*columns).select_from(JobPosting)
                .outerjoin(la, la.c.job_id == JobPosting.id).outerjoin(JobAnalysis, JobAnalysis.id == la.c.aid)
                .outerjoin(lp, lp.c.job_id == JobPosting.id).outerjoin(Application, Application.id == lp.c.app_id)
                .where(JobPosting.source != 'demo'))
        if q.strip():
            like = f'%{q.strip()}%'
            stmt = stmt.where(or_(JobPosting.company.ilike(like), JobPosting.title.ilike(like), JobPosting.location.ilike(like)))
        if decision == 'UNANALYZED':
            stmt = stmt.where(JobAnalysis.id.is_(None))
        elif decision:
            stmt = stmt.where(JobAnalysis.recommended_action == decision)
        if priority:
            stmt = stmt.where(JobAnalysis.priority.in_([x for x in priority.split(',') if x]))
        if workplace:
            stmt = stmt.where(JobPosting.workplace_type == workplace)
        if company:
            stmt = stmt.where(JobPosting.company == company)
        if min_fit:
            stmt = stmt.where(JobAnalysis.fit_score >= min_fit)
        if apply_mode == 'auto':
            stmt = stmt.where(_auto_apply_clause())
        elif apply_mode == 'manual':
            stmt = stmt.where(~_auto_apply_clause())
        return stmt

    total = db.scalar(filtered(func.count(JobPosting.id))) or 0
    stmt = filtered(JobPosting, JobAnalysis, Application.status)
    order = {
        'newest': [JobPosting.first_seen_at.desc()],
        'company': [JobPosting.company.asc(), JobPosting.title.asc()],
    }.get(sort, [JobAnalysis.fit_score.desc().nulls_last(), JobPosting.first_seen_at.desc()])
    page_size = max(5, min(100, page_size))
    pages = max(1, ceil(total / page_size))
    page = max(1, min(page, pages))
    rows = db.execute(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()

    items = []
    for job, analysis, app_status in rows:
        items.append({
            'id': job.id, 'company': job.company, 'title': job.title, 'location': job.location,
            'workplace_type': job.workplace_type, 'source': job.source,
            'first_seen_at': job.first_seen_at.isoformat() if job.first_seen_at else None,
            'salary_min': job.salary_min, 'salary_max': job.salary_max,
            'has_application_url': bool(job.application_url or job.canonical_url),
            'apply_mode': apply_mode_for(job.application_url or job.canonical_url, job.ats),
            'fit_score': round(analysis.fit_score) if analysis else None,
            'priority': analysis.priority if analysis else None,
            'action': analysis.recommended_action if analysis else None,
            'hard_filter': analysis.hard_filter_status if analysis else None,
            'application_status': app_status,
        })
    return {'items': items, 'total': total, 'page': page, 'pages': pages, 'page_size': page_size}


def job_facets(db: Session) -> dict:
    companies = db.execute(select(JobPosting.company, func.count(JobPosting.id)).where(JobPosting.source != 'demo')
                           .group_by(JobPosting.company).order_by(JobPosting.company)).all()
    la = _latest_analysis_ids()
    decisions = dict(db.execute(select(JobAnalysis.recommended_action, func.count())
                                .join(la, la.c.aid == JobAnalysis.id).group_by(JobAnalysis.recommended_action)).all())
    return {'companies': [{'name': c, 'count': n} for c, n in companies], 'decisions': decisions,
            'unanalyzed': pending_analysis_count(db)}


def pending_analysis_ids(db: Session, limit: int | None = None) -> list[int]:
    la = _latest_analysis_ids()
    stmt = (select(JobPosting.id).outerjoin(la, la.c.job_id == JobPosting.id)
            .where(JobPosting.source != 'demo', la.c.aid.is_(None)).order_by(JobPosting.first_seen_at.desc()))
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def pending_analysis_count(db: Session) -> int:
    la = _latest_analysis_ids()
    return db.scalar(select(func.count(JobPosting.id)).outerjoin(la, la.c.job_id == JobPosting.id)
                     .where(JobPosting.source != 'demo', la.c.aid.is_(None))) or 0
