"""Export prospects to Excel with categorized sheets."""

from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from cold_emailer.state_store.models import Prospect, ProspectStatus
from cold_emailer.utils import get_logger

logger = get_logger(__name__)


def export_prospects_to_excel(
    prospects: list[Prospect],
    output_path: Path,
    preserve_existing: bool = True,
) -> None:
    """
    Export prospects to Excel file with NO RESPONSE and RESPONSE sheets.
    
    Args:
        prospects: List of Prospect objects to export
        output_path: Path to Excel file to create/update
        preserve_existing: If True, preserve existing sheets and add to them
    """
    # Separate prospects by status
    no_response_prospects: list[Prospect] = []
    response_prospects: list[Prospect] = []
    
    for prospect in prospects:
        if prospect.status == ProspectStatus.REPLIED.value:
            response_prospects.append(prospect)
        elif prospect.status == ProspectStatus.COMPLETED.value:
            no_response_prospects.append(prospect)
        # Ignore other statuses (NEW, SENT_INITIAL, etc.) - they're still in progress
    
    # Load existing workbook or create new
    if output_path.exists() and preserve_existing:
        workbook = load_workbook(output_path)
    else:
        workbook = Workbook()
        # Remove default sheet
        if "Sheet" in workbook.sheetnames:
            workbook.remove(workbook["Sheet"])
    
    # Define headers
    headers = [
        "prospect_id",
        "email",
        "full_name",
        "company",
        "resume_id",
        "role_title",
        "sequence_id",
        "status",
        "followup_step",
        "last_sent_at",
        "created_at",
    ]
    
    # Helper function to write prospects to a sheet
    def write_prospects_to_sheet(sheet_name: str, prospect_list: list[Prospect]) -> None:
        """Write prospects to a specific sheet."""
        # Get or create sheet
        if sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            # Clear existing data (keep headers if they exist)
            if sheet.max_row > 1:
                sheet.delete_rows(2, sheet.max_row)
        else:
            sheet = workbook.create_sheet(sheet_name)
            # Write headers
            header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF")
            for col_idx, header in enumerate(headers, start=1):
                cell = sheet.cell(row=1, column=col_idx, value=header)
                cell.fill = header_fill
                cell.font = header_font
        
        # Write prospect data
        for row_idx, prospect in enumerate(prospect_list, start=2):
            sheet.cell(row=row_idx, column=1, value=str(prospect.id))
            sheet.cell(row=row_idx, column=2, value=prospect.email)
            sheet.cell(row=row_idx, column=3, value=prospect.full_name)
            sheet.cell(row=row_idx, column=4, value=prospect.company)
            sheet.cell(row=row_idx, column=5, value=prospect.resume_id)
            sheet.cell(row=row_idx, column=6, value=prospect.role_title or "")
            sheet.cell(row=row_idx, column=7, value=prospect.sequence_id)
            sheet.cell(row=row_idx, column=8, value=prospect.status)
            sheet.cell(row=row_idx, column=9, value=prospect.followup_step)
            sheet.cell(row=row_idx, column=10, value=prospect.last_sent_at.strftime("%Y-%m-%d %H:%M:%S") if prospect.last_sent_at else "")
            sheet.cell(row=row_idx, column=11, value=prospect.created_at.strftime("%Y-%m-%d %H:%M:%S") if prospect.created_at else "")
        
        # Auto-adjust column widths
        for col_idx in range(1, len(headers) + 1):
            column_letter = sheet.cell(row=1, column=col_idx).column_letter
            max_length = 0
            for row in sheet.iter_rows(min_row=1, max_row=sheet.max_row, min_col=col_idx, max_col=col_idx):
                cell_value = str(row[0].value) if row[0].value else ""
                max_length = max(max_length, len(cell_value))
            sheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
    
    # Write to sheets
    write_prospects_to_sheet("NO RESPONSE", no_response_prospects)
    write_prospects_to_sheet("RESPONSE", response_prospects)
    
    # Remove exported prospects from the main "Prospects" sheet (or active sheet)
    # Find the main prospects sheet (could be named "Prospects", "Sheet1", or be the active sheet)
    main_sheet_names = ["Prospects", "Sheet1", "Sheet"]
    main_sheet = None
    for sheet_name in main_sheet_names:
        if sheet_name in workbook.sheetnames and sheet_name not in ["NO RESPONSE", "RESPONSE"]:
            main_sheet = workbook[sheet_name]
            break
    
    # If no standard sheet found, use the active sheet if it's not a response sheet
    if main_sheet is None:
        active_sheet = workbook.active
        if active_sheet.title not in ["NO RESPONSE", "RESPONSE"]:
            main_sheet = active_sheet
    
    if main_sheet:
        # Get emails of all exported prospects
        exported_emails = set()
        for prospect in no_response_prospects + response_prospects:
            exported_emails.add(prospect.email)
        
        # Find the email column by looking at headers
        email_col = None
        for col_idx in range(1, main_sheet.max_column + 1):
            header = main_sheet.cell(row=1, column=col_idx).value
            if header and str(header).lower() == "email":
                email_col = col_idx
                break
        
        if email_col is None:
            logger.warning("Could not find 'email' column in main sheet", sheet_name=main_sheet.title)
        else:
            # Find and remove rows with exported emails
            rows_to_delete = []
            # Start from row 2 (skip header)
            for row_idx in range(2, main_sheet.max_row + 1):
                email_cell = main_sheet.cell(row=row_idx, column=email_col)
                if email_cell.value and email_cell.value in exported_emails:
                    rows_to_delete.append(row_idx)
            
            # Delete rows in reverse order to avoid index shifting
            for row_idx in reversed(rows_to_delete):
                main_sheet.delete_rows(row_idx, 1)
            
            logger.info(
                "Removed exported prospects from main sheet",
                sheet_name=main_sheet.title,
                removed_count=len(rows_to_delete),
            )
    
    # Save workbook
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    
    logger.info(
        "Exported prospects to Excel",
        file=str(output_path),
        no_response_count=len(no_response_prospects),
        response_count=len(response_prospects),
    )
