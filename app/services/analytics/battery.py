"""Battery health analytics from MyGeotab StatusData diagnostics."""
from __future__ import annotations

import pandas as pd

# MyGeotab diagnostic IDs for battery-related StatusData
BATTERY_DIAG_IDS = [
    "DiagnosticBatteryStateOfChargeId",
    "DiagnosticBatteryChargingCableConnectedId",
    "DiagnosticBatteryStateOfHealthId",
    "DiagnosticBatteryTemperatureId",
]

BATTERY_DIAG_LABELS = {
    "DiagnosticBatteryStateOfChargeId": "State of Charge (%)",
    "DiagnosticBatteryChargingCableConnectedId": "Cable Connected",
    "DiagnosticBatteryStateOfHealthId": "State of Health (%)",
    "DiagnosticBatteryTemperatureId": "Temperature (°C)",
}

# Fault codes considered as battery health issues
BATTERY_FAULT_CODES = {131, 290, 135}


def compute_battery_health(
    status_data: list[dict],
    fault_data: list[dict],
    device_ids: set[str],
) -> pd.DataFrame:
    """
    Compute battery health summary per device.

    Returns DataFrame: device_id, avg_soc, avg_soh, avg_temp, cable_connected_pct, fault_count.
    Devices appear if they have either StatusData or qualifying fault events.
    """
    # Count battery faults per device (only codes 131, 290, 135)
    # Code is in diagnostic.code, not fault.code
    fault_counts: dict[str, int] = {}
    for fd in fault_data:
        dev = fd.get("device", {})
        dev_id = dev.get("id") if isinstance(dev, dict) else dev
        if dev_id not in device_ids:
            continue

        # Get code from diagnostic.code
        diagnostic = fd.get("diagnostic", {})
        code = None
        if isinstance(diagnostic, dict):
            code = diagnostic.get("code")
        # Fallback to fault.code
        if code is None:
            code = fd.get("code")

        if code is not None:
            try:
                code_int = int(code)
            except (ValueError, TypeError):
                continue
            if code_int in BATTERY_FAULT_CODES:
                fault_counts[dev_id] = fault_counts.get(dev_id, 0) + 1

    rows = []
    for sd in status_data:
        dev = sd.get("device", {})
        dev_id = dev.get("id") if isinstance(dev, dict) else dev
        if dev_id not in device_ids:
            continue

        diag = sd.get("diagnostic", {})
        diag_id = diag.get("id") if isinstance(diag, dict) else diag
        value = sd.get("data")

        rows.append({"device_id": dev_id, "diag_id": diag_id, "value": value})

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["device_id", "diag_id", "value"])

    # Union of devices: those with StatusData + those with qualifying faults
    status_device_ids = set(df["device_id"].unique()) if not df.empty else set()
    all_dev_ids = status_device_ids | set(fault_counts.keys())

    if not all_dev_ids:
        return pd.DataFrame(columns=["device_id", "avg_soc", "avg_soh", "avg_temp",
                                     "cable_connected_pct", "fault_count"])

    results = []
    for dev_id in all_dev_ids:
        if not df.empty and dev_id in status_device_ids:
            dev_df = df[df["device_id"] == dev_id]
            soc_vals = dev_df[dev_df["diag_id"] == "DiagnosticBatteryStateOfChargeId"]["value"].dropna()
            soh_vals = dev_df[dev_df["diag_id"] == "DiagnosticBatteryStateOfHealthId"]["value"].dropna()
            temp_vals = dev_df[dev_df["diag_id"] == "DiagnosticBatteryTemperatureId"]["value"].dropna()
            cable_vals = dev_df[dev_df["diag_id"] == "DiagnosticBatteryChargingCableConnectedId"]["value"].dropna()

            cable_pct = None
            if len(cable_vals) > 0:
                cable_pct = round(float((cable_vals > 0).mean()) * 100, 1)

            avg_soc = round(float(soc_vals.mean()), 1) if len(soc_vals) > 0 else None
            avg_soh = round(float(soh_vals.mean()), 1) if len(soh_vals) > 0 else None
            avg_temp = round(float(temp_vals.mean()), 1) if len(temp_vals) > 0 else None
        else:
            avg_soc = avg_soh = avg_temp = cable_pct = None

        results.append({
            "device_id": dev_id,
            "avg_soc": avg_soc,
            "avg_soh": avg_soh,
            "avg_temp": avg_temp,
            "cable_connected_pct": cable_pct,
            "fault_count": fault_counts.get(dev_id, 0),
        })

    return pd.DataFrame(results)
