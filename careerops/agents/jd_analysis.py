from __future__ import annotations
import re
from careerops.db.models import JobPosting

SKILL_LIBRARY = [
    'Python','SQL','PostgreSQL','FastAPI','Django','Java','C++','JavaScript','TypeScript','React','Next.js','Angular',
    'REST APIs','GraphQL','Spark','PySpark','Dask','pandas','AWS','GCP','Azure','Docker','Kubernetes','Git','CI/CD',
    'Palantir Foundry','Elasticsearch','RAG','GraphRAG','LLMs','Generative AI','LangChain','LangGraph','AI agents',
    'machine learning','data engineering','distributed systems','monitoring','Grafana','Power BI','dbt','BigQuery','Neo4j','Qdrant'
]


def _contains(text: str, skill: str) -> bool:
    aliases = {
        'REST APIs':['rest api','restful api','rest services'], 'CI/CD':['ci/cd','continuous integration','continuous deployment'],
        'LLMs':['llm','large language model'], 'AI agents':['ai agent','agentic'], 'Generative AI':['generative ai','genai'],
        'Palantir Foundry':['palantir foundry','foundry'], 'machine learning':['machine learning',' ml '],
    }
    phrases = aliases.get(skill, [skill.lower()])
    low = ' ' + text.lower() + ' '
    return any(p in low for p in phrases)


def parse_salary(text: str):
    nums = []
    for m in re.finditer(r'\$\s*([0-9]{2,3}(?:,[0-9]{3})+|[0-9]{2,3})(?:\s*[kK])?', text):
        raw = m.group(0).replace('$','').replace(',','').strip()
        k = raw.lower().endswith('k')
        raw = raw[:-1] if k else raw
        try:
            val = int(float(raw) * (1000 if k else 1))
            if 20000 <= val <= 1000000: nums.append(val)
        except ValueError: pass
    return (min(nums), max(nums)) if nums else (None, None)


def analyze_job_text(job: JobPosting) -> dict:
    text = job.description or ''
    skills = [s for s in SKILL_LIBRARY if _contains(text, s)]
    years = None
    ym = re.search(r'(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)', text, re.I)
    if ym: years = float(ym.group(1))
    low = text.lower()
    sponsorship = job.sponsorship_policy
    if sponsorship == 'unknown':
        if any(p in low for p in ['no sponsorship','without sponsorship','will not sponsor','not provide sponsorship','without the need for current or future employer sponsorship']):
            sponsorship = 'unavailable'
        elif any(p in low for p in ['visa sponsorship','eligible for visa sponsorship','sponsorship available']):
            sponsorship = 'available'
    clearance = job.clearance_required or any(p in low for p in ['security clearance required','active clearance','must be a u.s. citizen','us citizen required'])
    salary_min, salary_max = (job.salary_min, job.salary_max)
    if salary_min is None and salary_max is None:
        salary_min, salary_max = parse_salary(text)
    responsibilities = job.responsibilities or [
        ln.lstrip('•-* ').strip() for ln in text.splitlines()
        if len(ln.strip()) > 25 and any(v in ln.lower() for v in ['build ','design ','develop ','create ','implement ','collaborate ','own '])
    ][:8]
    return {
        'required_years': job.required_years if job.required_years is not None else years,
        'detected_skills': skills,
        'salary_min': salary_min,
        'salary_max': salary_max,
        'sponsorship_policy': sponsorship,
        'clearance_required': clearance,
        'responsibilities': responsibilities,
    }
