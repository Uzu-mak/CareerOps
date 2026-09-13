from __future__ import annotations
import re
from sqlalchemy.orm import Session
from careerops.db.models import CandidateProfile, JobPosting, JobAnalysis
from careerops.agents.policy import evaluate_hard_constraints
from careerops.agents.evidence import rank_evidence


def norm(s: str) -> str:
    return re.sub(r'[^a-z0-9+#.]+',' ',s.lower()).strip()


def skill_match(profile_skills: list[str], skill: str) -> str:
    p = [norm(x) for x in profile_skills]
    s = norm(skill)
    if any(s == x or s in x or x in s for x in p): return 'MATCH'
    groups = [
        {'aws','gcp','azure','cloud platforms'}, {'react','next.js','javascript','typescript','frontend'},
        {'postgresql','sql','relational databases','sql server'}, {'rag','graphrag','retrieval','embeddings','reranking'},
        {'langgraph','langchain','ai agents','agentic systems'}, {'docker','kubernetes','containers'},
        {'grafana','monitoring','observability','telemetry'}, {'rest apis','graphql','apis','api integration'},
    ]
    for g in groups:
        if s in g and any(x in g for x in p): return 'PARTIAL'
    return 'GAP'


def score_job(db: Session, profile: CandidateProfile, job: JobPosting) -> JobAnalysis:
    policy = evaluate_hard_constraints(profile, job)
    required = job.required_skills or []
    preferred = job.preferred_skills or []
    matches, partials, gaps = [], [], []
    for skill in required + preferred:
        m = skill_match(profile.skills, skill)
        (matches if m == 'MATCH' else partials if m == 'PARTIAL' else gaps).append(skill)

    req_n = max(1, len(required))
    req_match = sum(1 for s in required if skill_match(profile.skills, s) == 'MATCH')
    req_partial = sum(1 for s in required if skill_match(profile.skills, s) == 'PARTIAL')
    technical = min(100, 100 * (req_match + 0.5 * req_partial) / req_n) if required else 70

    title_low = job.title.lower()
    role_terms = ' '.join(profile.role_families).lower()
    title_score = 90 if any(t.lower() in title_low or title_low in t.lower() for t in profile.role_families) else (75 if any(w in role_terms for w in title_low.split()) else 55)

    evidence = rank_evidence(db, profile, job)
    evidence_score = min(100, 45 + len(evidence) * 12)

    exp_item = policy['items']['experience']['status']
    experience = {'PASS':100,'REVIEW':65,'FAIL':30}[exp_item]
    workplace = 100 if policy['items']['workplace']['status'] == 'PASS' else 20

    score = round(0.45*technical + 0.15*title_score + 0.20*evidence_score + 0.15*experience + 0.05*workplace, 1)
    if policy['overall'] == 'FAIL': score = min(score, 64.0)

    priority = 'A+' if score >= 90 else 'A' if score >= 82 else 'B+' if score >= 74 else 'B' if score >= 65 else 'C'
    action = 'SKIP' if policy['overall'] == 'FAIL' else ('APPLY' if score >= 78 and policy['overall'] != 'FAIL' else 'REVIEW')
    if policy['overall'] == 'REVIEW' and action == 'APPLY': action = 'REVIEW'

    explanation = f"Technical alignment {technical:.0f}%; {len(matches)} matched, {len(partials)} partial, {len(gaps)} gaps. Hard constraints: {policy['overall']}. Evidence selected: {', '.join(e.title for e in evidence[:3])}."
    return JobAnalysis(job_id=job.id, hard_filter_status=policy['overall'], hard_constraints=policy['items'], fit_score=score,
                       component_scores={'technical':round(technical,1),'role':title_score,'evidence':evidence_score,'experience':experience,'workplace':workplace},
                       priority=priority, matched_skills=sorted(set(matches)), partial_skills=sorted(set(partials)), gap_skills=sorted(set(gaps)),
                       relevant_evidence_ids=[e.id for e in evidence], recommended_action=action, explanation=explanation)
