from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_name: str = 'CareerOps'
    environment: str = 'local'
    database_url: str = 'sqlite:///./careerops.db'
    base_url: str = 'http://localhost:8000'
    llm_provider: str = 'local'
    aws_region: str = 'us-west-2'
    bedrock_model_id: str = 'anthropic.claude-3-5-sonnet-20241022-v2:0'
    s3_bucket: str | None = None
    ses_from_email: str | None = None
    ses_to_email: str | None = None
    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    usajobs_api_key: str | None = None
    usajobs_user_agent: str | None = None
    notification_webhook_secret: str | None = None
    alert_ingest_token: str | None = None
    job_alert_imap_host: str | None = None
    job_alert_imap_port: int = 993
    job_alert_imap_user: str | None = None
    job_alert_imap_password: str | None = None
    job_alert_imap_folder: str = 'INBOX'
    application_queue_url: str | None = None
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    auto_submit_enabled: bool = False
    seed_demo_jobs: bool = False
    browser_headless: bool = True
    chromium_executable: str = '/usr/bin/chromium'
    secret_key: str = 'replace-me-in-production'
    generated_dir: str = 'careerops/generated'
    uploads_dir: str = 'careerops/uploads'
    demo_full_name: str = 'CareerOps User'
    demo_preferred_name: str = 'Builder'
    demo_email: str | None = None
    demo_phone: str | None = None
    demo_home_location: str = 'Seattle, WA'
    demo_linkedin_url: str | None = None
    demo_github_url: str | None = None

    @property
    def uploads_path(self) -> Path:
        p = Path(self.uploads_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def generated_path(self) -> Path:
        p = Path(self.generated_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
