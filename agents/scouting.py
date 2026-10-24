"""
Stage 2: Autonomous Research Scouting Agent
===========================================
Executes genuine searches against healthcare and scientific literature engines
(OpenAlex, NCBI PubMed, CrossRef, and Open Access repositories).
Retrieves real source content, extracts metadata (title, publisher, year, DOI/URL,
abstract/content), canonicalizes URLs, and avoids duplicates.
Dynamically adapts to user's topic, countries, cutoff years, and sections.
"""
import uuid
import re
from datetime import datetime
import requests
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from core.models import SourceRecord, ValidationStatus, SourceType, AccessType
from config.settings import (
    SECTION_KEYWORDS, MAX_SCOUT_RESULTS_PER_SECTION, MIN_PUBLICATION_YEAR,
)
from storage.database import ResearchDatabase


class ResearchScoutingAgent:
    """Agent executing real literature discovery and document retrieval."""

    def __init__(self, db: ResearchDatabase = None):
        self.db = db or ResearchDatabase()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ResearchAutomationHealthcare/1.0 (mailto:researcher@organization.org)"
        })
        self._content_cache: Dict[str, List[Dict[str, str]]] = {}
        self._source_metadata_cache: Dict[str, Dict[str, Any]] = {}
        self._last_provider_error = ""

    def scout(self, state: Dict[str, Any], targeted_queries: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """
        Execute literature search across all generated queries in the plan,
        or against targeted queries during recovery loops.
        """
        plan = state.get("plan", {})
        queries_to_run = targeted_queries or plan.get("generated_queries", [])
        disease = state.get("disease") or state.get("topic") or "Healthcare"
        min_year = state.get("min_publication_year", MIN_PUBLICATION_YEAR)
        existing_sources = state.get("candidate_sources", [])
        provider_diagnostics = []
        
        discovered: List[Dict[str, Any]] = list(existing_sources)
        newly_found = 0

        print(f"\n[Stage 2: Scouting] Scouting literature across {len(queries_to_run)} research queries...")

        for q_info in queries_to_run:
            country = q_info["country"]
            section = q_info["section"]
            query_text = q_info["query"]
            data_year = q_info.get("data_year")
            print(f"  [QUERY] [{country} | {section}] -> '{query_text}'")

            max_scout_limit = state.get("max_sources_per_section") or MAX_SCOUT_RESULTS_PER_SECTION
            result_limit = max_scout_limit
            # Search each section independently. The same publication may appear as
            # a separate section-specific record; deduplicate only within this section.
            self._last_provider_error = ""
            openalex_results = self._search_openalex(
                disease, country, section, min_year, max_results=result_limit,
                search_query=query_text,
            )
            openalex_error = self._last_provider_error
            self._last_provider_error = ""
            pubmed_results = self._search_pubmed(
                disease, country, section, min_year, max_results=result_limit,
                data_year=data_year,
            )
            pubmed_error = self._last_provider_error
            diag = {
                "country": country, "section": section,
                "openalex_retrieved": len(openalex_results),
                "pubmed_retrieved": len(pubmed_results),
            }
            if openalex_error:
                diag["openalex_error"] = openalex_error
            if pubmed_error:
                diag["pubmed_error"] = pubmed_error
            provider_diagnostics.append(diag)
            if openalex_error or pubmed_error:
                audit_trail = state.get("audit_trail", [])
                audit_trail.append(
                    f"[{country} | {section}] Provider search incomplete: "
                    f"OpenAlex={len(openalex_results)} ({openalex_error or 'ok'}); "
                    f"PubMed={len(pubmed_results)} ({pubmed_error or 'ok'})."
                )
            results = openalex_results + pubmed_results
            # Continue targeted searches when too few sources are retrieved for this section
            target_scout_batch = min(5, max_scout_limit)
            if len(results) < target_scout_batch:
                kw_list = SECTION_KEYWORDS.get(section, [])
                alt_terms = kw_list[3:7] if len(kw_list) > 3 else kw_list
                if alt_terms:
                    self._last_provider_error = ""
                    supp_pubmed = self._search_pubmed(
                        disease, country, section, min_year, max_results=result_limit,
                        data_year=data_year, custom_terms=alt_terms,
                    )
                    results.extend(supp_pubmed)
            added_before_query = newly_found
            section_seen = set()
            section_count = 0
            for source in discovered:
                if source.get("country", "").lower() != country.lower():
                    continue
                if section not in source.get("sections_covered", []):
                    continue
                section_count += 1
                source_title = re.sub(r"\W+", "", source.get("source_title", "").lower())
                source_link = source.get("source_link", "").lower().strip()
                if source_title:
                    section_seen.add(source_title)
                if source_link:
                    section_seen.add(source_link)

            for item in results:
                item_country = str(item.get("country") or country).strip()
                item["country"] = item_country
                item["disease"] = disease
                norm_title = re.sub(r"\W+", "", item.get("source_title", "").lower())
                link = item.get("source_link", "").lower().strip()

                # Keep one source row per underlying publication. Do not add
                # extra section labels here; validation assigns one primary
                # section from retrieved source content.
                duplicate = next((candidate for candidate in discovered
                    if str(candidate.get("country", "")).casefold() == item_country.casefold()
                    and (
                        (norm_title and re.sub(r"\W+", "", str(candidate.get("source_title", "")).lower()) == norm_title)
                        or (link and str(candidate.get("source_link", "")).lower().strip() == link)
                    )), None)
                if duplicate:
                    continue

                if (norm_title and norm_title in section_seen) or (link and link in section_seen):
                    continue

                if section_count >= max_scout_limit:
                    break

                if norm_title:
                    section_seen.add(norm_title)
                if link:
                    section_seen.add(link)

                # Record the requested country as a search target only. The
                # validator independently checks geographic evidence in source text.
                if section not in item["sections_covered"]:
                    item["sections_covered"].append(section)
                item["validation_status"] = ValidationStatus.RETRIEVED.value

                discovered.append(item)
                newly_found += 1
                section_count += 1
                
                # Persist source to database
                self.db.save_source(state.get("project_id", "PROJ-DEFAULT"), item)

            audit_trail = state.get("audit_trail", [])
            audit_trail.append(
                f"[{country} | {section}] Search returned {len(openalex_results)} OpenAlex and "
                f"{len(pubmed_results)} PubMed records; section coverage now has {section_count} sources, "
                f"with {newly_found - added_before_query} new unique candidates."
            )

        print(f"[Stage 2: Scouting] Discovered {newly_found} new sources. Total candidate pool: {len(discovered)}")
        
        audit_trail.append(f"Scouted {newly_found} new authentic sources for {len(queries_to_run)} queries.")

        return {
            "candidate_sources": discovered,
            "provider_diagnostics": provider_diagnostics,
            "status": f"Scouted {len(discovered)} total sources",
            "audit_trail": audit_trail,
        }

    def _search_openalex(self, disease: str, country: str, section: str, min_year: int, max_results: int = 3, search_query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search OpenAlex scholarly API for peer-reviewed studies."""
        sources: List[Dict[str, Any]] = []
        try:
            sec_tokens = [w for w in re.split(r"\W+", section) if len(w) > 3 and w.lower() not in ["and", "with", "from"]]
            kw_list = SECTION_KEYWORDS.get(section, sec_tokens)
            kw_sample = " ".join(kw_list[:2]) if kw_list else "healthcare"
            
            search_term = search_query or f"{disease} {country} {kw_sample}"
            
            url = "https://api.openalex.org/works"
            params = {
                "search": search_term,
                "filter": f"from_publication_date:{min_year}-01-01,to_publication_date:{datetime.now().year}-12-31",
                "per_page": max_results,
                "sort": "relevance_score:desc",
            }
            resp = self.session.get(url, params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                for work in data.get("results", []):
                    title = work.get("title") or "Untitled Publication"
                    pub_year = work.get("publication_year")
                    
                    # Extract publisher/journal name
                    primary_loc = work.get("primary_location") or {}
                    source_meta = primary_loc.get("source") or {}
                    publisher = source_meta.get("display_name") or "Peer-Reviewed Medical Journal"
                    
                    # Extract access and URL
                    oa_info = work.get("open_access") or {}
                    oa_url = oa_info.get("oa_url") or primary_loc.get("landing_page_url") or work.get("doi") or f"https://openalex.org/{work.get('id', '')}"
                    publication_url = primary_loc.get("landing_page_url") or work.get("doi") or f"https://openalex.org/{work.get('id', '')}"
                    access_type = AccessType.OPEN_ACCESS.value if oa_info.get("is_oa") else AccessType.ABSTRACT_ONLY.value

                    # Start with the real abstract from OpenAlex metadata.
                    abstract_index = work.get("abstract_inverted_index")
                    abstract = self._reconstruct_abstract(abstract_index) if abstract_index else ""
                    content_chunks = ([{"location": "Abstract", "text": abstract}] if abstract else [])
                    if (work.get("open_access") or {}).get("is_oa"):
                        open_chunks = self._fetch_openalex_full_text(work)
                        open_text = "\n\n".join(chunk["text"] for chunk in open_chunks)
                        if len(open_text) > len(abstract):
                            content_chunks = open_chunks
                    source_text = "\n\n".join(chunk["text"] for chunk in content_chunks)
                    content_completeness = (
                        "full_text" if content_chunks and content_chunks[0].get("location") != "Abstract"
                        else ("abstract_only" if abstract else "inaccessible")
                    )

                    # Classify source type
                    doc_type = work.get("type", "article")
                    if "guideline" in title.lower() or "recommendation" in title.lower():
                        stype = SourceType.CLINICAL_GUIDELINE.value
                    elif doc_type in ["report", "government"]:
                        stype = SourceType.GOVERNMENT_REPORT.value
                    else:
                        stype = SourceType.RESEARCH_ARTICLE.value

                    # Extract data period from abstract if mentioned (e.g. 2018-2022 or 2021)
                    period_details = self._detect_data_period_details(
                        content_chunks or ([{"location": "Abstract", "text": abstract}] if abstract else []),
                        content_completeness,
                    )

                    source_record = SourceRecord(
                        id=f"SRC-{uuid.uuid4().hex[:8].upper()}",
                        source_title=title,
                        name_of_source=publisher,
                        source_type=stype,
                        publication_year=pub_year,
                        data_period=period_details["data_period"],
                        data_period_start_year=period_details["start_year"],
                        data_period_end_year=period_details["end_year"],
                        data_period_type=period_details["period_type"],
                        data_period_evidence=period_details["evidence"],
                        data_period_location=period_details["location"],
                        data_period_status=period_details["status"],
                        description=f"Authentic scientific publication on {disease} and {section} in {country}.",
                        access_type=access_type,
                        source_link=publication_url,
                        canonical_url=work.get("doi") or publication_url,
                        sections_covered=[section],
                        summary=source_text[:400] + ("..." if len(source_text) > 400 else ""),
                        full_text_or_abstract=source_text,
                        country=country,
                        disease=disease,
                        validation_status=ValidationStatus.RETRIEVED,
                        content_completeness=content_completeness,
                        content_chunks=content_chunks,
                        source_provider="OpenAlex",
                        provider_record_id=str(work.get("id") or ""),
                        provider_record_url=str(work.get("id") or ""),
                        source_authenticity_verified=bool(work.get("id") and title and source_meta),
                        publication_year_verified=bool(pub_year and work.get("id")),
                    )
                    sources.append(source_record.model_dump())
            else:
                self._last_provider_error = f"HTTP {resp.status_code} from OpenAlex"
        except Exception as e:
            self._last_provider_error = str(e)
            print(f"  [Scouting Warning] OpenAlex query exception: {e}")

        return sources

    def _fetch_openalex_full_text(self, work: Dict[str, Any]) -> List[Dict[str, str]]:
        """Fetch readable, location-preserving text from an OA PDF or article page."""
        locations = [work.get("best_oa_location") or {}, work.get("primary_location") or {}]
        locations.extend(work.get("locations") or [])
        urls: List[str] = []
        for location in locations:
            if not location or location.get("is_oa") is False:
                continue
            for key in ("pdf_url", "landing_page_url"):
                candidate = location.get(key)
                if candidate and candidate not in urls:
                    urls.append(candidate)

        for url in urls:
            if url in self._content_cache:
                cached = self._content_cache[url]
                if cached:
                    return cached
                continue
            chunks: List[Dict[str, str]] = []
            try:
                response = self.session.get(url, timeout=(4, 10), stream=True)
                if response.status_code != 200:
                    self._content_cache[url] = []
                    continue
                content_type = response.headers.get("Content-Type", "").lower()
                payload = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    payload.extend(chunk)
                    if len(payload) > 30 * 1024 * 1024:
                        payload.clear()
                        break
                response.close()
                if not payload:
                    self._content_cache[url] = []
                    continue

                if "pdf" in content_type or payload.startswith(b"%PDF"):
                    try:
                        import fitz
                        document = fitz.open(stream=bytes(payload), filetype="pdf")
                        for page_number, page in enumerate(document, start=1):
                            page_text = self._trim_reference_section(page.get_text("text"))
                            if page_text:
                                chunks.append({"location": f"Page {page_number}", "text": page_text})
                        document.close()
                    except Exception as pdf_error:
                        print(f"  [Scouting Warning] Open-access PDF text extraction failed: {pdf_error}")
                elif "html" in content_type or "xml" in content_type or b"<html" in payload[:1000].lower():
                    soup = BeautifulSoup(bytes(payload), "html.parser")
                    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
                        tag.decompose()
                    article = soup.select_one(
                        "article, main, [itemprop='articleBody'], .article-body, #article-body, .fulltext"
                    ) or soup.body
                    if article is not None:
                        sections = article.find_all("section")
                        for section in sections:
                            heading = section.find(["h1", "h2", "h3", "h4"])
                            text = section.get_text("\n", strip=True)
                            text = self._trim_reference_section(text)
                            if text and len(text) >= 250:
                                chunks.append({
                                    "location": heading.get_text(" ", strip=True) if heading else "Open-access full text",
                                    "text": text,
                                })
                        if not chunks:
                            text = self._trim_reference_section(article.get_text("\n", strip=True))
                            if text:
                                chunks.append({"location": "Open-access full text", "text": text})

                # Do not replace a real abstract with a thin landing-page shell.
                if sum(len(chunk["text"]) for chunk in chunks) < 500:
                    chunks = []
            except Exception as fetch_error:
                print(f"  [Scouting Warning] Open-access full-text fetch failed: {fetch_error}")
            self._content_cache[url] = chunks
            if chunks:
                return chunks
        return []

    @staticmethod
    def _trim_reference_section(text: str) -> str:
        """Exclude bibliography text so it is not mistaken for study findings."""
        match = re.search(r"(?im)^\s*(references|bibliography|literature cited)\s*$", text or "")
        return (text[:match.start()] if match else text).strip()

    def _search_pubmed(self, disease: str, country: str, section: str, min_year: int, max_results: int = 2, data_year: Optional[int] = None, custom_terms: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Query NCBI PubMed e-utilities for medical literature and fetch real abstracts."""
        sources: List[Dict[str, Any]] = []
        try:
            publication_end_year = datetime.now().year
            term = f"({disease}[Title/Abstract]) AND ({country}[Title/Abstract]) AND {min_year}:{publication_end_year}[pdat]"
            section_terms = custom_terms or SECTION_KEYWORDS.get(section, [section])[:4]
            if section_terms:
                term += " AND (" + " OR ".join(f'"{keyword}"[Title/Abstract]' for keyword in section_terms) + ")"
            if data_year:
                term += f' AND "{data_year}"[Title/Abstract]'
            esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            params = {
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": max_results,
            }
            resp = self.session.get(esearch_url, params=params, timeout=10)
            if resp.status_code == 200:
                id_list = resp.json().get("esearchresult", {}).get("idlist", [])
                if id_list:
                    # --------------------------------------------------
                    # Fetch real abstracts via efetch (XML)
                    # --------------------------------------------------
                    efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                    fetch_resp = self.session.get(efetch_url, params={
                        "db": "pubmed",
                        "id": ",".join(id_list),
                        "retmode": "xml",
                        "rettype": "abstract",
                    }, timeout=15)
                    abstracts_by_pmid: Dict[str, str] = {}
                    pmcids_by_pmid: Dict[str, str] = {}
                    if fetch_resp.status_code == 200:
                        try:
                            from xml.etree import ElementTree as ET
                            root = ET.fromstring(fetch_resp.text)
                            for article in root.findall(".//PubmedArticle"):
                                pmid_el = article.find(".//PMID")
                                pmid_val = pmid_el.text.strip() if pmid_el is not None else ""
                                pmcid_el = article.find(".//ArticleId[@IdType='pmc']")
                                if pmid_val and pmcid_el is not None and pmcid_el.text:
                                    pmcids_by_pmid[pmid_val] = pmcid_el.text.strip()
                                # Collect all AbstractText elements (structured abstracts have multiple)
                                abstract_parts = []
                                for ab in article.findall(".//AbstractText"):
                                    label = ab.get("Label", "")
                                    text_part = (ab.text or "").strip()
                                    if label and text_part:
                                        abstract_parts.append(f"{label}: {text_part}")
                                    elif text_part:
                                        abstract_parts.append(text_part)
                                if abstract_parts:
                                    abstracts_by_pmid[pmid_val] = " ".join(abstract_parts)
                        except Exception as xml_err:
                            print(f"  [Scouting Warning] PubMed abstract XML parse error: {xml_err}")

                    # --------------------------------------------------
                    # Fetch metadata via esummary
                    # --------------------------------------------------
                    esummary_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                    s_resp = self.session.get(esummary_url, params={"db": "pubmed", "id": ",".join(id_list), "retmode": "json"}, timeout=10)
                    if s_resp.status_code == 200:
                        results_map = s_resp.json().get("result", {})
                        for pmid in id_list:
                            doc = results_map.get(pmid, {})
                            title = doc.get("title", "").rstrip(".")
                            pub_date = doc.get("pubdate", "")
                            match = re.search(r"\b(20\d\d)\b", pub_date)
                            pub_year = int(match.group(1)) if match else None
                            journal = doc.get("source", "PubMed Medical Journal")
                            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

                            # Prefer open full text from PubMed Central, then use the
                            # actual PubMed abstract. Never manufacture source text.
                            abstract = abstracts_by_pmid.get(pmid, "")
                            content_chunks = ([{"location": "Abstract", "text": abstract}] if abstract else [])
                            pmcid = pmcids_by_pmid.get(pmid)
                            if pmcid:
                                pmc_chunks = self._fetch_pmc_full_text(pmcid)
                                if sum(len(chunk["text"]) for chunk in pmc_chunks) > len(abstract):
                                    content_chunks = pmc_chunks
                            full_text = "\n\n".join(chunk["text"] for chunk in content_chunks)
                            content_completeness = (
                                "full_text" if content_chunks and content_chunks[0].get("location") != "Abstract"
                                else ("abstract_only" if abstract else "inaccessible")
                            )

                            period_details = self._detect_data_period_details(
                                content_chunks,
                                content_completeness,
                            )

                            source_record = SourceRecord(
                                id=f"SRC-{uuid.uuid4().hex[:8].upper()}",
                                source_title=title,
                                name_of_source=journal,
                                source_type=SourceType.RESEARCH_ARTICLE.value,
                                publication_year=pub_year,
                                data_period=period_details["data_period"],
                                data_period_start_year=period_details["start_year"],
                                data_period_end_year=period_details["end_year"],
                                data_period_type=period_details["period_type"],
                                data_period_evidence=period_details["evidence"],
                                data_period_location=period_details["location"],
                                data_period_status=period_details["status"],
                                description=f"PubMed indexed clinical research on {disease} and {section}.",
                                access_type=(AccessType.OPEN_ACCESS.value if content_completeness == "full_text" else AccessType.ABSTRACT_ONLY.value),
                                source_link=url,
                                sections_covered=[section],
                                summary=full_text[:400] + ("..." if len(full_text) > 400 else ""),
                                full_text_or_abstract=full_text,
                                country=country,
                                disease=disease,
                                validation_status=ValidationStatus.RETRIEVED,
                                content_completeness=content_completeness,
                                content_chunks=content_chunks,
                                source_provider="PubMed",
                                provider_record_id=str(pmid),
                                provider_record_url=url,
                                source_authenticity_verified=bool(pmid and title and journal and doc),
                                publication_year_verified=bool(pub_year and pmid),
                            )
                            sources.append(source_record.model_dump())
            else:
                self._last_provider_error = f"HTTP {resp.status_code} from PubMed"
        except Exception as e:
            self._last_provider_error = str(e)
            print(f"  [Scouting Warning] PubMed query exception: {e}")

        return sources

    def _fetch_pmc_full_text(self, pmcid: str) -> List[Dict[str, str]]:
        """Fetch section-preserving article body text for a PMC record."""
        pmcid = pmcid.strip().upper()
        if not re.fullmatch(r"PMC\d+", pmcid):
            return []
        cache_key = f"pmc:{pmcid}"
        if cache_key in self._content_cache:
            return self._content_cache[cache_key]
        chunks: List[Dict[str, str]] = []
        try:
            response = self.session.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                params={"db": "pmc", "id": pmcid, "retmode": "xml"},
                timeout=(10, 30),
            )
            if response.status_code == 200:
                from xml.etree import ElementTree as ET
                root = ET.fromstring(response.text)
                article_title = root.find(".//article-title")
                journal_title = root.find(".//journal-title")
                title_text = " ".join("".join(article_title.itertext()).split()) if article_title is not None else ""
                journal_text = " ".join("".join(journal_title.itertext()).split()) if journal_title is not None else ""
                publication_year = None
                article_meta = root.find(".//article-meta")
                if article_meta is not None:
                    pub_dates = article_meta.findall("./pub-date")
                    pub_dates.sort(key=lambda item: 0 if item.get("pub-type") in {"epub", "electronic"} else 1)
                    for pub_date in pub_dates:
                        year_element = pub_date.find("./year")
                        if year_element is not None and (year_element.text or "").strip().isdigit():
                            publication_year = int(year_element.text.strip())
                            break
                doi_element = root.find(".//article-id[@pub-id-type='doi']")
                self._source_metadata_cache[cache_key] = {
                    "source_title": title_text,
                    "name_of_source": journal_text,
                    "publication_year": publication_year,
                    "doi": (doi_element.text or "").strip() if doi_element is not None else "",
                }
                body = root.find(".//body")
                if body is not None:
                    def collect_section(section, parent_title=""):
                        title_element = section.find("./title")
                        section_title = " ".join("".join(title_element.itertext()).split()) if title_element is not None else ""
                        location = " — ".join(part for part in (parent_title, section_title) if part) or "PMC full text"
                        paragraphs = [
                            " ".join("".join(paragraph.itertext()).split())
                            for paragraph in section.findall("./p")
                        ]
                        section_text = self._trim_reference_section("\n".join(p for p in paragraphs if p))
                        if section_text:
                            chunks.append({"location": location, "text": section_text})
                        for child in section.findall("./sec"):
                            collect_section(child, location)

                    top_sections = body.findall("./sec")
                    for section in top_sections:
                        collect_section(section)
                    body_paragraphs = [
                        " ".join("".join(paragraph.itertext()).split())
                        for paragraph in body.findall("./p")
                    ]
                    if body_paragraphs:
                        body_text = self._trim_reference_section("\n".join(p for p in body_paragraphs if p))
                        if body_text:
                            chunks.insert(0, {"location": "PMC full text", "text": body_text})
        except Exception as fetch_error:
            print(f"  [Scouting Warning] PMC full-text fetch failed for {pmcid}: {fetch_error}")
        self._content_cache[cache_key] = chunks
        return chunks

    def _get_cached_pmc_metadata(self, pmcid: str) -> Dict[str, Any]:
        """Return metadata parsed from the same original PMC XML document."""
        return dict(self._source_metadata_cache.get(f"pmc:{pmcid.strip().upper()}", {}))


    def _reconstruct_abstract(self, inverted_index: Optional[Dict[str, List[int]]]) -> str:
        """Reconstruct plain abstract text from OpenAlex inverted index structure."""
        if not inverted_index:
            return ""
        try:
            word_positions = []
            for word, positions in inverted_index.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort(key=lambda x: x[0])
            return " ".join(w for _, w in word_positions)
        except Exception:
            return ""

    def _detect_data_period_details(
        self, chunks: List[Dict[str, str]], content_completeness: str = "unknown"
    ) -> Dict[str, Any]:
        """Extract a conservative data period from an explicit statement in source text."""
        year = r"(?:19\d{2}|20\d{2})"
        month = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|May\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Oct\.?|Nov\.?|Dec\.?)"
        date_prefix = rf"(?:{month}\s+\d{{1,2}},?\s+|{month}\s+)?"
        day_prefix = r"(?:\b\d{1,2}(?:st|nd|rd|th)?,?\s+)?"
        period = re.compile(
            rf"(?:(?:between|from|in|during)\s+)?{date_prefix}({year})(?:\s*,?\s*(?:-|–|—|to|through|and)\s*{date_prefix}({year}))?",
            re.I,
        )
        cue_pattern = re.compile(
            r"\b(?:data\s+(?:were|was)?\s*(?:collected|gathered|obtained|recorded|retrieved|drawn|abstracted)|"
            r"data\s+collection\s+(?:was\s+)?(?:carried\s+out|conducted|took\s+place)|"
            r"(?:study|survey|trial|investigation|evaluation|poll|fieldwork)s?\s+(?:were|was)?\s*(?:conducted|carried\s+out|performed|undertaken|implemented|executed|done)|"
            r"(?:surveys?|questionnaires?)\s+(?:were|was)?\s*(?:administered|completed)|"
            r"(?:patients|participants|subjects|individuals|cases|cohorts?|respondents)\s+(?:were)?\s*(?:enrolled|recruited|included|assessed|followed|surveyed|interviewed|examined)|"
            r"collection\s+period|collection\s+took\s+place|data\s+from|dataset\s+from|cohort\s+from)\b",
            re.I,
        )
        for chunk in chunks or []:
            location = str(chunk.get("location") or "Source text")
            text = str(chunk.get("text") or "")
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
                sentence = sentence.strip()
                cue = cue_pattern.search(sentence)
                if not cue:
                    continue
                lowered = sentence.casefold()
                after_cue = sentence[cue.end():]
                future_pos = re.search(r"\b(?:projected|planned|expected|anticipated|forecast|will\s+be)\b", after_cue, re.I)
                actual_clause = after_cue[:future_pos.start()] if future_pos else after_cue
                match = period.search(actual_clause)
                if not match:
                    reverse = re.search(
                        rf"({year})\s*(?:-|–|—|to|through)\s*({year})\s+(?:NFHS|survey|dataset|data|study|cohort)\b",
                        sentence, re.I,
                    )
                    if not reverse:
                        continue
                    start, end = int(reverse.group(1)), int(reverse.group(2))
                else:
                    start, end = int(match.group(1)), int(match.group(2) or match.group(1))
                if start > end:
                    start, end = end, start
                if not (1900 <= start <= 2100 and 1900 <= end <= 2100):
                    continue
                if any(term in lowered for term in ("secondary", "dataset", "database", "administrative data")):
                    period_type = "secondary_dataset"
                elif any(term in lowered for term in ("survey", "nfhs", "questionnaire")):
                    period_type = "survey"
                elif "fieldwork" in lowered:
                    period_type = "data_collection"
                else:
                    period_type = "data_collection"
                verified = content_completeness == "full_text" and location.casefold() != "abstract"
                return {
                    "data_period": str(start) if start == end else f"{start}–{end}",
                    "start_year": start,
                    "end_year": end,
                    "period_type": period_type,
                    "evidence": sentence[:1000],
                    "location": location,
                    "status": "Verified" if verified else "Partially verified",
                }

        return {
            "data_period": "Unknown", "start_year": None, "end_year": None,
            "period_type": "unknown", "evidence": "", "location": "", "status": "Unknown",
        }

    def _detect_data_period(self, text: str, pub_year: Optional[int] = None) -> str:
        """Compatibility helper returning only the source-grounded period string."""
        return self._detect_data_period_details(
            [{"location": "Abstract", "text": text}], "abstract_only"
        )["data_period"]
