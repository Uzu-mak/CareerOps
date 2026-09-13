from __future__ import annotations
from careerops.db.models import CandidateProfile, JobPosting
from careerops.services.search_policy import evaluate_job_location

MANUAL_TOPICS = ['race','ethnicity','gender','sex','disability','veteran','criminal','felony','religion','sexual orientation','captcha','attest','certify under penalty']


def evaluate_hard_constraints(profile: CandidateProfile, job: JobPosting) -> dict:
    out: dict[str, dict] = {}

    # Salary
    if profile.minimum_salary and job.salary_max:
        out['salary'] = {'status': 'PASS' if job.salary_max >= profile.minimum_salary else 'FAIL', 'detail': f'job max ${job.salary_max:,}; floor ${profile.minimum_salary:,}'}
    else:
        out['salary'] = {'status': 'REVIEW', 'detail': 'salary range or personal floor missing'}

    # Workplace mode + geographic location
    w = (job.workplace_type or '').lower()
    allowed = True
    if w == 'remote': allowed = profile.remote_allowed
    elif w == 'hybrid': allowed = profile.hybrid_allowed
    elif w == 'onsite': allowed = profile.onsite_allowed
    out['workplace'] = {'status': 'PASS' if allowed else 'FAIL', 'detail': w or 'unspecified'}
    out['location'] = evaluate_job_location(profile, job.location, job.workplace_type)

    # Work authorization: never infer if unverified.
    if profile.legal_answers_verified_at is None or profile.authorized_to_work_us is None:
        out['work_authorization'] = {'status': 'REVIEW', 'detail': 'candidate legal answers have not been user-verified'}
    elif not profile.authorized_to_work_us:
        out['work_authorization'] = {'status': 'FAIL', 'detail': 'candidate profile says not currently authorized'}
    else:
        out['work_authorization'] = {'status': 'PASS', 'detail': 'user-verified current authorization'}

    if job.sponsorship_policy == 'unavailable':
        if profile.legal_answers_verified_at is None or profile.requires_future_sponsorship is None:
            out['sponsorship'] = {'status': 'REVIEW', 'detail': 'job says sponsorship unavailable; candidate future need not verified'}
        elif profile.requires_future_sponsorship:
            out['sponsorship'] = {'status': 'FAIL', 'detail': 'job says no future sponsorship; verified profile says future sponsorship required'}
        else:
            out['sponsorship'] = {'status': 'PASS', 'detail': 'no future sponsorship need in verified profile'}
    elif job.sponsorship_policy == 'available':
        out['sponsorship'] = {'status': 'PASS', 'detail': 'posting indicates sponsorship is available'}
    else:
        out['sponsorship'] = {'status': 'REVIEW', 'detail': 'job sponsorship policy is unknown'}

    if job.clearance_required:
        out['clearance/export'] = {'status': 'REVIEW', 'detail': 'clearance/export-control language requires human verification'}
    else:
        out['clearance/export'] = {'status': 'PASS', 'detail': 'no explicit clearance requirement detected'}

    if job.required_years is None:
        out['experience'] = {'status': 'REVIEW', 'detail': 'required years not explicit'}
    elif profile.years_professional_software >= job.required_years:
        out['experience'] = {'status': 'PASS', 'detail': f'{profile.years_professional_software:g} professional years vs {job.required_years:g} required'}
    elif profile.years_hands_on_software >= job.required_years:
        out['experience'] = {'status': 'REVIEW', 'detail': f'professional years below threshold; {profile.years_hands_on_software:g} hands-on years may be relevant'}
    else:
        out['experience'] = {'status': 'FAIL', 'detail': f'{profile.years_professional_software:g} professional years vs {job.required_years:g} required'}

    statuses = [x['status'] for x in out.values()]
    overall = 'FAIL' if 'FAIL' in statuses else ('REVIEW' if 'REVIEW' in statuses else 'PASS')
    return {'overall': overall, 'items': out}


def classify_application_question(question: str) -> str:
    low = question.lower()
    if any(t in low for t in MANUAL_TOPICS): return 'MANUAL'
    if any(t in low for t in ['authorized to work','legally authorized','sponsor','sponsorship','immigration','work authorization']): return 'VERIFIED_LEGAL'
    if any(t in low for t in ['desired salary','salary expectation','compensation expectation']): return 'SALARY_RULE'
    if any(t in low for t in ['first name','last name','email','phone','linkedin','github','location','city']): return 'PROFILE'
    return 'GENERATIVE_REVIEW'
