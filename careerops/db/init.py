from sqlalchemy import select, delete, text
from sqlalchemy.orm import Session
from careerops.db.base import Base
from careerops.db.session import engine, SessionLocal
from careerops.db.models import CandidateProfile, CandidateEvidence, JobPosting, SourceConfig, RuntimeSettings
from careerops.services.fingerprint import job_fingerprint
from careerops.core.config import settings



def starter_source_specs():
    return [
        ('ashby','OpenAI','openai',True,30,None),
        ('lever','Palantir','palantir',True,30,None),
        ('company_career','SpaceX','https://www.spacex.com/careers',True,30,None),
        ('company_career','Microsoft','https://jobs.careers.microsoft.com/global/en/search',True,60,None),
        ('company_career','Amazon','https://www.amazon.jobs/en/search',True,60,None),
        ('company_career','Boeing','https://jobs.boeing.com/search-jobs',True,60,None),
        ('company_career','Meta','https://www.metacareers.com/jobs',True,60,None),
        ('company_career','Salesforce','https://careers.salesforce.com/en/jobs/',True,60,None),
        ('linkedin_alerts','LinkedIn Job Alert Inbox','inbox://linkedin',True,15,'waiting for forwarded/imported alerts'),
        ('indeed_alerts','Indeed Job Alert Inbox','inbox://indeed',True,15,'waiting for forwarded/imported alerts'),
        ('adzuna','Adzuna Broad Market','{"country":"us","results_per_query":20}',bool(settings.adzuna_app_id and settings.adzuna_app_key),60,None if settings.adzuna_app_id and settings.adzuna_app_key else 'setup needed: ADZUNA_APP_ID / ADZUNA_APP_KEY'),
        ('usajobs','USAJOBS','{"results_per_query":50}',bool(settings.usajobs_api_key and settings.usajobs_user_agent),60,None if settings.usajobs_api_key and settings.usajobs_user_agent else 'setup needed: USAJOBS_API_KEY / USAJOBS_USER_AGENT'),
    ]

def create_all():
    Base.metadata.create_all(bind=engine)
    _ensure_schema_compatibility()


def _ensure_schema_compatibility():
    """Apply small idempotent compatibility fixes for existing PostgreSQL volumes.

    SQLAlchemy create_all() creates missing tables but does not widen columns on an
    existing database. CareerOps source URLs and status/error messages can exceed
    legacy VARCHAR limits, so widen these fields before starter-source seeding.
    """
    if engine.dialect.name != 'postgresql':
        return
    statements = [
        "ALTER TABLE source_configs ALTER COLUMN source_type TYPE VARCHAR(60)",
        "ALTER TABLE source_configs ALTER COLUMN name TYPE VARCHAR(160)",
        "ALTER TABLE source_configs ALTER COLUMN token_or_url TYPE TEXT",
        "ALTER TABLE source_configs ALTER COLUMN last_status TYPE TEXT",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def seed_demo_data():
    db: Session = SessionLocal()
    try:
        profile = db.scalar(select(CandidateProfile).limit(1))
        if not profile:
            profile = CandidateProfile(
                full_name=settings.demo_full_name, preferred_name=settings.demo_preferred_name,
                email=settings.demo_email, phone=settings.demo_phone, home_location=settings.demo_home_location,
                linkedin_url=settings.demo_linkedin_url,
                github_url=settings.demo_github_url,
                role_families=['Applied AI Engineer','AI Engineer','Software Engineer','Forward Deployed Engineer','Data Engineer','AI Solutions Engineer'],
                skills=['Python','SQL','FastAPI','PostgreSQL','React','Next.js','TypeScript','Docker','Kubernetes','GCP','RAG','GraphRAG','LangGraph','Neo4j','Qdrant','BigQuery','dbt','Grafana','GitHub Actions','REST APIs','GraphQL','software development','system design','communication','data engineering','LLMs','Generative AI'],
                preferred_locations=['Seattle, WA','Bellevue, WA','Redmond, WA','Tacoma, WA'],
                minimum_salary=None, target_salary=None,
                years_professional_software=0.6, years_hands_on_software=3.0,
                # Sensitive work-authorization fields deliberately left unset for user verification.
            )
            db.add(profile); db.flush()
            items = [
                CandidateEvidence(profile_id=profile.id, category='experience', title='Software Engineer', organization='Revna Biosciences', date_range='Jun 2024 - Dec 2024',
                    summary='Production-facing biotech software and LIMS workflows.',
                    bullets=['Built frontend and backend components for a microservices-based biotech operations platform, translating laboratory and operations requirements into APIs, data flows, validation rules, RBAC, and user-facing LIMS workflows.',
                             'Partnered with laboratory/operations stakeholders and engineering teammates to diagnose business-critical application and integration issues, test fixes, document workflows, and support deployment.'],
                    skills=['APIs','microservices','RBAC','full-stack','stakeholder collaboration','testing','deployment']),
                CandidateEvidence(profile_id=profile.id, category='experience', title='Graduate Practicum - AI Decision Support for Manufacturing Operations', organization='Wayne State University / IntelliMake', date_range='Jan 2026 - Aug 2026',
                    summary='Context-aware decision support for robotic body-shop fault and quality events.',
                    bullets=['Worked within a 5-person team to turn robotic body-shop maintenance and quality workflows into requirements, acceptance criteria, data models, and validation workflows.',
                             'Modeled 7+ operational entity types and supported outreach to 30 manufacturing contacts to refine data requirements, provenance, human-review boundaries, and design tradeoffs.',
                             'Built a Streamlit/PostgreSQL validation workspace for evidence intake, issue tracking, task ownership, status history, and readiness evaluation.'],
                    skills=['PostgreSQL','Streamlit','data modeling','requirements','manufacturing','stakeholder discovery'],
                    verified_metrics={'team_size':5,'entity_types_min':7,'manufacturing_contacts':30}),
                CandidateEvidence(profile_id=profile.id, category='project', title='AegisOps AI', organization='Independent',
                    summary='Industrial AI reliability platform with canonical memory, graph/vector retrieval, agents, observability and failure recovery.',
                    bullets=['Architected and shipped a 5-service industrial AI reliability platform spanning API services, canonical operational memory, graph/vector retrieval, agentic workflows, deployment, evaluation, observability, and failure recovery.',
                             'Made PostgreSQL the source of truth for 8+ memory types across 4 lifecycle states and treated Neo4j/Qdrant as recoverable projections.',
                             'Built LangGraph tool/function-calling workflows with semantic, graph, and hybrid retrieval and evaluated Recall@5/10, MRR, citation accuracy, p50/p95 latency, health signals, and failure-recovery behavior.'],
                    skills=['Python','FastAPI','PostgreSQL','Neo4j','Qdrant','LangGraph','Docker','Kubernetes','Grafana','RAG','distributed systems'],
                    verified_metrics={'services':5,'memory_types_min':8,'lifecycle_states':4,'retrieval_modes':3}),
                CandidateEvidence(profile_id=profile.id, category='project', title='LLM Evaluation Harness for RAG Systems', organization='Independent',
                    summary='Evaluation harness for isolating retrieval, context, prompt, and model failures.',
                    bullets=['Built an automated evaluation harness that separates retrieval, context, prompt, and model failures and compares chunking, top-k, reranking, and hybrid search with regression-ready scorecards.'],
                    skills=['Python','RAG','evaluation','reranking','A/B testing','retrieval']),
            ]
            db.add_all(items)

        if settings.seed_demo_jobs and db.scalar(select(JobPosting).limit(1)) is None:
            demo_jobs = [
                dict(source='demo', source_job_id='bud-clary-ai-builder', ats='handshake', company='Bud Clary Auto Group', title='AI Builder / Data Engineer', location='Kelso, WA', workplace_type='onsite', employment_type='full-time',
                     salary_min=65000, salary_max=85010, required_years=None, sponsorship_policy='available',
                     required_skills=['Python','SQL','PostgreSQL','APIs','data engineering'], preferred_skills=['Generative AI','LLMs','Azure','React','prompt engineering','AI agents'],
                     responsibilities=['Build AI-powered tools, applications and automations','Develop data pipelines, integrations and reporting solutions','Build and support AI agents and workflows','Collaborate with stakeholders to turn ideas into practical solutions'],
                     company_mission='Apply modern AI, automation and data technologies to improve dealership operations and customer outcomes.',
                     description='Build AI-powered tools, applications, automations, data pipelines, integrations, dashboards and AI agents. Work with SQL Server, PostgreSQL, Azure, Python, APIs and commercial LLM platforms. Strong interest in AI, software development, automation and data engineering.'),
                dict(source='demo', source_job_id='rover-recs', ats='custom', company='Rover', title='Entry Level Software Engineer, Recommendations', location='Seattle, WA', workplace_type='hybrid', employment_type='full-time',
                     salary_min=99719, salary_max=128513, required_years=1, sponsorship_policy='unavailable',
                     required_skills=['software development','system design','AI tools','communication'], preferred_skills=['Python','Django','Elasticsearch','React','search','marketplaces'],
                     responsibilities=['Build user-impacting marketplace features','Improve search and personalization','Support data science ML models','Ship features from requirements through launch'],
                     company_mission='Improve and simplify life for pet parents and the pets they love through trusted, personalized care.',
                     description='Recommendations team working on Elasticsearch, personalization and ML-supported search. Requires 1-4 years professional software development. Applicants must be authorized to work without current or future employer sponsorship.'),
                dict(source='demo', source_job_id='nscale-data', ats='greenhouse', company='Nscale', title='Data Engineer', location='Seattle, WA', workplace_type='hybrid', employment_type='full-time',
                     salary_min=130000, salary_max=160000, required_years=None, sponsorship_policy='unknown',
                     required_skills=['Palantir Foundry','Python','data engineering','REST APIs','GraphQL','Git','CI/CD'], preferred_skills=['AWS','GCP','Azure','distributed systems','monitoring'],
                     responsibilities=['Build scalable reliable data pipelines','Define data models and schemas','Create trusted datasets and semantic layers','Implement data quality checks, lineage and governance'],
                     company_mission='Build the GPU cloud engineered for AI and turn infrastructure signals into reliable, scalable data products.',
                     description='High-impact early-stage data engineering role. Deep hands-on Palantir Foundry experience, Python, API-driven integration, Git and CI/CD. Nice to have cloud platforms, distributed systems and monitoring data.'),
            ]
            for j in demo_jobs:
                j['fingerprint'] = job_fingerprint(j['company'], j['title'], j['location'], j['source_job_id'], j['description'])
                db.add(JobPosting(**j, raw_payload={'seeded': True}))

        # Starter multi-channel discovery network. Public ATS/company sources work immediately.
        # Credentialed APIs are visible but stay disabled until their required environment variables are configured.
        existing={(x.source_type, x.token_or_url) for x in db.scalars(select(SourceConfig)).all()}
        starter_sources=starter_source_specs()
        for source_type, name, token, enabled, minutes, last_status in starter_sources:
            if (source_type, token) not in existing:
                db.add(SourceConfig(source_type=source_type,name=name,token_or_url=token,enabled=enabled,scan_interval_minutes=minutes,last_status=last_status))

        if db.scalar(select(RuntimeSettings).limit(1)) is None:
            db.add(RuntimeSettings(auto_apply_enabled=False, auto_apply_min_fit=90, max_auto_applications_per_day=5))

        # Disable misleading generic LinkedIn/Indeed page rows from older builds.
        # CareerOps uses alert-inbox ingestion for those platforms rather than logged-in scraping.
        for old in db.scalars(select(SourceConfig).where(SourceConfig.source_type == 'generic')).all():
            raw=(old.token_or_url or '').lower()
            if 'linkedin.com' in raw or 'indeed.com' in raw:
                old.enabled=False
                old.last_status='disabled: use the LinkedIn/Indeed Job Alert Inbox source'
                db.add(old)

        # Older CareerOps builds seeded example roles without real application URLs.
        # When demo seeding is disabled, remove those stale examples from persistent DB volumes
        # so the opportunity queue contains only live/manual jobs that can be acted on.
        if not settings.seed_demo_jobs:
            db.execute(delete(JobPosting).where(JobPosting.source == 'demo'))

        db.commit()
    finally:
        db.close()
