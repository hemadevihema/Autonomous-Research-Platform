"""
Project Configuration and Global Constants
===========================================
Defines research sections, spreadsheet column templates, publication date rules,
data-period thresholds, and default parameters for the Research Automation System.
"""
import sys
from pathlib import Path
from typing import List

# Ensure safe UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
DATABASE_PATH = BASE_DIR / "storage" / "research_vault.db"

# The 9 Mandatory Research Sections defined in Master Prompt
DEFAULT_RESEARCH_SECTIONS: List[str] = [
    "Healthcare system overview",
    "Epidemiology",
    "Societal & Provider Perception of Obesity",
    "Clinical Guidelines & Treatment Practices",
    "Regulatory Framework & Approval Bodies",
    "Unmet Needs & Clinical Gaps",
    "Access, Coverage & Reimbursement Barriers",
    "Competitive Landscape & Product Intelligence",
    "Patient Advocacy, Public Affairs & Strategic Initiatives",
]

# Section keyword triggers for accurate classification
SECTION_KEYWORDS = {
    "Healthcare system overview": [
        "healthcare system", "public health", "health infrastructure", "ayushman bharat",
        "health policy", "hospitals", "health spending", "universal healthcare", "delivery system", "insurance", "nhs", "medicare"
    ],
    "Epidemiology": [
        "epidemiology", "prevalence", "incidence", "morbidity", "mortality",
        "burden of disease", "demographics", "risk factors", "epidemiological", "statistics", "bmi trends"
    ],
    "Societal & Provider Perception of Obesity": [
        "stigma", "perception", "bias", "societal attitude", "provider attitude",
        "awareness", "lifestyle choice", "discrimination", "psychosocial", "patient perspective", "physician beliefs"
    ],
    "Clinical Guidelines & Treatment Practices": [
        "clinical guidelines", "treatment guidelines", "practice guidelines", "management of obesity",
        "pharmacotherapy", "bariatric surgery", "lifestyle intervention", "consensus", "recommendations", "dosage", "clinical practice",
        "prescribing practices", "prescribing patterns", "antiobesity medications", "anti-obesity medications",
        "obesity medications", "drug therapy", "treatment efficacy", "medical management"
    ],
    "Regulatory Framework & Approval Bodies": [
        "regulatory", "approval", "cdsco", "dcgi", "marketing authorization",
        "clinical trials", "drug evaluation", "compliance", "policy framework", "indication", "fda", "ema", "mhra"
    ],
    "Unmet Needs & Clinical Gaps": [
        "barriers", "challenges", "unmet need", "clinical gap", "treatment gap", "adherence", "long-term efficacy",
        "tolerability", "adverse events", "weight regain", "underdiagnosis", "barriers to care"
    ],
    "Access, Coverage & Reimbursement Barriers": [
        "affordability", "reimbursement", "cost barrier", "high costs", "cost barriers", "financial access",
        "insurance coverage", "access barrier", "health economics", "cost-effectiveness", "out-of-pocket", "payer", "pricing", "copay", "hta", "nice guidance"
    ],
    "Competitive Landscape & Product Intelligence": [
        "semaglutide", "tirzepatide", "glp-1", "pipeline", "competitors", "market share",
        "novo nordisk", "eli lilly", "wegovy", "ozempic", "mounjaro", "zepbound", "clinical trial pipeline"
    ],
    "Patient Advocacy, Public Affairs & Strategic Initiatives": [
        "advocacy", "awareness", "initiative", "campaign", "patient advocacy", "public affairs", "strategic initiative",
        "community engagement", "ngo", "policy initiative", "coalition", "world obesity federation"
    ],
}

# The 14 Exact Spreadsheet Column Headers (in exact mandatory order)
SPREADSHEET_COLUMNS: List[str] = [
    "S. No.",
    "Source Title",
    "Name of the Source",
    "Source Type (Research article, news, etc)",
    "Year of Publication",
    "Period of the data used",
    "Description",
    "Access Type",
    "Source Link",
    "Sections Covered",
    "Summary",
    "Insights",
    "Verbatim",
    "Visual",
]

# Non-Negotiable Source Validation Rules
MIN_PUBLICATION_YEAR: int = 2021  # Rule 1: 2021 onward is accepted, <= 2020 rejected
DATA_PERIOD_START_YEAR: int = 2021  # Preferred underlying data collection period
DATA_PERIOD_END_YEAR: int = 2026
# Backwards-compatible alias for older API clients and local scripts.
DATA_PERIOD_OLD_THRESHOLD: int = DATA_PERIOD_START_YEAR

# Scouting and Recovery Constraints (Expanded for deep, high-volume literature harvesting)
MAX_SCOUT_RESULTS_PER_SECTION: int = 20
MAX_RECOVERY_ATTEMPTS: int = 2
MAX_YEAR_GAP_QUERIES_PER_ATTEMPT: int = 6
MIN_ACCEPTABLE_CONFIDENCE: float = 0.65
# Completeness targets are quality checks, never quotas to fill with generated text.
MIN_INSIGHTS_PER_SOURCE: int = 3
MIN_VERBATIMS_PER_SOURCE: int = 2
