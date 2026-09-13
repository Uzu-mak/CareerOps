# CareerOps v3.0.1 — Fulfillment Matrix

This matrix maps the requested CareerOps behavior to the implementation in this build.

| Capability | Status | Implementation / boundary |
|---|---|---|
| Candidate profile + location/radius/work arrangement | ✅ | Profile page + deterministic location policy |
| Role-family filtering | ✅ | Discovery pre-filter rejects clearly unrelated titles before fit scoring |
| Salary + verified work-authorization policy | ✅ | Deterministic policy engine; LLM cannot invent legal answers |
| Master resume baseline | ✅ | PDF/DOCX/TXT upload; resume text + original persisted |
| Tailor resume per job | ✅ | Resume Agent uses master resume + verified CandidateEvidence |
| Cover letter / Q&A / outreach | ✅ | Generated per job with truth guard |
| LinkedIn + GitHub + portfolio/project/application links | ✅ | First-class profile fields + additional clickable links; browser autofill support |
| Daily Build Journal / living career memory | ✅ | Entries capture build, problem, architecture, tradeoffs, time, impact, explicit metrics, skills, links, lessons and project into CandidateEvidence |
| Greenhouse discovery | ✅ | Public ATS adapter |
| Lever discovery | ✅ | Public ATS adapter |
| Ashby discovery | ✅ | Public ATS adapter |
| Generic public job page | ✅ | Public page adapter |
| Official company career watch | ✅ | Bounded public crawler + JobPosting JSON-LD extraction + Chromium-rendered fallback for JavaScript public career pages; starter watchlist includes SpaceX, Microsoft, Amazon, Boeing, Meta, Salesforce |
| Adzuna broad-market / smaller-company discovery | ✅ code / 🔑 key required | Profile-driven keyword + location search; requires ADZUNA_APP_ID / ADZUNA_APP_KEY |
| USAJOBS search | ✅ code / 🔑 key required | Official search API; requires USAJOBS_API_KEY / USAJOBS_USER_AGENT |
| LinkedIn job discovery | ✅ via alert inbox | No logged-in scraping. Imports LinkedIn job-alert emails via IMAP or alert-ingest endpoint |
| Indeed job discovery | ✅ via alert inbox | No logged-in scraping. Imports Indeed job-alert emails via IMAP or alert-ingest endpoint |
| IMAP automatic alert polling | ✅ code / 🔑 mailbox credentials required | Watchtower imports unseen LinkedIn/Indeed alert messages every cycle |
| Cross-source deduplication | ✅ | Same company/title/location collapses across providers and prefers official/direct source URLs |
| Freshness / source status | ✅ | first_seen / last_seen / last_verified + SourceConfig scan status/count |
| 15-minute Watchtower | ✅ | Local Docker wake interval 900s; per-source interval honored; AWS EventBridge rate(15 minutes) |
| Immediate manual scan | ✅ | Dashboard “Scan jobs now” forces all enabled sources |
| Explainable fit scoring | ✅ | Hard constraints + component score + match/partial/gap + APPLY/REVIEW/SKIP |
| In-app notifications | ✅ | Notification center + unread events |
| Email notifications | ✅ code / 🔑 SES required | Amazon SES delivery |
| Slack / Discord notifications | ✅ code / 🔑 webhook required | Configurable webhooks |
| Telegram notifications | ✅ code / 🔑 bot credentials required | Bot API delivery |
| New-match / high-fit / review / submitted / failed alerts | ✅ | Notification policy with minimum and urgent fit thresholds |
| Recommended jobs queue | ✅ | Dashboard opportunity queue |
| Background auto-apply | ✅ opt-in | Min fit + daily cap + hard-constraint + verified-profile gates |
| Tailored resume used for application | ✅ | Browser gets generated tailored resume path |
| Cover letter upload where field exists | ✅ | Browser agent tries labeled cover-letter file controls and bounded multi-step Continue/Next flows |
| Autofill identity / LinkedIn / GitHub / portfolio / project links | ✅ | Browser agent field matching |
| Portal account planning | ✅ | Direct ATS, Google/OAuth, Workday tenant, unknown portal plans |
| Account-gated portal assistance | ✅ assisted | Browser may enter Create Account/Sign Up, prefill verified email, then pauses for password ownership/email verification/MFA. Raw passwords are not stored in PostgreSQL |
| CAPTCHA / MFA bypass | ❌ intentionally not implemented | Human takeover boundary |
| Sensitive EEO/disability/veteran/legal inference | ❌ intentionally not implemented | User must explicitly answer; answers are application-scoped and clickable in UI |
| Clickable human-review fields | ✅ | Expandable fields show pause reason, suggestion, exact answer + notes, save/resume path |
| Applications section | ✅ | Dedicated tracker with portal, status, outcomes, proof state |
| Submission confirmation | ✅ | Only CONFIRMED when employer acknowledgement is detected after submit |
| Submission proof | ✅ | Stores final URL, confirmation term/excerpt, timestamp, screenshot when available |
| Manual “submitted” counted as confirmed | ❌ intentionally blocked | Displays UNVERIFIED without browser evidence |
| Interview / offer / rejection / withdrawal tracking | ✅ | Application outcome controls |
| PostgreSQL canonical store | ✅ | Jobs, analyses, evidence, applications, notifications, settings |
| S3 artifact path on AWS | ✅ infrastructure | Terraform provisions encrypted artifact bucket |
| SQS queues + DLQs | ✅ infrastructure | Discovery and application/browser queues |
| Separate AWS browser worker | ✅ infrastructure | ECS/Fargate application worker consumes application queue |
| EventBridge 15-minute scans | ✅ infrastructure | Scheduler sends discovery messages to SQS |
| Bedrock integration | ✅ code / 🔑 AWS model access required | Semantic extraction/drafting; deterministic policy remains authoritative |
| CloudWatch | ✅ infrastructure | ECS log group and per-service streams |
| Secrets Manager + KMS | ✅ infrastructure | Runtime secrets stored in KMS-encrypted Secrets Manager secret; S3/RDS encrypted |
| Local Docker execution | ✅ | PostgreSQL + API + Watchtower |
| Continuous operation with laptop off | ✅ after AWS deploy | Local scans stop if Docker/laptop stops; AWS workers continue independently |

## External validation boundary

The repository validates logic, data flow, source mappings, UI routes, policy behavior, deduplication, notification policy, account planning, and submission-proof rules without using private provider credentials. Live Adzuna/USAJOBS calls require your API credentials. Email/Slack/Discord/Telegram delivery requires your channel credentials. Real employer application portals must still be validated against their current forms/authentication behavior; CareerOps intentionally pauses rather than bypassing CAPTCHA, MFA, email verification, or sensitive legal questions.
