"""
Comprehensive Unit and Integration Test Suite
==============================================
Validates non-negotiable rules:
- Rule 1: 2021+ publication year cutoff
- Rule 2: Older data period flagging
- Rule 3 & 4: Country and Disease relevance
- Stage 5: Verbatim match verification
- Stage 6: QC Coverage matrix calculation
- Stage 8: Excel & Word generation integrity
"""
import unittest
import os
from pathlib import Path

from config.settings import SPREADSHEET_COLUMNS, DEFAULT_RESEARCH_SECTIONS
from core.models import SourceRecord, ValidationStatus
from agents.planner import ResearchPlanner
from agents.validation import SourceValidationAgent
from agents.scouting import ResearchScoutingAgent
from agents.extraction import EvidenceExtractionAgent
from agents.qc import QualityControlAgent
from exporters.excel_exporter import ExcelSpreadsheetExporter
from exporters.docx_exporter import WordDocumentExporter
from graph.research_graph import build_research_graph
from api.index import ResearchRequest
from pydantic import ValidationError


class TestResearchAutomationSystem(unittest.TestCase):

    def setUp(self):
        self.planner = ResearchPlanner()
        self.validator = SourceValidationAgent()
        self.extractor = EvidenceExtractionAgent()
        self.qc = QualityControlAgent()
        self.excel_exp = ExcelSpreadsheetExporter()
        self.docx_exp = WordDocumentExporter()

    def test_01_planner_generates_coverage_matrix(self):
        """Test Stage 1: Planning creates correct country x section coverage matrix."""
        state = {
            "topic": "Obesity Care",
            "disease": "Obesity",
            "countries": ["India", "United Kingdom"],
            "sections": ["Epidemiology", "Clinical Guidelines & Treatment Practices"],
            "min_publication_year": 2021,
        }
        res = self.planner.plan_research(state)
        plan = res["plan"]
        
        # 2 countries x 2 sections = 4 coverage targets
        self.assertEqual(len(plan["required_coverage_keys"]), 4)
        self.assertIn("India | Epidemiology", plan["required_coverage_keys"])
        self.assertIn("United Kingdom | Clinical Guidelines & Treatment Practices", plan["required_coverage_keys"])
        self.assertEqual(plan["min_publication_year"], 2021)

    def test_02_validation_rule_1_rejects_pre_2021(self):
        """Test Rule 1: Sources published before 2021 must be strictly REJECTED."""
        old_source = SourceRecord(
            id="SRC-OLD-2019",
            source_title="Obesity trends in India",
            name_of_source="Indian Journal of Medical Research",
            publication_year=2019,  # < 2021
            country="India",
            disease="Obesity",
            sections_covered=["Epidemiology"],
            full_text_or_abstract="Study on obesity in India.",
        ).model_dump()

        res = self.validator.validate_sources({
            "candidate_sources": [old_source],
            "min_publication_year": 2021,
            "disease": "Obesity",
            "countries": ["India"],
        })

        self.assertEqual(len(res["rejected_sources"]), 1)
        self.assertEqual(len(res["validated_sources"]), 0)
        rejected = res["rejected_sources"][0]
        self.assertEqual(rejected["validation_status"], ValidationStatus.REJECTED.value)
        self.assertTrue(any("before the cutoff" in r for r in rejected["validation_reasons"]))

    def test_03_validation_rule_2_flags_old_data_period(self):
        """Test Rule 2: Recent publication using old data is FLAGGED FOR REVIEW."""
        recent_pub_old_data = SourceRecord(
            id="SRC-OLD-DATA",
            source_title="Comprehensive Obesity Assessment in India",
            name_of_source="Lancet Regional Health",
            publication_year=2024,  # >= 2021
            data_period="2015-2019",  # Older than 2021
            country="India",
            disease="Obesity",
            sections_covered=["Epidemiology"],
            full_text_or_abstract="Obesity epidemiology prevalence survey in India. Data were collected between 2015 and 2019.",
            data_period_evidence="Data were collected between 2015 and 2019.",
            data_period_start_year=2015, data_period_end_year=2019,
            data_period_status="Verified", content_completeness="full_text",
            data_period_location="Methods",
            source_link="https://example.org/old-data-study",
        ).model_dump()

        res = self.validator.validate_sources({
            "candidate_sources": [recent_pub_old_data],
            "min_publication_year": 2021,
            "data_period_threshold": 2021,
            "disease": "Obesity",
            "countries": ["India"],
        })

        # Old underlying data is a review candidate, not validated primary evidence.
        self.assertEqual(len(res["validated_sources"]), 0)
        self.assertEqual(len(res["review_sources"]), 1)
        source = res["review_sources"][0]
        self.assertEqual(source["validation_status"], ValidationStatus.NEEDS_REVIEW.value)
        self.assertTrue(any("starts in 2015" in r for r in source["validation_reasons"]))

    def test_data_period_inside_configured_window_passes_independently_of_publication_year(self):
        source = SourceRecord(
            id="SRC-IN-WINDOW", source_title="Obesity survey in India",
            name_of_source="Test Journal", publication_year=2023,
            data_period="2022-2025", country="India", disease="Obesity",
            sections_covered=["Epidemiology"],
            full_text_or_abstract="Obesity prevalence in India was assessed in a national survey. The survey data were collected from 2022 to 2025.",
            data_period_evidence="The survey data were collected from 2022 to 2025.",
            data_period_start_year=2022, data_period_end_year=2025,
            data_period_status="Verified", content_completeness="full_text",
            data_period_location="Methods",
            source_link="https://example.org/in-window-study",
            source_provider="Test fixture", provider_record_id="in-window-study",
            provider_record_url="https://example.org/records/in-window-study",
            source_authenticity_verified=True, publication_year_verified=True,
        ).model_dump()
        result = self.validator.validate_sources({
            "candidate_sources": [source], "min_publication_year": 2021,
            "data_period_start_year": 2022, "data_period_end_year": 2025,
            "disease": "Obesity", "countries": ["India"],
        })
        self.assertEqual(len(result["validated_sources"]), 1)
        self.assertFalse(result["validated_sources"][0]["validation_checks"]["data_period"]["old_data_flag"])

    def test_data_after_configured_window_is_review_not_publication_rejection(self):
        source = SourceRecord(
            id="SRC-AFTER-WINDOW", source_title="Obesity survey in India",
            name_of_source="Test Journal", publication_year=2024,
            data_period="2026", country="India", disease="Obesity",
            sections_covered=["Epidemiology"],
            full_text_or_abstract="Obesity prevalence in India was assessed in a national survey. The survey data were collected in 2026.",
            data_period_evidence="The survey data were collected in 2026.",
            data_period_start_year=2026, data_period_end_year=2026,
            data_period_status="Verified", content_completeness="full_text",
            data_period_location="Methods",
            source_link="https://example.org/after-window-study",
        ).model_dump()
        result = self.validator.validate_sources({
            "candidate_sources": [source], "min_publication_year": 2021,
            "data_period_start_year": 2021, "data_period_end_year": 2025,
            "disease": "Obesity", "countries": ["India"],
        })
        self.assertEqual(len(result["validated_sources"]), 0)
        self.assertEqual(len(result["review_sources"]), 1)
        self.assertEqual(result["review_sources"][0]["validation_status"], ValidationStatus.NEEDS_REVIEW.value)
        self.assertFalse(result["review_sources"][0]["validation_reasons"][0].startswith("Published"))

    def test_publication_cutoff_is_separate_from_data_collection_window(self):
        source = SourceRecord(
            id="SRC-OLD-PUBLICATION", source_title="Obesity survey in India",
            name_of_source="Test Journal", publication_year=2020,
            data_period="2024-2025", country="India", disease="Obesity",
            sections_covered=["Epidemiology"],
            full_text_or_abstract="Obesity prevalence in India was assessed in a national survey.",
            data_period_evidence="The survey data were collected from 2024 to 2025.",
            data_period_start_year=2024, data_period_end_year=2025,
            data_period_status="Verified", content_completeness="full_text",
            data_period_location="Methods",
        ).model_dump()
        result = self.validator.validate_sources({
            "candidate_sources": [source], "min_publication_year": 2021,
            "data_period_start_year": 2022, "data_period_end_year": 2025,
            "disease": "Obesity", "countries": ["India"],
        })
        self.assertEqual(len(result["rejected_sources"]), 1)
        self.assertIn("before the cutoff", result["rejected_sources"][0]["validation_reasons"][0])

    def test_04_validation_rule_3_country_relevance(self):
        """Test Rule 3: Irrelevant country must be rejected."""
        wrong_country_source = SourceRecord(
            id="SRC-WRONG-CTRY",
            source_title="Obesity in Australia",
            name_of_source="Medical Journal of Australia",
            publication_year=2023,
            country="Australia",  # Target is India
            disease="Obesity",
            sections_covered=["Epidemiology"],
            full_text_or_abstract="Adult obesity prevalence in Sydney, Australia.",
        ).model_dump()

        res = self.validator.validate_sources({
            "candidate_sources": [wrong_country_source],
            "min_publication_year": 2021,
            "disease": "Obesity",
            "countries": ["India"],
        })

        self.assertEqual(len(res["rejected_sources"]), 1)
        self.assertTrue(any("does not establish relevance to assigned target country" in reason for reason in res["rejected_sources"][0]["validation_reasons"]))

    def test_05_verbatim_exact_match_verification(self):
        """Test Stage 5: Verbatim extractor accurately matches substring against source."""
        passage = "In India, clinical practice guidelines emphasize early lifestyle intervention and GLP-1 receptor agonists."
        source = SourceRecord(
            id="SRC-GUIDELINES",
            source_title="Management of Obesity in India",
            name_of_source="Endocrine Society of India",
            publication_year=2023,
            country="India",
            disease="Obesity",
            sections_covered=["Clinical Guidelines & Treatment Practices"],
            full_text_or_abstract=passage,
        ).model_dump()

        res = self.extractor.extract_evidence({
            "validated_sources": [source],
            "project_id": "TEST-PROJ",
        })

        self.assertGreater(len(res["verbatims"]), 0)
        v = res["verbatims"][0]
        self.assertTrue(v["match_verified"])
        self.assertIn(v["exact_quote"].replace('"', ''), passage)

    def test_06_excel_spreadsheet_exporter_exact_columns(self):
        """Test Stage 8: Excel exporter generates file with the exact 14 columns."""
        source = SourceRecord(
            id="SRC-101",
            source_title="National Health Survey Obesity Data",
            name_of_source="Ministry of Health",
            publication_year=2023,
            data_period="2021-2022",
            description="Official public health report on obesity prevalence.",
            country="India",
            sections_covered=["Epidemiology"],
            summary="Adult obesity rose to 24% nationwide.",
            insights="Epidemiological shift toward urban centers.",
            verbatim="Adult obesity rose to 24% nationwide.",
        ).model_dump()

        qc_mock = {
            "overall_status": "PASSED",
            "completion_score_percent": 100.0,
            "total_sources_scouted": 1,
            "passed_sources_count": 1,
            "coverage_matrix": {"India | Epidemiology": 1},
        }

        path = self.excel_exp.export("TEST-EXCEL", "Obesity in India", [source], qc_mock)
        self.assertTrue(os.path.exists(path))

        # Inspect generated workbook
        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb["Research Sources"]
        headers_in_sheet = [ws.cell(row=1, column=c).value for c in range(1, len(SPREADSHEET_COLUMNS) + 1)]
        self.assertEqual(headers_in_sheet, SPREADSHEET_COLUMNS)

    def test_07_word_document_exporter(self):
        """Test Stage 8: Word document exporter produces readable .docx with all 9 sections."""
        source = SourceRecord(
            id="SRC-DOCX-1",
            source_title="Obesity Clinical Guidelines India",
            name_of_source="Indian Journal of Endocrinology",
            publication_year=2022,
            country="India",
            sections_covered=["Clinical Guidelines & Treatment Practices"],
        ).model_dump()

        path = self.docx_exp.export(
            project_id="TEST-WORD",
            topic="Obesity Research",
            disease="Obesity",
            countries=["India"],
            sections=DEFAULT_RESEARCH_SECTIONS,
            validated_sources=[source],
            insights=[{"country": "India", "section": "Clinical Guidelines & Treatment Practices", "insight_text": "Evidence highlights pharmacotherapy options.", "source_id": "SRC-DOCX-1", "data_period": "2022"}],
            verbatims=[{"country": "India", "section": "Clinical Guidelines & Treatment Practices", "exact_quote": "Pharmacotherapy is indicated for BMI > 27.", "match_verified": True, "location_reference": "Page 4"}],
            qc_report={"overall_status": "PASSED", "missing_coverage": []},
        )
        self.assertTrue(os.path.exists(path))

    def test_08_graph_compiles_successfully(self):
        """Test LangGraph StateGraph builds and compiles without errors."""
        graph = build_research_graph()
        self.assertIsNotNone(graph)

    def test_api_rejects_invalid_or_reversed_year_windows(self):
        with self.assertRaises(ValidationError):
            ResearchRequest(data_period_start_year=2028, data_period_end_year=2027)
        with self.assertRaises(ValidationError):
            ResearchRequest(min_publication_year=1800)

    def test_legacy_single_data_threshold_maps_to_start_year(self):
        request = ResearchRequest(data_period_threshold=2023)
        self.assertEqual(request.data_period_start_year, 2023)
        self.assertEqual(request.data_period_end_year, 2026)

    def test_scouting_does_not_infer_data_period_from_publication_year(self):
        scout = ResearchScoutingAgent()
        self.assertEqual(scout._detect_data_period("Published in 2024.", 2024), "Unknown")
        self.assertEqual(
            scout._detect_data_period("Data were collected between 2018 and 2020; published in 2024.", 2024),
            "2018–2020",
        )


if __name__ == "__main__":
    unittest.main()
