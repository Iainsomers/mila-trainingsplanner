"""Read the trainer comment matrix exported as an Excel workbook."""

from __future__ import annotations

import posixpath
import re
import unicodedata
import zipfile
from xml.etree import ElementTree


MAX_WORKBOOK_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_ARCHIVE_FILES = 128

FOCUS_POINT_HEADERS = {
    "Endurance Z1-Z3": "endurance_z1_z3",
    "Endurance Z4-Z5": "endurance_z4_z5",
    "Speed": "speed",
    "Running technique at race distance": "race_technique",
    "Races and tactics": "races_tactics",
    "Recovery capacity": "recovery_capacity",
    "Injuries": "injuries",
    "Balance in daily life (study / training / work)": "life_balance",
    "Coaching in collaboration with trainer": "coach_collaboration",
}

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS = {"x": _MAIN_NS, "r": _REL_NS, "p": _PKG_REL_NS}


class FocusPointImportError(ValueError):
    """The uploaded workbook is invalid or does not match the import format."""


def _normalize_header(value: str) -> str:
    value = value.strip().casefold()
    for dash in ("–", "—", "‑", "−"):
        value = value.replace(dash, "-")
    return re.sub(r"\s+", " ", value)


def normalize_athlete_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip()


_HEADER_TO_KEY = {_normalize_header(header): key for header, key in FOCUS_POINT_HEADERS.items()}


def _column_number(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref or "")
    if not letters:
        raise FocusPointImportError("The workbook contains a cell with an invalid address.")
    value = 0
    for char in letters.group(1):
        value = value * 26 + ord(char) - ord("A") + 1
    return value


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(node.text or "" for node in item.findall(".//x:t", _NS))
        for item in root.findall("x:si", _NS)
    ]


def _first_sheet_path(archive: zipfile.ZipFile) -> str:
    try:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ElementTree.ParseError) as exc:
        raise FocusPointImportError("This is not a readable Excel workbook.") from exc

    first_sheet = workbook.find("x:sheets/x:sheet", _NS)
    if first_sheet is None:
        raise FocusPointImportError("The workbook has no worksheet.")
    relationship_id = first_sheet.get(f"{{{_REL_NS}}}id")
    relationship = next(
        (item for item in relationships.findall("p:Relationship", _NS)
         if item.get("Id") == relationship_id),
        None,
    )
    if relationship is None:
        raise FocusPointImportError("The workbook worksheet could not be located.")
    target = relationship.get("Target", "")
    path = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target))
    if not path.startswith("xl/worksheets/") or ".." in path.split("/"):
        raise FocusPointImportError("The workbook contains an invalid worksheet path.")
    return path


def _cell_value(cell: ElementTree.Element, strings: list[str]) -> str:
    if cell.find("x:f", _NS) is not None:
        raise FocusPointImportError("Formula cells are not supported. Paste the values into the workbook first.")
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", _NS))
    value = cell.find("x:v", _NS)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        try:
            return strings[int(value.text)]
        except (ValueError, IndexError) as exc:
            raise FocusPointImportError("The workbook contains an invalid shared-string reference.") from exc
    return value.text


def parse_focus_point_comments_workbook(uploaded_file) -> tuple[list[str], list[dict]]:
    """Return the required focus-point keys and rows of athlete/comment values."""
    if uploaded_file.size > MAX_WORKBOOK_BYTES:
        raise FocusPointImportError("The workbook is too large. The maximum file size is 2 MB.")
    if not uploaded_file.name.lower().endswith(".xlsx"):
        raise FocusPointImportError("Choose an .xlsx workbook.")

    uploaded_file.seek(0)
    try:
        with zipfile.ZipFile(uploaded_file) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_FILES or sum(item.file_size for item in entries) > MAX_ARCHIVE_BYTES:
                raise FocusPointImportError("The workbook expands to an unsupported size.")
            if archive.testzip() is not None:
                raise FocusPointImportError("The workbook is damaged. Save a new .xlsx copy and try again.")
            shared_strings = _shared_strings(archive)
            sheet_path = _first_sheet_path(archive)
            sheet_root = ElementTree.fromstring(archive.read(sheet_path))
    except FocusPointImportError:
        raise
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, OSError) as exc:
        raise FocusPointImportError("This is not a readable .xlsx workbook.") from exc

    sheet_rows = {}
    for row in sheet_root.findall(".//x:sheetData/x:row", _NS):
        row_number = int(row.get("r", "0"))
        cells = {}
        for cell in row.findall("x:c", _NS):
            cells[_column_number(cell.get("r", ""))] = _cell_value(cell, shared_strings)
        sheet_rows[row_number] = cells

    header_row = sheet_rows.get(1, {})
    header_columns = {}
    unknown_headers = []
    for column, raw_header in header_row.items():
        header = _normalize_header(raw_header)
        if column == 1 and header in {"", "athlete", "athlete name", "name"}:
            continue
        if not header:
            continue
        key = _HEADER_TO_KEY.get(header)
        if key is None:
            unknown_headers.append(raw_header)
        elif key in header_columns.values():
            raise FocusPointImportError(f"The focus point '{raw_header}' appears more than once in the header.")
        else:
            header_columns[column] = key

    missing = sorted(set(FOCUS_POINT_HEADERS.values()) - set(header_columns.values()))
    if missing or unknown_headers:
        parts = []
        if missing:
            parts.append("Missing focus point columns: " + ", ".join(
                next(label for label, key in FOCUS_POINT_HEADERS.items() if key == item)
                for item in missing
            ))
        if unknown_headers:
            parts.append("Unrecognized column headers: " + ", ".join(unknown_headers))
        raise FocusPointImportError(" ".join(parts))

    result = []
    for row_number in sorted(number for number in sheet_rows if number > 1):
        cells = sheet_rows[row_number]
        athlete_name = cells.get(1, "").strip()
        comments = {key: cells.get(column, "").strip() for column, key in header_columns.items()}
        if not athlete_name and not any(comments.values()):
            continue
        if not athlete_name:
            raise FocusPointImportError(f"Row {row_number} has comments but no athlete name in column A.")
        result.append({"athlete_name": athlete_name, "comments": comments, "row_number": row_number})

    if not result:
        raise FocusPointImportError("The workbook contains no athlete rows to import.")
    return sorted(set(header_columns.values())), result
