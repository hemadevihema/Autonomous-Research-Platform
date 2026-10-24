"""
LangGraph Multi-Agent Orchestrator
==================================
Assembles the end-to-end research automation system into a compiled StateGraph.
Implements typed state passing, deterministic validation, autonomous gap detection,
bounded recovery loops, and final deliverable generation.
"""
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, START, END

from core.state import ResearchSystemState
from agents.planner import ResearchPlanner
from agents.scouting import ResearchScoutingAgent
from agents.validation import SourceValidationAgent
from agents.extraction import EvidenceExtractionAgent
from agents.qc import QualityControlAgent
from agents.correction import AutonomousCorrectionEngine
from exporters.excel_exporter import ExcelSpreadsheetExporter
from exporters.docx_exporter import WordDocumentExporter
from storage.database import ResearchDatabase
from config.settings import MAX_RECOVERY_ATTEMPTS


# Initialize shared agents
planner_agent = ResearchPlanner()
scouting_agent = ResearchScoutingAgent()
validation_agent = SourceValidationAgent()
extraction_agent = EvidenceExtractionAgent()
qc_agent = QualityControlAgent()
correction_engine = AutonomousCorrectionEngine()
excel_exporter = ExcelSpreadsheetExporter()
docx_exporter = WordDocumentExporter()
db = ResearchDatabase()


# -----------------------------------------------------------------------------
# Node Implementations
# -----------------------------------------------------------------------------

def node_plan(state: ResearchSystemState) -> Dict[str, Any]:
    """Stage 1: Intake and Planning Node."""
    return planner_agent.plan_research(state)


def node_scout(state: ResearchSystemState) -> Dict[str, Any]:
    """Stage 2: Literature Scouting Node."""
    return scouting_agent.scout(state)


def node_validate(state: ResearchSystemState) -> Dict[str, Any]:
    """Stage 3: Source Validation Node."""
    return validation_agent.validate_sources(state)


def node_extract(state: ResearchSystemState) -> Dict[str, Any]:
    """Stage 4 & 5: Insights and Verbatim Extraction & Verification Node."""
    return extraction_agent.extract_evidence(state)


def node_qc(state: ResearchSystemState) -> Dict[str, Any]:
    """Stage 6: Quality Control Audit Node."""
    return qc_agent.evaluate_project(state)


def _final_project_status(qc_status: str) -> str:
    """Show completion only after QC passes; preserve incomplete/review outcomes."""
    if qc_status == "PASSED":
        return "COMPLETED"
    if qc_status == "FAILED":
        return "FAILED"
    if qc_status == "INCOMPLETE":
        return "INCOMPLETE"
    return "COMPLETED_WITH_LIMITATIONS"


def route_after_qc(state: ResearchSystemState) -> Literal["node_recover", "node_export"]:
    """Conditional Edge: Route to autonomous recovery if gaps exist and retries remain."""
    if state.get("recovery_needed", False) and state.get("recovery_attempts", 0) < MAX_RECOVERY_ATTEMPTS:
        return "node_recover"
    return "node_export"


def node_recover(state: ResearchSystemState) -> Dict[str, Any]:
    """Stage 7: Autonomous Gap Recovery Node."""
    rec_info = correction_engine.prepare_recovery(state)
    if not rec_info.get("recovery_needed", False):
        return {"recovery_needed": False}

    # Execute targeted scouting for missing queries
    targeted_queries = rec_info.get("targeted_queries", [])
    recovery_state = dict(state)
    recovery_state["audit_trail"] = rec_info.get("audit_trail", state.get("audit_trail", []))
    scout_update = scouting_agent.scout(recovery_state, targeted_queries=targeted_queries)

    return {
        "candidate_sources": scout_update["candidate_sources"],
        "provider_diagnostics": state.get("provider_diagnostics", []) + scout_update.get("provider_diagnostics", []),
        "recovery_attempts": rec_info["recovery_attempts"],
        "recovery_needed": False,
        "status": f"Recovery attempt {rec_info['recovery_attempts']} completed",
        "audit_trail": scout_update.get("audit_trail", recovery_state["audit_trail"]),
    }


def node_export(state: ResearchSystemState) -> Dict[str, Any]:
    """Stage 8: Deliverables Generation Node (Excel & Word)."""
    project_id = state.get("project_id", "PROJ-DEFAULT")
    topic = state.get("topic", "")
    disease = state.get("disease", "Condition")
    countries = state.get("countries", ["India"])
    sections = state.get("sections", [])
    min_publication_year = state.get("min_publication_year")
    data_period_start_year = state.get("data_period_start_year", state.get("data_period_threshold"))
    data_period_end_year = state.get("data_period_end_year")
    validated = state.get("validated_sources", [])
    insights = state.get("insights", [])
    verbatims = state.get("verbatims", [])
    extraction_completeness = state.get("extraction_completeness", {})
    qc_report = state.get("qc_report", {})

    print(f"\n[Stage 8: Deliverables] Assembling final project artifacts for {project_id}...")

    # 1. Generate 14-Column Master Excel Spreadsheet
    excel_path = excel_exporter.export(
        project_id=project_id,
        topic=topic,
        validated_sources=validated,
        qc_report=qc_report,
        insights=insights,
        verbatims=verbatims,
        data_period_sources=state.get("candidate_sources", validated),
    )

    # 2. Generate Structured Word Monograph (.docx)
    docx_path = docx_exporter.export(
        project_id=project_id,
        topic=topic,
        disease=disease,
        countries=countries,
        sections=sections,
        validated_sources=validated,
        insights=insights,
        verbatims=verbatims,
        qc_report=qc_report,
        extraction_completeness=extraction_completeness,
        min_publication_year=min_publication_year,
        data_period_start_year=data_period_start_year,
        data_period_end_year=data_period_end_year,
        review_sources=state.get("review_sources", []),
    )

    final_status = _final_project_status(qc_report.get("overall_status", "INCOMPLETE"))
    db.update_project_status(project_id, final_status)
    db.log_audit_event(project_id, "DELIVERABLES", f"Generated deliverables. Status: {final_status}")

    audit_trail = state.get("audit_trail", [])
    audit_trail.append("Deliverables generated successfully")

    return {
        "excel_file_path": excel_path,
        "docx_file_path": docx_path,
        "status": final_status,
        "audit_trail": audit_trail,
    }


# -----------------------------------------------------------------------------
# Graph Assembly & Compilation
# -----------------------------------------------------------------------------

def build_research_graph():
    """Construct and compile the LangGraph workflow."""
    builder = StateGraph(ResearchSystemState)

    # Add Nodes
    builder.add_node("node_plan", node_plan)
    builder.add_node("node_scout", node_scout)
    builder.add_node("node_validate", node_validate)
    builder.add_node("node_extract", node_extract)
    builder.add_node("node_qc", node_qc)
    builder.add_node("node_recover", node_recover)
    builder.add_node("node_export", node_export)

    # Define Workflow Edges
    builder.add_edge(START, "node_plan")
    builder.add_edge("node_plan", "node_scout")
    builder.add_edge("node_scout", "node_validate")
    builder.add_edge("node_validate", "node_extract")
    builder.add_edge("node_extract", "node_qc")

    # Conditional Routing from QC
    builder.add_conditional_edges(
        "node_qc",
        route_after_qc,
        {
            "node_recover": "node_recover",
            "node_export": "node_export",
        }
    )

    # Recovery Loop Edge: re-validate new candidates after recovery scouting
    builder.add_edge("node_recover", "node_validate")

    # Final Edge
    builder.add_edge("node_export", END)

    return builder.compile()


# Singleton compiled graph instance
compiled_research_graph = build_research_graph()
