from __future__ import annotations
import re
from careerops.db.models import CandidateProfile

_REMOTE_WORDS = {"remote", "anywhere", "united states", "us remote", "u.s. remote"}
_STATE_RE = re.compile(r"(?:,|\s)\s*([A-Z]{2})(?:\b|$)")


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _state(value: str | None) -> str | None:
    if not value:
        return None
    m = _STATE_RE.search(value.upper())
    return m.group(1) if m else None


def _city(value: str | None) -> str:
    if not value:
        return ""
    return _norm(value.split(",", 1)[0])


def preferred_locations(profile: CandidateProfile) -> list[str]:
    values = [x.strip() for x in (profile.preferred_locations or []) if x and x.strip()]
    if not values and profile.home_location:
        values = [profile.home_location.strip()]
    return values


def evaluate_job_location(profile: CandidateProfile, location: str | None, workplace_type: str | None = None) -> dict:
    """Deterministic location gate used before fit scoring.

    Preferred locations are an allow-list. Remote jobs are handled separately.
    The radius value is stored in the profile and shown in the UI, but this local
    build intentionally does not pretend to calculate road/geodesic distance from
    free-form job locations. Add nearby cities explicitly to the preferred list.
    """
    w = _norm(workplace_type)
    loc = _norm(location)

    if "remote" in w or any(word in loc for word in _REMOTE_WORDS):
        return {
            "status": "PASS" if profile.remote_allowed else "FAIL",
            "detail": "remote role" if profile.remote_allowed else "remote roles disabled",
        }

    if not location:
        return {"status": "REVIEW", "detail": "job location missing"}

    prefs = preferred_locations(profile)
    if not prefs:
        return {"status": "REVIEW", "detail": "no preferred job locations configured"}

    loc_city = _city(location)
    loc_state = _state(location)

    for pref in prefs:
        p = _norm(pref)
        p_city = _city(pref)
        p_state = _state(pref)
        # Exact/substring phrase match catches variants like "Seattle, WA, United States".
        if p and (p in loc or loc in p):
            return {"status": "PASS", "detail": f"matches preferred location: {pref}"}
        # City + state match is robust to expanded state/country wording.
        if p_city and loc_city == p_city and (not p_state or not loc_state or p_state == loc_state):
            return {"status": "PASS", "detail": f"matches preferred city: {pref}"}

    # Strong reject when both sides expose state codes and the job is out of state.
    allowed_states = sorted({s for s in (_state(x) for x in prefs) if s})
    if loc_state and allowed_states and loc_state not in allowed_states:
        return {
            "status": "FAIL",
            "detail": f"job state {loc_state} is outside allowed state(s): {', '.join(allowed_states)}",
        }

    return {
        "status": "FAIL",
        "detail": "location is not in preferred job locations; add nearby cities explicitly to the profile",
    }


def should_keep_discovered_job(profile: CandidateProfile, item: dict) -> bool:
    location_ok=evaluate_job_location(profile, item.get('location'), item.get('workplace_type')).get('status') != 'FAIL'
    role_ok=evaluate_job_role(profile, item.get('title'), item.get('description')).get('status') != 'FAIL'
    return location_ok and role_ok


_TECH_ROLE_TERMS={
    'software','engineer','developer','machine learning','ml','artificial intelligence','ai','data',
    'platform','infrastructure','devops','cloud','solutions','solution','architect','scientist','analytics',
    'forward deployed','decision engineer','automation','backend','full stack','full-stack','applied scientist'
}
_STOP_ROLE_WORDS={'engineer','engineering','software','ai','ml','data','applied','the','and','of','for','i','ii','iii','senior','junior','entry','level'}

def evaluate_job_role(profile: CandidateProfile, title: str|None, description: str|None=None) -> dict:
    if not title: return {'status':'REVIEW','detail':'job title missing'}
    t=_norm(title)
    families=[_norm(x) for x in (profile.role_families or []) if x]
    if any(f and (f in t or t in f) for f in families):
        return {'status':'PASS','detail':'title matches configured role family'}
    if any(term in t for term in _TECH_ROLE_TERMS):
        return {'status':'PASS','detail':'title matches broad technical role vocabulary'}
    # A distinctive word from a configured role family can also keep uncommon titles.
    distinctive=set()
    for family in families:
        distinctive.update(w for w in re.findall(r'[a-z0-9+#.]+',family) if len(w)>=4 and w not in _STOP_ROLE_WORDS)
    if any(w in t for w in distinctive):
        return {'status':'PASS','detail':'title overlaps configured role family'}
    return {'status':'FAIL','detail':'title is outside configured role families'}
