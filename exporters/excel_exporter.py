"""
Stage 8: Organization Spreadsheet Exporter (Excel)
==================================================
Generates an executive-grade, beautifully formatted Excel spreadsheet (.xlsx)
strictly adhering to the organization's mandatory 14-column template order.
Includes an executive summary tab and QC verification audit trail.
"""
from pathlib import Path
from typing import List, Dict, Any
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from config.settings import SPREADSHEET_COLUMNS, OUTPUT_DIR

def _format_numbered_list(items):
    """Return a single string with each item numbered.
    Accepts a list or a newline-separated string. If the input is a string,
    it is split on newline characters. Empty items are ignored.
    """
    if isinstance(items, str):
        # Split by newlines and strip whitespace
        items = [i.strip() for i in items.split('\n') if i.strip()]
    if not isinstance(items, list):
        # Fallback to converting to list of strings
        items = [str(items)]
    formatted = []
    for idx, item in enumerate(items, start=1):
        formatted.append(f"{idx}) {item}")
    return "\n".join(formatted)


class ExcelSpreadsheetExporter:
    """Exporter producing the exact 14-column spreadsheet with professional styling."""

    def export(
        self,
        project_id: str,
        topic: str,
        validated_sources: List[Dict[str, Any]],
        qc_report: Dict[str, Any] = None,
        insights: List[Dict[str, Any]] = None,
        verbatims: List[Dict[str, Any]] = None,
        data_period_sources: List[Dict[str, Any]] = None,
    ) -> str:
        """Create and style the organization research spreadsheet."""
        wb = openpyxl.Workbook()
        
        # -------------------------------------------------------------
        # Sheet 1: Master Research Sources (Exact 14 Columns)
        # -------------------------------------------------------------
        ws = wb.active
        ws.title = "Research Sources"

        # Styling definitions
        navy_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        regular_font = Font(name="Calibri", size=10)
        zebra_fill = PatternFill(start_color="F7F9FC", end_color="F7F9FC", fill_type="solid")
        
        thin_border_side = Side(border_style="thin", color="D3D3D3")
        cell_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

        # Write Headers
        ws.append(SPREADSHEET_COLUMNS)
        ws.row_dimensions[1].height = 28

        for col_idx in range(1, len(SPREADSHEET_COLUMNS) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = navy_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = cell_border

        # Populate Rows
        for i, source in enumerate(validated_sources, start=1):
            # Ensure sections_covered is a list before joining
            sections = source.get("sections_covered", [])
            if not isinstance(sections, list):
                sections = []
            row_data = [
                i,  # S. No.
                source.get("source_title", "Untitled"),
                source.get("name_of_source", "Unknown Publisher"),
                source.get("source_type", "Research article"),
                source.get("publication_year", "Unknown"),
                source.get("data_period", "Unknown"),
                source.get("description", ""),
                source.get("access_type", "Open Access"),
                source.get("source_link", ""),
                "; ".join(sections),
                source.get("summary", ""),
                _format_numbered_list(source.get("insights", "")),
                _format_numbered_list(source.get("verbatim", "")),
                source.get("visual", "None found in retrieved text"),
            ]
            ws.append(row_data)
            # Determine the current row index (header is row 1)
            row_idx = ws.max_row
            # Dynamically scale row height to comfortably show multiple findings
            num_newlines = max(
                source.get("insights", "").count("\n"),
                source.get("verbatim", "").count("\n"),
                1,
            )
            ws.row_dimensions[row_idx].height = max(50, min(409, 22 * (num_newlines + 1)))

            is_even = (i % 2 == 0)
            for col_idx in range(1, len(row_data) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = regular_font
                cell.border = cell_border
                if is_even:
                    cell.fill = zebra_fill
                
                # Alignments
                if col_idx in [1, 5, 8]:  # S. No., Year, Access Type
                    cell.alignment = Alignment(horizontal="center", vertical="top")
                elif col_idx == 9:  # Source Link
                    cell.alignment = Alignment(horizontal="left", vertical="top")
                    cell.font = Font(name="Calibri", size=10, color="0000EE", underline="single")
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)

        # Optimal Column Widths
        col_widths = {
            1: 8,   # S. No.
            2: 32,  # Source Title
            3: 24,  # Name of Source
            4: 20,  # Source Type
            5: 14,  # Year of Publication
            6: 18,  # Period of data used
            7: 30,  # Description
            8: 16,  # Access Type
            9: 35,  # Source Link
            10: 25, # Sections Covered
            11: 42, # Summary
            12: 40, # Insights
            13: 40, # Verbatim
            14: 20, # Visual
        }
        for col_idx, width in col_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width

        # Keep the required 14-column master sheet intact, and expose every
        # extracted finding in a detail sheet so long multi-finding cells are
        # not visually clipped by Excel's row-height limit.
        if insights or verbatims:
            source_by_id = {source.get("id"): source for source in validated_sources if source.get("id")}
            findings_by_source: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
            for insight in insights or []:
                source_id = insight.get("source_id")
                if source_id:
                    findings_by_source.setdefault(source_id, {"insights": [], "verbatims": []})["insights"].append(insight)
            for verbatim in verbatims or []:
                source_id = verbatim.get("source_id")
                if source_id:
                    findings_by_source.setdefault(source_id, {"insights": [], "verbatims": []})["verbatims"].append(verbatim)

            ws_evidence = wb.create_sheet(title="Evidence Details")
            ws_evidence.freeze_panes = "A2"
            ws_evidence.append([
                "Source Title", "Publisher", "Publication Year", "Record Type", "Record ID",
                "Section", "Insight or Exact Verbatim", "Supporting Evidence Passage",
                "Verification Status", "Location", "Related Evidence IDs", "Source Link",
            ])
            for cell in ws_evidence[1]:
                cell.fill = navy_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = cell_border
            ws_evidence.row_dimensions[1].height = 32

            for source_id, findings in findings_by_source.items():
                source = source_by_id.get(source_id, {})
                records = [
                    ("Insight", item, item.get("insight_text", ""), item.get("evidence_passage", ""),
                     item.get("verification_status", "unresolved"), item.get("location_reference", ""),
                     item.get("supporting_verbatim_ids", []))
                    for item in findings["insights"]
                ] + [
                    ("Verbatim", item, item.get("exact_quote", ""), item.get("context", ""),
                     item.get("verification_status", "unverified"), item.get("location_reference", ""),
                     item.get("supports_insight_ids", []))
                    for item in findings["verbatims"]
                ]
                for record_type, item, content, evidence, verification, location, related_ids in records:
                    ws_evidence.append([
                        source.get("source_title", "Untitled"),
                        source.get("name_of_source", "Unknown Publisher"),
                        source.get("publication_year", "Unknown"),
                        record_type,
                        item.get("id", ""),
                        item.get("section", ""),
                        content,
                        evidence,
                        verification,
                        location,
                        ", ".join(related_ids),
                        source.get("source_link") or item.get("url", ""),
                    ])
                    row_idx = ws_evidence.max_row
                    ws_evidence.row_dimensions[row_idx].height = 110
                    for col_idx in range(1, 13):
                        cell = ws_evidence.cell(row=row_idx, column=col_idx)
                        cell.font = regular_font
                        cell.border = cell_border
                        cell.alignment = Alignment(vertical="top", wrap_text=True)
                    link_cell = ws_evidence.cell(row=row_idx, column=12)
                    if link_cell.value:
                        link_cell.hyperlink = str(link_cell.value)
                        link_cell.font = Font(name="Calibri", size=10, color="0000EE", underline="single")

            evidence_widths = {1: 40, 2: 26, 3: 15, 4: 14, 5: 20, 6: 32, 7: 60, 8: 70, 9: 24, 10: 26, 11: 32, 12: 45}
            for col_idx, width in evidence_widths.items():
                ws_evidence.column_dimensions[get_column_letter(col_idx)].width = width
            ws_evidence.auto_filter.ref = ws_evidence.dimensions

        period_sources = data_period_sources if data_period_sources is not None else validated_sources
        ws_period = wb.create_sheet(title="Data Period Audit")
        ws_period.freeze_panes = "A2"
        period_headers = [
            "Source ID", "Source Title", "Publisher", "Publication Year", "Data Period",
            "Start Year", "End Year", "Period Type", "Period Status", "Evidence Passage",
            "Evidence Location", "Source URL", "Country", "Validated Sections", "Validation Status",
        ]
        ws_period.append(period_headers)
        for cell in ws_period[1]:
            cell.fill = navy_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = cell_border
        seen_period_sources = set()
        for source in period_sources or []:
            source_id = source.get("id", "")
            if source_id and source_id in seen_period_sources:
                continue
            if source_id:
                seen_period_sources.add(source_id)
            ws_period.append([
                source_id,
                source.get("source_title", "Untitled"),
                source.get("name_of_source", "Unknown Publisher"),
                source.get("publication_year") or "Unknown",
                source.get("data_period") or "Unknown",
                source.get("data_period_start_year"),
                source.get("data_period_end_year"),
                source.get("data_period_type", "unknown"),
                source.get("data_period_status", "Unknown"),
                source.get("data_period_evidence", ""),
                source.get("data_period_location", ""),
                source.get("source_link", ""),
                source.get("country", ""),
                "; ".join(source.get("sections_covered", []) or []),
                source.get("validation_status", ""),
            ])
            row_idx = ws_period.max_row
            ws_period.row_dimensions[row_idx].height = 70
            for cell in ws_period[row_idx]:
                cell.font = regular_font
                cell.border = cell_border
                cell.alignment = Alignment(vertical="top", wrap_text=True)
            url_cell = ws_period.cell(row=row_idx, column=12)
            if url_cell.value:
                url_cell.hyperlink = str(url_cell.value)
                url_cell.font = Font(name="Calibri", size=10, color="0000EE", underline="single")
        for col_idx, width in enumerate((20, 42, 28, 16, 20, 14, 14, 20, 22, 80, 28, 50, 20, 42, 24), start=1):
            ws_period.column_dimensions[get_column_letter(col_idx)].width = width
        ws_period.auto_filter.ref = ws_period.dimensions

        # -------------------------------------------------------------
        # Sheet 2: QC Audit & Coverage Matrix
        # -------------------------------------------------------------
        if qc_report:
            ws_qc = wb.create_sheet(title="QC Audit & Coverage")
            ws_qc.views.sheetView[0].showGridLines = True
            
            ws_qc.append(["QUALITY CONTROL AUDIT & COVERAGE MATRIX"])
            ws_qc.merge_cells("A1:D1")
            ws_qc["A1"].font = Font(name="Calibri", size=14, bold=True, color="1B365D")
            ws_qc.row_dimensions[1].height = 24

            ws_qc.append([])
            ws_qc.append(["Metric", "Result"])
            ws_qc.append(["Overall Project Status", qc_report.get("overall_status", "UNKNOWN")])
            ws_qc.append(["QC Compliance Score", f"{qc_report.get('completion_score_percent', 0)}%"])
            ws_qc.append(["QC Checks Pass / Fail / Review / Total", f"{qc_report.get('qc_checks_passed', 0)} / {qc_report.get('qc_checks_failed', 0)} / {qc_report.get('qc_checks_review', 0)} / {qc_report.get('qc_checks_total', 0)}"])
            ws_qc.append(["QC Formula", "Passed applicable checks / all applicable source and quotation checks. Review checks remain in the denominator but are not hard rejection failures; coverage gaps are separate."])
            ws_qc.append(["Total Sources Evaluated", qc_report.get("total_sources_scouted", 0)])
            ws_qc.append(["Validated Sources Count", qc_report.get("passed_sources_count", 0)])
            ws_qc.append(["Sources Needing Review", qc_report.get("review_needed_count", 0)])
            ws_qc.append(["Rejected Sources Count", qc_report.get("rejected_sources_count", 0)])

            ws_qc.append([])
            ws_qc.append(["Country x Section Coverage Cell", "Validated Sources Count", "Status"])
            coverage_map = qc_report.get("coverage_matrix", {})
            for cell_key, count in coverage_map.items():
                status_text = "Satisfied" if count > 0 else "MISSING / GAP"
                ws_qc.append([cell_key, count, status_text])

            year_coverage = qc_report.get("year_wise_coverage", {})
            if year_coverage:
                ws_qc.append([])
                ws_qc.append(["Country x Section x Data Year", "Verified Sources", "Partial Sources", "Coverage Status", "Source IDs"])
                for cell_key, cell in year_coverage.items():
                    ws_qc.append([
                        cell_key,
                        cell.get("verified_sources_count", 0),
                        cell.get("partial_sources_count", 0),
                        cell.get("status", "No evidence"),
                        ", ".join(cell.get("source_ids", [])),
                    ])
                for row in ws_qc.iter_rows(min_row=ws_qc.max_row - len(year_coverage) + 1, max_row=ws_qc.max_row, min_col=1, max_col=5):
                    for cell in row:
                        cell.alignment = Alignment(vertical="top", wrap_text=True)

            issues = qc_report.get("issues", [])
            if issues:
                ws_qc.append([])
                ws_qc.append(["Severity", "Category", "Affected Record", "Issue", "Recommendation"])
                for issue in issues:
                    if hasattr(issue, "model_dump"):
                        issue = issue.model_dump()
                    ws_qc.append([
                        issue.get("severity", ""),
                        issue.get("category", ""),
                        issue.get("affected_record_id", ""),
                        issue.get("message", ""),
                        issue.get("recommendation", ""),
                    ])
                for row in ws_qc.iter_rows(min_row=ws_qc.max_row - len(issues) + 1, max_row=ws_qc.max_row, min_col=1, max_col=5):
                    for cell in row:
                        cell.alignment = Alignment(vertical="top", wrap_text=True)
                ws_qc.column_dimensions["D"].width = 65
                ws_qc.column_dimensions["E"].width = 65

            ws_qc.column_dimensions["A"].width = 45
            ws_qc.column_dimensions["B"].width = 25
            ws_qc.column_dimensions["C"].width = 20

        # Save workbook
        clean_name = f"Research_Spreadsheet_{project_id}.xlsx"
        target_path = OUTPUT_DIR / clean_name
        wb.save(str(target_path))
        print(f"\n[Stage 8: Excel Exporter] Master spreadsheet generated successfully:")
        print(f"  [FILE SAVED] {target_path}")
        return str(target_path)
