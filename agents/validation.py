"""
Stage 3: Dedicated Source Validation Agent
==========================================
Enforces project-specific validation rules configured by the researcher:
- Rule 1: Configurable publication year cutoff (rejects older sources).
- Rule 2: Data period analysis (flags publications using data older than threshold).
- Rule 3: Geographical / Country relevance based on user-specified countries.
- Rule 4: Disease / Health condition relevance dynamically matched to user's topic.
- Rule 5: User-defined research section alignment.
- Rule 6: Metadata completeness and source accessibility.
"""
import re
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional
from config.settings import (
    DEFAULT_RESEARCH_SECTIONS,
    MIN_PUBLICATION_YEAR,
    DATA_PERIOD_START_YEAR,
    DATA_PERIOD_END_YEAR,
    SECTION_KEYWORDS,
)
from core.models import ValidationStatus
from storage.database import ResearchDatabase


class SourceValidationAgent:
    """Agent that independently audits candidate sources against user-configured acceptance criteria."""

    COUNTRY_TERMS = {
        "india": ["india", "indian"],
        "united states": ["united states", "united states of america", "usa", "u.s.", "american"],
        "united kingdom": ["united kingdom", "uk", "u.k.", "britain", "british", "england", "scotland", "wales"],
        "south korea": ["south korea", "republic of korea", "korean"],
        "russia": ["russia", "russian federation", "russian"],
        "china": ["china", "chinese"],
        "japan": ["japan", "japanese"],
        "canada": ["canada", "canadian"],
        "australia": ["australia", "australian"],
    }

    @staticmethod
    def _has_term(text: str, term: str) -> bool:
        return bool(re.search(rf"(?<!\w){re.escape(term.casefold())}(?!\w)", text.casefold()))

    @classmethod
    def _country_is_evidenced(cls, text: str, country: str) -> bool:
        normalized = country.casefold().strip()
        terms = cls.COUNTRY_TERMS.get(normalized, [normalized])
        return any(cls._has_term(text, term) for term in terms if term)

    @classmethod
    def _countries_equivalent(cls, first: str, second: str) -> bool:
        a = first.casefold().strip()
        b = second.casefold().strip()
        a_terms = set(cls.COUNTRY_TERMS.get(a, [a]))
        b_terms = set(cls.COUNTRY_TERMS.get(b, [b]))
        return bool(a_terms & b_terms)

    @classmethod
    def _has_conflicting_country_scope(cls, source: Dict[str, Any], target_country: str) -> bool:
        """Do not mistake nationality/ethnicity mentions for the study's geography."""
        title = str(source.get("source_title") or "").casefold()
        content = str(source.get("full_text_or_abstract") or "")[:2500].casefold()
        text = f"{title} {content}"
        target = target_country.casefold().strip()
        target_title_scope = bool(re.search(
            rf"\b(?:in|across|within|throughout)\s+(?:the\s+)?{re.escape(target)}\b|"
            rf"\b{re.escape(target)}\s*[- ]wide\b", title
        ))
        # Treat a title naming the target in an explicit country list as
        # geographic scope (e.g. "China and India"), not a conflicting-country
        # study. Nationality terms such as "Indian immigrants" do not match
        # this exact-country list check.
        if not target_title_scope and re.search(rf"\b{re.escape(target)}\b", title):
            title_country_aliases = {
                alias
                for country, aliases in cls.COUNTRY_TERMS.items()
                if not cls._countries_equivalent(country, target)
                for alias in aliases
            }
            has_other_country = any(cls._has_term(title, alias) for alias in title_country_aliases)
            has_country_list = bool(re.search(r"\b(?:and|or)\b|,", title))
            target_title_scope = has_other_country and has_country_list
        for country, aliases in cls.COUNTRY_TERMS.items():
            if cls._countries_equivalent(country, target):
                continue
            for alias in aliases:
                alias_re = re.escape(alias.casefold())
                explicit_scope = re.search(
                    rf"\b(?:in|across|within|throughout|nationwide in)\s+(?:the\s+)?{alias_re}\b|"
                    rf"\b{alias_re}\s*[- ]wide\b|"
                    rf"\b(?:study|survey|sample|participants|data)\b[^.{{}}]{{0,55}}\b(?:in|from|across)\s+(?:the\s+)?{alias_re}\b",
                    text,
                )
                if explicit_scope and not target_title_scope:
                    return True
        return False

    @staticmethod
    def _normalize_source_key(source: Dict[str, Any]) -> tuple:
        country = str(source.get("country") or "").strip().casefold()
        canonical = str(source.get("canonical_url") or source.get("source_link") or "").strip().casefold()
        canonical = canonical.removeprefix("https://doi.org/").removeprefix("http://doi.org/").rstrip("/")
        title = re.sub(r"\W+", "", str(source.get("source_title") or "").casefold())
        return country, canonical, title

    @staticmethod
    def _normalized_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip().casefold()

    @staticmethod
    def _period_years_are_cue_bound(evidence: str, start: int, end: int) -> bool:
        year = r"((?:19|20)\d{2})"
        day_prefix = r"(?:\b\d{1,2}(?:st|nd|rd|th)?,?\s+)?"
        range_suffix = rf"(?:\s*,?\s*(?:-|–|—|to|through|and)\s*(?:[A-Za-z]+\s+\d{{1,2}},?\s+|[A-Za-z]+\s+)?{year})?"
        cue_prefix = re.compile(
            rf"\b(?:data\s+(?:were|was)?\s*(?:collected|gathered|obtained|recorded|retrieved|drawn|abstracted)|"
            rf"data\s+collection\s+(?:was\s+)?(?:carried\s+out|conducted|took\s+place)|"
            rf"(?:study|survey|trial|investigation|evaluation|poll|fieldwork)s?\s+(?:were|was)?\s*(?:conducted|carried\s+out|performed|undertaken|implemented|administered|executed|done)|"
            rf"(?:surveys?|questionnaires?)\s+(?:were|was)?\s*(?:administered|completed)|"
            rf"(?:patients|participants|subjects|individuals|cases|cohorts?|respondents)\s+(?:were)?\s*(?:enrolled|recruited|included|assessed|followed|surveyed|interviewed|examined)|"
            rf"collection\s+(?:took\s+place|was\s+conducted)|observations\s+(?:were\s+)?collected)"
            rf"[^\d]{{0,45}}{day_prefix}{year}{range_suffix}", re.I,
        )
        cue_data_from = re.compile(
            rf"\b(?:data|dataset|database|cohort|nfhs|national family health survey)\b[^\d]{{0,75}}"
            rf"(?:from|between|during|covering|spanning)\s*{day_prefix}{year}{range_suffix}", re.I,
        )
        reverse = re.compile(
            rf"{year}\s*(?:-|–|—|to|through)\s*{year}[^\d]{{0,45}}"
            rf"\b(?:survey|dataset|data|cohort|nfhs|study)\b", re.I,
        )
        for pattern in (cue_prefix, cue_data_from):
            match = pattern.search(evidence)
            if match:
                values = [int(value) for value in match.groups() if value]
                if values and values[0] == int(start) and (values[-1] if len(values) > 1 else values[0]) == int(end):
                    return True
        match = reverse.search(evidence)
        if match:
            values = [int(value) for value in match.groups() if value]
            return len(values) >= 2 and min(values[:2]) == int(start) and max(values[:2]) == int(end)
        return False

    @classmethod
    def _supported_period_evidence(cls, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return one period only when the cited passage occurs in the retrieved source."""
        chunks = source.get("content_chunks") or []
        original = "\n".join(str(chunk.get("text") or "") for chunk in chunks)
        original += "\n" + str(source.get("full_text_or_abstract") or "")
        original_normalized = cls._normalized_text(original)
        evidence = str(source.get("data_period_evidence") or "").strip()
        start, end = source.get("data_period_start_year"), source.get("data_period_end_year")
        if not evidence or cls._normalized_text(evidence) not in original_normalized:
            return None
        if start is None or end is None or not cls._period_years_are_cue_bound(evidence, int(start), int(end)):
            return None
        return {
            "evidence": evidence,
            "location": source.get("data_period_location", "Source text"),
            "start_year": int(start),
            "end_year": int(end),
            "period_type": source.get("data_period_type", "unknown"),
        }

    def __init__(self, db: ResearchDatabase = None):
        self.db = db or ResearchDatabase()

    def validate_sources(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Audit all candidate sources and partition into validated vs rejected."""
        candidates = state.get("candidate_sources", [])
        deduplicated: List[Dict[str, Any]] = []
        by_key: Dict[tuple, Dict[str, Any]] = {}
        for source in candidates:
            key = self._normalize_source_key(source)
            prior = next((candidate for prior_key, candidate in by_key.items()
                if prior_key[0] == key[0] and (
                    (key[1] and prior_key[1] == key[1])
                    or (key[2] and prior_key[2] == key[2])
                )), None)
            if prior is None:
                by_key[key] = source
                deduplicated.append(source)
                continue
            conflicts = prior.setdefault("metadata_conflicts", [])
            for field in ("publication_year", "data_period"):
                left, right = prior.get(field), source.get(field)
                if left not in (None, "", "Unknown", "Not specified") and right not in (None, "", "Unknown", "Not specified") and str(left) != str(right):
                    conflicts.append(f"Duplicate records disagree on {field}: {left} vs {right}.")
            completeness_rank = {"inaccessible": 0, "unknown": 0, "abstract_only": 1, "full_text": 2}
            if completeness_rank.get(source.get("content_completeness"), 0) > completeness_rank.get(prior.get("content_completeness"), 0):
                for field in ("content_completeness", "content_chunks", "full_text_or_abstract", "data_period", "data_period_start_year", "data_period_end_year", "data_period_type", "data_period_evidence", "data_period_location", "data_period_status"):
                    prior[field] = source.get(field, prior.get(field))
        candidates = deduplicated
        min_year = state.get("min_publication_year")
        if min_year is None:
            min_year = MIN_PUBLICATION_YEAR
        
        data_period_start_year = state.get("data_period_start_year")
        if data_period_start_year is None:
            data_period_start_year = state.get("data_period_threshold", DATA_PERIOD_START_YEAR)
        data_period_end_year = state.get("data_period_end_year", DATA_PERIOD_END_YEAR)

        target_disease = (state.get("disease") or state.get("topic") or "").lower().strip()
        target_countries = [c.lower().strip() for c in state.get("countries", []) if c.strip()]

        validated: List[Dict[str, Any]] = []
        review_candidates: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        print(f"\n[Stage 3: Validation] Auditing {len(candidates)} candidate sources against user criteria...")

        for s in candidates:
            checks: Dict[str, Any] = {}
            check_outcomes: Dict[str, str] = {}
            rejection_reasons: List[str] = []
            review_flags: List[str] = []

            # -------------------------------------------------------------
            # Rule 1: Publication Year (Dynamic User-Configured Cutoff)
            # -------------------------------------------------------------
            pub_year = s.get("publication_year")
            if pub_year is None:
                checks["pub_year"] = False
                checks["publication_cutoff"] = False
                check_outcomes["publication_cutoff"] = "review"
                review_flags.append("Publication year is Unknown and requires source verification.")
            elif pub_year < min_year:
                checks["pub_year"] = False
                checks["publication_cutoff"] = False
                check_outcomes["publication_cutoff"] = "fail"
                rejection_reasons.append(f"Published in {pub_year}, which is before the cutoff of {min_year}.")
            else:
                checks["pub_year"] = True
                checks["publication_cutoff"] = True
                check_outcomes["publication_cutoff"] = "pass"

            source_url = str(s.get("source_link") or "").strip()
            parsed_source_url = urlparse(source_url)
            checks["source_link"] = parsed_source_url.scheme in {"http", "https"} and bool(parsed_source_url.netloc)
            if not checks["source_link"]:
                review_flags.append("Source link is missing or malformed, so the intended publication could not be confirmed.")
            provider_url = urlparse(str(s.get("provider_record_url") or ""))
            checks["source_authenticity"] = bool(
                s.get("source_authenticity_verified") is True
                and s.get("publication_year_verified") is True
                and s.get("provider_record_id")
                and provider_url.scheme in {"http", "https"}
                and provider_url.netloc
                and checks["source_link"]
            )
            if not checks["source_authenticity"]:
                review_flags.append("Original publication identity or publication-year provenance is not fully verified.")
            check_outcomes["source_authenticity"] = "pass" if checks["source_authenticity"] else "review"

            # -------------------------------------------------------------
            # Rule 2: Data Period (User-Configured Threshold)
            # -------------------------------------------------------------
            period = self._supported_period_evidence(s)
            if not period:
                data_period_str = "Unknown"
                period_start = period_end = None
                period_status = "Unknown"
                review_flags.append("Data collection period is Unknown: no cited period passage was verifiably present in retrieved source text.")
            else:
                period_start, period_end = period["start_year"], period["end_year"]
                data_period_str = str(period_start) if period_start == period_end else f"{period_start}–{period_end}"
                period_status = (
                    "Verified" if s.get("content_completeness") == "full_text"
                    and str(period.get("location") or "").casefold() != "abstract"
                    else "Partially verified"
                )
                if period_start < data_period_start_year or period_end > data_period_end_year:
                    period_status = "Outside requested period"
                    if period_start < data_period_start_year:
                        review_flags.append(f"Data collection starts in {period_start}, before the configured start year {data_period_start_year}.")
                    if period_end > data_period_end_year:
                        review_flags.append(f"Data collection ends in {period_end}, after the configured end year {data_period_end_year}.")
            period_in_window = bool(
                period is not None
                and period_start >= data_period_start_year
                and period_end <= data_period_end_year
            )
            check_outcomes["data_period_classification"] = "pass" if period_in_window else "review"
            s["data_period"] = data_period_str
            s["data_period_start_year"] = period_start
            s["data_period_end_year"] = period_end
            s["data_period_status"] = period_status

            checks["data_period"] = {
                "recorded": period is not None,
                "old_data_flag": bool(period_start is not None and period_start < data_period_start_year),
                "outside_requested_period": period is not None and (period_start < data_period_start_year or period_end > data_period_end_year),
                "start_year": period_start,
                "end_year": period_end,
                "value": data_period_str,
                "status": s["data_period_status"],
                "type": s.get("data_period_type", "unknown"),
                "evidence": period["evidence"] if period else "",
                "location": s.get("data_period_location", ""),
                "source_url": s.get("source_link", ""),
                "preferred_start_year": data_period_start_year,
                "preferred_end_year": data_period_end_year,
                "preferred_window_pass": period is not None and data_period_start_year <= period_start and period_end <= data_period_end_year,
            }
            checks["data_period_classification"] = bool(
                period is not None
                and period_start >= data_period_start_year
                and period_end <= data_period_end_year
            )

            # -------------------------------------------------------------
            # Rule 3: Dynamic Country Relevance
            # -------------------------------------------------------------
            source_text = f"{s.get('source_title', '')} {s.get('full_text_or_abstract', '')}".casefold()
            has_original_content = bool(str(s.get("full_text_or_abstract") or "").strip())
            if target_countries:
                assigned_country = str(s.get("country") or "").strip()
                assigned_is_target = any(
                    self._countries_equivalent(assigned_country, target)
                    for target in target_countries
                ) if assigned_country else False
                country_match = (
                    assigned_is_target
                    and self._country_is_evidenced(source_text, assigned_country)
                    and not self._has_conflicting_country_scope(s, assigned_country)
                )
                checks["country_relevance"] = country_match
                checks["country_evidence"] = assigned_country if country_match else ""
                if country_match:
                    check_outcomes["country_relevance"] = "pass"
                elif not has_original_content:
                    check_outcomes["country_relevance"] = "review"
                    review_flags.append(f"Country relevance for {assigned_country or ', '.join(target_countries)} could not be verified because source content is inaccessible.")
                else:
                    check_outcomes["country_relevance"] = "fail"
                    rejection_reasons.append(f"Original source text does not establish relevance to assigned target country ({assigned_country or ', '.join(target_countries)}).")
            else:
                checks["country_relevance"] = True
                check_outcomes["country_relevance"] = "pass"

            # -------------------------------------------------------------
            # Rule 4: Dynamic Disease / Topic Relevance
            # -------------------------------------------------------------
            ignored_topic_words = {"type", "and", "the", "of", "for", "with"}
            disease_tokens = [w for w in re.split(r"\W+", target_disease) if len(w) > 2 and w not in ignored_topic_words]
            title_text = str(s.get("source_title") or "").casefold()
            title_topic_terms = list(disease_tokens)
            body_topic_terms = list(disease_tokens)
            if "obesity" in target_disease:
                obesity_terms = [
                    "obese", "overweight", "antiobesity", "anti-obesity", "adiposity",
                    "adipose", "bariatric", "weight bias", "weight stigma",
                    "weight management", "weight loss", "excess weight", "body fat",
                ]
                title_topic_terms.extend(obesity_terms)
                body_topic_terms.extend(obesity_terms + ["body mass index", "bmi"])
            source_text = f"{s.get('source_title', '')} {s.get('full_text_or_abstract', '')}".casefold()
            topic_in_title = not disease_tokens or any(
                self._has_term(title_text, term) for term in title_topic_terms
            )
            matching_body_terms = [term for term in body_topic_terms if self._has_term(source_text, term)]
            total_topic_occurrences = sum(
                len(re.findall(rf"(?<!\w){re.escape(term)}(?!\w)", source_text))
                for term in body_topic_terms
            )
            topic_is_central = topic_in_title or (len(matching_body_terms) >= 2 and total_topic_occurrences >= 3) or total_topic_occurrences >= 4
            topic_is_mentioned = topic_is_central or len(matching_body_terms) >= 1
            if topic_is_central:
                checks["disease_relevance"] = True
                check_outcomes["topic_relevance"] = "pass"
            elif not has_original_content:
                checks["disease_relevance"] = False
                check_outcomes["topic_relevance"] = "review"
                review_flags.append("Disease/topic relevance could not be verified because source content is inaccessible.")
            elif topic_is_mentioned:
                checks["disease_relevance"] = False
                check_outcomes["topic_relevance"] = "review"
                review_flags.append("The source mentions obesity-related concepts, but its title and content do not establish obesity as a central subject; review topical relevance.")
            else:
                checks["disease_relevance"] = False
                check_outcomes["topic_relevance"] = "fail"
                rejection_reasons.append(
                    f"Source title and retrieved text do not establish a substantive connection to '{target_disease}'."
                )

            # -------------------------------------------------------------
            # Rule 5: User-Defined Section Relevance
            # -------------------------------------------------------------
            candidate_sections = s.get("sections_covered", [])
            checks["scout_assigned_sections"] = list(candidate_sections)
            section_pool = list(dict.fromkeys(state.get("sections") or DEFAULT_RESEARCH_SECTIONS or candidate_sections))
            content_text = str(s.get("full_text_or_abstract") or "").casefold()
            title_text = str(s.get("source_title") or "").casefold()
            section_scores = []
            for sec in section_pool:
                sec_tokens = [w for w in re.split(r"\W+", sec.casefold()) if len(w) > 3 and w not in {"and", "with", "from", "for"}]
                keywords = SECTION_KEYWORDS.get(sec, sec_tokens)
                evidence_terms = [term.casefold() for term in keywords if term and self._has_term(content_text, term)]
                # Frequency and specificity-weighted score
                score = 0
                for term in evidence_terms:
                    occurrences = len(re.findall(rf"(?<!\w){re.escape(term)}(?!\w)", content_text))
                    weight = 1 + term.count(" ")
                    title_bonus = 2 if self._has_term(title_text, term) else 0
                    score += (weight + title_bonus) * min(occurrences, 10)
                if score > 0:
                    section_scores.append((score, sec, evidence_terms))
            section_scores.sort(key=lambda item: -item[0])
            if section_scores:
                top_score = section_scores[0][0]
                tied_sections = [entry for entry in section_scores if entry[0] == top_score]
                # Deterministic tie-breaking:
                # 1. Prefer candidate section if it is among the tied top sections
                primary_entry = None
                for candidate_sec in candidate_sections:
                    for tied in tied_sections:
                        if tied[1] == candidate_sec:
                            primary_entry = tied
                            break
                    if primary_entry:
                        break
                # 2. If no candidate section among tied, prefer section with longest specific phrase evidence
                if not primary_entry:
                    tied_sections.sort(key=lambda item: (-sum(len(t) for t in item[2]), item[1].casefold()))
                    primary_entry = tied_sections[0]
                primary_section = primary_entry[1]
                supported_sections = [primary_section]
                checks["section_evidence_terms"] = primary_entry[2]
            else:
                supported_sections = []
            s["sections_covered"] = supported_sections
            checks["section_relevance"] = bool(supported_sections)
            checks["supported_sections"] = supported_sections
            if not supported_sections:
                if not has_original_content:
                    check_outcomes["section_assignment"] = "review"
                    review_flags.append("Research-section relevance could not be verified because source content is inaccessible.")
                else:
                    check_outcomes["section_assignment"] = "review"
                    review_flags.append("Original source text does not substantiate any assigned research section.")
            else:
                check_outcomes["section_assignment"] = "pass"

            if not has_original_content:
                review_flags.append("Original source content is inaccessible; inspect the source before relying on its metadata.")
            if s.get("metadata_conflicts"):
                review_flags.extend(s["metadata_conflicts"])

            checks["duplicate_detection"] = True  # Candidate records were deduplicated above.
            checks["publication_year_verified"] = s.get("publication_year_verified") is True
            checks["country_relevance"] = bool(checks.get("country_relevance"))
            checks["topic_relevance"] = bool(checks.get("disease_relevance"))
            check_outcomes["duplicate_detection"] = "pass"
            checks["check_outcomes"] = check_outcomes
            s["validation_check_outcomes"] = check_outcomes

            # -------------------------------------------------------------
            # Final Decision Logic
            # -------------------------------------------------------------
            s["validation_checks"] = checks

            if rejection_reasons:
                s["validation_status"] = ValidationStatus.REJECTED.value
                s["validation_reasons"] = rejection_reasons + review_flags
                # Keep hard validation failures in the returned rejected list so
                # the API, QC summary, and Rejected & Review tab can count/render them.
                rejected.append(s)
                clean_title = str(s.get('source_title', ''))[:50].encode('ascii', 'replace').decode('ascii')
                print(f"  [REJECTED] '{clean_title}...' -> {'; '.join(rejection_reasons)}")
            elif review_flags:
                s["validation_status"] = ValidationStatus.NEEDS_REVIEW.value
                s["validation_reasons"] = review_flags
                # Add to review list but do NOT count as a primary validated source.
                review_candidates.append(s)
                # Also include in rejected_sources for visibility under "Rejected & Review" tab.
                rejected.append(s)
                clean_title = str(s.get('source_title', ''))[:50].encode('ascii', 'replace').decode('ascii')
                print(f"  [REVIEW CANDIDATE] '{clean_title}...' -> {'; '.join(review_flags)}")
            else:
                s["validation_status"] = ValidationStatus.PASSED_CHECKS.value
                s["validation_reasons"] = ["Passed all user-configured criteria."]
                validated.append(s)
                clean_title = str(s.get('source_title', ''))[:50].encode('ascii', 'replace').decode('ascii')
                print(f"  [PASSED] '{clean_title}...' (Year: {pub_year})")

            # Update DB with audit details
            self.db.save_source(state.get("project_id", "PROJ-DEFAULT"), s)

        review_candidate_count = len(review_candidates)
        hard_rejected_count = len(rejected) - len(review_candidates)
        print(
            f"[Stage 3: Validation] Summary: {len(validated)} accepted, "
            f"{review_candidate_count} review candidates, {hard_rejected_count} rejected."
        )

        audit_trail = state.get("audit_trail", [])
        audit_trail.append(
            f"Validation complete: {len(validated)} accepted, {review_candidate_count} review candidates, "
            f"{hard_rejected_count} rejected against user criteria."
        )

        return {
            "candidate_sources": candidates,
            "validated_sources": validated,
            "review_sources": review_candidates,
            "rejected_sources": rejected,
            "status": f"Validation complete: {len(validated)} passed",
            "audit_trail": audit_trail,
        }
