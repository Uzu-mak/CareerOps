"""Option lists for the UI: one place for every dropdown, chip suggestion and label.

Templates get these as the ``ui`` global, so a select menu is never hand-typed in
HTML and the API validates against the same values.
"""
from __future__ import annotations

from careerops.agents.apply_plan import classify
import re

from careerops.agents.jd_analysis import SKILL_LIBRARY

ROLE_FAMILIES = [
    'AI Engineer', 'Applied AI Engineer', 'Machine Learning Engineer', 'Forward Deployed Engineer',
    'AI Solutions Engineer', 'Solutions Architect', 'Software Engineer', 'Backend Engineer', 'Full Stack Engineer',
    'Data Engineer', 'Analytics Engineer', 'Data Scientist', 'MLOps Engineer', 'Platform Engineer',
    'Site Reliability Engineer', 'DevOps Engineer', 'Cloud Engineer', 'Technical Program Manager',
    'Product Engineer', 'Research Engineer',
]

EXTRA_SKILLS = [
    'Go', 'Rust', 'Scala', 'Kotlin', 'C#', '.NET', 'Node.js', 'Flask', 'Spring', 'Vue', 'Svelte', 'Tailwind CSS',
    'Redis', 'MongoDB', 'MySQL', 'DynamoDB', 'Snowflake', 'Databricks', 'Airflow', 'Kafka', 'Flink', 'Terraform',
    'Ansible', 'Linux', 'Bash', 'PyTorch', 'TensorFlow', 'scikit-learn', 'Hugging Face', 'OpenAI API', 'Bedrock',
    'SageMaker', 'Vertex AI', 'MCP', 'vector databases', 'Pinecone', 'Weaviate', 'prompt engineering',
    'evaluation', 'NLP', 'computer vision', 'Playwright', 'Selenium', 'pytest', 'Prometheus', 'OpenTelemetry',
    'CloudWatch', 'Lambda', 'ECS', 'EKS', 'S3', 'Tableau', 'Looker', 'Excel', 'system design', 'microservices',
    'event-driven architecture', 'stakeholder management', 'technical writing',
]
SKILLS = sorted(set(SKILL_LIBRARY) | set(EXTRA_SKILLS), key=str.lower)

US_LOCATIONS = [
    'Remote (US)', 'Seattle, WA', 'Bellevue, WA', 'Redmond, WA', 'Kirkland, WA', 'Tacoma, WA', 'Auburn, WA',
    'Everett, WA', 'Renton, WA', 'Portland, OR', 'San Francisco, CA', 'San Jose, CA', 'Palo Alto, CA',
    'Mountain View, CA', 'Los Angeles, CA', 'San Diego, CA', 'Denver, CO', 'Austin, TX', 'Dallas, TX',
    'Houston, TX', 'Chicago, IL', 'Atlanta, GA', 'Miami, FL', 'Boston, MA', 'New York, NY', 'Washington, DC',
    'Arlington, VA', 'Raleigh, NC', 'Charlotte, NC', 'Phoenix, AZ', 'Salt Lake City, UT', 'Minneapolis, MN',
    'Pittsburgh, PA', 'Philadelphia, PA', 'Columbus, OH', 'Detroit, MI', 'Nashville, TN',
]

WORK_AUTH_TYPES = [
    'U.S. citizen', 'Permanent resident (green card)', 'H-1B', 'F-1 OPT', 'F-1 STEM OPT', 'H-4 EAD', 'L-1',
    'L-2 EAD', 'TN', 'O-1', 'E-3', 'Asylum / refugee EAD', 'Other EAD',
]

EEO_PREFERENCES = [
    ('', 'Leave blank when optional; ask me when required'),
    ('decline', 'Answer "decline to self-identify"'),
]

LINK_TYPES = [('portfolio', 'Portfolio'), ('project', 'Project'), ('website', 'Website'),
              ('publication', 'Publication'), ('other', 'Other')]

# (value, label, tone) - tone maps to badge colours in the stylesheet.
APPLICATION_STATUSES = [
    ('planned', 'Planned', 'neutral'), ('prepared', 'Prepared', 'neutral'), ('review', 'Needs review', 'warn'),
    ('submitted', 'Submitted', 'good'), ('interview', 'Interview', 'accent'), ('offer', 'Offer', 'accent'),
    ('rejected', 'Rejected', 'bad'), ('withdrawn', 'Withdrawn', 'neutral'),
]
APPLICATION_STATUS_VALUES = {v for v, _, _ in APPLICATION_STATUSES}

SOURCE_TYPES = {
    'greenhouse': {'label': 'Greenhouse board', 'field': 'Board token', 'placeholder': 'e.g. openai (from boards.greenhouse.io/openai)', 'key': False},
    'lever': {'label': 'Lever board', 'field': 'Site name', 'placeholder': 'e.g. palantir (from jobs.lever.co/palantir)', 'key': False},
    'ashby': {'label': 'Ashby board', 'field': 'Board name', 'placeholder': 'e.g. openai (from jobs.ashbyhq.com/openai)', 'key': False},
    'company_career': {'label': 'Company careers site', 'field': 'Careers page URL', 'placeholder': 'https://careers.example.com/jobs', 'key': False},
    'generic': {'label': 'Single job page', 'field': 'Job page URL', 'placeholder': 'https://example.com/jobs/123', 'key': False},
    'adzuna': {'label': 'Adzuna (broad market)', 'field': 'Search config (JSON, optional)', 'placeholder': '{"country": "us"}', 'key': True},
    'usajobs': {'label': 'USAJOBS (federal)', 'field': 'Search config (JSON, optional)', 'placeholder': '{}', 'key': True},
    'hn_hiring': {'label': 'Hacker News: Who is hiring?', 'field': 'Thread', 'placeholder': 'latest', 'key': False},
    'remotive': {'label': 'Remotive remote jobs', 'field': 'Categories (JSON)', 'placeholder': '{"categories": ["software-dev", "data"]}', 'key': False},
    'linkedin_alerts': {'label': 'LinkedIn alert emails', 'field': 'Label', 'placeholder': 'linkedin', 'key': False},
    'indeed_alerts': {'label': 'Indeed alert emails', 'field': 'Label', 'placeholder': 'indeed', 'key': False},
}

SCAN_INTERVALS = [(15, 'Every 15 minutes'), (60, 'Hourly'), (240, 'Every 4 hours'), (720, 'Every 12 hours'), (1440, 'Daily')]

DECISIONS = [('APPLY', 'Apply'), ('REVIEW', 'Review'), ('SKIP', 'Skip')]
PRIORITIES = ['A+', 'A', 'B+', 'B', 'C']
WORKPLACES = [('remote', 'Remote'), ('hybrid', 'Hybrid'), ('onsite', 'On-site')]
JOB_SORTS = [('fit', 'Best fit'), ('newest', 'Newest'), ('company', 'Company A–Z')]

YES_NO_CATEGORIES = {'work_auth', 'sponsorship', 'criminal', 'citizenship', 'clearance', 'attestation'}


def review_input(question: str, plan: dict | None = None) -> dict:
    """How the review queue should ask a question.

    When the browser agent saw the field, ``plan`` carries its type and the form's own
    options, so the user picks exactly what the employer offers.
    """
    plan = plan or {}
    cat = classify(question)
    ftype, options = plan.get('field_type'), [o for o in (plan.get('options') or []) if o]
    words = re.search(r'(\d{2,4})\s*words', question or '', re.I)
    spec = {'category': cat, 'words': int(words.group(1)) if words else None}
    if ftype == 'checkbox_group' and options:
        return {**spec, 'kind': 'multi', 'options': options}
    if ftype == 'checkbox':
        return {**spec, 'kind': 'select', 'options': ['Yes', 'No']}
    if ftype in {'select', 'radio', 'buttons', 'combobox'} and options:
        return {**spec, 'kind': 'select', 'options': options}
    if cat in YES_NO_CATEGORIES:
        return {**spec, 'kind': 'select', 'options': ['Yes', 'No']}
    if cat == 'eeo':
        return {**spec, 'kind': 'select', 'options': ['Decline to self-identify'], 'free': True}
    if cat == 'salary':
        return {**spec, 'kind': 'number'}
    if ftype == 'textarea' or spec['words'] or (cat in {'motivation', 'question'} and len(question) > 60):
        return {**spec, 'kind': 'textarea'}
    return {**spec, 'kind': 'text'}


AUTO_APPLY_HOSTS = ('greenhouse.io', 'lever.co', 'ashbyhq.com')
AUTO_APPLY_ATS = {'greenhouse', 'lever', 'ashby'}


def apply_mode(url: str | None, ats: str | None = None) -> str:
    """'auto' when the browser agent can fill this portal's form, else 'manual'.

    Greenhouse, Lever and Ashby forms are public and tested. Big-company career
    portals (Workday, Meta, Amazon, Microsoft, ...) require signing in to their
    own account system first, so the agent stops before any form appears.
    """
    low = (url or '').lower()
    if (ats or '').lower() in AUTO_APPLY_ATS or any(h in low for h in AUTO_APPLY_HOSTS):
        return 'auto'
    return 'manual'


# Review reasons that are not questions: what stopped the agent, why, and what to do.
# (prefix match, title, explanation, suggested action)
BLOCKERS = [
    ('application form not detected', "Couldn't find the application form",
     'The page opened, but CareerOps found no form to fill. The site may need you to sign in first, or the posting may have closed.',
     'Open the employer page. If it asks you to sign in, apply there yourself, then mark the application Submitted on the Applications page.'),
    ('final submit control not detected', "Couldn't find the Submit button",
     'Every field was filled, but no Submit or Next button was recognised.',
     'Open the employer page, check the form and submit it yourself.'),
    ('submission confirmation not detected', 'Submitted, but no confirmation appeared',
     'CareerOps clicked Submit, but no "thank you" message appeared within 20 seconds, so it does not count the application as sent.',
     'Check your email for a confirmation from the employer. If you got one, set the status to Submitted.'),
    ('captcha', 'A CAPTCHA appeared',
     'The site asked for a human check. CareerOps never solves CAPTCHAs.',
     'Open the employer page and finish the application yourself.'),
    ('authentication/mfa', 'A verification code was requested',
     'The site asked for a one-time code (email, SMS or authenticator).',
     'Sign in on the employer site yourself, then run Apply again.'),
    ('portal account password', 'The site needs an account',
     'This portal requires creating an account with a password and email verification. CareerOps never stores portal passwords.',
     'Create the account on the employer site, then run Apply again.'),
    ('portal sign-in', 'The site needs you to sign in',
     'This portal asked for a sign-in before showing the application.',
     'Sign in on the employer site, then run Apply again.'),
    ('final submission approval', 'Practice run finished',
     'This came from the old "Simulate browser agent" practice form, which never submits anything.',
     'Nothing to do. Dismiss it.'),
    ('form error:', 'The form showed an error',
     'After submitting, the employer form reported a problem with one of the answers.',
     'Open the employer page to see which field it flagged, fix the answer here if it is one of yours, and run Apply again.'),
    ('truth guard', 'Some resume claims were held back',
     'The tailored documents left out claims your evidence does not support, so Autopilot did not submit unattended.',
     'Look at the Documents tab. Add evidence in the Build Journal, or apply manually if you are happy with the documents.'),
    ('browser error', 'The browser agent crashed',
     'Something went wrong while running the browser.',
     'Try a Dry run to see where it stops. If it keeps failing, send the app log.'),
]


def blocker_info(reason: str) -> dict | None:
    """Explain a review reason that is a status, not a question; None for real questions."""
    low = (reason or '').strip().lower()
    for prefix, title, why, action in BLOCKERS:
        if low.startswith(prefix):
            detail = reason[len(prefix):].strip(' :-') if prefix.endswith(':') or prefix == 'truth guard' else ''
            return {'title': title, 'why': why, 'action': action, 'detail': detail}
    return None


def is_blocker(reason: str) -> bool:
    return blocker_info(reason) is not None


SKILL_ALIASES = {
    'REST APIs': ['rest api', 'restful', 'rest services'], 'CI/CD': ['ci/cd', 'continuous integration', 'continuous deployment'],
    'LLMs': ['llm', 'llms', 'large language model'], 'AI agents': ['ai agent', 'ai agents', 'agentic'],
    'Generative AI': ['generative ai', 'genai'], 'machine learning': ['machine learning'], 'Kubernetes': ['kubernetes', 'k8s'],
    'JavaScript': ['javascript'], 'Node.js': ['node.js', 'nodejs'], 'Go': ['golang'], 'Next.js': ['next.js', 'nextjs'],
    'PostgreSQL': ['postgresql', 'postgres'], 'scikit-learn': ['scikit-learn', 'sklearn'],
}
CASE_SENSITIVE = {'Go', 'ECS', 'EKS', 'S3', 'MCP', 'NLP', 'SQL', 'RAG', 'AWS', 'GCP', 'dbt'}


def _skill_pattern(skill: str) -> re.Pattern:
    phrases = SKILL_ALIASES.get(skill, []) + [skill]
    body = '|'.join(re.escape(p) for p in phrases)
    flags = 0 if skill in CASE_SENSITIVE and skill not in SKILL_ALIASES else re.I
    return re.compile(r'(?<![A-Za-z0-9+#.])(?:' + body + r')(?![A-Za-z0-9+#])', flags)


_PATTERNS = None


def detect_skills(text: str) -> list[str]:
    """Skills from the shared vocabulary that appear in ``text`` as whole words."""
    global _PATTERNS
    if _PATTERNS is None:
        _PATTERNS = [(s, _skill_pattern(s)) for s in SKILLS]
    text = text or ''
    return [s for s, pat in _PATTERNS if pat.search(text)]


def suggest_roles(text: str) -> list[str]:
    low = (text or '').lower()
    return [r for r in ROLE_FAMILIES if r.lower() in low]


def as_template_globals() -> dict:
    return {
        'role_families': ROLE_FAMILIES, 'skills': SKILLS, 'locations': US_LOCATIONS,
        'work_auth_types': WORK_AUTH_TYPES, 'eeo_preferences': EEO_PREFERENCES, 'link_types': LINK_TYPES,
        'application_statuses': APPLICATION_STATUSES, 'source_types': SOURCE_TYPES, 'scan_intervals': SCAN_INTERVALS,
        'decisions': DECISIONS, 'priorities': PRIORITIES, 'workplaces': WORKPLACES, 'job_sorts': JOB_SORTS,
        'status_label': {v: lbl for v, lbl, _ in APPLICATION_STATUSES},
        'status_tone': {v: tone for v, _, tone in APPLICATION_STATUSES},
    }
