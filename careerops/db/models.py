from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, Text, Float, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from careerops.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CandidateProfile(Base):
    __tablename__ = 'candidate_profiles'

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(220))
    preferred_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(220), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    home_location: Mapped[str | None] = mapped_column(String(220), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Master resume uploaded by the user. It is the baseline for every tailored version.
    baseline_resume_filename: Mapped[str | None] = mapped_column(String(320), nullable=True)
    baseline_resume_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    baseline_resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    baseline_resume_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role_families: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    search_radius_miles: Mapped[int] = mapped_column(Integer, default=50)
    remote_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    hybrid_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    onsite_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    minimum_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    years_professional_software: Mapped[float] = mapped_column(Float, default=0)
    years_hands_on_software: Mapped[float] = mapped_column(Float, default=0)

    # Sensitive/legal fields are explicit user-verified values. Agents must not infer them.
    authorized_to_work_us: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    requires_current_sponsorship: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    requires_future_sponsorship: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    work_authorization_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    work_authorization_expiration: Mapped[str | None] = mapped_column(String(40), nullable=True)
    legal_answers_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    baseline_minutes: Mapped[dict] = mapped_column(JSON, default=lambda: {
        'jd_analysis': 8,
        'fit_assessment': 12,
        'resume_tailoring': 20,
        'cover_letter': 20,
        'application_questions': 15,
        'tracking': 5,
        'outreach_draft': 10,
    })
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    evidence_items: Mapped[list['CandidateEvidence']] = relationship(back_populates='profile', cascade='all, delete-orphan')


class CandidateEvidence(Base):
    __tablename__ = 'candidate_evidence'
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey('candidate_profiles.id', ondelete='CASCADE'), index=True)
    category: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(220))
    organization: Mapped[str | None] = mapped_column(String(220), nullable=True)
    date_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    bullets: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    verified_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile: Mapped[CandidateProfile] = relationship(back_populates='evidence_items')


class ProfileLink(Base):
    __tablename__ = 'profile_links'
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey('candidate_profiles.id', ondelete='CASCADE'), index=True)
    label: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(Text)
    link_type: Mapped[str] = mapped_column(String(60), default='other')
    include_in_applications: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CareerJournalEntry(Base):
    __tablename__ = 'career_journal_entries'
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey('candidate_profiles.id', ondelete='CASCADE'), index=True)
    entry_date: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(240))
    project: Mapped[str | None] = mapped_column(String(220), nullable=True)
    what_built: Mapped[str] = mapped_column(Text)
    problem_solved: Mapped[str | None] = mapped_column(Text, nullable=True)
    architecture_decisions: Mapped[str | None] = mapped_column(Text, nullable=True)
    tradeoffs: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_spent_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    links: Mapped[list[str]] = mapped_column(JSON, default=list)
    lessons: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey('candidate_evidence.id', ondelete='SET NULL'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ApplicationReviewAnswer(Base):
    __tablename__ = 'application_review_answers'
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey('applications.id', ondelete='CASCADE'), index=True)
    question: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(80), default='review')
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class JobPosting(Base):
    __tablename__ = 'job_postings'
    __table_args__ = (UniqueConstraint('fingerprint', name='uq_job_fingerprint'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(80), default='manual')
    source_job_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ats: Mapped[str | None] = mapped_column(String(80), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str] = mapped_column(String(220))
    title: Mapped[str] = mapped_column(String(320))
    location: Mapped[str | None] = mapped_column(String(240), nullable=True)
    workplace_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    company_mission: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default='USD')
    required_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    responsibilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    sponsorship_policy: Mapped[str] = mapped_column(String(40), default='unknown')
    clearance_required: Mapped[bool] = mapped_column(Boolean, default=False)
    export_control_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default='open')

    analyses: Mapped[list['JobAnalysis']] = relationship(back_populates='job', cascade='all, delete-orphan')
    applications: Mapped[list['Application']] = relationship(back_populates='job', cascade='all, delete-orphan')


class JobAnalysis(Base):
    __tablename__ = 'job_analyses'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('job_postings.id', ondelete='CASCADE'), index=True)
    hard_filter_status: Mapped[str] = mapped_column(String(20), default='REVIEW')
    hard_constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    fit_score: Mapped[float] = mapped_column(Float, default=0)
    component_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    priority: Mapped[str] = mapped_column(String(4), default='C')
    matched_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    partial_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    gap_skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    relevant_evidence_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    recommended_action: Mapped[str] = mapped_column(String(20), default='REVIEW')
    explanation: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    job: Mapped[JobPosting] = relationship(back_populates='analyses')


class GeneratedArtifact(Base):
    __tablename__ = 'generated_artifacts'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('job_postings.id', ondelete='CASCADE'), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey('applications.id', ondelete='SET NULL'), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(220))
    content: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    truth_guard_passed: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked_claims: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Application(Base):
    __tablename__ = 'applications'
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('job_postings.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(50), default='planned')
    portal: Mapped[str | None] = mapped_column(String(80), nullable=True)
    portal_account_email: Mapped[str | None] = mapped_column(String(220), nullable=True)
    mode: Mapped[str] = mapped_column(String(30), default='PREPARE')
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    human_review_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    job: Mapped[JobPosting] = relationship(back_populates='applications')




class PortalAccount(Base):
    __tablename__ = 'portal_accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    company: Mapped[str | None] = mapped_column(String(220), nullable=True)
    login_email: Mapped[str | None] = mapped_column(String(220), nullable=True)
    auth_strategy: Mapped[str] = mapped_column(String(60), default='direct')
    status: Mapped[str] = mapped_column(String(40), default='unknown')
    session_state_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AgentRun(Base):
    __tablename__ = 'agent_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(80), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey('job_postings.id', ondelete='SET NULL'), nullable=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey('applications.id', ondelete='SET NULL'), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='success')
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    model_provider: Mapped[str] = mapped_column(String(40), default='local')
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LLMCache(Base):
    __tablename__ = 'llm_cache'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(80), index=True)
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



class RuntimeSettings(Base):
    __tablename__ = 'runtime_settings'
    id: Mapped[int] = mapped_column(primary_key=True)
    auto_apply_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_apply_min_fit: Mapped[int] = mapped_column(Integer, default=90)
    max_auto_applications_per_day: Mapped[int] = mapped_column(Integer, default=5)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class SourceConfig(Base):
    __tablename__ = 'source_configs'
    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(160))
    token_or_url: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    scan_interval_minutes: Mapped[int] = mapped_column(Integer, default=240)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_count: Mapped[int] = mapped_column(Integer, default=0)


class NotificationPreference(Base):
    __tablename__ = 'notification_preferences'
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_new_match: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_high_fit: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_submitted: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_failed: Mapped[bool] = mapped_column(Boolean, default=True)
    minimum_fit_score: Mapped[int] = mapped_column(Integer, default=75)
    urgent_fit_score: Mapped[int] = mapped_column(Integer, default=90)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    email_to: Mapped[str | None] = mapped_column(String(320), nullable=True)
    slack_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    slack_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discord_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    discord_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_bot_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class NotificationEvent(Base):
    __tablename__ = 'notification_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(320))
    message: Mapped[str] = mapped_column(Text)
    job_id: Mapped[int | None] = mapped_column(ForeignKey('job_postings.id', ondelete='SET NULL'), nullable=True, index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey('applications.id', ondelete='SET NULL'), nullable=True, index=True)
    fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(10), nullable=True)
    channels_requested: Mapped[list[str]] = mapped_column(JSON, default=list)
    delivery_results: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default='created')
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertInboxMessage(Base):
    __tablename__ = 'alert_inbox_messages'
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(60), default='unknown', index=True)
    sender: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(320), nullable=True, unique=True)
    raw_text: Mapped[str] = mapped_column(Text)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovered_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    jobs_created: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiscoveryRun(Base):
    __tablename__ = 'discovery_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(60), default='watchtower')
    totals: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default='running')
