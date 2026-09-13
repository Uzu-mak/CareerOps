from __future__ import annotations
from pydantic import BaseModel, Field

class ProfileUpdate(BaseModel):
    full_name: str
    preferred_name: str | None=None
    email: str | None=None
    phone: str | None=None
    home_location: str | None=None
    linkedin_url: str | None=None
    github_url: str | None=None
    role_families: list[str]=Field(default_factory=list)
    skills: list[str]=Field(default_factory=list)
    preferred_locations: list[str]=Field(default_factory=list)
    search_radius_miles: int=50
    minimum_salary: int | None=None
    target_salary: int | None=None
    remote_allowed: bool=True
    hybrid_allowed: bool=True
    onsite_allowed: bool=True
    years_professional_software: float=0
    years_hands_on_software: float=0
    authorized_to_work_us: bool | None=None
    requires_current_sponsorship: bool | None=None
    requires_future_sponsorship: bool | None=None
    work_authorization_type: str | None=None
    work_authorization_expiration: str | None=None

class ManualJobIn(BaseModel):
    company: str
    title: str
    location: str | None=None
    workplace_type: str | None=None
    employment_type: str | None='full-time'
    description: str
    canonical_url: str | None=None
    application_url: str | None=None
    salary_min: int | None=None
    salary_max: int | None=None
    required_years: float | None=None
    required_skills: list[str]=Field(default_factory=list)
    preferred_skills: list[str]=Field(default_factory=list)
    sponsorship_policy: str='unknown'
    company_mission: str | None=None
