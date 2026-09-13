from __future__ import annotations
import re
from careerops.db.models import CandidateEvidence

NUMBER_RE = re.compile(r'(?<!\w)(?:\$?\d[\d,.]*%?|\d+\+)(?!\w)')


def verify_generated_claims(text: str, evidence: list[CandidateEvidence], baseline_text: str = '') -> tuple[bool, list[str]]:
    """Block numeric claims not traceable to an evidence bullet/verified metric.

    This is intentionally conservative. Non-numeric prose is constrained by agents to
    paraphrase evidence; high-risk numeric claims receive an additional mechanical guard.
    """
    allowed_blob = ' '.join(
        [e.summary + ' ' + ' '.join(e.bullets or []) + ' ' + str(e.verified_metrics or {}) for e in evidence]
    ).lower() + ' ' + (baseline_text or '').lower()
    blocked = []
    for sentence in re.split(r'(?<=[.!?])\s+', text):
        nums = NUMBER_RE.findall(sentence)
        if nums and not all(n.lower().replace(',','') in allowed_blob.replace(',','') for n in nums):
            # Ignore ordinary years/dates and contact-like values by focusing on impact syntax.
            if any(x in sentence.lower() for x in ['improved','reduced','increased','saved','processed','latency','accuracy','%','users','records','hours/week']):
                blocked.append(sentence.strip())
    return (not blocked, blocked)
