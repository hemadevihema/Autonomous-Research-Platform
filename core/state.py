"""
LangGraph Shared Workflow State
================================
Typed state dictionary managed by the LangGraph orchestrator.
Preserves records, coverage matrix, audit events, and artifact file paths across nodes.
"""
from typing import TypedDict, List, Dict, Any, Optional


class ResearchSystemState(TypedDict, total=False):
    # Stage 1: Intake & Planning
    project_id: str
    topic: str
    disease: str
    treatment_focus: str
    countries: List[str]
    sections: List[str]
    min_publication_year: int
    data_period_start_year: int
    data_period_end_year: int
    # Backwards-compatible alias for older local callers.
    data_period_threshold: int
    max_sources_per_section: int
    min_insights_per_source: int
    min_verbatims_per_source: int
    plan: Dict[str, Any]
    
    # Stage 2: Scouting
    candidate_sources: List[Dict[str, Any]]
    provider_diagnostics: List[Dict[str, Any]]
    
    # Stage 3: Validation
    validated_sources: List[Dict[str, Any]]
    review_sources: List[Dict[str, Any]]
    rejected_sources: List[Dict[str, Any]]
    
    # Stage 4 & 5: Insights and Verbatim
    insights: List[Dict[str, Any]]
    verbatims: List[Dict[str, Any]]
    extraction_completeness: Dict[str, Dict[str, Any]]
    
    # Stage 6: Quality Control
    qc_report: Dict[str, Any]
    coverage_matrix: Dict[str, int]
    year_wise_coverage: Dict[str, Dict[str, Any]]
    year_coverage_gaps: List[str]
    missing_sections: List[str]
    
    # Stage 7: Autonomous Recovery Loop
    recovery_attempts: int
    recovery_needed: bool
    
    # Stage 8: Deliverables and Tracking
    excel_file_path: Optional[str]
    docx_file_path: Optional[str]
    status: str
    audit_trail: List[str]
