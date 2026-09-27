import csv
import io

from openpyxl import load_workbook

from insights_app.exports import render_csv, render_xlsx, safe_cell


def test_spreadsheet_formula_injection_is_neutralized() -> None:
    for value in ("=1+1", "+SUM(A1:A2)", "-2+3", "@cmd", "  =hidden"):
        assert str(safe_cell(value)).startswith("'")
    assert safe_cell("ordinary text") == "ordinary text"


def test_csv_and_xlsx_exports_are_valid() -> None:
    rows = [["CASE-1", "=1+1"]]
    csv_bytes = render_csv(["identifier", "display_label"], rows)
    parsed = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    assert parsed[1] == ["CASE-1", "'=1+1"]

    workbook = load_workbook(io.BytesIO(render_xlsx(["identifier", "display_label"], rows)))
    assert workbook.active["B2"].value == "'=1+1"
