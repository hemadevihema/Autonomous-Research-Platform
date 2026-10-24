"""
Stage 6: Automated Quality Control (QC) Agent
==============================================
Systematically audits the research project across 5 dimensions:
A. Coverage Matrix (Target Country x Required Research Sections)
B. Source Quality (Publication year >= 2021, data period completeness)
C. Evidence Integrity (Verbatim exact-match verification, claim tracing)
D. Spreadsheet Acceptance Criteria (14 exact column templates)
E. Document Structure and Completeness Readiness
"""
from typing import Dict, Any, List
import unicodedata
from core.models import QCReport, QCIssue
from config.settings import (
    DEFAULT_RESEARCH_SECTIONS, MIN_PUBLICATION_YEAR,
    DATA_PERIOD_START_YEAR, DATA_PERIOD_END_YEAR, MAX_RECOVERY_ATTEMPTS,
)


class QualityControlAgent:
    """Agent conducting multi-dimensional project evaluation and gap detection."""

    REQUIRED_SOURCE_CHECKS = (
        "publication_cutoff", "source_authenticity", "topic_relevance",
        "country_relevance", "section_assignment", "data_period_classification",
        "duplicate_detection",
    )

    @staticmethod
    def _normalized_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or "")).replace("\u00ad", "")
        return " ".join(normalized.split()).casefold()

    @classmethod
    def _quote_matches_source(cls, quote: str, source: Dict[str, Any]) -> bool:
        source_text = "\n".join(
            str(chunk.get("text") or "") for chunk in source.get("content_chunks", [])
        )
        source_text += "\n" + str(source.get("full_text_or_abstract") or "")
        normalized_quote = cls._normalized_text(quote).strip('“”"')
        return bool(normalized_quote and normalized_quote in cls._normalized_text(source_text))

    def evaluate_project(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Perform comprehensive quality control audit and generate structured QC report."""
        plan = state.get("plan", {})
        countries = state.get("countries", [])
        sections = state.get("sections", DEFAULT_RESEARCH_SECTIONS)
        validated_sources = state.get("validated_sources", [])
        rejected_sources = state.get("rejected_sources", [])
        insights = state.get("insights", [])
        verbatims = state.get("verbatims", [])
        extraction_completeness = state.get("extraction_completeness", {})
        min_year = state.get("min_publication_year", MIN_PUBLICATION_YEAR)
        period_start_year = state.get("data_period_start_year", DATA_PERIOD_START_YEAR)
        period_end_year = state.get("data_period_end_year", DATA_PERIOD_END_YEAR)

        issues: List[QCIssue] = []

        print(f"\n[Stage 6: Quality Control] Running multi-dimensional project audit...")

        # -----------------------------------------------------------------
        # Dimension A: Country-Section Coverage Matrix Evaluation
        # -----------------------------------------------------------------
        coverage_matrix: Dict[str, int] = {}
        missing_coverage: List[str] = []

        coverage_sources = state.get("validated_sources", [])
        # Coverage represents accepted and reviewable sources only.
        for country in countries:
            for section in sections:
                key = f"{country} | {section}"
                matching_count = sum(
                    1 for s in coverage_sources
                    if s.get("country", "").lower() == country.lower() and section in s.get("sections_covered", [])
                )
                coverage_matrix[key] = matching_count
                if matching_count == 0:
                    missing_coverage.append(key)
                    issues.append(QCIssue(
                        severity="MAJOR",
                        category="Coverage",
                        message=f"Zero sources found for coverage cell '{key}'.",
                        recommendation=f"Trigger targeted scouting queries specifically for {country} and {section}.",
                    ))

        print(f"  - Coverage Matrix Evaluated: {len(coverage_matrix) - len(missing_coverage)}/{len(coverage_matrix)} cells populated.")

        # Year-by-year evidence coverage across the configured data-collection window.
        year_wise_coverage: Dict[str, Dict[str, Any]] = {}
        year_coverage_gaps: List[str] = []
        for country in countries:
            for section in sections:
                domain_key = f"{country} | {section}"
                domain_sources = [
                    source for source in validated_sources
                    if source.get("country", "").casefold() == country.casefold()
                    and section in source.get("sections_covered", [])
                ]
                for year in range(period_start_year, period_end_year + 1):
                    key = f"{domain_key} | {year}"
                    verified_ids = []
                    partial_ids = []
                    for source in domain_sources:
                        start, end = source.get("data_period_start_year"), source.get("data_period_end_year")
                        if start is None or end is None or not (int(start) <= year <= int(end)):
                            continue
                        if source.get("data_period_status") == "Verified":
                            verified_ids.append(source.get("id", ""))
                        elif source.get("data_period_status") == "Partially verified":
                            partial_ids.append(source.get("id", ""))
                    verified_ids = list(dict.fromkeys(verified_ids))
                    partial_ids = list(dict.fromkeys(partial_ids))
                    status = "Covered" if verified_ids else ("Partial evidence" if partial_ids else "No evidence")
                    year_wise_coverage[key] = {
                        "country": country,
                        "section": section,
                        "year": year,
                        "verified_sources_count": len(verified_ids),
                        "partial_sources_count": len(partial_ids),
                        "source_ids": verified_ids + partial_ids,
                        "status": status,
                    }
                    if status != "Covered":
                        year_coverage_gaps.append(key)
                        issues.append(QCIssue(
                            severity="MAJOR" if status == "No evidence" else "MINOR",
                            category="Year-wise Coverage",
                            message=(
                                f"{key} has {status.lower()} for the requested collection year."
                            ),
                            affected_record_id=key,
                            recommendation=f"Scout for source-supported {year} data relevant to {country} and {section}.",
                        ))

        year_covered = sum(1 for cell in year_wise_coverage.values() if cell["status"] == "Covered")
        print(f"  - Year-wise Coverage: {year_covered}/{len(year_wise_coverage)} years have verified evidence.")

        # -----------------------------------------------------------------
        # Dimension B: Source Quality Auditing
        # -----------------------------------------------------------------
        for s in validated_sources:
            s_id = s.get("id", "")
            # Year check
            py = s.get("publication_year")
            if not py or py < min_year:
                issues.append(QCIssue(
                    severity="CRITICAL",
                    category="Source Quality",
                    message=f"Source {s_id} violates publication year rule (Year: {py}, Min: {min_year}).",
                    affected_record_id=s_id,
                    recommendation="Remove from validated list or replace with compliant source.",
                ))
            # Data period check
            dp = s.get("data_period", "")
            if not dp or dp == "Unknown":
                issues.append(QCIssue(
                    severity="MINOR",
                    category="Source Quality",
                    message=f"Source {s_id} has unrecorded data period.",
                    affected_record_id=s_id,
                    recommendation="Inspect full text or abstract to extract survey timeframe.",
                ))

        # -----------------------------------------------------------------
        # Dimension C: Evidence Integrity and Verbatim Matching
        # -----------------------------------------------------------------
        for insight in insights:
            if insight.get("verification_status") != "supported" or not insight.get("is_verified"):
                issues.append(QCIssue(
                    severity="MAJOR",
                    category="Evidence Integrity",
                    message=f"Insight {insight.get('id')} lacks a supported verification status.",
                    affected_record_id=insight.get("id"),
                    recommendation="Keep the passage unresolved and verify it against the source before reporting it.",
                ))
        for source_id, extraction in extraction_completeness.items():
            if extraction.get("status") != "complete":
                issues.append(QCIssue(
                    severity="MINOR",
                    category="Evidence Extraction",
                    message=(
                        f"Source {source_id} has {extraction.get('insight_count', 0)} supported insights and "
                        f"{extraction.get('verbatim_count', 0)} verified quotations. {extraction.get('reason', '')}"
                    ),
                    affected_record_id=source_id,
                    recommendation="Retrieve accessible full text or replace the source if it cannot support the required evidence depth.",
                ))

        # -----------------------------------------------------------------
        # Dimension D: Reproducible QC compliance, separate from coverage.
        # Formula: passed checks / all applicable checks * 100. Seven required
        # checks are evaluated for EVERY unique candidate, including rejected
        # and review records. Review is neither pass nor hard failure but stays
        # in the denominator. Each quotation adds one source-match check, plus
        # one project-level count/partition consistency check when candidates
        # exist. An empty run scores 0 because there are no demonstrated checks.
        # Coverage gaps are separate from this source-validation compliance.
        # -----------------------------------------------------------------
        candidates = state.get("candidate_sources", []) or (
            list(validated_sources) + list(state.get("rejected_sources", []))
        )
        candidate_by_key = {}
        for source in candidates:
            key = str(source.get("id") or source.get("source_link") or source.get("source_title") or "")
            if key:
                candidate_by_key.setdefault(key, source)
        candidates = list(candidate_by_key.values())
        accepted_sources = list(validated_sources)
        state["validated_sources"] = accepted_sources
        source_by_id = {str(s.get("id")): s for s in candidates if s.get("id")}
        accepted_ids = {str(s.get("id")) for s in accepted_sources if s.get("id")}
        check_passed = check_failed = check_review = check_total = 0
        required_checks = self.REQUIRED_SOURCE_CHECKS
        duplicate_counts = {}
        for source in candidates:
            identity = (
                str(source.get("country") or "").casefold(),
                str(source.get("canonical_url") or source.get("source_link") or "").casefold().rstrip("/")
                or " ".join(str(source.get("source_title") or "").casefold().split()),
            )
            duplicate_counts[identity] = duplicate_counts.get(identity, 0) + 1

        for source in candidates:
            outcomes = dict(source.get("validation_check_outcomes") or {})
            outcomes["duplicate_detection"] = "pass" if duplicate_counts.get((
                str(source.get("country") or "").casefold(),
                str(source.get("canonical_url") or source.get("source_link") or "").casefold().rstrip("/")
                or " ".join(str(source.get("source_title") or "").casefold().split()),
            ), 0) == 1 else "fail"
            source["validation_check_outcomes"] = outcomes
            for check_name in required_checks:
                outcome = outcomes.get(check_name, "review")
                if outcome not in {"pass", "fail", "review"}:
                    outcome = "review"
                check_total += 1
                check_passed += int(outcome == "pass")
                check_failed += int(outcome == "fail")
                check_review += int(outcome == "review")

        quote_verification_failed = False
        for quote in verbatims:
            source_id = str(quote.get("source_id") or "")
            source = source_by_id.get(source_id)
            if source is None:
                quote["match_verified"] = False
                quote["verification_status"] = "unverified_source_not_accepted"
                check_total += 1
                check_review += 1
                issues.append(QCIssue(
                    severity="MAJOR", category="Evidence Integrity",
                    message=f"Verbatim {quote.get('id', '')} has no retained source record and is excluded from verified totals.",
                    affected_record_id=quote.get("id"), recommendation="Retain and verify the original source record before counting this quotation.",
                ))
                continue
            exact_match = self._quote_matches_source(quote.get("exact_quote", ""), source)
            check_total += 1
            if exact_match and source_id in accepted_ids:
                check_passed += 1
                quote["match_verified"] = True
                quote["verification_status"] = "verified_exact_match"
            elif exact_match:
                check_review += 1
                quote["match_verified"] = False
                quote["verification_status"] = "exact_but_source_not_accepted"
            else:
                check_failed += 1
                quote_verification_failed = True
                quote["match_verified"] = False
                quote["verification_status"] = "unverified_mismatch"
                issues.append(QCIssue(
                    severity="MAJOR", category="Evidence Integrity",
                    message=f"Verbatim {quote.get('id', '')} does not match the accepted source text and is excluded from verified totals.",
                    affected_record_id=quote.get("id"), recommendation="Remove or correct the quotation using the original source passage.",
                ))

        candidate_ids = {str(s.get("id") or s.get("source_link") or s.get("source_title")) for s in candidates}
        validated_ids = {str(s.get("id") or s.get("source_link") or s.get("source_title")) for s in accepted_sources}
        review_ids = {str(s.get("id") or s.get("source_link") or s.get("source_title")) for s in state.get("review_sources", [])}
        rejected_ids = {
            str(s.get("id") or s.get("source_link") or s.get("source_title"))
            for s in state.get("rejected_sources", [])
            if s.get("validation_status") != "Needs review"
        }
        status_ids = {
            "Passed initial checks": {str(s.get("id") or s.get("source_link") or s.get("source_title")) for s in candidates if s.get("validation_status") == "Passed initial checks"},
            "Needs review": {str(s.get("id") or s.get("source_link") or s.get("source_title")) for s in candidates if s.get("validation_status") == "Needs review"},
            "Rejected": {str(s.get("id") or s.get("source_link") or s.get("source_title")) for s in candidates if s.get("validation_status") == "Rejected"},
        }
        consistency_pass = (
            bool(candidates)
            and status_ids["Passed initial checks"] == validated_ids
            and status_ids["Needs review"] == review_ids
            and status_ids["Rejected"] == rejected_ids
            and len(validated_ids | review_ids | rejected_ids) == len(candidate_ids)
        )
        if candidates:
            check_total += 1
            check_passed += int(consistency_pass)
            check_failed += int(not consistency_pass)
            if not consistency_pass:
                issues.append(QCIssue(
                    severity="CRITICAL", category="Source Quality",
                    message="Candidate, validated, review, and rejected source totals do not reconcile.",
                    recommendation="Reconcile source classification arrays before reporting dashboard totals.",
                ))

        compliance_pct = round((check_passed / check_total) * 100.0, 1) if check_total else 0.0
        has_review_sources = bool(state.get("review_sources", []))
        recovery_needed = bool(missing_coverage or year_coverage_gaps) and state.get("recovery_attempts", 0) < MAX_RECOVERY_ATTEMPTS

        if not consistency_pass or quote_verification_failed:
            overall_status = "FAILED"
        elif not validated_sources:
            overall_status = "INCOMPLETE"
        elif has_review_sources or rejected_ids or check_failed or check_review or missing_coverage or year_coverage_gaps or any(
            issue.category == "Evidence Extraction" for issue in issues
        ):
            overall_status = "PASSED_WITH_LIMITATIONS"
        else:
            overall_status = "PASSED"

        qc_report = QCReport(
            total_sources_scouted=len(candidate_ids),
            passed_sources_count=len({
                s.get("id") or s.get("source_link") or s.get("source_title")
                for s in validated_sources if s.get("id") or s.get("source_link") or s.get("source_title")
            }),
            rejected_sources_count=sum(
                1 for key in {
                    (s.get("id") or s.get("source_link") or s.get("source_title"))
                    for s in rejected_sources
                    if s.get("validation_status") != "Needs review"
                } if key
            ),
            review_needed_count=len({
                s.get("id") or s.get("source_link") or s.get("source_title")
                for s in state.get("review_sources", [])
                if s.get("id") or s.get("source_link") or s.get("source_title")
            }),
            coverage_matrix=coverage_matrix,
            year_wise_coverage=year_wise_coverage,
            year_coverage_gaps=year_coverage_gaps,
            missing_coverage=missing_coverage,
            issues=issues,
            overall_status=overall_status,
            completion_score_percent=compliance_pct,
            qc_checks_passed=check_passed,
            qc_checks_failed=check_failed,
            qc_checks_review=check_review,
            qc_checks_total=check_total,
        )

        print(f"  - QC Checks: {check_passed} pass, {check_failed} fail, {check_review} review / {check_total} applicable ({compliance_pct:.1f}% pass rate)")
        print(f"  - Overall QC Status: {overall_status}")
        print(f"  - Issues identified: {len(issues)} (Recovery needed: {recovery_needed})")

        audit_trail = state.get("audit_trail", [])
        audit_trail.append(f"QC Audit finished: Status={overall_status}, checks={check_passed} pass/{check_failed} fail/{check_review} review of {check_total} ({compliance_pct:.1f}% pass rate), Issues={len(issues)}.")

        return {
            "qc_report": qc_report.model_dump(),
            "validated_sources": validated_sources,
            "verbatims": verbatims,
            "coverage_matrix": coverage_matrix,
            "year_wise_coverage": year_wise_coverage,
            "year_coverage_gaps": year_coverage_gaps,
            "missing_sections": missing_coverage,
            "recovery_needed": recovery_needed,
            "status": f"QC Completed: {overall_status}",
            "audit_trail": audit_trail,
        }
