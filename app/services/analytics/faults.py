"""Fault code analytics: DTC decoding and top fault summary."""
from __future__ import annotations

from collections import Counter

import pandas as pd

# MyGeotab OBD controller IDs (system names used in controller references)
# Includes both legacy IDs and WWH (World Wide Harmonized) variants
OBD_CONTROLLER_IDS = {
    "ControllerObdPowertrainId",
    "ControllerObdBodyId",
    "ControllerObdChassisId",
    "ControllerObdNetworkId",
    # WWH variants (World Wide Harmonized OBD)
    "ControllerObdWwhPowertrainId",
    "ControllerObdWwhBodyId",
    "ControllerObdWwhChassisId",
    "ControllerObdWwhNetworkingId",
}

# DTC code prefix characters (SAE J2012)
CONTROLLER_PREFIX = {
    "ControllerObdPowertrainId": "P",
    "ControllerObdBodyId": "B",
    "ControllerObdChassisId": "C",
    "ControllerObdNetworkId": "U",
    # WWH variants
    "ControllerObdWwhPowertrainId": "P",
    "ControllerObdWwhBodyId": "B",
    "ControllerObdWwhChassisId": "C",
    "ControllerObdWwhNetworkingId": "U",
}


def dtc_code(fault: dict) -> str | None:
    """
    Convert a FaultData record to a DTC string like 'P0300'.
    Returns None for non-OBD faults.

    The DTC code can be found in:
    - fault.diagnostic.code (raw integer fault value, rendered as a 4-digit hex
      DTC per SAE J2012 — e.g. 768 → "P0300" — or an already-formatted string)
    - fault.code (numeric fallback, needs the controller prefix)
    """
    controller = fault.get("controller", {})
    ctrl_id = controller.get("id") if isinstance(controller, dict) else controller

    if ctrl_id not in OBD_CONTROLLER_IDS:
        return None

    prefix = CONTROLLER_PREFIX.get(ctrl_id, "P")

    # First try diagnostic.code
    diagnostic = fault.get("diagnostic", {})
    if isinstance(diagnostic, dict):
        diag_code = diagnostic.get("code")
        if diag_code is not None:
            # Check if already formatted string like "P0400"
            if isinstance(diag_code, str) and len(diag_code) >= 4:
                return diag_code
            # Otherwise it's a raw integer fault value — format as a 4-digit hex
            # DTC and prepend the controller prefix (SAE J2012), e.g. 768 → "P0300".
            try:
                code_int = int(diag_code)
                return f"{prefix}{code_int:04X}"
            except (ValueError, TypeError):
                pass

    # Fallback to fault.code with controller prefix
    code_val = fault.get("code")
    if code_val is None:
        return None

    try:
        code_int = int(code_val)
    except (ValueError, TypeError):
        return None

    # Same 4-digit hex DTC formatting as the diagnostic.code branch above.
    return f"{prefix}{code_int:04X}"


def compute_fault_codes(
    fault_data: list[dict],
    device_ids: set[str],
    top_n: int = 20,
) -> pd.DataFrame:
    """
    Compute the top-N DTC fault codes across the fleet.

    Returns a DataFrame with columns: dtc_code, count, description (the raw
    diagnostic name when available).

    NOTE: device_fault_counts is tallied below but NOT returned here — the
    per-vehicle and per-group fault breakdowns shown in the report are built
    separately in report_builder.py (which counts all engine faults, decoded or
    not). "Recurring" (>1 event) banding is likewise applied there.
    """
    device_fault_counts: dict[str, int] = {}
    dtc_counter: Counter = Counter()
    dtc_diag_names: dict[str, str] = {}

    for fd in fault_data:
        dev = fd.get("device", {})
        dev_id = dev.get("id") if isinstance(dev, dict) else dev
        if dev_id not in device_ids:
            continue

        device_fault_counts[dev_id] = device_fault_counts.get(dev_id, 0) + 1

        code = dtc_code(fd)
        if code:
            dtc_counter[code] += 1
            if code not in dtc_diag_names:
                diag = fd.get("diagnostic", {})
                name = diag.get("name") if isinstance(diag, dict) else None
                if name:
                    dtc_diag_names[code] = name

    top = dtc_counter.most_common(top_n)
    if not top:
        return pd.DataFrame(columns=["dtc_code", "count", "description"])

    rows = [
        {
            "dtc_code": code,
            "count": cnt,
            "description": dtc_diag_names.get(code, ""),
        }
        for code, cnt in top
    ]
    return pd.DataFrame(rows)
