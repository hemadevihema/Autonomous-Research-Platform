"""
Stage 7: Autonomous Correction and Recovery Coordinator
========================================================
Analyzes QC gaps and missing country-section coverage cells.
Generates targeted recovery search queries specifically for under-covered areas,
manages bounded retries, and prevents infinite loops.
"""
from typing import Dict, Any, List
from config.settings import (
    SECTION_KEYWORDS, MAX_RECOVERY_ATTEMPTS,
    MAX_YEAR_GAP_QUERIES_PER_ATTEMPT,
)


class AutonomousCorrectionEngine:
    """Coordinator handling self-healing, targeted recovery, and gap remediation."""

    def prepare_recovery(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate if recovery loop should execute.
        If under limits, construct targeted queries for missing coverage cells.
        """
        attempts = state.get("recovery_attempts", 0)
        missing_cells = state.get("missing_sections", [])
        year_gaps = state.get("year_coverage_gaps", [])
        disease = state.get("disease", "Obesity")
        min_year = state.get("min_publication_year", 2021)

        print(f"\n[Stage 7: Correction Engine] Evaluating Recovery Loop (Attempt {attempts + 1}/{MAX_RECOVERY_ATTEMPTS})...")

        if attempts >= MAX_RECOVERY_ATTEMPTS or not (missing_cells or year_gaps):
            print("  - Max recovery attempts reached or no missing cells. Proceeding to Deliverables generation.")
            return {
                "recovery_needed": False,
                "status": "Recovery completed or limit reached",
            }

        # First scout empty domains, then target years not covered by verified sources.
        targeted_queries: List[Dict[str, str]] = []
        # Rotate the bounded batch between attempts so sections at the end of
        # the configured list are not starved by the same first few gaps.
        batch_size = MAX_YEAR_GAP_QUERIES_PER_ATTEMPT
        if missing_cells:
            start = (attempts * batch_size) % len(missing_cells)
            rotated_cells = missing_cells[start:] + missing_cells[:start]
        else:
            rotated_cells = []
        for cell in rotated_cells[:batch_size]:
            # cell format: "Country | Section"
            parts = cell.split(" | ")
            if len(parts) == 2:
                country, section = parts[0].strip(), parts[1].strip()
                kws = " ".join(SECTION_KEYWORDS.get(section, ["health"])[:2])
                targeted_queries.append({
                    "country": country,
                    "section": section,
                    "coverage_key": cell,
                    "query": f"{disease} {country} {kws}"
                })

        remaining = max(0, MAX_YEAR_GAP_QUERIES_PER_ATTEMPT - len(targeted_queries))
        for cell in year_gaps[:remaining]:
            parts = cell.split(" | ")
            if len(parts) != 3:
                continue
            country, section, raw_year = (part.strip() for part in parts)
            if not raw_year.isdigit():
                continue
            year = int(raw_year)
            kws = " ".join(SECTION_KEYWORDS.get(section, [section])[:2])
            targeted_queries.append({
                "country": country,
                "section": section,
                "coverage_key": cell,
                "data_year": year,
                "query": f"{disease} {country} {kws} data collected {year} survey {year}",
            })

        print(f"  - Generated {len(targeted_queries)} targeted recovery queries for source and year gaps.")
        for tq in targeted_queries:
            print(f"    -> Target: [{tq['country']} | {tq['section']}]")

        audit_trail = state.get("audit_trail", [])
        audit_trail.append(f"Autonomous recovery triggered: Attempt {attempts + 1} targeting {len(targeted_queries)} missing cells.")

        return {
            "recovery_needed": True,
            "recovery_attempts": attempts + 1,
            "targeted_queries": targeted_queries,
            "status": f"Recovery in progress (Attempt {attempts + 1})",
            "audit_trail": audit_trail,
        }
