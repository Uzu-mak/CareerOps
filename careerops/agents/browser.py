from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from careerops.core.config import settings
from careerops.db.models import CandidateProfile, JobPosting, Application

SENSITIVE_LABELS = [
    'disability','veteran','race','ethnicity','gender','sex','criminal','felony',
    'attest','certify','captcha','export control','security clearance','sponsorship'
]

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
    host=urlparse(url or '').netloc.lower()
    if 'greenhouse' in host: return 'greenhouse'
    if 'lever.co' in host: return 'lever'
    if 'ashbyhq' in host: return 'ashby'
    if 'myworkdayjobs' in host or 'workday' in host: return 'workday'
    if 'google' in host: return 'google'
    return 'generic'


def _fill(page, labels: list[str], value: str, filled: list[str]):
    if value is None: return False
    for label in labels:
        try:
            loc=page.get_by_label(label, exact=False)
            if loc.count():
                loc.first.fill(str(value)); filled.append(label); return True
        except Exception:
            pass
    return False


def _fill_or_select(page, labels: list[str], value: str, filled: list[str]) -> bool:
    if value is None or str(value).strip()=='' : return False
    for label in labels:
        try:
            loc=page.get_by_label(label, exact=False)
            if not loc.count():
                continue
            el=loc.first
            tag=el.evaluate('(e)=>e.tagName.toLowerCase()')
            typ=(el.get_attribute('type') or '').lower()
            if tag=='select':
                try: el.select_option(label=str(value))
                except Exception:
                    try: el.select_option(value=str(value))
                    except Exception: continue
            elif typ in {'radio','checkbox'}:
                try: el.check()
                except Exception: continue
            else:
                el.fill(str(value))
            filled.append(label); return True
        except Exception:
            pass
    return False


def _upload(page, path: str | None, labels: list[str], uploaded: list[str], fallback: bool=True) -> bool:
    if not path or not Path(path).exists(): return False
    for label in labels:
        try:
            loc=page.get_by_label(label, exact=False)
            if loc.count():
                loc.first.set_input_files(path); uploaded.append(Path(path).name); return True
        except Exception:
            pass
    # Fallback to the first raw file input only for the resume.
    if fallback:
        try:
            inputs=page.locator('input[type="file"]')
            if inputs.count():
                inputs.first.set_input_files(path); uploaded.append(Path(path).name); return True
        except Exception:
            pass
    return False




def _handle_account_gate(page, profile: CandidateProfile, filled: list[str], manual: list[str]):
    """Conservatively handle account-gated portals without storing passwords.

    CareerOps may click a visible Create account/Sign up action and prefill the user's
    verified email. Password creation, email verification, MFA and OAuth ownership
    confirmation remain explicit human/session steps.
    """
    try:
        body=(page.locator('body').inner_text() or '').lower()
    except Exception:
        body=''
    create_markers=['create account','create an account','sign up','register']
    login_markers=['sign in to continue','log in to continue','sign in','login']
    if any(m in body for m in create_markers):
        for text in ['Create account','Create an account','Sign up','Register']:
            try:
                btn=page.get_by_role('button',name=text,exact=False)
                if not btn.count(): btn=page.get_by_role('link',name=text,exact=False)
                if btn.count():
                    btn.first.click(); page.wait_for_timeout(700); break
            except Exception:
                pass
        _fill(page,['Email','Email Address','Username'],profile.email or '',filled)
        manual.append('portal account password / email verification')
        return
    if any(m in body for m in login_markers):
        # Reusable authenticated sessions are preferred; raw account passwords are never stored in PostgreSQL.
        _fill(page,['Email','Email Address','Username'],profile.email or '',filled)
        manual.append('portal sign-in/session required')

def _visible_form_text(page) -> str:
    """Return label/fieldset/form text used for sensitive-field detection.

    We intentionally avoid scanning the whole job-description page for words such as
    "sponsorship" because that creates false human-review stops. The goal is to
    detect questions the application is actually asking.
    """
    chunks=[]
    for selector in ['label','legend','form']:
        try:
            vals=page.locator(selector).all_inner_texts()
            chunks.extend(vals[:200])
        except Exception:
            pass
    return '\n'.join(chunks).lower()


def _fill_standard_fields(page, profile: CandidateProfile, filled: list[str], extra_links: list[dict] | None, approved_review_answers: dict[str,str] | None):
    _fill(page,['First Name','First name','Given Name'], profile.preferred_name or profile.full_name.split()[0], filled)
    _fill(page,['Last Name','Last name','Family Name'], profile.full_name.split()[-1], filled)
    _fill(page,['Email','Email Address'], profile.email or '', filled)
    _fill(page,['Phone','Phone Number','Mobile'], profile.phone or '', filled)
    _fill(page,['LinkedIn','LinkedIn Profile','LinkedIn URL'], profile.linkedin_url or '', filled)
    _fill(page,['GitHub','Github','GitHub URL'], profile.github_url or '', filled)
    links=[x for x in (extra_links or []) if x.get('include_in_applications', True) and x.get('url')]
    portfolio=next((x.get('url') for x in links if x.get('link_type') in {'portfolio','website'}), None)
    project=next((x.get('url') for x in links if x.get('link_type')=='project'), None)
    if portfolio:
        _fill(page,['Website','Personal Website','Portfolio','Portfolio URL','Website URL'], portfolio, filled)
    if project:
        _fill(page,['Project URL','Project Link','Demo URL','Live Demo'], project, filled)
    _fill(page,['Location','City'], profile.home_location or '', filled)
    for question, value in (approved_review_answers or {}).items():
        _fill_or_select(page,[question],value,filled)


def _detect_manual_fields(page, approved_review_answers: dict[str,str] | None, filled: list[str]) -> list[str]:
    manual=[]
    form_text=_visible_form_text(page)
    try: body=(page.locator('body').inner_text() or '').lower()
    except Exception: body=''
    approved={str(k).lower():str(v) for k,v in (approved_review_answers or {}).items() if v is not None and str(v).strip()}
    for label in SENSITIVE_LABELS:
        if label not in form_text: continue
        matching=[(q,v) for q,v in approved.items() if label in q]
        if matching and _fill_or_select(page,[matching[0][0],label,label.title()],matching[0][1],filled):
            continue
        manual.append(label)
    if 'captcha' in body or page.locator('iframe[src*="captcha"],iframe[title*="captcha" i]').count():
        manual.append('CAPTCHA')
    for auth_word in ['verification code','two-factor','multi-factor','one-time code']:
        if auth_word in form_text or auth_word in body:
            manual.append('authentication/MFA'); break
    return sorted(set(manual))


def _click_first(page, names: list[str]) -> str | None:
    for text in names:
        for role in ['button','link']:
            try:
                loc=page.get_by_role(role,name=text,exact=False)
                if loc.count() and loc.first.is_visible():
                    loc.first.click(); return text
            except Exception:
                pass
    return None


def _confirmation(page) -> tuple[str|None,str|None]:
    try: after=(page.locator('body').inner_text() or '').lower()
    except Exception: after=''
    terms=['thank you for applying','thanks for applying','application submitted','application has been submitted','we received your application','your application was submitted','application received','thank you for your application']
    term=next((x for x in terms if x in after),None)
    if not term: return None,None
    idx=after.find(term)
    return term,after[max(0,idx-100):idx+len(term)+220].strip()


def run_generic_browser(
    profile: CandidateProfile,
    job: JobPosting,
    application: Application,
    target_url: str,
    resume_path: str | None = None,
    cover_letter_path: str | None = None,
    submit: bool=False,
    extra_links: list[dict] | None = None,
    approved_review_answers: dict[str, str] | None = None,
) -> BrowserResult:
    """Fill a live application using verified profile/evidence and tailored files.

    The browser can traverse a bounded multi-step public application flow. It does
    not bypass CAPTCHA/MFA, invent sensitive answers, or store raw portal passwords.
    A submission is only considered successful when an employer acknowledgement is
    observed after the final submit action.
    """
    filled=[]; manual=[]; uploaded=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=settings.browser_headless, executable_path=settings.chromium_executable, args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page()
        page.goto(target_url, wait_until='domcontentloaded', timeout=45000)
        did_submit=False; confirmation_term=None; confirmation_excerpt=None
        final_clicked=False

        # Bound traversal so a malformed portal cannot loop forever.
        for _step in range(10):
            _handle_account_gate(page,profile,filled,manual)
            _fill_standard_fields(page,profile,filled,extra_links,approved_review_answers)
            _upload(page,resume_path,['Resume','Resume/CV','CV','Attach Resume'],uploaded,fallback=True)
            if cover_letter_path:
                _upload(page,cover_letter_path,['Cover Letter','Cover letter','Attach Cover Letter'],uploaded,fallback=False)

            manual.extend(_detect_manual_fields(page,approved_review_answers,filled))
            manual=sorted(set(manual))
            if manual or not submit:
                break

            # Multi-step ATS flows generally expose Continue/Next before their final submit.
            clicked=_click_first(page,['Save and Continue','Save & Continue','Continue','Next','Next Step','Review Application','Review'])
            if clicked:
                try: page.wait_for_load_state('domcontentloaded',timeout=12000)
                except Exception: page.wait_for_timeout(1200)
                continue

            clicked=_click_first(page,['Submit Application','Submit application','Submit my application','Submit'])
            if clicked:
                final_clicked=True
                try: page.wait_for_load_state('domcontentloaded',timeout=12000)
                except Exception: page.wait_for_timeout(1800)
                confirmation_term,confirmation_excerpt=_confirmation(page)
                did_submit=confirmation_term is not None
                if not did_submit: manual.append('submission confirmation not detected')
                break

            # Some direct-apply pages expose Apply/Apply now as the transition into the form.
            clicked=_click_first(page,['Apply now','Apply Now','Start application','Start Application'])
            if clicked:
                try: page.wait_for_load_state('domcontentloaded',timeout=12000)
                except Exception: page.wait_for_timeout(1000)
                continue
            manual.append('final submit control not detected')
            break

        screenshot_path = str(settings.generated_path / f'application_{application.id}_review.png')
        if did_submit:
            screenshot_path = str(settings.generated_path / f'application_{application.id}_confirmation.png')
        try: page.screenshot(path=screenshot_path, full_page=True)
        except Exception: screenshot_path=None

        if did_submit:
            status='SUBMITTED'; msg='Submitted and employer confirmation detected.'
        elif manual:
            status='PAUSED_FOR_REVIEW'; msg='Human review required before submission can be confirmed.'
        else:
            status='READY_FOR_SUBMISSION'; msg='Application fields and files prepared; final submission not triggered.'
        result=BrowserResult(status=status,url=page.url,filled_fields=sorted(set(filled)),manual_fields=sorted(set(manual)),uploaded_files=sorted(set(uploaded)),submitted=did_submit,message=msg,screenshot_path=screenshot_path,confirmation_term=confirmation_term,confirmation_excerpt=confirmation_excerpt)
        browser.close()
        return result


def run_mock_browser(profile: CandidateProfile, job: JobPosting, application: Application) -> BrowserResult:
    filled=[]; manual=[]; uploaded=[]
    html=f'''<!doctype html><html><body>
    <h1>{job.company}</h1><h2>{job.title}</h2>
    <form>
      <label>First Name<input aria-label="First Name"></label>
      <label>Last Name<input aria-label="Last Name"></label>
      <label>Email Address<input aria-label="Email Address"></label>
      <label>Phone Number<input aria-label="Phone Number"></label>
      <label>LinkedIn Profile<input aria-label="LinkedIn Profile"></label>
      <label>Voluntary self-identification of disability<select aria-label="Voluntary self-identification of disability"><option>Prefer not to answer</option></select></label>
      <button type="button">Submit Application</button>
    </form></body></html>'''
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, executable_path=settings.chromium_executable, args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(); page.set_content(html)
        _fill(page,['First Name'], profile.preferred_name or profile.full_name.split()[0], filled)
        _fill(page,['Last Name'], profile.full_name.split()[-1], filled)
        _fill(page,['Email Address'], profile.email or '', filled)
        _fill(page,['Phone Number'], profile.phone or '', filled)
        _fill(page,['LinkedIn Profile'], profile.linkedin_url or '', filled)
        if page.get_by_text('disability', exact=False).count(): manual.append('disability')
        browser.close()
    return BrowserResult(status='PAUSED_FOR_REVIEW',url='mock://local-ats',filled_fields=filled,manual_fields=manual,uploaded_files=uploaded,submitted=False,message='Mock ATS fields filled; sensitive disclosure left for human review.')
