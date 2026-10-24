"""
Stage 1: Research Intake and Planning Agent
===========================================
Interprets and validates the research brief (ASK). Decomposes requirements
into structured country-section coverage targets, establishes publication
and data period cutoff rules, and generates targeted search query plans.
"""
import uuid
import re
from typing import Dict, Any, List
from config.settings import (
    DEFAULT_RESEARCH_SECTIONS,
    MIN_PUBLICATION_YEAR,
    DATA_PERIOD_START_YEAR,
    DATA_PERIOD_END_YEAR,
    SECTION_KEYWORDS,
)
from core.models import ResearchPlan
from storage.database import ResearchDatabase


class ResearchPlanner:
    """Agent responsible for research brief validation and coverage planning."""

    def __init__(self, db: ResearchDatabase = None):
        self.db = db or ResearchDatabase()

    def plan_research(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Validate input brief and construct the master research plan."""
        topic = state.get("topic", "").strip()
        disease = state.get("disease", "").strip() or topic
        countries = state.get("countries", [])
        
        # Normalize single country to list if passed as string
        if isinstance(countries, str):
            countries = [c.strip() for c in countries.split(",") if c.strip()]
        if not countries:
            # Default to India if unspecified in initial prompt
            countries = ["India"]

        sections = state.get("sections") or DEFAULT_RESEARCH_SECTIONS
        min_pub_year = state.get("min_publication_year")
        if min_pub_year is None:
            min_pub_year = MIN_PUBLICATION_YEAR
        data_period_start_year = state.get("data_period_start_year")
        if data_period_start_year is None:
            data_period_start_year = state.get("data_period_threshold", DATA_PERIOD_START_YEAR)
        data_period_end_year = state.get("data_period_end_year")
        if data_period_end_year is None:
            data_period_end_year = DATA_PERIOD_END_YEAR
        for label, year in (
            ("publication cutoff year", min_pub_year),
            ("data period start year", data_period_start_year),
            ("data period end year", data_period_end_year),
        ):
            if not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year <= 2100:
                raise ValueError(f"{label} must be a whole year between 1900 and 2100.")
        if data_period_start_year > data_period_end_year:
            raise ValueError("Data period start year must be less than or equal to end year.")
        project_id = state.get("project_id") or f"PROJ-{uuid.uuid4().hex[:8].upper()}"

        print(f"\n[Stage 1: Planner] Validating ASK for Project {project_id}")
        print(f"  - Disease/Topic : {disease}")
        print(f"  - Target Country: {', '.join(countries)}")
        print(f"  - Sections Count: {len(sections)} sections")
        print(f"  - Year Cutoff   : >= {min_pub_year} (Strict Rule 1)")
        print(f"  - Data Period   : {data_period_start_year}-{data_period_end_year} (out-of-range data flagged for review)")

        # Generate targeted query plans for each Country x Section combination
        generated_queries: List[Dict[str, str]] = []
        required_coverage_keys: List[str] = []

        for country in countries:
            for section in sections:
                coverage_key = f"{country} | {section}"
                required_coverage_keys.append(coverage_key)
                
                # Extract keywords dynamically from section title if custom
                sec_tokens = [w for w in re.split(r"\W+", section) if len(w) > 3 and w.lower() not in ["and", "with", "from", "for"]]
                kw_list = SECTION_KEYWORDS.get(section, sec_tokens or ["healthcare"])
                kws = " ".join(kw_list[:3])
                
                # Keep provider queries focused on the subject, geography, and section.
                # Publication and data-period rules are applied after retrieval from source metadata.
                query_str = f"{disease} {country} {kws}"
                generated_queries.append({
                    "country": country,
                    "section": section,
                    "coverage_key": coverage_key,
                    "query": query_str
                })

        plan = ResearchPlan(
            project_id=project_id,
            topic=topic,
            disease=disease,
            countries=countries,
            sections=sections,
            min_publication_year=min_pub_year,
            data_period_start_year=data_period_start_year,
            data_period_end_year=data_period_end_year,
            data_period_threshold=data_period_start_year,
            generated_queries=generated_queries,
            required_coverage_keys=required_coverage_keys,
        )

        # Persist project in DB
        self.db.save_project(
            project_id=project_id,
            topic=topic,
            disease=disease,
            countries=countries,
            sections=sections,
            min_year=min_pub_year,
            status="PLANNED",
        )
        self.db.log_audit_event(
            project_id=project_id,
            stage="PLANNING",
            message=f"Research plan created. Total target coverage cells: {len(required_coverage_keys)}",
        )

        return {
            "project_id": project_id,
            "topic": topic,
            "disease": disease,
            "countries": countries,
            "sections": sections,
            "min_publication_year": min_pub_year,
            "data_period_start_year": data_period_start_year,
            "data_period_end_year": data_period_end_year,
            "data_period_threshold": data_period_start_year,
            "plan": plan.model_dump(),
            "status": "Plan established",
            "audit_trail": [f"[{project_id}] Master plan generated with {len(required_coverage_keys)} targets."],
        }
