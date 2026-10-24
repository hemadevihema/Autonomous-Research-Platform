"""Regression coverage for source-evidenced data periods and year-wise gaps."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from agents.correction import AutonomousCorrectionEngine
from agents.qc import QualityControlAgent
from agents.scouting import ResearchScoutingAgent
from agents.validation import SourceValidationAgent
from api.index import ResearchRequest
from graph.research_graph import _final_project_status
from storage.database import ResearchDatabase


class TestCriticalDataPeriodIntegrity(unittest.TestCase):
    def setUp(self):
        self.scout = ResearchScoutingAgent()
        self.validator = SourceValidationAgent()

    def _source(self, text, period, start, end, **extra):
        return {
            "id": "SRC-CRITICAL-1",
            "source_title": "Obesity epidemiology in India",
            "name_of_source": "Test journal",
            "publication_year": 2025,
            "data_period": period,
            "data_period_start_year": start,
            "data_period_end_year": end,
            "data_period_evidence": text,
            "data_period_location": "Methods",
            "data_period_status": "Verified",
            "data_period_type": "survey",
            "content_completeness": "full_text",
            "full_text_or_abstract": (
                "Obesity prevalence in India; epidemiology and survey methods. " + text
            ),
            "country": "India",
            "disease": "Obesity",
            "sections_covered": ["Epidemiology"],
            "source_link": "https://example.invalid/source",
            "source_provider": "Test fixture",
            "provider_record_id": "fixture-1",
            "provider_record_url": "https://example.invalid/record/fixture-1",
            "source_authenticity_verified": True,
            "publication_year_verified": True,
            **extra,
        }

    def _validate(self, source, start=2021, end=2026):
        return self.validator.validate_sources({
            "candidate_sources": [source], "countries": ["India"],
            "disease": "Obesity", "min_publication_year": 2021,
            "data_period_start_year": start, "data_period_end_year": end,
        })

    def test_unknown_or_llm_only_year_does_not_verify(self):
        details = self.scout._detect_data_period_details(
            [{"location": "Abstract", "text": "Published in 2026. No collection dates are stated."}],
            "abstract_only",
        )
        self.assertEqual(details["data_period"], "Unknown")
        source = self._source("The article was published in 2026.", "2026", 2026, 2026)
        result = self._validate(source)
        review = result["review_sources"][0]
        self.assertEqual(review["data_period"], "Unknown")
        self.assertEqual(review["data_period_status"], "Unknown")

    def test_publication_cutoff_and_data_period_are_independent(self):
        source = self._source("Data were collected between 2021 and 2023.", "2021–2023", 2021, 2023)
        source["publication_year"] = 2020
        result = self._validate(source)
        self.assertFalse(result["rejected_sources"][0]["validation_checks"]["pub_year"])
        self.assertEqual(result["rejected_sources"][0]["validation_checks"]["data_period"]["start_year"], 2021)
        source["publication_year"] = 2021
        result = self._validate(source)
        self.assertTrue(result["validated_sources"][0]["validation_checks"]["pub_year"])

    def test_overlapping_range_contributes_only_documented_years(self):
        source = self._source("Data were collected between 2022 and 2024.", "2022–2024", 2022, 2024)
        result = self._validate(source)
        accepted = result["validated_sources"][0]
        qc = QualityControlAgent().evaluate_project({
            "countries": ["India"], "sections": ["Epidemiology"],
            "validated_sources": [accepted], "review_sources": [], "rejected_sources": [],
            "data_period_start_year": 2021, "data_period_end_year": 2026,
            "recovery_attempts": 0, "insights": [], "verbatims": [],
        })
        statuses = [qc["year_wise_coverage"][f"India | Epidemiology | {year}"]["status"] for year in range(2021, 2027)]
        self.assertEqual(statuses, ["No evidence", "Covered", "Covered", "Covered", "No evidence", "No evidence"])
        self.assertEqual(qc["year_wise_coverage"]["India | Epidemiology | 2023"]["source_ids"], ["SRC-CRITICAL-1"])

    def test_projected_completion_never_counts_as_observed(self):
        detail = self.scout._detect_data_period_details(
            [{"location": "Methods", "text": "The study is projected to finish in 2027."}],
            "full_text",
        )
        self.assertEqual(detail["data_period"], "Unknown")
        self.assertEqual(detail["status"], "Unknown")
        source = self._source("The study is projected to finish in 2027.", "2027", 2027, 2027)
        result = self._validate(source)
        candidate = result["review_sources"][0]
        self.assertEqual(candidate["data_period"], "Unknown")

    def test_accessible_text_is_required_for_verified_period(self):
        source = self._source("Data were collected in 2024.", "2024", 2024, 2024)
        source["full_text_or_abstract"] = ""
        source["content_chunks"] = []
        result = self._validate(source)
        self.assertEqual(result["review_sources"][0]["data_period_status"], "Unknown")

    def test_gap_triggers_targeted_query(self):
        result = AutonomousCorrectionEngine().prepare_recovery({
            "disease": "Obesity", "min_publication_year": 2021,
            "missing_sections": [], "year_coverage_gaps": ["India | Epidemiology | 2025"],
            "recovery_attempts": 0, "audit_trail": [],
        })
        self.assertTrue(result["recovery_needed"])
        self.assertEqual(result["targeted_queries"][0]["data_year"], 2025)
        self.assertIn("data collected 2025", result["targeted_queries"][0]["query"])

    def test_duplicate_records_count_once_after_validation(self):
        source = self._source("Data were collected in 2024.", "2024", 2024, 2024)
        duplicate = {**source, "id": "SRC-CRITICAL-DUPLICATE"}
        duplicate["canonical_url"] = source["source_link"]
        source["canonical_url"] = source["source_link"]
        # Validate both together to exercise workflow deduplication.
        result = self.validator.validate_sources({
            "candidate_sources": [source, duplicate], "countries": ["India"],
            "disease": "Obesity", "min_publication_year": 2021,
            "data_period_start_year": 2021, "data_period_end_year": 2026,
        })
        self.assertEqual(len(result["candidate_sources"]), 1)
        self.assertEqual(len(result["validated_sources"]), 1)

    def test_country_nationality_does_not_override_explicit_other_country_scope(self):
        source = self._source(
            "The Australia-wide cross-sectional survey studied Indian immigrant mothers. "
            "Data were collected in 2024.", "2024", 2024, 2024,
        )
        source["source_title"] = "Infant feeding practices of Indian immigrant mothers: Australia-wide survey"
        result = self._validate(source)
        self.assertEqual(len(result["validated_sources"]), 0)
        self.assertTrue(result["rejected_sources"])
        self.assertFalse(result["rejected_sources"][0]["validation_checks"]["country_relevance"])

    def test_country_list_including_india_is_not_rejected_as_foreign_scope(self):
        source = self._source(
            "Data were collected in 2024.", "2024", 2024, 2024,
        )
        source["source_title"] = "Fast food and obesity policy in China and India"
        result = self._validate(source)
        classified = (result["validated_sources"] + result["review_sources"] + result["rejected_sources"])[0]
        self.assertTrue(classified["validation_checks"]["country_relevance"])
        self.assertFalse(any("assigned target country" in reason for reason in classified["validation_reasons"]))

    def test_incidental_topic_mention_does_not_establish_obesity_relevance(self):
        source = self._source(
            "This report examines colorectal cancer. Obesity is listed among several risk factors. "
            "Data were collected in 2024.", "2024", 2024, 2024,
        )
        source["source_title"] = "Epidemiological trends and risk factors of colorectal cancer in India"
        result = self._validate(source)
        self.assertEqual(len(result["validated_sources"]), 0)
        self.assertTrue(result["rejected_sources"])
        self.assertFalse(result["rejected_sources"][0]["validation_checks"]["disease_relevance"])

    def test_publication_2026_and_data_2021_2026_pass_date_rules(self):
        source = self._source("Data were collected between 2021 and 2026.", "2021–2026", 2021, 2026)
        source["publication_year"] = 2026
        result = self._validate(source)
        self.assertEqual(len(result["validated_sources"]), 1)

    def test_publication_2026_old_data_is_review_not_publication_rejection(self):
        source = self._source("Data were collected between 2019 and 2020.", "2019–2020", 2019, 2020)
        source["publication_year"] = 2026
        result = self._validate(source)
        self.assertEqual(len(result["review_sources"]), 1)
        self.assertFalse(any("Published in" in reason for reason in result["review_sources"][0]["validation_reasons"]))

    def test_data_ending_after_configured_end_year_is_review_not_rejected(self):
        source = self._source("Data were collected in 2027.", "2027", 2027, 2027)
        result = self._validate(source, start=2021, end=2026)
        self.assertEqual(len(result["validated_sources"]), 0)
        self.assertEqual(len(result["review_sources"]), 1)
        self.assertEqual(result["review_sources"][0]["data_period_status"], "Outside requested period")
        self.assertFalse(any("Published in" in reason for reason in result["review_sources"][0]["validation_reasons"]))

    def test_unknown_publication_year_is_review_and_old_publication_is_rejected(self):
        unknown = self._source("Data were collected between 2021 and 2026.", "2021–2026", 2021, 2026)
        unknown["publication_year"] = None
        result = self._validate(unknown)
        self.assertEqual(len(result["review_sources"]), 1)
        old = self._source("Data were collected between 2021 and 2026.", "2021–2026", 2021, 2026)
        old["publication_year"] = 2020
        result = self._validate(old)
        self.assertEqual(len(result["rejected_sources"]), 1)

    def test_negative_obesity_finding_is_not_rejected_for_sentiment(self):
        source = self._source(
            "Data were collected between 2021 and 2026.", "2021–2026", 2021, 2026,
        )
        source["full_text_or_abstract"] = (
            "The obesity intervention did not improve prevalence in India. "
            "Data were collected between 2021 and 2026. Epidemiology findings were reported."
        )
        result = self._validate(source)
        self.assertEqual(len(result["validated_sources"]), 1)

    def test_qc_formula_separates_compliance_from_coverage_and_checks_quotes(self):
        source = self._source("Data were collected between 2021 and 2026.", "2021–2026", 2021, 2026)
        validated = self._validate(source)["validated_sources"]
        quote = {
            "id": "VERB-QC", "source_id": source["id"],
            "exact_quote": "This quotation is fabricated.", "match_verified": True,
            "verification_status": "verified_exact_match",
        }
        irrelevant = self._source(
            "Data were collected between 2021 and 2026.", "2021–2026", 2021, 2026,
        )
        irrelevant.update({
            "id": "SRC-IRRELEVANT",
            "source_title": "Colorectal cancer epidemiology in India",
            "source_link": "https://example.invalid/irrelevant",
            "full_text_or_abstract": "Colorectal cancer epidemiology in India. Data were collected between 2021 and 2026.",
        })
        rejected = self._validate(irrelevant)["rejected_sources"][0]
        result = QualityControlAgent().evaluate_project({
            "countries": ["India"], "sections": ["Epidemiology"],
            "validated_sources": validated, "candidate_sources": [source, rejected],
            "review_sources": [], "rejected_sources": [rejected],
            "data_period_start_year": 2021, "data_period_end_year": 2026,
            "recovery_attempts": 2, "insights": [], "verbatims": [quote],
        })
        report = result["qc_report"]
        self.assertFalse(quote["match_verified"])
        self.assertEqual(report["completion_score_percent"], 87.5)
        self.assertEqual(report["qc_checks_passed"], 14)
        self.assertEqual(report["qc_checks_failed"], 2)
        self.assertEqual(report["qc_checks_review"], 0)
        self.assertEqual(report["qc_checks_total"], 16)
        self.assertEqual(report["year_coverage_gaps"], [])

    def test_noncentral_obesity_mention_is_review_not_hard_rejection(self):
        source = self._source(
            "The study measures obesity markers alongside sleep outcomes. Data were collected in 2024.",
            "2024", 2024, 2024,
        )
        source["source_title"] = "Smartphone use and sleep outcomes among adolescents in India"
        result = self._validate(source)
        self.assertEqual(len(result["rejected_sources"]), 1)
        self.assertEqual(result["rejected_sources"][0]["validation_status"], "Needs review")
        self.assertEqual(result["rejected_sources"][0]["validation_check_outcomes"]["topic_relevance"], "review")

    def test_reclassification_preserves_previous_source_audit_state(self):
        test_root = Path(__file__).resolve().parents[1] / ".test_tmp"
        test_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            db = ResearchDatabase(f"{directory}/audit.sqlite")
            source = self._source("Data were collected in 2024.", "2024", 2024, 2024)
            source.update({"validation_status": "Rejected", "validation_reasons": ["Prior rule"]})
            db.save_source("PROJ-AUDIT", source)
            source["validation_status"] = "Passed initial checks"
            source["validation_reasons"] = ["Reclassified under corrected rules"]
            source["validation_checks"] = {"publication_cutoff": True}
            db.save_source("PROJ-AUDIT", source)
            saved = db.get_sources_for_project("PROJ-AUDIT")[0]
            self.assertEqual(saved["validation_status"], "Passed initial checks")
            self.assertEqual(saved["validation_history"][0]["previous_state"]["validation_status"], "Rejected")

    def test_search_limit_is_configurable_and_status_does_not_overclaim(self):
        self.assertEqual(ResearchRequest().max_sources_per_section, 20)
        self.assertEqual(ResearchRequest(max_sources_per_section=30).max_sources_per_section, 30)
        self.assertEqual(_final_project_status("PASSED"), "COMPLETED")
        self.assertEqual(_final_project_status("PASSED_WITH_LIMITATIONS"), "COMPLETED_WITH_LIMITATIONS")
        self.assertEqual(_final_project_status("INCOMPLETE"), "INCOMPLETE")

    def test_openalex_and_pubmed_requests_use_the_configured_section_limit(self):
        class DummyDB:
            def save_source(self, *_args, **_kwargs):
                pass

        scout = ResearchScoutingAgent(DummyDB())
        results = [
            {"id": f"SRC-{i}", "source_title": f"Source {i}", "source_link": f"https://example.org/{i}", "sections_covered": []}
            for i in range(5)
        ]
        with patch.object(scout, "_search_openalex", return_value=results) as openalex, \
             patch.object(scout, "_search_pubmed", return_value=results) as pubmed:
            result = scout.scout({
                "plan": {"generated_queries": [{"country": "India", "section": "Epidemiology", "query": "obesity India"}]},
                "disease": "Obesity", "min_publication_year": 2021,
                "max_sources_per_section": 2,
            })
        self.assertEqual(openalex.call_args.kwargs["max_results"], 2)
        self.assertEqual(pubmed.call_args.kwargs["max_results"], 2)
        self.assertEqual(len(result["candidate_sources"]), 2)
        self.assertEqual(result["provider_diagnostics"], [{
            "country": "India", "section": "Epidemiology",
            "openalex_retrieved": 5, "pubmed_retrieved": 5,
        }])

    def test_duplicate_provider_hits_do_not_assign_a_source_to_multiple_sections(self):
        source = self._source(
            "Data were collected in 2024.", "2024", 2024, 2024,
            full_text_or_abstract=(
                "Obesity prevalence and epidemiology in India. "
                "Data were collected in 2024."
            ),
        )
        source["sections_covered"] = ["Epidemiology"]
        duplicate = {**source, "id": "SRC-CRITICAL-DUPLICATE", "sections_covered": ["Clinical Guidelines & Treatment Practices"]}
        result = self.validator.validate_sources({
            "candidate_sources": [source, duplicate], "countries": ["India"],
            "sections": ["Epidemiology", "Clinical Guidelines & Treatment Practices"],
            "disease": "Obesity", "min_publication_year": 2021,
            "data_period_start_year": 2021, "data_period_end_year": 2026,
        })
        self.assertEqual(len(result["candidate_sources"]), 1)
        self.assertEqual(result["validated_sources"][0]["sections_covered"], ["Epidemiology"])

    def test_primary_section_uses_strongest_direct_content_evidence(self):
        text = (
            "Obesity in India. This study explored prescribing practices and use of "
            "antiobesity medications among healthcare professionals. Data were collected in 2025. "
            "Semaglutide and tirzepatide were discussed, including affordability and regulation."
        )
        source = self._source(text, "2025", 2025, 2025)
        source["sections_covered"] = ["Competitive Landscape & Product Intelligence"]
        source["content_completeness"] = "full_text"
        result = self._validate(source)
        self.assertEqual(len(result["validated_sources"]), 1)
        self.assertEqual(result["validated_sources"][0]["sections_covered"], ["Clinical Guidelines & Treatment Practices"])

    def test_recovery_rotates_through_late_missing_sections(self):
        sections = [f"Section {i}" for i in range(9)]
        first = AutonomousCorrectionEngine().prepare_recovery({
            "disease": "Obesity", "missing_sections": [f"India | {s}" for s in sections],
            "year_coverage_gaps": [], "recovery_attempts": 0, "audit_trail": [],
        })
        second = AutonomousCorrectionEngine().prepare_recovery({
            "disease": "Obesity", "missing_sections": [f"India | {s}" for s in sections],
            "year_coverage_gaps": [], "recovery_attempts": 1, "audit_trail": [],
        })
        covered = {q["section"] for q in first["targeted_queries"] + second["targeted_queries"]}
        self.assertEqual(covered, set(sections))

    def test_old_default_2026_pattern_regression(self):
        for text in (
            "This report was published in 2026.",
            "The source was retrieved in 2026.",
            "The URL contains /2026/report.",
        ):
            details = self.scout._detect_data_period_details(
                [{"location": "Abstract", "text": text}], "abstract_only"
            )
            self.assertEqual(details["data_period"], "Unknown", text)


if __name__ == "__main__":
    unittest.main()
