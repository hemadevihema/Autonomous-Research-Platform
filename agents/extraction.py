"""
Evidence Extraction & Verification
==================================
Extracts distinct supported sentences from real source content. Missing content
produces an explicit shortfall, never synthetic findings or quotations.
"""
import hashlib
import re
import unicodedata
from typing import Dict, Any, List, Tuple

from config.settings import MIN_INSIGHTS_PER_SOURCE, MIN_VERBATIMS_PER_SOURCE, SECTION_KEYWORDS
from core.models import InsightRecord, VerbatimRecord
from storage.database import ResearchDatabase


class EvidenceExtractionAgent:
    EVIDENCE_TERMS = (
        "%", "prevalence", "incidence", "mortality", "guideline", "recommend",
        "treatment", "significant", "trial", "burden", "cost", "risk", "associated",
        "efficacy", "effective", "approved", "adverse", "reimbursement", "coverage",
        "barrier", "access", "therapy", "management", "patient", "clinical", "policy",
        "spending", "disparity", "concluded", "demonstrated", "observed", "increased",
        "decreased", "results", "finding", "odds ratio", "hazard ratio",
        "confidence interval", "participants", "respondents", "compared with",
        "higher than", "lower than", "p-value", "p value", "estimate", "estimated",
        "conclusion", "diagnosed", "risk ratio", "regression", "recommendation",
    )
    PLACEHOLDER_MARKERS = (
        "national library of medicine indexed research on",
        "scientific publication investigating",
        "pubmed indexed clinical research on",
        "authentic scientific publication on",
        "general evidence regarding",
        "analysis indicates national library of medicine",
    )

    def __init__(self, db: ResearchDatabase = None):
        self.db = db or ResearchDatabase()

    @staticmethod
    def _normalize(text: str) -> str:
        text = unicodedata.normalize("NFKC", text or "").replace("\u00ad", "")
        return " ".join(text.split()).casefold()

    @classmethod
    def verify_exact_quote(cls, quote: str, source_text: str) -> bool:
        """Allow whitespace/Unicode normalization only; preserve all quote wording."""
        normalized_quote = cls._normalize(quote).strip('“”"')
        return bool(normalized_quote and normalized_quote in cls._normalize(source_text))

    @staticmethod
    def _stable_id(prefix: str, source_id: str, section: str, text: str) -> str:
        raw = f"{source_id}|{section}|{text}".encode("utf-8")
        return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:12].upper()}"

    @classmethod
    def _is_placeholder(cls, passage: str, source_title: str) -> bool:
        normalized = cls._normalize(passage)
        return normalized == cls._normalize(source_title) or any(
            marker in normalized for marker in cls.PLACEHOLDER_MARKERS
        )

    @staticmethod
    def _sentences(text: str) -> List[str]:
        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or "")
            if len(sentence.strip()) >= 35
        ]

    @classmethod
    def _deduplicate_passages(cls, passages: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        result: List[Tuple[str, str]] = []
        fingerprints = set()
        for location, passage in passages:
            key = cls._normalize(passage).strip(" .;:")
            if len(key) < 30 or key in fingerprints:
                continue
            if any(key in existing or existing in key for existing in fingerprints):
                continue
            fingerprints.add(key)
            result.append((location, passage.strip()))
        return result

    def _collect_passages(
        self,
        chunks: List[Dict[str, str]],
        sections: List[str],
        disease: str,
        country: str,
        broad_pass: bool = False,
    ) -> List[Tuple[str, str]]:
        disease_terms = [term for term in re.split(r"\W+", disease.casefold()) if len(term) > 3]
        section_terms = []
        for section in sections:
            section_terms.extend(SECTION_KEYWORDS.get(section, []))
            section_terms.extend(
                term for term in re.split(r"\W+", section.casefold()) if len(term) > 4
            )
        relevant_terms = list(dict.fromkeys([*disease_terms, country.casefold(), *section_terms]))
        candidates: List[Tuple[str, str]] = []
        for chunk in chunks:
            location = str(chunk.get("location") or "Source text")
            chunk_text = str(chunk.get("text", ""))
            chunk_lower = chunk_text.casefold()
            chunk_relevant = any(term and term in chunk_lower for term in relevant_terms)
            for sentence in self._sentences(chunk_text):
                lower = sentence.casefold()
                triggered = any(term in lower for term in self.EVIDENCE_TERMS)
                structured = bool(
                    re.match(r"(?i)^\s*(results?|findings?|conclusions?|interpretation)\s*[:—-]", sentence)
                )
                topic_match = any(term and term in lower for term in relevant_terms)
                numeric = bool(
                    re.search(
                        r"\b\d+(?:[.,]\d+)?\s*(?:%|years?|months?|participants?|patients?|cases?)\b",
                        lower,
                    )
                )
                # Keep evidence findings tied to the requested disease, country,
                # or section; an unrelated sentence containing "results" or a
                # percentage is not sufficient relevance on its own.
                relevant = topic_match or (broad_pass and numeric and chunk_relevant)
                if relevant and (triggered or structured or broad_pass):
                    candidates.append((location, sentence))
        return self._deduplicate_passages(candidates)

    @staticmethod
    def _assign_section(passage: str, sections: List[str]) -> str:
        lower = passage.casefold()
        for section in sections:
            if any(term.casefold() in lower for term in SECTION_KEYWORDS.get(section, [])):
                return section
        return sections[0] if sections else "General"

    def extract_evidence(self, state: Dict[str, Any]) -> Dict[str, Any]:
        sources = state.get("validated_sources", [])
        project_id = state.get("project_id", "PROJ-DEFAULT")
        min_insight_target = max(1, int(state.get("min_insights_per_source", MIN_INSIGHTS_PER_SOURCE)))
        min_verbatim_target = max(1, int(state.get("min_verbatims_per_source", MIN_VERBATIMS_PER_SOURCE)))
        all_insights: List[Dict[str, Any]] = []
        all_verbatims: List[Dict[str, Any]] = []
        completeness: Dict[str, Dict[str, Any]] = {}

        print(f"\n[Stage 4 & 5: Extraction] Inspecting retrieved content for {len(sources)} sources...")
        for source in sources:
            source_id = source.get("id", "")
            country = source.get("country", "")
            disease = source.get("disease", "")
            sections = source.get("sections_covered", []) or ["General"]
            source_title = source.get("source_title", "")
            source_url = source.get("source_link", "")
            chunks = [
                {
                    "location": str(chunk.get("location") or "Source text"),
                    "text": str(chunk.get("text") or ""),
                }
                for chunk in source.get("content_chunks", [])
                if str(chunk.get("text") or "").strip()
            ]
            if not chunks and source.get("full_text_or_abstract"):
                location = (
                    "Abstract"
                    if source.get("content_completeness") == "abstract_only"
                    else "Retrieved source text"
                )
                chunks = [{"location": location, "text": str(source["full_text_or_abstract"])}]

            passages = self._collect_passages(chunks, sections, disease, country)
            passes = 1
            if len(passages) < min_insight_target:
                targeted = self._collect_passages(
                    chunks, sections, disease, country, broad_pass=True
                )
                passages = self._deduplicate_passages(passages + targeted)
                passes = 2

            source_insights: List[Dict[str, Any]] = []
            source_verbatims: List[Dict[str, Any]] = []
            source_text = "\n".join(chunk["text"] for chunk in chunks)
            for location, passage in passages:
                if self._is_placeholder(passage, source_title):
                    continue
                if not self.verify_exact_quote(passage, source_text):
                    continue

                # Keep each insight and quotation linked to its source and primary research section
                section = sections[0] if sections else "General"
                insight_id = self._stable_id(
                    "INS", source_id, section, self._normalize(passage)
                )
                verbatim_id = self._stable_id(
                    "VERB", source_id, section, self._normalize(passage)
                )
                insight = InsightRecord(
                    id=insight_id,
                    source_id=source_id,
                    country=country,
                    section=section,
                    insight_text=passage,
                    evidence_passage=passage,
                    relevance_explanation=(
                        "Extracted from the cited source passage; see linked verbatim and location."
                    ),
                    location_reference=location,
                    publication_date=str(source.get("publication_year") or ""),
                    data_period=source.get("data_period", "Unknown"),
                    is_verified=True,
                    verification_status="supported",
                    supporting_verbatim_ids=[verbatim_id],
                    limitations=(
                        "Abstract-only source content; full article was not retrieved."
                        if source.get("content_completeness") == "abstract_only"
                        else ""
                    ),
                ).model_dump()
                verbatim = VerbatimRecord(
                    id=verbatim_id,
                    source_id=source_id,
                    country=country,
                    section=section,
                    exact_quote=passage,
                    context=passage,
                    location_reference=location,
                    match_verified=True,
                    verification_status="verified_exact_match",
                    supports_insight_ids=[insight_id],
                    url=source_url,
                ).model_dump()
                source_insights.append(insight)
                source_verbatims.append(verbatim)

            insight_count = len(source_insights)
            quote_count = len(source_verbatims)
            if not chunks:
                status = "source_content_inaccessible"
                reason = "No source abstract or full text was retrieved; no evidence was generated."
            elif insight_count < min_insight_target or quote_count < min_verbatim_target:
                status = "below_target"
                reason = (
                    f"Retrieved {insight_count} supported insights and {quote_count} verified quotes; "
                    "available source content did not support the configured targets."
                )
            else:
                status = "complete"
                reason = "Configured minimums met using distinct source passages."
            quality = {
                "status": status,
                "content_completeness": source.get("content_completeness", "unknown"),
                "extraction_passes": passes,
                "insight_count": insight_count,
                "verbatim_count": quote_count,
                "minimum_insights": min_insight_target,
                "minimum_verbatims": min_verbatim_target,
                "reason": reason,
            }

            source["insights"] = "\n\n".join(
                f"Insight {idx}: {item['insight_text']} "
                f"[Section: {item['section']}; Location: {item['location_reference']}]"
                for idx, item in enumerate(source_insights, start=1)
            )
            source["verbatim"] = "\n\n".join(
                f"Quote {idx}: \"{item['exact_quote']}\" "
                f"[Location: {item['location_reference']}; Verification: {item['verification_status']}]"
                for idx, item in enumerate(source_verbatims, start=1)
            )
            source["extraction_status"] = status
            source["extraction_quality"] = quality
            source["insight_count"] = insight_count
            source["verbatim_count"] = quote_count
            all_insights.extend(source_insights)
            all_verbatims.extend(source_verbatims)
            completeness[source_id] = quality

            self.db.save_source(project_id, source)
            for item in source_insights:
                self.db.save_insight(project_id, item)
            for item in source_verbatims:
                self.db.save_verbatim(project_id, item)
            print(
                f"  - {source_title[:55]}: {insight_count} insight(s), "
                f"{quote_count} quote(s), {status}"
            )

        below_target = sum(
            1 for item in completeness.values() if item["status"] != "complete"
        )
        audit_trail = state.get("audit_trail", [])
        audit_trail.append(
            f"Evidence extraction recorded {len(all_insights)} supported insights and "
            f"{len(all_verbatims)} exact quotations across {len(sources)} sources; "
            f"{below_target} source(s) fell below target or lacked content."
        )
        return {
            "validated_sources": sources,
            "insights": all_insights,
            "verbatims": all_verbatims,
            "extraction_completeness": completeness,
            "status": (
                f"Extracted {len(all_insights)} insights and "
                f"{len(all_verbatims)} verified quotations"
            ),
            "audit_trail": audit_trail,
        }
