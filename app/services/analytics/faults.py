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
    - fault.diagnostic.code (integer like 71 or pre-formatted string like "P0071")
    - fault.code (numeric fallback, needs prefix from controller)
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
            # Otherwise it's an integer - format with prefix
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

    return f"{prefix}{code_int:04X}"


def compute_fault_codes(
    fault_data: list[dict],
    device_ids: set[str],
    top_n: int = 20,
) -> pd.DataFrame:
    """
    Compute top N DTC fault codes across the fleet.

    Returns DataFrame: dtc_code, count, description (raw diagnostic name if available).
    Also returns per-device fault count as a separate series.
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
