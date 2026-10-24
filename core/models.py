"""
Data Schemas and Domain Models
===============================
Strongly typed Pydantic models for projects, sources, insights, quotations,
validation status, quality control, and exportable records.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    CANDIDATE = "Candidate"
    RETRIEVED = "Retrieved"
    PASSED_CHECKS = "Passed initial checks"
    VERIFIED = "Verified for claim/quotation"
    NEEDS_REVIEW = "Needs review"
    REJECTED = "Rejected"
    INACCESSIBLE = "Inaccessible"
    UNRESOLVED = "Unresolved"


class SourceType(str, Enum):
    RESEARCH_ARTICLE = "Research article"
    GOVERNMENT_REPORT = "Government report"
    CLINICAL_GUIDELINE = "Clinical guideline"
    REGULATORY_PUBLICATION = "Regulatory publication"
    NEWS_ARTICLE = "News article"
    OTHER = "Other authoritative publication"


class AccessType(str, Enum):
    OPEN_ACCESS = "Open Access"
    RESTRICTED = "Restricted Access"
    ABSTRACT_ONLY = "Abstract-only"
    SUBSCRIPTION = "Subscription"


class VerbatimRecord(BaseModel):
    """Exact verbatim quotation extracted and verified against source text."""
    id: str
    source_id: str
    country: str
    section: str
    exact_quote: str
    context: str = ""
    location_reference: str = "Abstract / Findings"
    match_verified: bool = False
    verification_status: str = "unverified"
    supports_insight_ids: List[str] = Field(default_factory=list)
    url: str = ""


class InsightRecord(BaseModel):
    """Structured evidence-backed analytical insight extracted from verified sources."""
    id: str
    source_id: str
    country: str
    section: str
    insight_text: str
    evidence_passage: str
    relevance_explanation: str
    location_reference: str = "Source text"
    publication_date: str = ""
    data_period: str = "Unknown"
    is_verified: bool = False
    verification_status: str = "unresolved"
    supporting_verbatim_ids: List[str] = Field(default_factory=list)
    limitations: str = "None noted"


class SourceRecord(BaseModel):
    """Comprehensive source entity matching both internal workflow and spreadsheet output."""
    id: str
    source_title: str
    name_of_source: str  # Publisher, journal, or organization
    source_type: str = SourceType.RESEARCH_ARTICLE.value
    publication_year: Optional[int] = None
    data_period: str = "Unknown"
    data_period_start_year: Optional[int] = None
    data_period_end_year: Optional[int] = None
    data_period_type: str = "unknown"
    data_period_evidence: str = ""
    data_period_location: str = ""
    data_period_status: str = "Unknown"
    description: str = ""
    access_type: str = AccessType.OPEN_ACCESS.value
    source_link: str = ""
    canonical_url: Optional[str] = None
    sections_covered: List[str] = Field(default_factory=list)
    summary: str = ""
    insights: str = ""
    verbatim: str = ""
    visual: str = "None found in retrieved text"
    
    # Internal validation and research metadata
    country: str = ""
    disease: str = ""
    full_text_or_abstract: str = ""
    content_completeness: str = "unknown"
    content_chunks: List[Dict[str, str]] = Field(default_factory=list)
    extraction_status: str = "pending"
    extraction_quality: Dict[str, Any] = Field(default_factory=dict)
    validation_status: ValidationStatus = ValidationStatus.CANDIDATE
    validation_reasons: List[str] = Field(default_factory=list)
    validation_checks: Dict[str, Any] = Field(default_factory=dict)
    retrieval_timestamp: str = ""
    # Provider provenance retained internally for authenticity and publication-year audits.
    source_provider: str = ""
    provider_record_id: str = ""
    provider_record_url: str = ""
    source_authenticity_verified: bool = False
    publication_year_verified: bool = False

    def to_spreadsheet_row(self, serial_num: int) -> Dict[str, Any]:
        """Convert to the exact 14 columns of the organization spreadsheet."""
        return {
            "S. No.": serial_num,
            "Source Title": self.source_title,
            "Name of the Source": self.name_of_source,
            "Source Type (Research article, news, etc)": self.source_type,
            "Year of Publication": self.publication_year if self.publication_year else "Unknown",
            "Period of the data used": self.data_period,
            "Description": self.description,
            "Access Type": self.access_type,
            "Source Link": self.source_link,
            "Sections Covered": "; ".join(self.sections_covered) if self.sections_covered else "General",
            "Summary": self.summary,
            "Insights": self.insights,
            "Verbatim": self.verbatim,
            "Visual": self.visual,
        }


class QCIssue(BaseModel):
    severity: str  # "CRITICAL", "MAJOR", "MINOR", "INFO"
    category: str  # "Coverage", "Source Quality", "Evidence Integrity", "Spreadsheet"
    message: str
    affected_record_id: Optional[str] = None
    recommendation: str
    is_resolved: bool = False


class QCReport(BaseModel):
    """Complete Quality Control audit report."""
    total_sources_scouted: int = 0
    passed_sources_count: int = 0
    rejected_sources_count: int = 0
    review_needed_count: int = 0
    coverage_matrix: Dict[str, int] = Field(default_factory=dict)  # "Country | Section" -> count
    year_wise_coverage: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    year_coverage_gaps: List[str] = Field(default_factory=list)
    missing_coverage: List[str] = Field(default_factory=list)
    issues: List[QCIssue] = Field(default_factory=list)
    overall_status: str = "PENDING"  # "PASSED", "PASSED_WITH_LIMITATIONS", "FAILED"
    completion_score_percent: float = 0.0
    qc_checks_passed: int = 0
    qc_checks_failed: int = 0
    qc_checks_review: int = 0
    qc_checks_total: int = 0


class ResearchPlan(BaseModel):
    """Structured machine-readable research plan parsed from the research ASK."""
    project_id: str
    topic: str
    disease: str
    countries: List[str]
    sections: List[str]
    min_publication_year: int = 2021
    data_period_start_year: int = 2021
    data_period_end_year: int = 2026
    data_period_threshold: int = 2021
    generated_queries: List[Dict[str, str]] = Field(default_factory=list)
    required_coverage_keys: List[str] = Field(default_factory=list)
