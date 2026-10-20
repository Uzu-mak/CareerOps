"""Browser application agent.

How one application run works:

1. Open the posting at its *application* URL (Lever ``/apply``, Ashby
   ``/application``, the Greenhouse embed's own board page), or click the
   page's "Apply" control when the form is not on the first page.
2. Scan every frame with ``form_scan.js``: visible inputs, selects, radio and
   checkbox groups, custom comboboxes, file inputs, buttons, and whether a real
   CAPTCHA challenge, password or MFA prompt is showing.
3. Upload the tailored resume first (Lever/Ashby parse it and prefill fields),
   then fill everything ``apply_plan.plan_application`` can answer from the
   verified profile, approved review answers, the EEO preference and the
   answer bank. Re-scan and repeat, so conditional follow-up questions are seen.
4. If any required field is still empty, stop and report the *exact* question
   text. Those questions go to the review queue; once answered, the next run
   fills them and continues.
5. Click Next/Continue through multi-step flows (``for _step in range(10)``),
   then Submit, and count the application as submitted only when a
   confirmation message that was not on the page before appears.

It never solves CAPTCHA, never handles passwords or MFA, and never invents an
answer to a legal, EEO or attestation question.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

from careerops.agents.apply_plan import Answer, Facts, build_facts, choose_option, classify, norm, plan_application

if TYPE_CHECKING:  # pragma: no cover
    from careerops.db.models import Application, CandidateProfile, JobPosting

SCAN_JS = Path(__file__).with_name('form_scan.js').read_text(encoding='utf-8')

# Kept for callers that list topics needing a human; matching now happens per
# question in apply_plan.classify with word boundaries.
SENSITIVE_LABELS = [
    'disability', 'veteran', 'race', 'ethnicity', 'gender', 'sex', 'criminal', 'felony',
    'attest', 'certify', 'captcha', 'export control', 'security clearance', 'sponsorship',
]

SKIP_FRAME_HINTS = ('recaptcha', 'hcaptcha', 'challenges.cloudflare.com', 'doubleclick', 'googletagmanager',
                    'youtube.com', 'vimeo.com', 'facebook.com', 'linkedin.com/px', 'about:srcdoc')

APPLY_ENTRY = ['Apply for this job', 'Apply for this position', 'Apply for this role', 'Apply now', 'Apply Now',
               'Apply', 'Start application', 'Start Application', "I'm interested"]
NEXT_STEP = ['Save and Continue', 'Save & Continue', 'Continue', 'Next', 'Next Step', 'Review Application', 'Review']
SUBMIT = ['Submit Application', 'Submit application', 'Submit my application', 'Send application', 'Submit',
          'Apply', 'Apply now', 'Send']
SOCIAL_APPLY = ('linkedin', 'indeed', 'google', 'facebook', 'seek', 'glassdoor', 'later', 'save for')

CONFIRMATION_TERMS = [
    'thank you for applying', 'thanks for applying', 'application submitted', 'application has been submitted',
    'application was submitted', 'application was successfully submitted', 'successfully submitted',
    'we received your application', "we've received your application", 'we have received your application',
    'your application has been received', 'your application was submitted', 'application received',
    'thank you for your application', 'thanks for your application', 'application is complete',
]
CONFIRMATION_URL_HINTS = ('/thanks', '/thank-you', '/thankyou', '/confirmation', '/submitted', '/success')
MFA_LABEL = re.compile(r'\b(verification code|one.time (pass)?code|security code|two.factor|2fa|authenticator code|sms code)\b', re.I)


@dataclass
class BrowserResult:
    status: str
    url: str
    filled_fields: list[str]
    manual_fields: list[str]
    uploaded_files: list[str]
    submitted: bool = False
    message: str = ''
    screenshot_path: str | None = None
    confirmation_term: str | None = None
    confirmation_excerpt: str | None = None


def detect_portal(url: str | None) -> str:
    host = urlparse(url or '').netloc.lower()
    if 'greenhouse' in host: return 'greenhouse'
    if 'lever.co' in host: return 'lever'
    if 'ashbyhq' in host: return 'ashby'
    if 'myworkdayjobs' in host or 'workday' in host: return 'workday'
    if 'google' in host: return 'google'
    return 'generic'


_UUID = r'[0-9a-fA-F-]{36}'


def application_entry_url(url: str) -> str:
    """Point Lever and Ashby postings at their application form instead of the description."""
    parsed = urlparse(url)
    host, path = parsed.netloc.lower(), parsed.path.rstrip('/')
    if 'lever.co' in host and re.fullmatch(rf'/[^/]+/{_UUID}', path):
        return urlunparse(parsed._replace(path=path + '/apply'))
    if 'ashbyhq.com' in host and re.fullmatch(rf'/[^/]+/{_UUID}', path):
        return urlunparse(parsed._replace(path=path + '/application'))
    return url


# --------------------------------------------------------------------------- page access

class _Form:
    """The scanned state of a page: fields from every frame, with frame-unique keys."""

    def __init__(self, page):
        self.page = page
        self.frames = []
        self.fields: list[dict] = []
        self.buttons: list[dict] = []
        self.captcha = False
        self.password = False
        self.errors: list[str] = []
        self.embed: str | None = None
        self.text = ''
        self.form_frame = None
        counts = []
        for frame in _usable_frames(page):
            try:
                data = frame.evaluate(SCAN_JS, {'op': 'scan'})
            except Exception:
                continue
            if not data:
                continue
            fi = len(self.frames)
            self.frames.append(frame)
            for f in data.get('fields') or []:
                f['key'] = f'{fi}:{f["id"]}'
                f['frame'] = fi
                self.fields.append(f)
            for b in data.get('buttons') or []:
                b['frame'] = fi
                self.buttons.append(b)
            self.captcha = self.captcha or bool(data.get('captcha'))
            self.password = self.password or bool(data.get('password'))
            self.errors.extend(data.get('errors') or [])
            self.embed = self.embed or data.get('embed')
            self.text += '\n' + (data.get('text') or '')
            counts.append((len([f for f in data.get('fields') or [] if f['type'] != 'file']), fi))
        if counts:
            best = max(counts)
            self.form_frame = best[1] if best[0] else 0

    def frame_of(self, field: dict):
        return self.frames[field['frame']]

    @property
    def application_fields(self) -> list[dict]:
        return self.fields

    def looks_like_application(self) -> bool:
        fields = self.application_fields
        has_file = any(f['type'] == 'file' for f in fields)
        has_contact = any(re.search(r'\b(e-?mail|name|phone)\b', norm(f.get('label'))) for f in fields)
        return (has_file and len(fields) >= 2) or (has_contact and len(fields) >= 3)

    def mfa(self) -> bool:
        return any(f.get('autocomplete') == 'one-time-code' or MFA_LABEL.search(f.get('label') or '') for f in self.fields)

    def find_button(self, names: list[str], frame_index: int | None = None) -> dict | None:
        pool = [b for b in self.buttons if not b.get('disabled') and (frame_index is None or b['frame'] == frame_index)]
        for name in names:
            want = norm(name)
            for b in pool:
                text = norm(b['text'])
                if any(s in text for s in SOCIAL_APPLY):
                    continue
                if text == want or (len(want) > 6 and text.startswith(want)):
                    return b
        return None


def _usable_frames(page):
    frames = []
    for frame in page.frames:
        try:
            if frame.is_detached():
                continue
        except Exception:
            continue
        url = (frame.url or '').lower()
        if frame is not page.main_frame and any(h in url for h in SKIP_FRAME_HINTS):
            continue
        frames.append(frame)
    return frames


def _settle(page, ms: int = 800):
    try:
        page.wait_for_load_state('domcontentloaded', timeout=12000)
    except Exception:
        pass
    try:
        page.wait_for_load_state('networkidle', timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(ms)


def _all_text(page) -> str:
    out = []
    for frame in _usable_frames(page):
        try:
            out.append(frame.evaluate(SCAN_JS, {'op': 'text'}) or '')
        except Exception:
            pass
    return '\n'.join(out)


def _loc(frame, element_id: str):
    return frame.locator(f'[data-careerops-id="{element_id}"]').first


def _click(frame, element_id: str) -> bool:
    try:
        _loc(frame, element_id).click(timeout=5000)
        return True
    except Exception:
        try:
            return bool(frame.evaluate(SCAN_JS, {'op': 'click', 'id': element_id}))
        except Exception:
            return False


# --------------------------------------------------------------------------- actions

def _pick_combobox(form: _Form, field: dict, text: str) -> bool:
    """Open a custom dropdown, type to filter, and click the option that matches."""
    frame = form.frame_of(field)
    loc = _loc(frame, field['id'])
    answer = Answer(text, 'plan', 'decline' if text == 'decline' else ('yesno' if norm(text) in {'yes', 'no'} else 'text'))
    attempts = [''] if answer.kind == 'decline' else [text, '']
    for typed in attempts:
        try:
            loc.click(timeout=4000)
            loc.fill(typed, timeout=4000)
        except Exception:
            try:
                loc.click(timeout=4000)
            except Exception:
                return False
        form.page.wait_for_timeout(700)
        options = []
        for fr in form.frames:  # menus are often portaled to the top frame
            try:
                options.extend((fr, o) for o in (fr.evaluate(SCAN_JS, {'op': 'options'}) or []))
            except Exception:
                pass
        idx = choose_option([o['text'] for _, o in options], answer)
        if idx is not None:
            fr, opt = options[idx]
            if _click(fr, opt['id']):
                form.page.wait_for_timeout(300)
                return True
    try:
        loc.press('Escape')
    except Exception:
        pass
    return False


def _execute(form: _Form, actions, filled: list[str], uploaded: list[str], uploaded_keys: set[str]) -> int:
    by_key = {f['key']: f for f in form.fields}
    done = 0
    # Files first: ATS resume parsers overwrite text fields after an upload.
    for action in sorted(actions, key=lambda a: a.op != 'upload'):
        field = by_key.get(action.key)
        if not field:
            continue
        frame = form.frame_of(field)
        try:
            if action.op == 'upload':
                if not action.value or not Path(action.value).exists():
                    continue
                _loc(frame, field['id']).set_input_files(action.value)
                uploaded.append(Path(action.value).name)
                uploaded_keys.add(action.key)
                form.page.wait_for_timeout(2500)  # let the portal parse the file
            elif action.op == 'fill':
                _loc(frame, field['id']).fill(str(action.value), timeout=5000)
            elif action.op == 'select':
                _loc(frame, field['id']).select_option(value=str(action.value), timeout=5000)
            elif action.op == 'check':
                if not frame.evaluate(SCAN_JS, {'op': 'check', 'id': action.option_key, 'on': True}):
                    _click(frame, action.option_key)
            elif action.op == 'click':
                _click(frame, action.option_key)
            elif action.op == 'combobox':
                if not _pick_combobox(form, field, str(action.value)):
                    continue
            filled.append(action.label)
            done += 1
        except Exception:
            continue
    return done


def _fill_page(page, facts: Facts, filled: list[str], uploaded: list[str], uploaded_keys: set[str]) -> _Form:
    """Fill until a pass changes nothing (follow-up questions appear after answers)."""
    form = _Form(page)
    for _pass in range(4):
        plan = plan_application(form.application_fields, facts, uploaded=uploaded_keys)
        if not plan.actions:
            break
        if not _execute(form, plan.actions, filled, uploaded, uploaded_keys):
            break
        page.wait_for_timeout(400)
        form = _Form(page)
    return form


def _still_missing(form: _Form, facts: Facts, uploaded_keys: set[str]) -> list[str]:
    plan = plan_application(form.application_fields, facts, uploaded=uploaded_keys)
    labels = [u['label'] for u in plan.unresolved]
    # A required field we tried to fill but that is still empty is also missing.
    for f in form.application_fields:
        if f.get('required') and not str(f.get('value') or '').strip() and f['key'] not in uploaded_keys:
            if f['type'] == 'file' and classify(f.get('label') or 'resume') == 'resume' and any(k.split(':')[0] == str(f['frame']) for k in uploaded_keys):
                continue  # the portal re-rendered the resume input after our upload
            label = f.get('label') or f.get('name') or 'unlabeled required field'
            if label not in labels:
                labels.append(label)
    return labels


def _handle_account_gate(page, form: _Form, profile, filled: list[str], manual: list[str]):
    """Account-gated portals: prefill the email at most; passwords, email verification
    and MFA stay with the candidate. Raw portal passwords are never stored."""
    text = form.text
    create = any(m in text for m in ['create account', 'create an account', 'sign up', 'register'])
    for f in form.fields:
        if re.search(r'\b(e-?mail|username)\b', norm(f.get('label'))) and profile.email:
            try:
                _loc(form.frame_of(f), f['id']).fill(profile.email, timeout=3000)
                filled.append(f.get('label') or 'Email')
            except Exception:
                pass
            break
    manual.append('portal account password / email verification' if create else 'portal sign-in/session required')


def _confirmation_text(text: str, term: str) -> str:
    idx = text.find(term)
    return text[max(0, idx - 100):idx + len(term) + 220].strip()


def _confirm(page, before_text: str, before_url: str, timeout_s: float = 20.0) -> tuple[str | None, str | None, list[str]]:
    """Wait for a confirmation that was not on the page before submitting.

    Returns (term, excerpt, problems). Problems are validation errors, newly
    required fields or a CAPTCHA challenge that appeared instead.
    """
    deadline = time.monotonic() + timeout_s
    problems: list[str] = []
    while time.monotonic() < deadline:
        page.wait_for_timeout(700)
        text = _all_text(page)
        term = next((t for t in CONFIRMATION_TERMS if t in text and t not in before_text), None)
        if term:
            return term, _confirmation_text(text, term), []
        url = (page.url or '').lower()
        if url != (before_url or '').lower() and any(h in url for h in CONFIRMATION_URL_HINTS) and 'thank' in text and 'thank' not in before_text:
            return 'confirmation page', _confirmation_text(text, 'thank'), []
        form = _Form(page)
        if form.captcha:
            return None, None, ['CAPTCHA']
        invalid = [f.get('label') or 'field' for f in form.fields if f.get('invalid')]
        new_errors = [e for e in form.errors if e.lower() not in before_text]
        if invalid or new_errors:
            problems = [f'form error: {x}' for x in (invalid + new_errors)][:8]
            if time.monotonic() > deadline - timeout_s + 4:  # give async validation a moment
                return None, None, problems
    return None, None, problems


# --------------------------------------------------------------------------- entry points

def _launch_options(settings, headless: bool) -> dict:
    opts = {'headless': headless, 'args': ['--no-sandbox', '--disable-dev-shm-usage']}
    exe = settings.chromium_executable
    if exe and Path(exe).exists():
        opts['executable_path'] = exe  # Docker image ships /usr/bin/chromium
    return opts  # otherwise Playwright's own Chromium (local dev, CI)


def run_generic_browser(
    profile: 'CandidateProfile',
    job: 'JobPosting',
    application: 'Application',
    target_url: str,
    resume_path: str | None = None,
    cover_letter_path: str | None = None,
    submit: bool = False,
    extra_links: list[dict] | None = None,
    approved_review_answers: dict[str, str] | None = None,
    answer_bank: dict[str, str] | None = None,
) -> BrowserResult:
    """Fill a live application using verified profile facts and the tailored files.

    Submission is reported only when an employer acknowledgement appears after
    the final submit click; otherwise the exact blocking questions are returned
    in ``manual_fields`` for the review queue.
    """
    from playwright.sync_api import sync_playwright
    from careerops.core.config import settings

    facts = build_facts(profile, extra_links, approved_review_answers, answer_bank, resume_path, cover_letter_path)
    filled: list[str] = []; manual: list[str] = []; uploaded: list[str] = []; uploaded_keys: set[str] = set()
    did_submit = False; confirmation_term = None; confirmation_excerpt = None

    with sync_playwright() as p:
        browser = p.chromium.launch(**_launch_options(settings, settings.browser_headless))
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.goto(application_entry_url(target_url), wait_until='domcontentloaded', timeout=45000)
        _settle(page)
        entered_embed = False

        # Bound traversal so a malformed portal cannot loop forever.
        for _step in range(10):
            form = _Form(page)
            if form.captcha:
                manual.append('CAPTCHA'); break
            if form.mfa():
                manual.append('authentication/MFA'); break

            if form.embed and not entered_embed:
                # Company career pages embed Greenhouse in an iframe; open the board itself.
                entered_embed = True
                page.goto(form.embed, wait_until='domcontentloaded', timeout=45000); _settle(page)
                continue
            if not form.looks_like_application():
                if form.password:
                    _handle_account_gate(page, form, profile, filled, manual); break
                entry = form.find_button(APPLY_ENTRY)
                if entry:
                    _click(form.frames[entry['frame']], entry['id']); _settle(page, 1200)
                    continue
                manual.append('application form not detected'); break

            form = _fill_page(page, facts, filled, uploaded, uploaded_keys)
            if form.captcha:
                manual.append('CAPTCHA'); break
            missing = _still_missing(form, facts, uploaded_keys)
            if missing:
                manual.extend(missing); break
            if not submit:
                break

            final = form.find_button(SUBMIT, form.form_frame) or form.find_button(SUBMIT[:4])
            step = None if final else (form.find_button(NEXT_STEP, form.form_frame) or form.find_button(NEXT_STEP))
            if step:
                # Multi-step ATS flows expose Continue/Next before their final submit.
                _click(form.frames[step['frame']], step['id']); _settle(page)
                continue
            if not final:
                manual.append('final submit control not detected'); break

            before_text, before_url = _all_text(page), page.url
            _click(form.frames[final['frame']], final['id'])
            confirmation_term, confirmation_excerpt, problems = _confirm(page, before_text, before_url)
            did_submit = confirmation_term is not None
            if not did_submit:
                after = _Form(page)
                if after.looks_like_application() and not problems and after.find_button(SUBMIT + NEXT_STEP) and _step < 9:
                    # A new step rendered in place (single-page multi-step form).
                    if [f['label'] for f in after.fields] != [f['label'] for f in form.fields]:
                        continue
                manual.extend(problems)
                manual.append('submission confirmation not detected')
            break

        screenshot_path = str(settings.generated_path / f'application_{application.id}_{"confirmation" if did_submit else "review"}.png')
        try:
            page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            screenshot_path = None
        final_url = page.url
        browser.close()

    manual = list(dict.fromkeys(manual))
    if did_submit:
        status = 'SUBMITTED'; msg = 'Submitted and employer confirmation detected.'
    elif manual:
        status = 'PAUSED_FOR_REVIEW'; msg = 'Human review required before submission can be confirmed.'
    else:
        status = 'READY_FOR_SUBMISSION'; msg = 'Application fields and files prepared; final submission not triggered.'
    return BrowserResult(status=status, url=final_url, filled_fields=sorted(set(filled)), manual_fields=manual,
                         uploaded_files=sorted(set(uploaded)), submitted=did_submit, message=msg,
                         screenshot_path=screenshot_path, confirmation_term=confirmation_term,
                         confirmation_excerpt=confirmation_excerpt)


MOCK_FORM = '''<!doctype html><html><body>
<h1>{company}</h1><h2>{title}</h2>
<form>
  <label>First Name<input name="first"></label>
  <label>Last Name<input name="last"></label>
  <label>Email Address<input name="email" type="email"></label>
  <label>Phone Number<input name="phone" type="tel"></label>
  <label>LinkedIn Profile<input name="linkedin"></label>
  <label>Voluntary self-identification of disability *<select name="disability" required>
    <option value="">Select...</option><option>Yes, I have a disability</option><option>No, I do not have a disability</option>
    <option>I do not want to answer</option></select></label>
  <button type="button">Submit Application</button>
</form></body></html>'''


def run_mock_browser(profile: 'CandidateProfile', job: 'JobPosting', application: 'Application') -> BrowserResult:
    """Run the real fill engine against a local form (no network, never submits)."""
    from html import escape
    from playwright.sync_api import sync_playwright
    from careerops.core.config import settings

    facts = build_facts(profile)
    filled: list[str] = []; uploaded: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(**_launch_options(settings, True))
        page = browser.new_page()
        page.set_content(MOCK_FORM.format(company=escape(job.company or ''), title=escape(job.title or '')))
        form = _fill_page(page, facts, filled, uploaded, set())
        manual = _still_missing(form, facts, set())
        browser.close()
    return BrowserResult(status='PAUSED_FOR_REVIEW' if manual else 'READY_FOR_SUBMISSION', url='mock://local-ats',
                         filled_fields=filled, manual_fields=manual, uploaded_files=uploaded, submitted=False,
                         message='Mock ATS filled by the live engine; final submission is never triggered.')
