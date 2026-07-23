"""Server-side diagnostic CSV/ZIP export for report jobs.

The interactive report used to embed every diagnostic row as a JSON blob and
build the CSVs in the browser. That data now stays on the job server-side and is
offered as a single ZIP of CSVs from the tool's Done screen
(``GET /api/download/{job_id}/diagnostics.zip``), which keeps the shared HTML
report small.

Column order, headers, and cell formatting are copied verbatim from the old
client-side exporter (``app/templates/report_template.html`` -> ``downloadDiagCsv``)
so the CSVs are a drop-in replacement: each data row is byte-identical to what
the browser produced. ``build_diagnostic_data()`` in ``report_builder.py`` remains
the source of the row dicts consumed here.
"""
from __future__ import annotations

import csv
import io
import math
import zipfile
from typing import Any

# For each CSV kind: the column headers (row 1) paired with the ``diagnostic_data``
# row keys, in matching order. Copied verbatim from the former in-browser
# exporter so server output is identical. Dict order also fixes the order of
# entries inside the ZIP: vehicles, safety_events, battery_faults, engine_faults.
_CSV_SCHEMAS: dict[str, dict[str, list[str]]] = {
    "vehicles": {
        "headers": ["Device ID", "Device Name", "Group", "Trip Count",
                    "Active Days", "Distance (km)", "Drive Hours", "Idle Hours",
                    "Idle Cost", "Safety Score", "Safety Events", "Battery Faults"],
        "fields": ["device_id", "device_name", "group", "trip_count",
                   "active_days", "distance_km", "drive_hours", "idle_hours",
                   "idle_cost", "safety_score", "safety_events", "battery_faults"],
    },
    "safety_events": {
        "headers": ["Device ID", "Device Name", "Rule ID", "Rule Name",
                    "Date Time", "Duration"],
        "fields": ["device_id", "device_name", "rule_id", "rule_name",
                   "date_time", "duration"],
    },
    "battery_faults": {
        "headers": ["Device ID", "Device Name", "Diagnostic ID",
                    "Diagnostic Name", "Code", "Date Time"],
        "fields": ["device_id", "device_name", "diagnostic_id",
                   "diagnostic_name", "code", "date_time"],
    },
    "engine_faults": {
        "headers": ["Device ID", "Device Name", "Diagnostic ID",
                    "Diagnostic Name", "Code", "Controller ID", "Date Time"],
        "fields": ["device_id", "device_name", "diagnostic_id",
                   "diagnostic_name", "code", "controller_id", "date_time"],
    },
}


def _fmt(value: Any) -> str:
    """Render one cell exactly as the old browser exporter did.

    Mirrors JavaScript ``String(v)`` and ``csvEscape``'s null handling so output
    is byte-identical to the former client-side CSV: ``None`` -> ``''``;
    integer-valued floats print with no trailing ``.0`` (e.g. ``100.0`` ->
    ``'100'``, matching how the embedded JSON round-tripped through a JS Number);
    every other value uses its natural ``str()`` form — the same fallback the old
    path received from ``json.dumps(default=str)`` for exotic types.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


def yymmdd(iso: str) -> str:
    """'2026-01-31' -> '260131' (drop the century, strip dashes); '' -> ''."""
    return iso[2:].replace("-", "") if iso else ""


def report_basename(job) -> str:
    """Build the shared ``Fleet Insights_<DB>_<YYMMDD-YYMMDD>`` filename stem.

    Centralises the naming convention that both download routers and the SPA use,
    derived from the job's database (credentials) and analysis window (request).
    Each part degrades gracefully when a value is missing. ``job`` is a
    ``JobState``; it is left untyped here to avoid an import cycle with the store.
    """
    db = (job.credentials.get("database") or "report").upper()
    period = f"{yymmdd(job.request.get('start_date', ''))}-{yymmdd(job.request.get('end_date', ''))}"
    return f"Fleet Insights_{db}_{period}"


def render_csv(kind: str, diagnostic_data: dict | None) -> str:
    """Render one diagnostic CSV as text (UTF-8-ready, CRLF rows, RFC-4180 quoting).

    ``kind`` must be a key of ``_CSV_SCHEMAS``. The header row is always emitted;
    a missing or empty section yields a header-only CSV. Cells are pre-formatted
    with ``_fmt`` (for row parity with the old export) before being handed to the
    stdlib ``csv`` writer, whose ``QUOTE_MINIMAL`` quoting matches ``csvEscape``
    exactly (quote only when a field contains ``,``, ``"``, ``\\r`` or ``\\n``).
    """
    if kind not in _CSV_SCHEMAS:
        raise ValueError(f"Unknown diagnostic CSV kind: {kind!r}")
    schema = _CSV_SCHEMAS[kind]
    rows = (diagnostic_data or {}).get(kind) or []

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(schema["headers"])
    for row in rows:
        writer.writerow([_fmt(row.get(field)) for field in schema["fields"]])
    return buf.getvalue()


def build_diagnostics_zip(diagnostic_data: dict | None, basename: str) -> bytes:
    """Build a ``ZIP_DEFLATED`` archive of the four diagnostic CSVs.

    Entries are flat and named ``{basename}_<kind>.csv``. Every kind is always
    included (header-only when its section is empty) so the archive shape is
    stable regardless of the fleet's data.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for kind in _CSV_SCHEMAS:
            zf.writestr(
                f"{basename}_{kind}.csv",
                render_csv(kind, diagnostic_data).encode("utf-8"),
            )
    return buf.getvalue()
