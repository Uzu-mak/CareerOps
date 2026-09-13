# CareerOps Autopilot v3.0.1 — Build & Validation Report

## Scope audited

This build was audited against the full conversation requirements: continuous discovery, location/role policy, broad-market and priority-company coverage, LinkedIn/Indeed alert ingestion, notifications, living candidate evidence, master-resume tailoring, application Q&A, portal/account handling, Playwright application automation, human review, application tracking/proof, and AWS-ready 24/7 architecture.

## Implemented

- Candidate profile with location/work arrangement/role/salary/legal policy.
- Master resume upload and job-specific tailoring.
- LinkedIn, GitHub and additional portfolio/project/application links.
- Build Journal -> structured CandidateEvidence with explicit metric provenance.
- Greenhouse, Lever, Ashby, generic public page, and rendered public company-career adapters.
- Starter company watchlist: OpenAI, Palantir, SpaceX, Microsoft, Amazon, Boeing, Meta, Salesforce.
- Adzuna broad-market adapter (credentials required for live calls).
- USAJOBS adapter (credentials required for live calls).
- LinkedIn/Indeed alert-email ingestion through manual API/UI or optional IMAP polling; no logged-in scraping.
- Cross-source dedupe that prefers direct/official records over aggregator duplicates.
- 15-minute Watchtower with per-source intervals and manual force-scan.
- Explainable fit engine and hard-policy gates.
- In-app/SES/Slack/Discord/Telegram notification service.
- Opt-in background Autopilot with threshold and daily cap.
- Tailored resume/cover-letter/Q&A/outreach package generation with truth guard.
- Playwright browser agent with low-risk field fill, link fill, file upload, bounded multi-step navigation, sensitive-field/authentication pauses, and employer-confirmation detection.
- Portal account planning for direct ATS, Workday, Google/OAuth and unknown portals; visible account gates can be started and email prefilled, while passwords/MFA/email verification remain human-owned.
- Clickable per-application review items with explicit approved answers and notes.
- Applications CRM with confirmation proof, final URL, screenshot, verification timestamp and outcome tracking.
- AWS Terraform topology for ECS API/discovery/browser services, RDS, S3, SQS+DLQ, EventBridge, Secrets Manager/KMS, CloudWatch, Bedrock and SES.

## Validation performed in this build environment

The final verification pass runs:

1. Python bytecode compilation of `careerops` and `tests`.
2. Full pytest suite.
3. FastAPI TestClient route smoke test for dashboard/profile/journal/applications/notifications/provider APIs.
4. Fresh-database source-seed verification.
5. Static project audit (`scripts/project_audit.py`) mapping required capabilities to concrete files/routes/config.
6. ZIP integrity check after packaging.
7. Second clean test pass after documentation/final code changes.

Provider adapters are covered by unit/contract tests for mapping/parsing and source-matrix behavior. Submission verification is regression-tested so a click without acknowledgement cannot become a confirmed application.

## External validation boundaries

These are not defects hidden by the report; they require credentials, a live third-party account, or user authorization and therefore cannot be truthfully validated inside this build environment:

- Live Adzuna calls require `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`.
- Live USAJOBS calls require `USAJOBS_API_KEY` / `USAJOBS_USER_AGENT`.
- Automatic LinkedIn/Indeed alert ingestion requires a mailbox/IMAP credential; CareerOps does not log in and scrape those sites.
- SES, Slack, Discord and Telegram delivery require user-owned channel credentials.
- Employer application portals change DOM/auth flows. CareerOps can attempt public forms, but password ownership, email verification, OAuth, CAPTCHA and MFA remain human takeover steps.
- The repository does not claim every employer portal is guaranteed unattended. It records failures/review rather than falsely claiming submission.
- AWS infrastructure is defined but was not provisioned because this environment has no authorization to create billable resources in the user's AWS account.
- The Terraform CLI is not installed in this build environment, so the HCL received static review but **not** `terraform validate`. Run Terraform validation in an environment with Terraform installed before provisioning.
- Local Watchtower is continuous only while the laptop and Docker are running. 24/7 operation requires AWS deployment.

## Correctness rules enforced

- LLMs do not invent work-authorization/legal answers.
- Unsupported impact metrics are blocked by the truth guard.
- Journal numeric metrics are verified only when explicitly entered by the user.
- CAPTCHA/MFA is never bypassed.
- Raw portal passwords are not stored in PostgreSQL.
- A submit-button click alone is not proof of application.
- `CONFIRMED` requires employer acknowledgement evidence.
- Manual submitted status remains `UNVERIFIED` without browser proof.
- Cross-source duplicates prefer direct/official job URLs.

See `FEATURE_MATRIX.md` for the requirement-by-requirement status table.

## Final verification results

Final in-container verification completed after the v3.0.1 integration changes:

```text
Python compileall:                  PASS
pytest:                             26 passed
FastAPI route smoke test:           PASS (8/8 routes returned HTTP 200)
Fresh source seed matrix:           PASS (12/12 expected sources present)
Docker Compose YAML parse:          PASS
Static requirement/project audit:   PASS (42/42 checks)
Stale demo-sidebar wording audit:   PASS
```

A second clean verification pass is performed on the packaged/extracted ZIP before delivery. See `VALIDATION_CHECKLIST.md` for the repeat-pass record.

## Packaged-build repeat verification

The generated ZIP was extracted into a separate clean directory and the verification suite was repeated against the extracted copy:

```text
ZIP integrity:                        PASS
Python compileall:                   PASS
pytest:                              26 passed
Static project audit:                42/42 passed
FastAPI packaged route smoke:         8/8 HTTP 200
Fresh packaged source matrix:        12/12 expected sources
```
