"""CSV parsing for dataset import.

Robustness per ISSUES #6: BOM, delimiter sniffing (, ; tab |),
empty rows skipped, duplicate/empty column names deduped.
Everything is stored as strings — typing is the consumer's problem.
"""
from __future__ import annotations

import csv
import io


class CsvError(ValueError):
    """User-facing import error (message shown on the upload page)."""


def _decode(data: bytes) -> str:
    """utf-8-sig strips the BOM if present; fall back to cp1252 for old exports."""
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        # Sniffer gives up on single-column files etc. — pick the most
        # frequent candidate in the first line, default comma.
        first = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {d: first.count(d) for d in (",", ";", "\t", "|")}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] > 0 else ","


def _dedupe_columns(header: list[str]) -> list[str]:
    """Strip, name empty columns, and suffix duplicates: kod, kod_2, kod_3…"""
    seen: dict[str, int] = {}
    columns = []
    for i, raw in enumerate(header):
        name = (raw or "").strip() or f"kolumn_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        seen.setdefault(name, 1)
        columns.append(name)
    return columns


def parse_csv(data: bytes) -> tuple[list[str], list[dict]]:
    """Parse CSV bytes → (columns, rows as dicts). Raises CsvError."""
    if not data or not data.strip():
        raise CsvError("Filen är tom.")
    text = _decode(data)
    delimiter = _sniff_delimiter(text[:4096])
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)

    header = None
    for candidate in reader:
        if any((c or "").strip() for c in candidate):
            header = candidate
            break
    if header is None:
        raise CsvError("Hittade ingen rubrikrad i filen.")
    columns = _dedupe_columns(header)

    rows: list[dict] = []
    for raw in reader:
        if not any((c or "").strip() for c in raw):
            continue  # skip fully empty rows
        # Pad short rows, ignore cells beyond the header width
        values = [ (raw[i].strip() if i < len(raw) else "") for i in range(len(columns)) ]
        rows.append(dict(zip(columns, values)))

    if not rows:
        raise CsvError("Filen innehåller en rubrikrad men inga datarader.")
    return columns, rows
