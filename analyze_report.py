import json
import re
import sys
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")

print("=" * 70)
print("FAULT CODE ANALYSIS")
print("=" * 70)

# Battery faults - header at row 8
battery = pd.read_excel("Advanced Telematic Fault Report_20260519_084812.xlsx", header=8)
print("\n1. BATTERY FAULT CODES (from .Diagnostic.DiagnosticCode)")
print("-" * 70)

# Get unique codes
battery_codes = battery[".Diagnostic.DiagnosticCode"].dropna().unique()
print(f"Unique codes: {sorted([str(c) for c in battery_codes])}")

# Count target codes 131, 290, 135
for code in [131, 135, 290]:
    count = len(battery[battery[".Diagnostic.DiagnosticCode"] == code])
    print(f"  Code {code}: {count} occurrences")

# Total battery faults with codes 131, 290, 135
target_codes = [131, 135, 290]
battery_target = battery[battery[".Diagnostic.DiagnosticCode"].isin(target_codes)]
print(f"\nTotal battery faults (codes 131/135/290): {len(battery_target)}")

# Engine faults - header at row 8
engine = pd.read_excel("Advanced Engine Fault Report_20260519_084914.xlsx", header=8)
print("\n\n2. ENGINE FAULT CODES (DTC codes)")
print("-" * 70)

# Get unique DTC codes
engine_codes = engine[".Diagnostic.DiagnosticCode"].dropna().unique()
print(f"Total unique DTC codes: {len(engine_codes)}")
print(f"Sample codes: {sorted([str(c) for c in engine_codes])[:20]}")

# Count by code
engine_code_counts = engine[".Diagnostic.DiagnosticCode"].value_counts().head(20)
print("\nTop 20 engine fault codes:")
for code, count in engine_code_counts.items():
    print(f"  {code}: {count}")

# Check controller IDs
print("\n\n3. CONTROLLER IDS")
print("-" * 70)
print("Battery controllers:")
print(battery[".Controller.ControllerId"].value_counts())
print("\nEngine controllers:")
print(engine[".Controller.ControllerId"].value_counts())
