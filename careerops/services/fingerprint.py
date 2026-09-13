import hashlib
import re


def _norm(value: str | None) -> str:
    return re.sub(r'\s+', ' ', (value or '').strip().lower())


def job_fingerprint(company: str, title: str, location: str | None, source_job_id: str | None, description: str = '') -> str:
    stable = '|'.join([_norm(company), _norm(title), _norm(location), _norm(source_job_id)])
    if not source_job_id:
        stable += '|' + _norm(description)[:800]
    return hashlib.sha256(stable.encode()).hexdigest()


def cache_key(*parts: str) -> str:
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()
