"""Decide what to put in each application field.

This module is pure Python (no browser, no database) so every decision the
browser agent makes can be unit-tested. ``browser.py`` scans the live form with
``form_scan.js``, hands the fields to :func:`plan_application`, and executes the
returned actions.

Answer sources, in priority order:

1. Answers the user approved for *this* application (the review queue).
2. Verified profile facts: name, contact details, links, location, and the
   work-authorization / sponsorship answers the user explicitly verified.
3. The user's EEO preference: if they opted in to "decline to self-identify",
   voluntary EEO questions get the decline option. Otherwise they are left
   blank when optional and sent to review when required.
4. The answer bank: answers the user gave on earlier applications to the same
   question (e.g. "How did you hear about us?"). Sensitive categories (EEO,
   criminal history, attestations, citizenship, clearance, salary) are never
   reused across applications.

Anything required that none of these can answer is returned as *unresolved*
with the exact question text, so the review queue can ask the user and the next
run can finish the form.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- text helpers

STOPWORDS = {
    'a', 'an', 'the', 'is', 'are', 'you', 'your', 'do', 'does', 'of', 'to', 'in', 'for', 'and', 'or',
    'what', 'please', 'this', 'that', 'on', 'with', 'be', 'will', 'if', 'any', 'have', 'at', 'as', 'by',
    # Subject words that vary between employers without changing the question.
    'us', 'we', 'our', 'job', 'role', 'position', 'opportunity', 'company', 'here', 'team',
}


def norm(text: str | None) -> str:
    text = (text or '').lower().replace('’', "'")
    text = re.sub(r'[*✱]', ' ', text)
    text = re.sub(r'[^a-z0-9'+"'"+r'+#./ -]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def tokens(text: str | None) -> set[str]:
    return {t.strip("'.") for t in norm(text).replace('/', ' ').split() if t.strip("'.") and t not in STOPWORDS}


def same_question(a: str, b: str) -> bool:
    """True when two question labels are the same question worded slightly differently."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(small) >= 2 and small <= big and len(small) / len(big) >= 0.5:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.75


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


# --------------------------------------------------------------------------- classification

EEO = r"\b(gender|sex|race|racial|ethnicity|ethnic|hispanic|latino|latinx|veteran|disability|disabled|sexual orientation|transgender|lgbtq)\b"
SENSITIVE = {
    'eeo': EEO,
    'identity': r'\b(pronouns?|date of birth|birth ?date|marital|religion|religious)\b',
    'criminal': r'\b(criminal|felony|felonies|convicted|conviction|misdemeanor|arrest(ed)?)\b',
    'attestation': r'\b(certify|attest|under penalty|true and (correct|complete)|accurate and complete|electronic signature|signature)\b',
    'citizenship': r'\b(citizen|citizenship|green card|permanent resident|visa (status|type)|immigration)\b',
    'clearance': r'\b(security clearance|clearance|export control|itar|u\.?s\.? person)\b',
    'salary': r'\b(salary|compensation|pay (expectation|range)|desired pay|expected pay|rate expectation)\b',
    # True today, stale next month: answered per application, never reused.
    'timing': r'\b(deadlines?|start date|available to start|earliest start|notice period|availability)\b',
}
WORK_AUTH = r'\b(authori[sz]ed to work|legally (authori[sz]ed|eligible|able)|eligible to work|right to work|work authori[sz]ation|work permit)\b'
SPONSOR = r'\bsponsor(ship)?\b'
MOTIVATION = r"\b(why|what (interests|excites|attracts|draws) you|interest(ed)? in (joining|working)|cover letter|didn't exist|did not exist|most excited)\b"
# Categories whose answers must come from this application's review, never the bank.
# Motivation answers name the employer, so they never carry over either.
NO_BANK = {'eeo', 'identity', 'criminal', 'attestation', 'citizenship', 'clearance', 'salary', 'work_auth',
           'sponsorship', 'motivation', 'timing'}

# Education questions are often long ("Which university are you currently attending...?"),
# so they are matched without the short-label rule used for contact fields. Order matters.
EDUCATION_RULES: list[tuple[str, str]] = [
    ('hs_year', r'\bhigh school\b.*\b(year|graduat\w*)\b|\b(year|graduat\w*)\b.*\bhigh school\b'),
    ('high_school', r'\bhigh school\b'),
    ('grad_year', r'\b(graduation (year|date)|year of graduation|graduat\w* (year|date|in)|expected graduation|intended graduation|when (did|do|will) you graduate)\b'),
    ('gpa', r'\bgpa\b|\bgrade point\b'),
    ('major', r'\b(major|field of study|area of study|discipline|concentration)\b'),
    ('degree', r'\b(degree|highest (level of )?education|education level|level of education)\b'),
    ('school', r'\b(university|college|school|institution)\b'),
]
EDUCATION = {name for name, _ in EDUCATION_RULES}

PROFILE_RULES: list[tuple[str, str]] = [
    ('preferred_name', r'\b(preferred (first )?name|nickname|goes by)\b'),
    ('first_name', r'\b(first|given) ?name\b|^first$'),
    ('last_name', r'\b(last|family) ?name\b|\bsurname\b|^last$'),
    ('full_name', r'^(your )?(full |legal |full legal )?name$|\bfull (legal )?name\b'),
    ('email', r'\be-?mail\b'),
    ('phone', r'\b(phone|mobile|cell|telephone)\b'),
    ('linkedin', r'\blinked ?in\b'),
    ('github', r'\bgit ?hub\b'),
    ('portfolio', r'\b(portfolio|personal (web ?)?site|website|web site|blog)\b'),
    ('location', r'^(current )?(location|city)( city)?$|\b(current location|where are you (currently )?(located|based)|city of residence|city and state|location \(city\))\b'),
]


def classify(label: str) -> str:
    """Return the field's category: a profile fact, a legal/sensitive topic, or 'question'."""
    low = norm(label)
    if _has(SPONSOR, low):
        return 'sponsorship'
    if _has(WORK_AUTH, low):
        return 'work_auth'
    for cat, pattern in SENSITIVE.items():
        if _has(pattern, low):
            return cat
    if not re.match(r'^(are|do|did|have|has|would|will|can|is)\b', low):
        for name, pattern in EDUCATION_RULES:
            if _has(pattern, low):
                return name
    if len(low) <= 80 and not re.match(r'^(are|do|did|have|has|would|will|can|is)\b', low):
        for name, pattern in PROFILE_RULES:
            if _has(pattern, low):
                return name
    if _has(MOTIVATION, low) and not _has(r'\bcover ?letter\b', low):
        return 'motivation'
    if _has(r'\b(resume|cv|curriculum vitae)\b', low):
        return 'resume'
    if _has(r'\bcover ?letter\b', low):
        return 'cover_letter'
    return 'question'


# --------------------------------------------------------------------------- facts

@dataclass
class Facts:
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    preferred_name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    portfolio: str | None = None
    location: str | None = None
    legal_verified: bool = False
    authorized: bool | None = None
    sponsor_now: bool | None = None
    sponsor_future: bool | None = None
    eeo_decline: bool = False
    school: str | None = None
    degree: str | None = None
    major: str | None = None
    grad_year: str | None = None
    gpa: str | None = None
    high_school: str | None = None
    hs_year: str | None = None
    approved: dict[str, str] = field(default_factory=dict)
    bank: dict[str, str] = field(default_factory=dict)
    resume_path: str | None = None
    cover_letter_path: str | None = None


def build_facts(profile, extra_links=None, approved_answers=None, answer_bank=None,
                resume_path=None, cover_letter_path=None) -> Facts:
    """Build facts from a CandidateProfile-like object (attribute access only)."""
    full = (getattr(profile, 'full_name', '') or '').strip()
    parts = full.split()
    links = [x for x in (extra_links or []) if x.get('include_in_applications', True) and x.get('url')]
    portfolio = next((x['url'] for x in links if x.get('link_type') in {'portfolio', 'website'}), None)
    portfolio = portfolio or next((x['url'] for x in links if x.get('link_type') == 'project'), None)
    verified = getattr(profile, 'legal_answers_verified_at', None) is not None
    return Facts(
        first_name=parts[0] if parts else None,
        last_name=parts[-1] if len(parts) > 1 else None,
        full_name=full or None,
        preferred_name=getattr(profile, 'preferred_name', None) or (parts[0] if parts else None),
        email=getattr(profile, 'email', None),
        phone=getattr(profile, 'phone', None),
        linkedin=getattr(profile, 'linkedin_url', None),
        github=getattr(profile, 'github_url', None),
        portfolio=portfolio,
        location=getattr(profile, 'home_location', None),
        legal_verified=verified,
        authorized=getattr(profile, 'authorized_to_work_us', None) if verified else None,
        sponsor_now=getattr(profile, 'requires_current_sponsorship', None) if verified else None,
        sponsor_future=getattr(profile, 'requires_future_sponsorship', None) if verified else None,
        eeo_decline=(getattr(profile, 'eeo_preference', None) or '').lower() == 'decline',
        school=getattr(profile, 'education_school', None), degree=getattr(profile, 'education_degree', None),
        major=getattr(profile, 'education_field', None),
        grad_year=str(getattr(profile, 'education_graduation_year', None) or '') or None,
        gpa=getattr(profile, 'education_gpa', None), high_school=getattr(profile, 'high_school_name', None),
        hs_year=str(getattr(profile, 'high_school_graduation_year', None) or '') or None,
        approved={str(k): str(v) for k, v in (approved_answers or {}).items() if v is not None and str(v).strip()},
        bank={str(k): str(v) for k, v in (answer_bank or {}).items() if v is not None and str(v).strip()},
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
    )


# --------------------------------------------------------------------------- answers

DECLINE = r"\b(decline|prefer not|not wish|don't wish|do not wish|do not want|don't want|choose not|rather not|not to (answer|disclose|say|self.identify|specify)|i don't know)\b"
YES = {'yes', 'y', 'true', 'checked', 'agree', 'i agree', 'on'}
NO = {'no', 'n', 'false', 'unchecked', 'off'}


@dataclass
class Answer:
    value: str          # text to type, or the intent for choice fields
    source: str         # approved | profile | verified | eeo-preference | answer-bank | file
    kind: str = 'text'  # text | yesno | decline | file
    needs_sponsor: bool | None = None   # work-authorization answers: pick between "authorized" statements


def lookup(store: dict[str, str], label: str) -> str | None:
    for question, value in store.items():
        if same_question(question, label):
            return value
    return None


def answer_for(field_: dict, facts: Facts) -> tuple[Answer | None, str]:
    """Return (answer, category). A None answer means we do not know it."""
    label = field_.get('label') or ''
    cat = classify(label)
    ftype = field_.get('type')

    if ftype == 'file':
        if cat == 'cover_letter':
            return (Answer(facts.cover_letter_path, 'file', 'file') if facts.cover_letter_path else None), cat
        if cat == 'resume' or not label:
            return (Answer(facts.resume_path, 'file', 'file') if facts.resume_path else None), 'resume'
        return None, cat

    approved = lookup(facts.approved, label)
    if approved is not None:
        return Answer(approved, 'approved', _kind_of(approved)), cat

    if cat == 'work_auth':
        if facts.authorized is None:
            return None, cat
        need = None if facts.sponsor_now is None and facts.sponsor_future is None else bool(facts.sponsor_now or facts.sponsor_future)
        return Answer('Yes' if facts.authorized else 'No', 'verified', 'yesno', need), cat
    if cat == 'sponsorship':
        need = _sponsorship_need(norm(label), facts)
        if need is None:
            return None, cat
        return Answer('Yes' if need else 'No', 'verified', 'yesno'), cat
    if cat == 'eeo':
        return (Answer('decline', 'eeo-preference', 'decline') if facts.eeo_decline else None), cat
    if cat in SENSITIVE:
        return None, cat

    profile_value = {
        'first_name': facts.first_name, 'last_name': facts.last_name, 'full_name': facts.full_name,
        'preferred_name': facts.preferred_name, 'email': facts.email, 'phone': facts.phone,
        'linkedin': facts.linkedin, 'github': facts.github, 'portfolio': facts.portfolio,
        'location': facts.location,
        'school': facts.school, 'degree': facts.degree, 'major': facts.major, 'grad_year': facts.grad_year,
        'gpa': facts.gpa, 'high_school': facts.high_school, 'hs_year': facts.hs_year,
    }
    if cat in profile_value:
        value = profile_value[cat]
        return (Answer(value, 'profile') if value else None), cat

    if cat not in NO_BANK:
        banked = lookup(facts.bank, label)
        if banked is not None:
            return Answer(banked, 'answer-bank', _kind_of(banked)), cat
    return None, cat


def _sponsorship_need(low: str, facts: Facts) -> bool | None:
    """Map a sponsorship question onto the two verified profile answers."""
    now, future = facts.sponsor_now, facts.sponsor_future
    asks_now_only = _has(r'\b(currently|right now|at this time|today)\b', low) and not _has(r'\bfuture\b', low)
    if asks_now_only:
        if now is not None:
            return now
        return False if future is False else None
    # "now or in the future" and unqualified questions: Yes if either answer is Yes.
    if now or future:
        return True
    if future is False:
        return False  # no future need implies no current need
    return None


def _kind_of(value: str) -> str:
    v = norm(value)
    if v in YES or v in NO:
        return 'yesno'
    if _has(DECLINE, v):
        return 'decline'
    return 'text'


def choose_option(options: list[str], answer: Answer) -> int | None:
    """Index of the option that expresses ``answer``, or None when nothing fits."""
    normed = [norm(o) for o in options]
    real = [i for i, o in enumerate(normed) if o and not _has(r'^(select|choose|please select|--|none selected)', o)]
    if answer.kind == 'decline':
        for i in real:
            if _has(DECLINE, normed[i]):
                return i
        return None
    want = norm(answer.value)
    if answer.kind == 'yesno':
        yes = want in YES
        for i in real:
            first = normed[i].split(' ')[0].strip(',.')
            if (yes and first in {'yes', 'i agree', 'agree', 'true'}) or (not yes and first in {'no', 'false'}):
                return i
        for i in real:
            if (yes and normed[i].startswith(('i agree', 'agree', 'i acknowledge', 'i consent'))):
                return i
        return _statement_option(normed, real, yes, answer.needs_sponsor)
    for i in real:
        if normed[i] == want:
            return i
    for i in real:
        if normed[i].startswith(want) or want.startswith(normed[i]):
            return i
    best, best_score = None, 0.0
    wt = tokens(want)
    for i in real:
        ot = tokens(normed[i])
        if not ot or not wt:
            continue
        score = len(ot & wt) / len(ot | wt)
        if score > best_score:
            best, best_score = i, score
    return best if best_score >= 0.5 else None


NEGATED = r"\b(not|no|don't|do not|cannot|can't|unable|won't|will not)\b"
QUALIFIED = r'\b(sponsor(ship)?|visa|h-?1b|opt|cpt|ead|require|requires|requiring|but|only|present employer|current employer)\b'


def _statement_option(normed: list[str], real: list[int], yes: bool, needs_sponsor: bool | None) -> int | None:
    """Forms that answer in sentences ("I am authorized to work … for any employer").

    Picks only when exactly one option says it; anything ambiguous goes to review.
    """
    real = [i for i in real if not _has(DECLINE, normed[i])]
    negated = [i for i in real if _has(NEGATED, normed[i])]
    if not yes:
        return negated[0] if len(negated) == 1 else None
    plain = [i for i in real if i not in negated]
    if len(plain) == 1:
        return plain[0]
    if needs_sponsor is None:
        return None
    sponsor = [i for i in plain if _has(r'\b(sponsor(ship)?|visa|h-?1b)\b', normed[i])]
    pick = sponsor if needs_sponsor else [i for i in plain if not _has(QUALIFIED, normed[i])]
    return pick[0] if len(pick) == 1 else None


# --------------------------------------------------------------------------- plan

@dataclass
class Action:
    key: str
    op: str             # fill | select | check | click | combobox | upload
    label: str
    value: str | None = None
    option_key: str | None = None
    source: str = ''


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)
    unresolved: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


MULTI_SEP = ' | '   # how the review queue stores several choices for one question
ALWAYS_SET = {'first_name', 'last_name', 'full_name', 'preferred_name', 'email', 'phone', 'linkedin', 'github', 'portfolio'}


def _same_value(a, b) -> bool:
    squash = lambda x: re.sub(r'[^a-z0-9@]', '', str(x or '').lower())
    return squash(a) == squash(b) or squash(a).endswith(squash(b)) and len(squash(b)) >= 7


def _is_filled(f: dict) -> bool:
    return bool(str(f.get('value') or '').strip())


def plan_application(fields: list[dict], facts: Facts, uploaded: set[str] | None = None) -> Plan:
    """Turn scanned fields into actions plus the required questions nobody can answer yet.

    ``fields`` are dicts produced by ``form_scan.js`` with an added ``key`` that
    is unique across frames. ``uploaded`` holds field keys already given a file.
    """
    plan = Plan()
    uploaded = uploaded or set()
    resume_done = False
    for f in fields:
        key, ftype, label = f['key'], f.get('type'), f.get('label') or ''
        answer, cat = answer_for(f, facts)
        filled = _is_filled(f)

        if ftype == 'file':
            if key in uploaded or filled:
                continue
            if answer and cat == 'resume' and resume_done:
                continue  # only the first unlabeled/resume input gets the resume
            if answer:
                plan.actions.append(Action(key, 'upload', label or 'Resume', answer.value, source='file'))
                resume_done = resume_done or cat == 'resume'
            elif f.get('required'):
                plan.unresolved.append({'label': label or 'file upload', 'category': cat, 'reason': 'required file upload'})
            continue

        if answer is None:
            if f.get('required') and not filled:
                plan.unresolved.append({'label': label or f.get('name') or 'unlabeled required field', 'category': cat,
                                        'reason': _reason(cat, facts)})
            elif not filled:
                plan.skipped.append(label)
            continue

        # Leave values the portal (or a resume parser) already filled, except
        # profile facts we know exactly.
        if filled and (cat not in ALWAYS_SET or _same_value(f.get('value'), answer.value)):
            continue

        options = f.get('options') or []
        if ftype == 'checkbox_group' and MULTI_SEP in str(answer.value):
            # "Check all that apply": one check per chosen option.
            picked = 0
            for part in [x.strip() for x in str(answer.value).split(MULTI_SEP) if x.strip()]:
                idx = choose_option([o.get('text', '') for o in options], Answer(part, answer.source, _kind_of(part)))
                if idx is not None:
                    plan.actions.append(Action(key, 'check', label, options[idx].get('text'), option_key=options[idx]['id'], source=answer.source))
                    picked += 1
            if not picked and f.get('required') and not filled:
                plan.unresolved.append({'label': label, 'category': cat, 'reason': f'none of "{answer.value}" match the options'})
            continue
        if ftype in {'select', 'radio', 'buttons', 'checkbox_group'}:
            idx = choose_option([o.get('text', '') for o in options], answer)
            if idx is None and cat in {'school', 'high_school'}:
                # "Please select Other (School Not Listed) if your school is not listed."
                idx = next((i for i, o in enumerate(options) if re.search(r'\bother\b', o.get('text', ''), re.I)), None)
            if idx is None:
                if f.get('required') and not filled:
                    plan.unresolved.append({'label': label, 'category': cat,
                                            'reason': f'no option matches "{answer.value}"'})
                continue
            opt = options[idx]
            if ftype == 'select':
                plan.actions.append(Action(key, 'select', label, opt.get('value', opt.get('text')), source=answer.source))
            elif ftype == 'buttons':
                plan.actions.append(Action(key, 'click', label, opt.get('text'), option_key=opt['id'], source=answer.source))
            else:
                plan.actions.append(Action(key, 'check', label, opt.get('text'), option_key=opt['id'], source=answer.source))
        elif ftype == 'checkbox':
            want = norm(answer.value)
            if want in YES:
                plan.actions.append(Action(key, 'check', label, 'checked', option_key=f['id'], source=answer.source))
            elif f.get('required') and want not in NO:
                plan.unresolved.append({'label': label, 'category': cat, 'reason': 'checkbox needs an explicit yes'})
        elif ftype == 'combobox':
            plan.actions.append(Action(key, 'combobox', label, _choice_text(answer), source=answer.source))
        else:
            if answer.kind == 'decline' and answer.source == 'eeo-preference':
                if f.get('required'):
                    plan.unresolved.append({'label': label, 'category': cat, 'reason': 'free-text EEO question'})
                continue
            plan.actions.append(Action(key, 'fill', label, answer.value, source=answer.source))
    return plan


def _choice_text(answer: Answer) -> str:
    if answer.kind == 'decline':
        return 'decline'
    return answer.value


def _reason(cat: str, facts: Facts) -> str:
    if cat in {'work_auth', 'sponsorship'}:
        return 'work authorization answers are not verified in your profile' if not facts.legal_verified else 'verified answer missing for this question'
    if cat == 'eeo':
        return 'voluntary EEO question; set an EEO preference or answer it'
    if cat in SENSITIVE:
        return f'{cat} question requires your answer'
    return 'required question with no saved answer'


def bankable(question: str) -> bool:
    """Whether an answer to ``question`` may be reused on other applications."""
    return classify(question) not in NO_BANK
