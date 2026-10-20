# CareerOps Autopilot

[![tests](https://github.com/Uzu-mak/CareerOps/actions/workflows/tests.yml/badge.svg)](https://github.com/Uzu-mak/CareerOps/actions/workflows/tests.yml)

CareerOps is a personal AI job-search control tower built around **Discover → Evaluate → Prepare → Apply → Verify → Report**. It combines deterministic policy rules, live job-source adapters, a living candidate-evidence store, document generation, Playwright browser automation, application proof, notifications, and AWS-ready workers.

## What it does

### Discover

- Greenhouse, Lever, and Ashby public ATS feeds.
- **Small companies and startups:** the monthly Hacker News "Who is hiring?" thread (public Algolia API, no key) and Remotive's remote-jobs API (no key; called at most 4 times a day as Remotive asks, with links back to Remotive).
- **Automatic company discovery:** when any source links to a company's Greenhouse, Lever or Ashby board, CareerOps adds that whole board as a source (up to 15 per scan, `AUTO_DISCOVER_BOARDS=false` to turn off). Those are also the boards the browser agent can apply to.
- Generic public job pages.
- Public company-career watcher with schema.org `JobPosting` extraction and a bounded Chromium-rendered fallback for JavaScript career pages.
- Starter priority watchlist: OpenAI, Palantir, SpaceX, Microsoft, Amazon, Boeing, Meta, Salesforce.
- Adzuna broad-market search driven by your configured role families and locations (`ADZUNA_APP_ID` + `ADZUNA_APP_KEY` required).
- USAJOBS official search API driven by your role/location/radius policy (`USAJOBS_API_KEY` + `USAJOBS_USER_AGENT` required).
- LinkedIn and Indeed discovery through job-alert email ingestion instead of logged-in scraping. Alerts can be pasted into CareerOps or polled automatically through IMAP.
- Cross-source deduplication: the same company + title + location from two sources is one opportunity, and direct/official records win over aggregator copies.
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

The policy layer applies hard constraints first. The Fit Agent produces an explainable score, matched/partial/gap skills, A+/A/B+/B/C priority, and an `APPLY / REVIEW / SKIP` recommendation.

**Job-description extraction.** Rules always run: a fixed skill vocabulary, explicit "N+ years", sponsorship and clearance phrases. With `LLM_PROVIDER=openai` (or `bedrock`) a model also extracts skills outside that vocabulary, required vs preferred skills, years, sponsorship policy and work arrangement as JSON. The output is validated (types, allowed values, length limits), the posting is passed to the model as untrusted data, explicit rule matches win over the model, and results are cached per posting. If the model is unavailable, CareerOps falls back to rules alone.

### Living candidate evidence

CareerOps is not limited to one static resume.

- Upload a **Master Resume** (PDF/DOCX/TXT) as the baseline.
- Add LinkedIn, GitHub, portfolio, live demo, repository, publication, and other application links.
- Use **Build Journal** (`/journal`) to record what you built, problem solved, architecture/decisions, tradeoffs, time spent, impact, explicit measured metrics, skills, links, and lessons.
- Every journal entry is projected into `CandidateEvidence` and becomes retrievable for fit scoring, resume tailoring, cover letters, application answers, outreach, and interview stories.
- Numeric impact is treated as verified only when the user explicitly entered it; CareerOps does not invent metrics.

### Prepare

For each job, CareerOps tailors a resume from the master resume plus verified CandidateEvidence, writes a cover letter, prepares application Q&A and drafts outreach. These documents are assembled from your evidence with templates, not free-written by a model.

Every generated claim goes through the **truth guard**. A bullet with a number or claim that your evidence does not support is withheld from the document, and the withheld lines are listed on the artifact. Autopilot will not submit an application whose documents had claims withheld; it sends it to review instead.

### Apply: the browser agent

`careerops/agents/browser.py` drives Chromium with Playwright:

1. **Open the form.** Lever links go to `/apply`, Ashby links to `/application`, a Greenhouse board embedded in a company careers page is opened directly, and otherwise the agent clicks "Apply for this job" / "Apply now" (never "Apply with LinkedIn").
2. **Scan every frame.** `form_scan.js` lists visible inputs, selects, radio and checkbox groups, custom dropdowns (React-Select style comboboxes), Yes/No button pairs and file inputs, with each field's question text and whether it is required.
3. **Plan the answers.** `apply_plan.py` (pure Python, unit-tested) decides each field from, in order: answers you approved for this application; your profile (name, email, phone, links, location); your *verified* work-authorization and sponsorship answers; your EEO preference; and the answer bank.
4. **Fill.** The tailored resume is uploaded first, because Lever and Ashby parse it and overwrite fields; then everything else is filled, and the page is scanned again so follow-up questions that appear after an answer are handled too.
5. **Stop or submit.** If a required question is still unanswered, the run stops and reports that exact question. Otherwise it clicks through Next/Continue steps and Submit, and waits up to 20 seconds for a confirmation message that was not on the page before.

What it will not do:

- **CAPTCHA / MFA / accounts.** A visible CAPTCHA challenge, a verification-code prompt or a sign-in/create-account wall pauses the run. The invisible reCAPTCHA badge most ATS pages carry is not treated as a blocker. Raw portal passwords are never stored.
- **Legal and EEO answers.** Work authorization and sponsorship are answered only from values you verified on `/profile`. Voluntary EEO questions (gender, race, veteran, disability) are left blank when optional; if you set *Voluntary EEO questions → "decline to self-identify"* on `/profile`, the agent picks the decline option instead. Criminal history, attestations, citizenship, clearance and salary are never answered without your explicit answer for that application.

### Human review and the answer bank

When a run pauses, the job page lists the exact questions it could not answer. Enter the answer you approve and run Apply again; the agent fills it and continues.

Answers you approve are also kept as an **answer bank**. The next application that asks the same question ("How did you hear about this job?", "Are you at least 18?") reuses your answer, so the review queue shrinks over time. Sensitive answers (EEO, legal, salary, citizenship, clearance) and motivation answers that name an employer are never reused across applications.

Background Autopilot is opt-in. It requires: hard constraints not `FAIL`, recommendation `APPLY`, fit above your configured threshold, a master resume, verified work-authorization answers, a passing truth guard, a live application URL, and remaining daily application budget.

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

Start Docker Desktop, then from the project folder:

```bat
copy .env.example .env
notepad .env
start_careerops.bat
```

`start_careerops.bat` builds and starts everything in the background, waits until CareerOps answers, and opens it in your browser. `stop_careerops.bat` stops it; `docker compose logs -f app` shows the log.

The log line `Uvicorn running on http://0.0.0.0:8000` is the address *inside* the container; open `http://localhost:8001` instead.

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

## Hosting on Google Cloud

[`docs/deploy-gcp.md`](docs/deploy-gcp.md) deploys CareerOps to Cloud Run:

- the app runs as a Cloud Run service, with Chromium for the apply agent;
- discovery runs as a Cloud Run job triggered every 15 minutes by Cloud Scheduler;
- files live in a Cloud Storage bucket mounted at `/data`;
- PostgreSQL is Neon's free tier or Cloud SQL;
- keys are kept in Secret Manager.

**Login.** A hosted copy is protected by Google sign-in limited to the accounts in `ALLOWED_EMAILS` (`AUTH_MODE=google`). On your own machine, `AUTH_MODE=none` with `ENVIRONMENT=local` needs no login. CareerOps refuses to start with no login anywhere else, so a misconfigured deployment fails closed instead of exposing your resume and work-authorization answers. Scripts can call the API with `Authorization: Bearer <API_TOKEN>`.

Vercel is not a good fit: the apply agent needs a real Chromium and runs for minutes, discovery is a scheduled worker, and documents need persistent storage.

## AWS architecture (alternative)

The Terraform in `infra/terraform` defines an AWS topology:

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

The test suite includes end-to-end browser runs against local fixtures that reproduce Lever, Greenhouse (embedded from a second origin, with React-Select dropdowns and a location autocomplete) and Ashby forms, plus a CAPTCHA challenge and an account wall (`tests/test_browser_ats.py`). They need Playwright's Chromium (`python -m playwright install chromium`). GitHub Actions runs the suite on every push.

Live employer portals change their markup. When a run pauses with *application form not detected* or *submission confirmation not detected*, the screenshot saved with the application shows where it stopped.

See `FEATURE_MATRIX.md` for what is implemented, what needs credentials, and what is intentionally out of scope.


## Changelog

- **Small-company discovery.** Hacker News "Who is hiring?" and Remotive sources, and automatic addition of Greenhouse/Lever/Ashby boards linked from any source.
- **Interface rebuild.** New design matching the Digital Twin; Jobs page with search, filters, sorting and pagination (server-side, one query); job tabs with typed answer inputs (Yes/No, salary, free text), dry run and document viewer; tag inputs with autocomplete for skills, roles and locations; skills auto-filled from the uploaded resume; Sources & automation page with per-source switches and frequency; server-side batch analysis; setup checklist; mobile layout.
- **Hosting.** Google sign-in for hosted instances (fails closed without it), Cloud Run guide, `$PORT` support, `.dockerignore` so `.env` is never baked into images, Compose reads `.env` directly.
- **Browser agent rebuild.** Frame-aware form scanning, answer planning, React-Select/autocomplete/Yes-No button support, Lever/Ashby/Greenhouse-embed entry, required-question pauses with exact question text, answer bank, EEO decline preference, visible-only CAPTCHA detection, and confirmation that must appear after submit.
- **LLM job-description extraction** (OpenAI or Bedrock), validated and merged with rules.
- **Truth guard on documents.** Unsupported claims are withheld from resumes and cover letters, and block unattended submission.
- **3.0.1.** `SourceConfig.last_status` is `TEXT` on PostgreSQL, with an idempotent widening step for existing volumes.
