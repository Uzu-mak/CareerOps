# CareerOps v3.0.1 — Validation Checklist

## Product requirements

- [x] Automatic Watchtower scanning
- [x] Preferred-location / work-arrangement filtering
- [x] Role-family filtering
- [x] Greenhouse / Lever / Ashby discovery
- [x] Public company-career watcher with JavaScript render fallback
- [x] Priority sources: OpenAI, Palantir, SpaceX, Microsoft, Amazon, Boeing, Meta, Salesforce
- [x] Adzuna broad-market integration (credential-gated)
- [x] USAJOBS integration (credential-gated)
- [x] LinkedIn alert-email ingestion without logged-in scraping
- [x] Indeed alert-email ingestion without logged-in scraping
- [x] IMAP automatic alert polling (credential-gated)
- [x] Cross-source deduplication
- [x] Immediate manual scan + 15-minute recurring Watchtower
- [x] Explainable fit scoring and hard constraints
- [x] Master resume baseline + per-job tailoring
- [x] LinkedIn / GitHub / portfolio / project/application links
- [x] Daily Build Journal and living CandidateEvidence
- [x] Explicit metric provenance / no invented impact numbers
- [x] Cover letter / Q&A / outreach generation
- [x] Opt-in background auto-apply threshold + daily cap
- [x] Playwright safe-field fill, resume/cover-letter upload
- [x] Bounded multi-step Continue/Next application traversal
- [x] Portal account planning + assisted account-gate handling
- [x] No raw password storage
- [x] No CAPTCHA/MFA bypass
- [x] Clickable human-review fields and application-scoped approved answers
- [x] Dedicated Applications section
- [x] Employer-side submission confirmation required for CONFIRMED
- [x] Confirmation final URL / excerpt / timestamp / screenshot where available
- [x] Interview / offer / rejection / withdrawal tracking
- [x] In-app notifications
- [x] SES email notifications (credential-gated)
- [x] Slack / Discord / Telegram notifications (credential-gated)
- [x] New-match / high-fit / human-review / submitted / failed event policies
- [x] AWS ECS API + discovery worker + browser worker design
- [x] RDS / S3 / SQS+DLQ / EventBridge / KMS / Secrets Manager / CloudWatch / Bedrock / SES Terraform

## Verification pass 1

- [x] `python -m compileall -q careerops tests scripts`
- [x] `pytest -q` → 26 passed
- [x] FastAPI smoke routes → 8/8 HTTP 200
- [x] Fresh source seed matrix → 12/12 expected providers/sources
- [x] Docker Compose YAML parse
- [x] `python scripts/project_audit.py` → 42/42

## Explicit live-system boundaries

- [ ] Adzuna live request — requires the user's API credentials
- [ ] USAJOBS live request — requires the user's API credentials
- [ ] LinkedIn/Indeed automatic mailbox polling — requires mailbox credentials
- [ ] SES/Slack/Discord/Telegram live delivery — requires user-owned channel credentials
- [ ] Every employer ATS/account flow — portal-specific live validation is required because external forms/authentication change
- [ ] AWS deployment — requires the user's authorized AWS account and may incur charges
- [ ] `terraform validate` — Terraform CLI is not installed in this build environment

Unchecked items above are external authorization/third-party validation requirements, not silently claimed as completed.

## Verification pass 2 — clean packaged extraction

The final ZIP was extracted into a clean directory and revalidated independently:

- [x] ZIP integrity check → no compressed-data errors
- [x] Python compileall → PASS
- [x] pytest → 26 passed
- [x] static project audit → 42/42 passed
- [x] FastAPI packaged smoke routes → 8/8 HTTP 200
- [x] packaged fresh-database source seed matrix → 12/12 expected sources
