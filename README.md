# Autonomous-Research-Platform

An enterprise-grade, multi-agent research automation platform built using **LangGraph**, **Pydantic**, **SQLite**, and **open healthcare literature engines** (OpenAlex & NCBI PubMed). 

Designed for healthcare, epidemiology, market access, and pharmaceutical research organizations to autonomously transform a research brief (ASK) into verified evidence deliverables.

---

## 🌟 Key Capabilities & Architectural Pillars

1. **100% Free & Open-Access Data Ecosystem**:
   - Zero paid API keys required.
   - Connects directly to **OpenAlex** (>250M scholarly works) and **NCBI PubMed** (NIH National Library of Medicine).
   - Retrieves real peer-reviewed articles, clinical guidelines, regulatory approvals, and epidemiology studies.

2. **Non-Negotiable Source Validation Rules**:
   - **Rule 1 (Publication Date)**: Enforces strict publication cutoff of **>= 2021** (sources <= 2020 are rejected).
   - **Rule 2 (Data Period Tracking)**: Tracks survey/data period separately from publication date; automatically flags older underlying data cohorts for review.
   - **Rule 3 & 4 (Country & Disease Relevance)**: Filters out sources that fail to establish genuine geographical and condition relevance.
   - **Rule 5 & 6 (Section Relevance & Verification)**: Ensures findings substantiate assigned sections.

3. **Verbatim Quotation Exact-Match Verification**:
   - Verifies extracted quotations against the original retrieved text with substring matching.
   - Never hallucinates, modifies, or paraphrases quotes as verbatim.

4. **Multi-Agent LangGraph Workflow**:
   - **Stage 1: Planner Agent** (`ResearchPlanner`) - Decomposes ASK into country x section matrix targets.
   - **Stage 2: Scouting Agent** (`ResearchScoutingAgent`) - Discovers and retrieves primary literature.
   - **Stage 3: Validation Agent** (`SourceValidationAgent`) - Audits candidate sources against rules.
   - **Stage 4 & 5: Extraction Agent** (`EvidenceExtractionAgent`) - Extracts structured insights and verified quotations.
   - **Stage 6: Quality Control Agent** (`QualityControlAgent`) - Computes coverage matrix across 9 mandatory sections.
   - **Stage 7: Autonomous Correction Engine** (`AutonomousCorrectionEngine`) - Automatically triggers targeted queries for missing cells with bounded recovery loops.
   - **Stage 8: Exporters** (`ExcelSpreadsheetExporter`, `WordDocumentExporter`) - Generates exact deliverables.

5. **Exact Organization Deliverables**:
   - **Master Spreadsheet (`.xlsx`)**: Conforms strictly to the organization's exact 14 columns:
     1. `S. No.` | 2. `Source Title` | 3. `Name of the Source` | 4. `Source Type` | 5. `Year of Publication` | 6. `Period of the data used` | 7. `Description` | 8. `Access Type` | 9. `Source Link` | 10. `Sections Covered` | 11. `Summary` | 12. `Insights` | 13. `Verbatim` | 14. `Visual`
   - **Research Monograph (`.docx`)**: Formal Word report organized hierarchically by Country and the 9 Mandatory Sections:
     1. *Healthcare system overview*
     2. *Epidemiology*
     3. *Societal & Provider Perception of Obesity*
     4. *Clinical Guidelines & Treatment Practices*
     5. *Regulatory Framework & Approval Bodies*
     6. *Unmet Needs & Clinical Gaps*
     7. *Access, Coverage & Reimbursement Barriers*
     8. *Competitive Landscape & Product Intelligence*
     9. *Patient Advocacy, Public Affairs & Strategic Initiatives*

6. **ACID-Compliant State Persistence & Audit Trail**:
   - Uses SQLite (`storage/research_vault.db`) to log every project, source, insight, verbatim record, and workflow audit event.

---

## 🚀 Quick Start Guide

### 1. Activate Virtual Environment
Open PowerShell in the project directory:
```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Run the Full Autonomous Project
To immediately execute the complete end-to-end pipeline for the default brief (**Obesity in India across all 9 sections**):
```powershell
python run_project.py
```

### 3. Run the Interactive CLI
To submit custom topics, target countries, or customize section coverage:
```powershell
python main.py
```

Or run automated demo mode:
```powershell
python main.py --demo
```

### 4. Run the Test Suite
Run the 8 automated unit and integration tests:
```powershell
python -m unittest tests/test_system.py
```

---

## 📁 Project Directory Layout

```
c:\Users\HP\ResearchAutomation\
├── config\
│   └── settings.py          # Mandatory 9 sections, 14 spreadsheet columns, cutoff rules
├── core\
│   ├── models.py            # Pydantic data schemas: SourceRecord, InsightRecord, QCReport
│   └── state.py             # LangGraph ResearchSystemState typed dictionary
├── agents\
│   ├── planner.py           # Stage 1: Intake and planning agent
│   ├── scouting.py          # Stage 2: Scouting agent (OpenAlex & PubMed APIs)
│   ├── validation.py        # Stage 3: Source validation agent (2021+ rule, data period)
│   ├── extraction.py        # Stage 4 & 5: Insights and verbatim verification agent
│   ├── qc.py                # Stage 6: Quality control agent (coverage matrix)
│   └── correction.py        # Stage 7: Autonomous recovery coordinator
├── exporters\
│   ├── excel_exporter.py    # Stage 8: Exact 14-column spreadsheet (.xlsx) generator
│   └── docx_exporter.py     # Stage 8: Structured Word report (.docx) generator
├── storage\
│   └── database.py          # SQLite persistence & audit trail logger
├── graph\
│   └── research_graph.py    # LangGraph StateGraph assembly and compilation
├── output\                  # Generated .xlsx and .docx deliverables
├── tests\
│   └── test_system.py       # Automated unit & integration tests
├── main.py                  # Interactive CLI runner
├── run_project.py           # One-click execution script
└── README.md                # Comprehensive documentation
```
>>>>>>> fc8b414 (Fix source discovery regression, improve data period detection, ensure single primary section per source, add .gitignore)
