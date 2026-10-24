"""
Interactive Command Line Interface & Runner
===========================================
Allows researchers to submit a structured research brief (ASK),
configure target countries, publication cutoff rules, and sections,
and monitor the autonomous multi-agent LangGraph workflow in real time.
"""
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import (
    DEFAULT_RESEARCH_SECTIONS, MIN_PUBLICATION_YEAR,
    DATA_PERIOD_START_YEAR, DATA_PERIOD_END_YEAR,
)
from graph.research_graph import compiled_research_graph


def run_interactive():
    print("=" * 75)
    print("  AUTONOMOUS HEALTHCARE & PHARMA RESEARCH SYSTEM")
    print("  Powered by Multi-Agent Architecture & LangGraph")
    print("=" * 75)
    
    topic = input("\nEnter Research Topic / Disease (Default: 'Obesity'): ").strip() or "Obesity"
    countries_input = input("Enter Target Countries separated by comma (Default: 'India'): ").strip() or "India"
    countries = [c.strip() for c in countries_input.split(",") if c.strip()]
    
    print("\nDefault 9 Mandatory Research Sections will be investigated:")
    for idx, sec in enumerate(DEFAULT_RESEARCH_SECTIONS, 1):
        print(f"  {idx}. {sec}")

    use_defaults = input("\nUse all 9 standard sections? (Y/n): ").strip().lower()
    if use_defaults == 'n':
        print("\nEnter section numbers separated by comma (e.g. 1,2,4):")
        chosen_indices = input("Selection: ").strip()
        selected_sections = []
        for part in chosen_indices.split(","):
            if part.strip().isdigit():
                i = int(part.strip()) - 1
                if 0 <= i < len(DEFAULT_RESEARCH_SECTIONS):
                    selected_sections.append(DEFAULT_RESEARCH_SECTIONS[i])
        sections = selected_sections if selected_sections else DEFAULT_RESEARCH_SECTIONS
    else:
        sections = DEFAULT_RESEARCH_SECTIONS

    min_pub_year = _prompt_year("Earliest acceptable publication year", MIN_PUBLICATION_YEAR)
    period_start_year = _prompt_year("Preferred data collection start year", DATA_PERIOD_START_YEAR)
    period_end_year = _prompt_year("Preferred data collection end year", DATA_PERIOD_END_YEAR)
    while period_start_year > period_end_year:
        print("Start year must be less than or equal to end year.")
        period_start_year = _prompt_year("Preferred data collection start year", DATA_PERIOD_START_YEAR)
        period_end_year = _prompt_year("Preferred data collection end year", DATA_PERIOD_END_YEAR)

    print(f"\nConfiguration summary:")
    print(f"  * Disease / Topic : {topic}")
    print(f"  * Countries       : {', '.join(countries)}")
    print(f"  * Total Sections  : {len(sections)}")
    print(f"  * Total Coverage  : {len(countries) * len(sections)} target matrix cells")
    print(f"  * Publication Rule: >= {min_pub_year} (Rule 1)")
    print(f"  * Preferred Data Period: {period_start_year}-{period_end_year} (out-of-window data is reviewed)")
    
    confirm = input("\nStart Autonomous Research Workflow? (Y/n): ").strip().lower()
    if confirm == 'n':
        print("Cancelled.")
        return

    execute_workflow(topic, countries, sections, min_pub_year, period_start_year, period_end_year)


def _prompt_year(label: str, default: int) -> int:
    while True:
        value = input(f"{label} (1900-2100, Default: {default}): ").strip()
        if not value:
            return default
        try:
            year = int(value)
        except ValueError:
            year = 0
        if 1900 <= year <= 2100:
            return year
        print("Enter a whole year between 1900 and 2100.")


def execute_workflow(
    topic: str, countries: list, sections: list,
    min_pub_year: int = MIN_PUBLICATION_YEAR,
    period_start_year: int = DATA_PERIOD_START_YEAR,
    period_end_year: int = DATA_PERIOD_END_YEAR,
):
    initial_state = {
        "topic": topic,
        "disease": topic,
        "countries": countries,
        "sections": sections,
        "min_publication_year": min_pub_year,
        "data_period_start_year": period_start_year,
        "data_period_end_year": period_end_year,
        "data_period_threshold": period_start_year,
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

    print("\n>>> Launching LangGraph Orchestration Engine...")
    result = compiled_research_graph.invoke(initial_state)

    print("\n" + "=" * 75)
    print("  RESEARCH WORKFLOW EXECUTION COMPLETED")
    print("=" * 75)
    print(f"Final Project Status : {result.get('status')}")
    print(f"Total Validated Sources: {len(result.get('validated_sources', []))}")
    print(f"Total Insights Extracted: {len(result.get('insights', []))}")
    verified_quotes = [
        item for item in result.get("verbatims", [])
        if item.get("match_verified") is True and item.get("verification_status") == "verified_exact_match"
    ]
    print(f"Total Verified Verbatims: {len(verified_quotes)}")
    print(f"Spreadsheet Deliverable : {result.get('excel_file_path')}")
    print(f"Word Report Deliverable : {result.get('docx_file_path')}")
    print("=" * 75)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Healthcare Research Automation")
    parser.add_argument("--demo", action="store_true", help="Run automated default demonstration on Obesity in India")
    args = parser.parse_args()

    if args.demo:
        print("[DEMO MODE] Running default research brief: Obesity in India...")
        execute_workflow("Obesity", ["India"], DEFAULT_RESEARCH_SECTIONS)
    else:
        run_interactive()
