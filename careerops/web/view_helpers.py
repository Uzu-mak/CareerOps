"""Pure helpers for server-rendered pages (no database access, unit-testable)."""
from __future__ import annotations

from datetime import datetime, timezone


def iso(value) -> str:
    """ISO 8601 in UTC for <time datetime=...>; the browser renders it in local time."""
    if not value:
        return ''
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def short_dt(value) -> str:
    """Server-side fallback text, e.g. 'Oct 20, 17:42 UTC' (JS replaces it with local time)."""
    if not value:
        return '—'
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime('%b %d, %H:%M UTC').replace(' 0', ' ')


def money(value) -> str:
    if value in (None, ''):
        return ''
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f'${n / 1000:.0f}k' if n >= 1000 else f'${n:.0f}'


def salary_range(lo, hi) -> str:
    if not lo and not hi:
        return 'Not listed'
    if lo and hi and lo != hi:
        return f'{money(lo)} – {money(hi)}'
    return money(lo or hi)


def setup_checklist(profile, link_count: int = 0, notifications_configured: bool = False) -> list[dict]:
    """What still needs doing before CareerOps can apply well, in the order it matters."""
    if profile is None:
        return []
    items = [
        ('resume', 'Upload your master resume', bool(getattr(profile, 'baseline_resume_path', None)), '/profile#resume'),
        ('legal', 'Verify work-authorization answers', getattr(profile, 'legal_answers_verified_at', None) is not None, '/profile#legal'),
        ('skills', 'Add at least 5 skills', len(getattr(profile, 'skills', None) or []) >= 5, '/profile#search'),
        ('education', 'Add your education', bool(getattr(profile, 'education_school', None) and getattr(profile, 'education_graduation_year', None)), '/profile#education'),
        ('roles', 'Choose target role families', bool(getattr(profile, 'role_families', None)), '/profile#search'),
        ('links', 'Add LinkedIn and GitHub', bool(getattr(profile, 'linkedin_url', None) and getattr(profile, 'github_url', None))
         and 'your-name' not in (getattr(profile, 'linkedin_url', '') or ''), '/profile#identity'),
        ('alerts', 'Turn on a notification channel', notifications_configured, '/notifications'),
    ]
    return [{'key': k, 'label': label, 'done': done, 'href': href} for k, label, done, href in items]


def time_of_day(hour: int) -> str:
    return 'morning' if 5 <= hour < 12 else 'afternoon' if 12 <= hour < 18 else 'evening'
