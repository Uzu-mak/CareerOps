# CareerOps Autopilot v3.0.1

CareerOps is a personal AI job-search control tower built around **Discover → Evaluate → Prepare → Apply → Verify → Report**. It combines deterministic policy rules, live job-source adapters, a living candidate-evidence store, document generation, Playwright browser automation, application proof, notifications, and AWS-ready workers.

## What v3.0.1 does

### Discover

- Greenhouse, Lever, and Ashby public ATS feeds.
- Generic public job pages.
- Public company-career watcher with schema.org `JobPosting` extraction and a bounded Chromium-rendered fallback for JavaScript career pages.
- Starter priority watchlist: OpenAI, Palantir, SpaceX, Microsoft, Amazon, Boeing, Meta, Salesforce.
- Adzuna broad-market search driven by your configured role families and locations (`ADZUNA_APP_ID` + `ADZUNA_APP_KEY` required).
- USAJOBS official search API driven by your role/location/radius policy (`USAJOBS_API_KEY` + `USAJOBS_USER_AGENT` required).
- LinkedIn and Indeed discovery through job-alert email ingestion instead of logged-in scraping. Alerts can be pasted into CareerOps or polled automatically through IMAP.
- Cross-source semantic deduplication. Direct/official records are preferred over aggregator duplicates.
- Watchtower wakes every 15 minutes locally; each source can also have its own scan interval.

CareerOps does **not** claim to crawl literally every job site on the internet. It combines supported ATS feeds, configured company career sites, broad-market APIs, and alert-email ingestion. Public sites that block automated access are reported as source errors; CareerOps does not bypass anti-bot controls.

### Evaluate

Your Candidate Profile controls:

- home location and preferred job locations
- search radius (stored; exact geocoding is not faked in local mode)
- remote / hybrid / onsite preferences
- role families
- skills
- salary floor and target
- user-verified work authorization and sponsorship answers

The policy layer applies hard constraints before expensive semantic work. The Fit Agent produces an explainable score, matched/partial/gap skills, A+/A/B+/B/C priority, and `APPLY / REVIEW / SKIP` recommendation.

### Living candidate evidence

CareerOps is not limited to one static resume.

- Upload a **Master Resume** (PDF/DOCX/TXT) as the baseline.
- Add LinkedIn, GitHub, portfolio, live demo, repository, publication, and other application links.
- Use **Build Journal** (`/journal`) to record what you built, problem solved, architecture/decisions, tradeoffs, time spent, impact, explicit measured metrics, skills, links, and lessons.
- Every journal entry is projected into `CandidateEvidence` and becomes retrievable for fit scoring, resume tailoring, cover letters, application answers, outreach, and interview stories.
- Numeric impact is treated as verified only when the user explicitly entered it; CareerOps does not invent metrics.

### Prepare and apply

For each job, CareerOps can:

- tailor a resume from the master resume + verified CandidateEvidence
- generate a grounded cover letter
- prepare application Q&A
- draft outreach
- autofill identity, LinkedIn, GitHub, portfolio/project links
- upload the tailored resume and cover letter where supported
- traverse a bounded multi-step application flow with Playwright
- attempt final submission when Autopilot is enabled and all gates pass

Background Autopilot is opt-in. It requires: hard constraints not `FAIL`, recommendation `APPLY`, fit above your configured threshold, a master resume, verified legal/work-authorization values, a live application URL, and remaining daily application budget.

### Account/authentication boundary

CareerOps has a Portal Account Agent for direct ATS flows, Google/OAuth, Workday company-scoped accounts, and unknown portals. It can detect visible account creation/sign-in gates, click a public **Create Account / Sign Up** action, and prefill your verified email.

It intentionally **does not store raw portal passwords**, bypass CAPTCHA/MFA, or invent one-time verification codes. Password creation, email verification, OAuth ownership, MFA, CAPTCHA, and other authentication challenges are human/session takeover boundaries. Real employer portals change frequently, so live portal behavior must be validated against the current page before treating a portal as unattended.

### Human review

Sensitive or ambiguous questions pause instead of being guessed. Review items are clickable on the job page. You can see why CareerOps paused, view any safe configured suggestion, enter the exact answer you approve, add notes, save it for that application, and retry.

Examples of review boundaries include disability/EEO/veteran questions, criminal-history questions, ambiguous sponsorship language, legal attestations, export-control/clearance questions, CAPTCHA, MFA, and account verification.

### Applications + proof

`/applications` is the application CRM. CareerOps tracks prepared, review, submitted, interview, offer, rejected, and withdrawn states.

A browser click is **not** counted as a successful application. `CONFIRMED` is only shown when CareerOps detects an employer acknowledgement such as “application submitted” or “thank you for applying.” When available it stores:

- confirmation phrase/excerpt
- final URL
- verification timestamp
- confirmation screenshot
- portal and job

A manual “submitted” status without browser proof is shown as **UNVERIFIED**.

### Notifications

`/notifications` supports:

- in-app notifications
- Amazon SES email
- Slack webhook
- Discord webhook
- Telegram bot

Events include new matching job, high-fit/A+ opportunity, human review required, confirmed submission, and failure. Minimum and urgent fit thresholds are configurable.

LinkedIn/Indeed alert emails can be ingested manually or through optional IMAP polling.

## Windows + Docker quick start

From the extracted project folder:

```bat
copy .env.example .env
docker compose up --build
```

Open:

- Dashboard: `http://localhost:8001`
- Candidate Profile: `http://localhost:8001/profile`
- Build Journal: `http://localhost:8001/journal`
- Applications: `http://localhost:8001/applications`
- Notifications: `http://localhost:8001/notifications`
- API docs: `http://localhost:8001/docs`

The local stack is:

```text
Windows localhost:8001 -> CareerOps app:8000
Windows localhost:5433 -> PostgreSQL:5432
app/watchtower internal DB -> db:5432
```

Do not use `http://0.0.0.0:8000` in your browser; that is the container bind address.

### First-run checklist

1. Upload your master resume on `/profile`.
2. Add LinkedIn, GitHub and any portfolio/project/application links.
3. Configure role families, preferred locations, work arrangement, salary policy, and skills.
4. Explicitly verify work-authorization/sponsorship values.
5. Add Build Journal evidence for recent work not represented on the base resume.
6. Configure notifications on `/notifications`.
7. Add optional provider credentials to `.env` for Adzuna, USAJOBS, IMAP and external notification channels.
8. Click **Scan jobs now** or run `enable_live_sources.bat` to force a scan.
9. Enable Autopilot only after reviewing the fit threshold and daily cap.

## Optional provider configuration

```text
# Broad market
ADZUNA_APP_ID=
ADZUNA_APP_KEY=

# Federal jobs
USAJOBS_API_KEY=
USAJOBS_USER_AGENT=your-email@example.com

# LinkedIn / Indeed alert inbox
JOB_ALERT_IMAP_HOST=
JOB_ALERT_IMAP_PORT=993
JOB_ALERT_IMAP_USER=
JOB_ALERT_IMAP_PASSWORD=
JOB_ALERT_IMAP_FOLDER=INBOX

# Notifications
SES_FROM_EMAIL=
SES_TO_EMAIL=
SLACK_WEBHOOK_URL=
DISCORD_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Credentialed providers remain visible as `SETUP` until configured. The public ATS/company sources still work without those credentials.

## Local Watchtower

Docker Compose runs three services:

```text
db          PostgreSQL canonical store
app         FastAPI UI/API + local Playwright actions
watchtower  discovery loop; wakes every 15 minutes
```

Useful commands:

```bat
docker compose ps
docker compose logs -f app
docker compose logs -f watchtower
enable_live_sources.bat
validate_careerops.bat
docker compose down
```

Do **not** use `docker compose down -v` during upgrades unless you intentionally want to delete your PostgreSQL data.

## AWS architecture

The Terraform configuration defines the production topology:

- ECS/Fargate FastAPI service
- separate discovery worker
- separate application/browser worker
- RDS PostgreSQL
- S3 artifacts with KMS encryption
- SQS discovery/application queues + DLQs
- EventBridge Scheduler every 15 minutes + daily report trigger
- Secrets Manager + KMS
- CloudWatch logs
- Bedrock permissions
- SES permissions
- ALB

For a production internet deployment, add ACM/HTTPS and a custom domain. AWS resources are not provisioned by this repository automatically; an authenticated AWS account and billing approval are required.

## Validation

Run locally:

```bat
validate_careerops.bat
```

Or directly:

```bash
python -m compileall -q careerops tests
pytest -q
python scripts/project_audit.py
```

See `BUILD_REPORT.md` and `FEATURE_MATRIX.md` for the exact verification result and explicit external-validation boundaries.


## v3.0.1 PostgreSQL startup hotfix

A PostgreSQL-only startup defect in v3.0 used `VARCHAR(40)` for `SourceConfig.last_status` even though provider setup/error messages can exceed 40 characters. v3.0.1 changes this field to `TEXT` and runs an idempotent PostgreSQL compatibility widening step before source seeding. It also widens legacy `token_or_url`, source name, and source type columns where needed, preserving existing rows instead of requiring volume deletion.
