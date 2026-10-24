"""
End-to-End Autonomous Research System Execution Script
======================================================
Executes the complete multi-agent pipeline for the standard organization ASK:
- Condition: Obesity
- Target Country: India
- Required Sections: All 9 mandatory sections
- Rule 1: Publication Year >= 2021
- Rule 2: Data Period analysis
- Stage 8: Real Excel spreadsheet & Word document deliverables
"""
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import (
    DEFAULT_RESEARCH_SECTIONS, MIN_PUBLICATION_YEAR,
    DATA_PERIOD_START_YEAR, DATA_PERIOD_END_YEAR,
)
from graph.research_graph import compiled_research_graph


def main():
    print("=" * 80)
    print("   AUTONOMOUS PHARMA & HEALTHCARE RESEARCH AUTOMATION SYSTEM")
    print("   Orchestrator: LangGraph | State Persistence: SQLite | Deliverables: XLSX & DOCX")
    print("=" * 80)

    start_time = time.time()

    project_id = sys.argv[1] if len(sys.argv) > 1 else "PROJ-91EFDA0F"

    initial_state = {
        "project_id": project_id,
        "topic": "Obesity",
        "disease": "Obesity",
        "countries": ["India"],
        "sections": DEFAULT_RESEARCH_SECTIONS,
        "min_publication_year": MIN_PUBLICATION_YEAR,
        "data_period_start_year": DATA_PERIOD_START_YEAR,
        "data_period_end_year": DATA_PERIOD_END_YEAR,
        "data_period_threshold": DATA_PERIOD_START_YEAR,
        "recovery_attempts": 0,
        "recovery_needed": False,
        "candidate_sources": [],
        "validated_sources": [],
        "rejected_sources": [],
        "insights": [],
        "verbatims": [],
        "status": "Starting workflow",
        "audit_trail": [],
    }

    print("\n[WORKFLOW LAUNCH] Submitting research brief to LangGraph StateGraph:")
    print("  - Disease Focus    : Obesity")
    print("  - Geography        : India")
    print("  - Required Sections: 9 Mandatory Sections")
    print(f"  - Publication Rule : Year >= {MIN_PUBLICATION_YEAR} (Rule 1 strictly enforced)")
    print(f"  - Preferred Data Period : {DATA_PERIOD_START_YEAR}-{DATA_PERIOD_END_YEAR} (out-of-window data is reviewed)")
    print("-" * 80)

    # Invoke the compiled graph
    final_state = compiled_research_graph.invoke(initial_state)

    elapsed = time.time() - start_time

    print("\n" + "=" * 80)
    print("   WORKFLOW FINISHED IN {:.2f} SECONDS".format(elapsed))
    print("=" * 80)
    print(f"  Status                  : {final_state.get('status')}")
    print(f"  Validated Sources Count : {len(final_state.get('validated_sources', []))}")
    rejected = [s for s in final_state.get("rejected_sources", []) if s.get("validation_status") != "Needs review"]
    print(f"  Rejected Sources Count  : {len(rejected)}")
    print(f"  Review Sources Count    : {len(final_state.get('review_sources', []))}")
    print(f"  Extracted Insights      : {len(final_state.get('insights', []))}")
    verified_quotes = [
        item for item in final_state.get("verbatims", [])
        if item.get("match_verified") is True and item.get("verification_status") == "verified_exact_match"
    ]
    print(f"  Verified Verbatims      : {len(verified_quotes)}")
    print(f"  Master Excel Deliverable: {final_state.get('excel_file_path')}")
    print(f"  Master Word Deliverable : {final_state.get('docx_file_path')}")
    
    qc = final_state.get("qc_report", {})
    print(f"  QC Completion Score     : {qc.get('completion_score_percent', 0)}%")
    print(f"  QC Overall Assessment   : {qc.get('overall_status')}")
    print("=" * 80)


if __name__ == "__main__":
    main()
