"""
FastAPI Backend & Vercel Serverless Function
============================================
Exposes RESTful endpoints for research brief submission, live LangGraph
orchestration, and direct downloads for Excel (.xlsx) and Word (.docx) deliverables.
Also serves the rich interactive web dashboard.
"""
import sys
import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Ensure workspace root is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.settings import (
    DEFAULT_RESEARCH_SECTIONS, MIN_PUBLICATION_YEAR,
    DATA_PERIOD_START_YEAR, DATA_PERIOD_END_YEAR,
    MIN_INSIGHTS_PER_SOURCE, MIN_VERBATIMS_PER_SOURCE, OUTPUT_DIR,
    MAX_SCOUT_RESULTS_PER_SECTION,
)
from graph.research_graph import compiled_research_graph


app = FastAPI(
    title="Autonomous Healthcare Research API",
    description="Multi-Agent Research Automation System powered by LangGraph",
    version="1.0.0"
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static folder if it exists
STATIC_DIR = ROOT_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve generated deliverables as static files (fallback)
DOWNLOAD_DIR = OUTPUT_DIR
app.mount("/download", StaticFiles(directory=str(DOWNLOAD_DIR)), name="download")


class ResearchRequest(BaseModel):
    topic: str = "Obesity"
    disease: Optional[str] = "Obesity"
    countries: List[str] = ["India"]
    sections: Optional[List[str]] = None
    min_publication_year: int = Field(default=MIN_PUBLICATION_YEAR, ge=1900, le=2100)
    data_period_start_year: int = Field(default=DATA_PERIOD_START_YEAR, ge=1900, le=2100)
    data_period_end_year: int = Field(default=DATA_PERIOD_END_YEAR, ge=1900, le=2100)
    # Compatibility for older clients that still send the former single threshold.
    data_period_threshold: Optional[int] = Field(default=None, ge=1900, le=2100)
    max_sources_per_section: int = Field(default=MAX_SCOUT_RESULTS_PER_SECTION, ge=1, le=100)
    min_insights_per_source: Optional[int] = MIN_INSIGHTS_PER_SOURCE
    min_verbatims_per_source: Optional[int] = MIN_VERBATIMS_PER_SOURCE

    @model_validator(mode="after")
    def validate_data_period_window(self):
        if (
            self.data_period_threshold is not None
            and "data_period_threshold" in self.model_fields_set
            and "data_period_start_year" not in self.model_fields_set
        ):
            self.data_period_start_year = self.data_period_threshold
        if self.data_period_start_year > self.data_period_end_year:
            raise ValueError("Data Period Start Year must be less than or equal to End Year.")
        return self


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the master web application dashboard."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Research Automation API is running. Dashboard loading...</h2>")


@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "service": "Autonomous Healthcare Research Automation",
        "engine": "LangGraph Multi-Agent StateGraph",
        "cost": "$0.00 (Zero API Key Dependency)"
    }


@app.get("/api/defaults")
async def get_defaults():
    """Return default configuration parameters for UI dropdowns."""
    return {
        "default_topic": "Obesity",
        "default_countries": ["India"],
        "min_publication_year": MIN_PUBLICATION_YEAR,
        "data_period_start_year": DATA_PERIOD_START_YEAR,
        "data_period_end_year": DATA_PERIOD_END_YEAR,
        "data_period_threshold": DATA_PERIOD_START_YEAR,
        "sections": DEFAULT_RESEARCH_SECTIONS,
    }


@app.post("/api/research")
async def launch_research(req: ResearchRequest):
    """Execute the full autonomous LangGraph workflow and return structured results."""
    try:
        sections = req.sections if req.sections else DEFAULT_RESEARCH_SECTIONS
        disease = req.disease or req.topic

        initial_state = {
            "topic": req.topic,
            "disease": disease,
            "countries": req.countries,
            "sections": sections,
            "min_publication_year": req.min_publication_year,
            "data_period_start_year": req.data_period_start_year,
            "data_period_end_year": req.data_period_end_year,
            "data_period_threshold": req.data_period_start_year,
            "max_sources_per_section": req.max_sources_per_section,
            "min_insights_per_source": req.min_insights_per_source or MIN_INSIGHTS_PER_SOURCE,
            "min_verbatims_per_source": req.min_verbatims_per_source or MIN_VERBATIMS_PER_SOURCE,
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

        # Run the compiled LangGraph workflow
        final_state = compiled_research_graph.invoke(initial_state)

        project_id = final_state.get("project_id", "PROJ-DEFAULT")
        excel_path = final_state.get("excel_file_path", "")
        docx_path = final_state.get("docx_file_path", "")

        return {
            "success": True,
            "project_id": project_id,
            "status": final_state.get("status"),
            "topic": req.topic,
            "countries": req.countries,
            "validation_rules": {
                "min_publication_year": req.min_publication_year,
                "data_period_start_year": req.data_period_start_year,
                "data_period_end_year": req.data_period_end_year,
            },
            "coverage_matrix": final_state.get("coverage_matrix", {}),
            "year_wise_coverage": final_state.get("year_wise_coverage", {}),
            "year_coverage_gaps": final_state.get("year_coverage_gaps", []),
            "qc_report": final_state.get("qc_report", {}),
            "validated_sources_count": len({s.get("id") for s in final_state.get("validated_sources", []) if s.get("id")}),
            "rejected_sources_count": sum(
                1 for s in final_state.get("rejected_sources", [])
                if s.get("validation_status") != "Needs review"
            ),
            "review_sources_count": len(final_state.get("review_sources", [])),
            "insights_count": len(final_state.get("insights", [])),
            "verbatims_count": sum(
                1 for item in final_state.get("verbatims", [])
                if item.get("match_verified") is True
                and item.get("verification_status") == "verified_exact_match"
            ),
            "extraction_completeness": final_state.get("extraction_completeness", {}),
            "validated_sources": final_state.get("validated_sources", []),
            "review_sources": final_state.get("review_sources", []),
            "rejected_sources": final_state.get("rejected_sources", []),
            "insights": final_state.get("insights", []),
            "verbatims": final_state.get("verbatims", []),
            "audit_trail": final_state.get("audit_trail", []),
            "excel_filename": Path(excel_path).name if excel_path else "",
            "docx_filename": Path(docx_path).name if docx_path else "",
            "excel_download_url": f"/api/download/excel/{project_id}",
            "docx_download_url": f"/api/download/word/{project_id}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/download/excel/{project_id}")
async def download_excel(project_id: str):
    """Download the generated 14-column spreadsheet for the given project ID."""
    target = OUTPUT_DIR / f"Research_Spreadsheet_{project_id}.xlsx"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Excel spreadsheet not found for this project.")
    return FileResponse(
        path=str(target),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=target.name,
    )


@app.get("/api/download/word/{project_id}")
async def download_word(project_id: str):
    """Download the generated Word monograph for the given project ID."""
    target = OUTPUT_DIR / f"Research_Report_{project_id}.docx"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Word report not found for this project.")
    return FileResponse(
        path=str(target),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=target.name,
    )
