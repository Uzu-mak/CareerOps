from __future__ import annotations
from careerops.db.models import CandidateProfile, JobPosting
from careerops.agents.policy import classify_application_question


def answer_question(profile: CandidateProfile, job: JobPosting, question: str) -> dict:
    kind = classify_application_question(question)
    low = question.lower()
    if kind == 'MANUAL':
        return {'mode':'MANUAL','answer':None,'reason':'Sensitive disclosure, CAPTCHA, or legal attestation requires the user.'}
    if kind == 'VERIFIED_LEGAL':
        if profile.legal_answers_verified_at is None:
            return {'mode':'REVIEW','answer':None,'reason':'Work-authorization answers are not user-verified.'}
        if 'authorized' in low:
            return {'mode':'AUTO_VERIFIED','answer':'Yes' if profile.authorized_to_work_us else 'No','reason':'From user-verified candidate profile.'}
        if 'future' in low or 'sponsor' in low:
            value = profile.requires_future_sponsorship
            return {'mode':'AUTO_VERIFIED' if value is not None else 'REVIEW','answer':('Yes' if value else 'No') if value is not None else None,'reason':'From user-verified candidate profile.'}
    if kind == 'SALARY_RULE':
        target = profile.target_salary
        if job.salary_min and job.salary_max and target:
            if job.salary_min <= target <= job.salary_max:
                return {'mode':'AUTO_RULE','answer':str(target),'reason':'Configured target is within posting range.'}
            return {'mode':'REVIEW','answer':str(target),'reason':'Configured target is outside posting range; review before use.'}
        return {'mode':'REVIEW','answer':str(target) if target else None,'reason':'Salary range or configured target is missing.'}
    if kind == 'PROFILE':
        mapping = {
            'email': profile.email, 'phone': profile.phone, 'linkedin': profile.linkedin_url, 'github': profile.github_url,
            'location': profile.home_location, 'city': (profile.home_location or '').split(',')[0],
            'first name': (profile.preferred_name or profile.full_name.split()[0]), 'last name': profile.full_name.split()[-1]
        }
        for key, value in mapping.items():
            if key in low: return {'mode':'AUTO_PROFILE','answer':value,'reason':'Candidate profile field.'}
    return {'mode':'REVIEW','answer':None,'reason':'Open-ended question should be generated from verified evidence and reviewed.'}


def build_standard_application_answers(profile: CandidateProfile, job: JobPosting) -> dict:
    questions = [
        'First name','Last name','Email','Phone','LinkedIn Profile','GitHub Profile','Current location',
        'What is your desired salary?',
        'Are you currently legally authorized to work in the United States?',
        'Will you now or in the future require sponsorship for employment authorization?',
        'Voluntary self-identification of disability',
    ]
    return {q: answer_question(profile, job, q) for q in questions}
