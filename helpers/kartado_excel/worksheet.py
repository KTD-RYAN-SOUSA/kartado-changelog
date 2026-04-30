import logging

from openpyxl.comments.comment_sheet import CommentRecord
from openpyxl.worksheet._writer import WorksheetWriter

from helpers.kartado_excel.cell import write_cell

logger = logging.getLogger(__name__)


class KartadoWorksheetWriter(WorksheetWriter):
    def write_row(self, xf, row, row_idx):
        attrs = {"r": f"{row_idx}"}
        dims = self.ws.row_dimensions
        attrs.update(dims.get(row_idx, {}))

        with xf.element("row", attrs):
            for cell in row:
                if cell._comment is not None:
                    comment = CommentRecord.from_cell(cell)
                    self.ws._comments.append(comment)
                if cell._value is None and not cell.has_style and not cell._comment:
                    continue
                write_cell(xf, self.ws, cell, cell.has_style)


def copy_sheet_with_settings(workbook, source_sheet, new_sheet_name, index=None):
    """
    Copy worksheet with all settings including view, print and page setup

    Args:
        workbook: Workbook object
        source_sheet: Source worksheet to copy from
        new_sheet_name: Name for the new worksheet
        index: Position to insert the new worksheet
    """
    new_sheet = workbook.copy_worksheet(source_sheet)
    new_sheet.title = new_sheet_name

    # Copy sheet view settings
    if hasattr(source_sheet, "sheet_view"):
        """
        TODO: Valor de zoom não funciona no libre office e excel web
        """
        new_sheet.sheet_view.zoomScale = source_sheet.sheet_view.zoomScale
        new_sheet.sheet_view.zoomScaleNormal = source_sheet.sheet_view.zoomScaleNormal

        new_sheet.sheet_view.selection[
            0
        ].activeCell = source_sheet.sheet_view.selection[0].activeCell
        new_sheet.sheet_view.selection[0].sqref = source_sheet.sheet_view.selection[
            0
        ].sqref

    # Copy print settings
    new_sheet.print_area = source_sheet.print_area
    new_sheet.print_options = source_sheet.print_options
    new_sheet.page_setup = source_sheet.page_setup
    new_sheet.page_margins = source_sheet.page_margins

    # Copy column dimensions
    for col, dimension in source_sheet.column_dimensions.items():
        new_sheet.column_dimensions[col].width = dimension.width
        new_sheet.column_dimensions[col].hidden = dimension.hidden

    # Copy row dimensions
    for row, dimension in source_sheet.row_dimensions.items():
        new_sheet.row_dimensions[row].height = dimension.height
        new_sheet.row_dimensions[row].hidden = dimension.hidden

    # Reposition sheet if index provided
    if index is not None:
        workbook._sheets.remove(new_sheet)
        workbook._sheets.insert(index, new_sheet)

    return new_sheet
