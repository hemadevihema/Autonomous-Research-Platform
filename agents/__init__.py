"""Agents package initialization."""
from agents.planner import ResearchPlanner
from agents.scouting import ResearchScoutingAgent
from agents.validation import SourceValidationAgent
from agents.extraction import EvidenceExtractionAgent
from agents.qc import QualityControlAgent
from agents.correction import AutonomousCorrectionEngine

__all__ = [
    "ResearchPlanner",
    "ResearchScoutingAgent",
    "SourceValidationAgent",
    "EvidenceExtractionAgent",
    "QualityControlAgent",
    "AutonomousCorrectionEngine",
]
