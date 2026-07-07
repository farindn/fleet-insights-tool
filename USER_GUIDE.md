<!--
  Fleet Insights Tool — User Guide
  Screenshot placeholders are marked with 🖼️. Replace each with the actual
  image at the suggested path under docs/screenshots/.
-->

# Fleet Insights Tool

## User Guide

**Version 1.0.0 — July 2026**

---

## Table of Contents

- [1. Introduction](#1-introduction)
  - [Document Disclaimer](#document-disclaimer)
  - [Prerequisites](#prerequisites)
- [2. Revision History](#2-revision-history)
- [3. Installation & Setup](#3-installation--setup)
  - [Step 1 — Install Python](#step-1--install-python)
  - [Step 2 — Download the Project](#step-2--download-the-project)
  - [Step 3 — Configure the Tool](#step-3--configure-the-tool)
  - [Step 4 — Install Required Packages](#step-4--install-required-packages)
  - [Step 5 — Start the Tool](#step-5--start-the-tool)
  - [Step 6 — Open in Your Browser](#step-6--open-in-your-browser)
  - [Stopping the Tool](#stopping-the-tool)
  - [Updating to a New Version](#updating-to-a-new-version)
  - [Troubleshooting](#troubleshooting)
- [4. Logging In](#4-logging-in)
- [5. Configuring a Report](#5-configuring-a-report)
  - [Analysis Period](#analysis-period)
  - [Fleet Configuration](#fleet-configuration)
  - [Report Sections](#report-sections)
  - [Safety Scorecard Rules](#safety-scorecard-rules)
  - [Fuel & Idling Settings](#fuel--idling-settings)
- [6. Generating & Downloading the Report](#6-generating--downloading-the-report)
  - [Generation Progress](#generation-progress)
  - [Report Ready](#report-ready)
- [7. Understanding the Report](#7-understanding-the-report)
  - [Navigating the Report](#navigating-the-report)
  - [Cover](#cover)
  - [Group Overview](#group-overview)
  - [Geographic Coverage](#geographic-coverage)
  - [Utilization](#utilization)
  - [Idling](#idling)
  - [Safety & Risk](#safety--risk)
  - [Battery Health](#battery-health)
  - [Fault Codes](#fault-codes)
  - [At-Risk Vehicles](#at-risk-vehicles)
  - [Key Strategic Recommendations](#key-strategic-recommendations)
  - [Exporting Diagnostic CSVs](#exporting-diagnostic-csvs)
- [8. Understanding the Calculations](#8-understanding-the-calculations)
  - [Utilization Score](#utilization-score)
  - [Idling Cost](#idling-cost)
  - [Safety Score](#safety-score)
  - [At-Risk Matrix](#at-risk-matrix)
  - [Fault Codes & Battery Health](#fault-codes--battery-health)
  - [Default Fuel Prices & Idle Rates](#default-fuel-prices--idle-rates)
  - [AI-Generated Insights](#ai-generated-insights)
  - [Data Sources and Variance](#data-sources-and-variance)

> 🖼️ **Screenshots:** Lines that begin with 🖼️ are placeholders. Replace each with the actual screenshot; a suggested filename under `docs/screenshots/` is provided for each.

---

## 1. Introduction

Fleet Insights Tool is a reporting tool that connects to your MyGeotab database, analyses your fleet's activity over a period you choose, and produces a polished, shareable **HTML report** enriched with AI-generated insights. A single report covers fleet **utilization**, **idling cost**, **driver safety and risk**, **vehicle fault codes**, and **battery health**, and closes with **strategic recommendations**.

Unlike a MyGeotab add-in, Fleet Insights Tool runs as a small web application on your own computer. You start it locally, open it in your browser, log in with your MyGeotab credentials, configure the report, and download a self-contained HTML file that you can open or share with anyone.

The generated report is an interactive, slide-style deck that you navigate with on-screen arrows or your keyboard, and it can export per-vehicle diagnostic data to CSV for validation.

### Document Disclaimer

This document's content, including specifications, procedures, and screenshots, is subject to review and revision. We may make changes, updates, or modifications to product features, specifications, procedures, or the visual presentation without prior notice. Users should consult the current guide version for the most accurate information.

### Prerequisites

- **A Windows or Mac computer** with an internet connection.
- **Python 3.13 or newer** — used to run the tool locally (installation steps below).
- **A Geotab GenAI Gateway API key** — required for the AI-written insights and recommendations. Contact the tool administrator to obtain one. *(The report still generates without a key; AI sections fall back to standard descriptive text.)*
- **Your MyGeotab login details** — username, password, and server name (the part of your MyGeotab URL after `my.geotab.com/`, for example `my744`).
- **A MyGeotab account with read access** to the group you want to analyse. The account must be able to view devices, groups, trips, exception events, rules, status data, fault data, and diagnostics for that group.
- **Correct MyGeotab configuration** for full results:
  - **Powertrain & Fuel Type groups** — vehicles must be assigned to the correct Powertrain and Fuel Type groups so idling cost can be calculated. Vehicles without a valid powertrain assignment are excluded from cost calculations (the tool warns you when it detects them).
  - **Exception rules** — the Safety & Risk section is built from the MyGeotab exception rules you select; those rules must already exist in your database.
  - **Organisational sub-groups** — the "Group" columns and all "Affected Groups" tables map each vehicle to the first sub-group it belongs to beneath the company root. Vehicles that sit only in the company root are shown as `UNASSIGNED`.
- **An active internet connection when viewing the report** — the generated report loads maps and fonts online.

---

## 2. Revision History

| Date | Editor | Change |
|------|--------|--------|
| 2026-07-07 | Farin Nugraha | Document creation. |

---

## 3. Installation & Setup

Fleet Insights Tool runs on your own computer. You only need to complete this setup once; afterwards, starting the tool takes a few seconds.

### Step 1 — Install Python

> If you already have Python 3.13 or newer, skip this step.

**Windows**
1. Go to [python.org/downloads](https://www.python.org/downloads/).
2. Click the **Download Python** button.
3. Run the installer — on the very first screen, tick **"Add Python to PATH"** *before* clicking **Install**.

**Mac**
1. Go to [python.org/downloads](https://www.python.org/downloads/).
2. Download and run the `.pkg` installer, then follow the prompts.

**Verify it worked** — open Terminal (Mac) or Command Prompt (Windows) and run:

```
python --version
```

You should see something like `Python 3.13.x`.

### Step 2 — Download the Project

1. On the project's GitHub page, click the green **Code** button.
2. Select **Download ZIP**.
3. Extract the ZIP somewhere easy to find, such as your Desktop or Documents folder.

### Step 3 — Configure the Tool

The tool reads a few private values from a settings file called `.env`.

1. In the project folder, find the file named **`.env.example`**.
2. Make a copy of it and rename the copy to **`.env`** (remove the `.example` part).
   > **Windows tip:** if you can't see file extensions, open File Explorer → **View → Show → File name extensions** and turn it on.
3. Open your new `.env` file in **Notepad** (Windows) or **TextEdit** (Mac) and fill in the two values below.

**`SESSION_SECRET`** — a private security key that protects your session. Generate one by running this in your terminal:

```
python -c "import secrets; print(secrets.token_hex(16))"
```

Copy the output and paste it after `SESSION_SECRET=`.

**`GENAI_API_KEY`** — your Geotab GenAI Gateway API key (from the tool administrator). Paste it after `GENAI_API_KEY=`.

**Leave everything else as-is.** `GENAI_GATEWAY_URL` and `GENAI_MODEL` are already set to the correct defaults. A finished `.env` looks like this:

```
SESSION_SECRET=a3f8c2d1e4b7f09a2c5d8e1f4b7c0d3a
GENAI_API_KEY=your-key-here
GENAI_GATEWAY_URL=https://genai-us.geotab.com/api/v2
GENAI_MODEL=gemini-2.5-flash-lite
```

### Step 4 — Install Required Packages

Open a terminal in the project folder and run:

```
pip install -r requirements.txt
```

This downloads everything the tool needs. It may take a minute or two.

> **How to open a terminal in the project folder**
> - **Windows:** open the folder in File Explorer, click the address bar, type `cmd`, and press Enter.
> - **Mac:** right-click the folder in Finder and choose **New Terminal at Folder**.

### Step 5 — Start the Tool

In the same terminal, run:

```
python -m uvicorn app.main:app --reload
```

Some text will appear — that's normal. The tool is ready when you see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### Step 6 — Open in Your Browser

Open any modern browser (Chrome, Edge, or Safari) and go to:

**http://localhost:8000**

You should see the Fleet Insights Tool login screen.

### Stopping the Tool

When you're finished, return to the terminal window and press **Ctrl + C**.

### Updating to a New Version

To update, download the latest project ZIP (Step 2), extract it, and repeat Steps 4–6. Re-use your existing `.env` file so you don't have to re-enter your keys.

### Troubleshooting

| Problem | Fix |
|---------|-----|
| `python` is not recognised (Windows) | Re-run the Python installer and tick **"Add Python to PATH"**. |
| `No module named uvicorn` | Run `pip install -r requirements.txt` again. |
| The page doesn't load | Make sure the terminal is still running; also try `http://127.0.0.1:8000`. |
| "Authentication failed" | Double-check your MyGeotab username, password, and server name. |

---

## 4. Logging In

Open **http://localhost:8000** to reach the login screen.

> 🖼️ **[Screenshot: Login screen — Username, Database, and Password fields with the "Sign In" button]** — `docs/screenshots/01-login.png`

Enter:

- **Username** — your MyGeotab username (usually your email).
- **Database** — your MyGeotab database name.
- **Password** — your MyGeotab password.

Click **Sign In**. A modal shows "Signing In… Authenticating with MyGeotab" while the tool connects. On success, you're taken to the configuration screen; on failure, the modal shows the reason and a **Try Again** button.

**Notes**
- The tool connects to the standard `my.geotab.com` federation server and resolves your specific server automatically.
- Your **currency is auto-detected** from your MyGeotab user profile and pre-selected on the next screen (you can change it).
- Your session stays active for **4 hours**. Your login is remembered in the browser tab until you log out or close it. Use the **user menu** in the top-right of the navigation bar to **Log out** at any time.

---

## 5. Configuring a Report

After logging in you land on the **Generate New Report** screen. Configure the parameters below, then generate the report. The navigation bar shows your signed-in username and database.

> A banner reminds you: *"The generated report requires an active internet connection to display maps and fonts correctly."*

> 🖼️ **[Screenshot: Full configuration screen showing all five sections]** — `docs/screenshots/02-config-overview.png`

### Analysis Period

Define the reporting window at **month granularity**.

> 🖼️ **[Screenshot: Analysis Period section — Start Month/Year and End Month/Year selectors with the period hint]** — `docs/screenshots/03-analysis-period.png`

- **Start Month / Start Year** — the first month of the analysis. The analysis begins on the **first day** of this month.
- **End Month / End Year** — the last month of the analysis. The analysis ends on the **last day** of this month.

A hint below the selectors confirms the exact window, e.g. *"Analysis period: Jan 1, 2026 – Jun 30, 2026."*

**Defaults & rules**
- The period defaults to the **last 6 complete months**, ending with the **previous month** (the current, incomplete month is excluded).
- Year options range from the current year back three years.
- The end month must be on or after the start month.

> **Performance note:** longer periods and larger fleets require more data to be fetched from MyGeotab and take longer to generate. A typical report takes about **1–3 minutes**.

### Fleet Configuration

> 🖼️ **[Screenshot: Fleet Configuration section — Group, Report Language, and Currency dropdowns]** — `docs/screenshots/04-fleet-config.png`

- **Group** — the fleet group to analyse. Each option shows the group name and its vehicle count, e.g. *"Company Group (128 vehicles)."* **Subgroups are automatically included.** The tool defaults to your top-level **Company Group** (the whole fleet) when available.
- **Report Language** — the language for AI-generated insights. **English** is the standard option.
- **Currency** — the currency used throughout the report. It is **auto-detected from your MyGeotab profile** and can be changed. The currency is shown as a code (e.g. `MYR`, `IDR`, `USD`) beside monetary values.

### Report Sections

Choose which content to include. A table of contents is generated automatically inside the report, and every included section carries an AI-written insight.

> 🖼️ **[Screenshot: Report Sections selector with the grouped slide cards and "Select All / Clear All"]** — `docs/screenshots/05-report-sections.png`

Sections are organised into six groups. Use **Select All** or **Clear All**, and watch the *"X of 19 selected"* counter. All sections are selected by default; at least one must remain selected.

| Group | Included content |
|-------|------------------|
| **Overview** | Group Overview, Geographic Coverage |
| **Utilization** | Days Driven, Distance Travelled, Driving Duration, Utilization Trend, Utilization Distribution, Utilization by Vehicle |
| **Efficiency** | Idling Trend, Top Idling Vehicles |
| **Safety & Risk** | Safety Overview, Safety Events, Bottom-Scoring Vehicles |
| **Fleet Health** | Battery Health, Battery by Group, Fault Codes, At-Risk Vehicles, At-Risk by Group |
| **Summary** | Key Recommendations |

> **Note:** selection is by content family. Turning on any card in a family includes that family's full set of slides in the report. Some views (for example, **Max Speeding** within Safety & Risk) appear automatically when the relevant data is present.

### Safety Scorecard Rules

Define how the driver **safety score** is weighted. This section applies when the **Safety & Risk** group is included.

> 🖼️ **[Screenshot: Safety Scorecard Rules table with rule dropdowns, weights, and the "0% / 100%" weight bar]** — `docs/screenshots/06-safety-rules.png`

- Add up to **six** rules with **Add Rule**.
- For each row, pick a **Rule Name** from your MyGeotab exception rules; the **Rule ID** fills in automatically.
- Enter each rule's **Weight (%)**. The weight bar shows the running total.
- **The weights must total exactly 100%.** The **Generate** button stays disabled until they do (when Safety & Risk is included).

> **Tip:** common choices are harsh-driving rules such as Harsh Acceleration, Harsh Braking, and Harsh Cornering. If you include a **seatbelt** rule, the tool automatically scores it using a distance-driven-without-belt method (see [Safety Score](#safety-score)).

### Fuel & Idling Settings

Set the fuel prices and idle-consumption rates used to calculate idling cost. Powertrain types are **auto-detected** from each vehicle's group assignments in MyGeotab.

> 🖼️ **[Screenshot: Fuel & Idling Settings table — Fuel Type, Powertrain, Vehicles, Price/Unit, Idle Rate]** — `docs/screenshots/07-fuel-settings.png`

The table lists one row per fuel type found in the selected group:

| Column | Description | Editable |
|--------|-------------|----------|
| **Fuel Type** | The detected fuel/energy type (colour-coded badge) | No |
| **Powertrain** | The powertrain category (ICE, Electric, Plug-in, Fuel Cell) | No |
| **Vehicles** | Number of vehicles with this fuel type | No |
| **Price / Unit** | Cost per unit of fuel/energy (per L, kWh, or kg), prefixed with your selected currency | Yes |
| **Idle Rate** | Estimated fuel/energy consumed per hour of idling | Yes |

- **Fuel Type, Powertrain, and Vehicles are read-only.** To change a vehicle's fuel type, update its group membership in MyGeotab.
- **Price / Unit and Idle Rate are editable** — adjust them to match your region and vehicles. Defaults are provided per powertrain (see [Default Fuel Prices & Idle Rates](#default-fuel-prices--idle-rates)).
- **PHEV** rows show two inputs each — one for electricity (kWh) and one for liquid fuel (L).
- If any vehicles have **no valid powertrain assigned**, a warning banner tells you how many; those vehicles are **excluded from cost calculations** until corrected in MyGeotab.

> Fuel type is resolved from `GroupPowertrainAndFuelTypeId` in each vehicle's group hierarchy.

---

## 6. Generating & Downloading the Report

When every section is valid, the **Generate Report** button becomes active. Click it to start.

The button requires: a selected group, a valid analysis period, at least one report section, and — if Safety & Risk is included — safety rule weights totalling 100%.

### Generation Progress

A full-screen overlay shows live progress while the tool fetches and processes your data. Each step lights up as it runs and turns to a checkmark when done:

1. Authenticating
2. Loading fleet devices
3. Fetching trip data
4. Computing utilization
5. Calculating idle costs
6. Analysing safety events
7. Checking battery health
8. Processing fault codes
9. Building risk matrix
10. Generating AI insights
11. Rendering HTML report

> 🖼️ **[Screenshot: Generation overlay with the step list in progress]** — `docs/screenshots/08-generating.png`

Generation typically takes **1–3 minutes** depending on fleet size and period length. If the connection drops, the tool automatically checks whether the report finished.

### Report Ready

When generation completes, the **Report Ready** screen summarises the result and offers three actions.

> 🖼️ **[Screenshot: Report Ready screen with Group / Period / Slides summary and the action buttons]** — `docs/screenshots/09-report-ready.png`

- **Download HTML Report** — saves the report as a single self-contained file, named like `Fleet Insights_<DATABASE>_<YYMMDD-YYMMDD>.html`.
- **Open in Browser** — opens the report immediately in a new tab.
- **Generate Another Report** — returns to the configuration screen.

The report is a standalone HTML file: you can email it, store it, or open it on any computer with an internet connection.

---

## 7. Understanding the Report

The report opens on a cover slide and is navigated like a slide deck. Sections appear only if you selected them, and data-driven sections are shown only when there is data for them.

### Navigating the Report

> 🖼️ **[Screenshot: A report slide showing the title bar, navigation arrows, and an AI insight banner]** — `docs/screenshots/10-report-nav.png`

- Move between slides using the **on-screen arrows** or the **arrow keys** (Left/Right/Up/Down).
- The **title bar** shows *"Fleet Insights Tool | \<database\>"*.
- Most sections display a blue **insight banner** — a short, AI-written interpretation of that section's data — and a strip of up to four **stat cards** summarising the key numbers.
- A **Diagnostic CSV** menu in the top bar exports the underlying per-vehicle data (see [Exporting Diagnostic CSVs](#exporting-diagnostic-csvs)).

### Cover

The opening slide shows **"Fleet Data Insights — Powered by Geotab"**, your **database name**, and the **analysis period**.

### Group Overview

Vehicle distribution across your fleet's groups.

- **Table:** Group · Vehicles · Share of Fleet (with a bar showing the percentage). Rows are sorted from largest to smallest; any `UNASSIGNED` row is highlighted.
- **Stat cards:** Groups (number of groups), Total Vehicles.

> 🖼️ **[Screenshot: Group Overview slide]** — `docs/screenshots/11-group-overview.png`

### Geographic Coverage

A heat map of where your fleet operates, plotted from the end point of each trip.

- **Map:** brighter/warmer areas indicate more trip activity.
- **Stat cards:** GPS Stop-Points (points plotted), Analysis Period.

> 🖼️ **[Screenshot: Geographic Coverage heat map]** — `docs/screenshots/12-geographic-coverage.png`

### Utilization

Six views describe how intensively vehicles are used over the period. Each ranks or bands vehicles against the fleet's own **Q1 (25th percentile)** and **Q3 (75th percentile)** thresholds, labelling them **Under**, **Optimum**, or **Over**.

1. **Days Driven** — table of days in service per vehicle (Vehicle · Group · Days Driven · Status). Cards: Q1 Threshold, Q3 Threshold, Fleet Size.
2. **Distance Travelled** — total km per vehicle (Vehicle · Group · Distance (km) · Status). Cards: Q1 Threshold, Q3 Threshold, Fleet Size.
3. **Driving Duration** — engine-on driving hours per vehicle (Vehicle · Group · Drive Time (h) · Status). Cards: Q1 Threshold, Q3 Threshold, Fleet Size.
4. **Fleet Utilization Trend** — a line chart of the fleet's average monthly utilization score (0–100). Cards: Q1 Score, Q3 Score, Months.
5. **Utilization Distribution** — a donut splitting the fleet into Under-Utilized / Optimum / Over-Utilized. Cards: the count in each band.
6. **Utilization by Vehicle** — a combined table (Vehicle · Group · Days · Distance · Drive · Score · Status) ranking every vehicle by its composite utilization score.

> 🖼️ **[Screenshot: Utilization Distribution donut and one Utilization table]** — `docs/screenshots/13-utilization.png`

### Idling

How much time and money the fleet loses to idling. Idle cost is based on your Fuel & Idling Settings; vehicles without a valid powertrain are excluded from cost (but still counted in idle hours).

1. **Idling Duration** — a monthly chart with idle **hours** as bars and estimated idle **cost** as a line. Cards: Total Idle Hours, Est. Fuel Waste (in your currency), Burn Rate (per-hour idle rate, shown in the powertrain's unit — L/h, kWh/h, or kg/h).
2. **Top Idling Vehicles** — the 15 highest-idling vehicles, each showing idle hours and estimated cost. Cards: Fleet Total Idle, Est. Total Cost.

> 🖼️ **[Screenshot: Idling Duration chart and Top Idling Vehicles]** — `docs/screenshots/14-idling.png`

### Safety & Risk

Driver risk based on the exception rules and weights you configured. Vehicles are scored 0–100 (higher is safer) and banded:

| Band | Score |
|------|-------|
| High Risk | below 60 |
| Medium Risk | 60 to below 75 |
| Mild Risk | 75 to below 90 |
| Low Risk | 90 and above |

1. **Safety Overview** — a donut of the risk-band distribution. Cards: High / Medium / Mild / Low Risk counts.
2. **Safety Events** — a bar chart of total events per selected rule. Cards: Total Events, Rule Types.
3. **Max Speeding** — the 15 vehicles with the highest recorded speed (shown when speeding data exists); bars are red above 120 km/h, orange above 100 km/h. Cards: Max Speed, Avg Max Speed (Top 15), Over 120 km/h.
4. **Bottom-Scoring Vehicles** — the 15 lowest safety scores with reference lines at 60 / 75 / 90. Cards: Avg Score (Bottom 15), Need Coaching (High + Medium), Top Violation.

> 🖼️ **[Screenshot: Safety Overview donut and Bottom-Scoring Vehicles]** — `docs/screenshots/15-safety.png`

### Battery Health

Battery-related fault activity across the fleet.

1. **Battery Health** — per-vehicle table (Vehicle · Group · Events · Fault Names). A vehicle is flagged red when it has more than one event. Cards: Total Events, Vehicles Affected, Recurring (>1).
2. **Battery by Group** — per-group table (Group · Total Events · Vehicles Affected), flagged red above two events. Cards: Affected Groups, Total Events.

> 🖼️ **[Screenshot: Battery Health tables]** — `docs/screenshots/16-battery.png`

### Fault Codes

Diagnostic trouble codes (DTCs) reported by vehicle engines.

1. **Top Fault Codes** — a ranked bar chart of the most frequent standardised fault codes (shown as *"description (CODE)"*). Cards: Total Fault Events, Vehicles Affected.
2. **Fault Codes by Vehicle** — per-vehicle table (Vehicle · Group · Events · Fault Names). Cards: Total Events, Vehicles Affected, Recurring (>1).
3. **Fault Codes by Group** — per-group table (Group · Total Events · Vehicles Affected). Cards: Affected Groups, Total Events.

> 🖼️ **[Screenshot: Top Fault Codes chart and per-vehicle table]** — `docs/screenshots/17-fault-codes.png`

### At-Risk Vehicles

A composite view that flags vehicles triggering **multiple** risk signals at once (out of five — see [At-Risk Matrix](#at-risk-matrix)).

1. **At-Risk Vehicles** — a horizontal bar chart scoring each vehicle by its number of risk factors (out of 5), with markers at 60% and 80%. Cards: Critical (4–5 factors), High (3 factors), Medium (1–2 factors), Clean (0 factors).
2. **At-Risk by Group** — per-group table (Group · At-Risk Vehicles · Total Vehicles · Top Risk Flag). Cards: At-Risk Vehicles, Affected Groups.

> 🖼️ **[Screenshot: At-Risk Vehicles chart]** — `docs/screenshots/18-at-risk.png`

### Key Strategic Recommendations

A closing grid of AI-written, prioritised action items drawn from the whole report — each with a bold title and a short, data-referenced rationale. Cards: Insights (count), Period.

> 🖼️ **[Screenshot: Key Strategic Recommendations grid]** — `docs/screenshots/19-recommendations.png`

### Exporting Diagnostic CSVs

Use the **Diagnostic CSV** menu in the report's top bar to download the raw per-vehicle data behind the report — useful for validation or deeper analysis in a spreadsheet.

| Export | Contents |
|--------|----------|
| **Vehicle Summary** | Device ID, Device Name, Group, Trip Count, Active Days, Distance (km), Drive Hours, Idle Hours, Idle Cost, Safety Score, Safety Events, Battery Faults |
| **Safety Events** | Device ID, Device Name, Rule ID, Rule Name, Date Time, Duration |
| **Battery Faults** | Device ID, Device Name, Diagnostic ID, Diagnostic Name, Code, Date Time |
| **Engine Faults** | Device ID, Device Name, Diagnostic ID, Diagnostic Name, Code, Controller ID, Date Time |
| **Download All** | All four files at once |

> 🖼️ **[Screenshot: Diagnostic CSV export menu]** — `docs/screenshots/20-diagnostic-csv.png`

---

## 8. Understanding the Calculations

This section explains how the headline numbers are derived. All analytics are computed directly from your MyGeotab data for the selected group and period.

### Utilization Score

Each vehicle receives a composite utilization score from 0 to 100:

```
Active Days      = number of distinct calendar days the vehicle started a trip
Total Days       = (End Date − Start Date) + 1
Utilization %    = Active Days ÷ Total Days × 100

Composite Score  = 0.6 × normalised(Distance) + 0.4 × normalised(Utilization %)
```

`normalised(…)` places each vehicle on a 0–100 scale relative to the fleet, using an interquartile (IQR) method that caps extreme outliers so a few unusual vehicles don't distort the scale. Vehicles are then banded **Under / Optimum / Over** using the fleet's own **Q1 (25th percentile)** and **Q3 (75th percentile)** thresholds for each metric.

### Idling Cost

Idle cost is calculated per vehicle and summed across the fleet:

```
Idle Cost = Idle Hours × Idle Rate × Price per Unit
```

- **Idle Hours** come from each trip's idling duration.
- **Idle Rate** and **Price per Unit** come from your Fuel & Idling Settings (per-powertrain defaults that you can override).
- **PHEV (plug-in hybrid)** vehicles are dual-fuel: the tool adds the electricity component (idle hours × kWh/h rate × price per kWh) to the liquid-fuel component (idle hours × L/h rate × price per L).
- Vehicles **without a valid powertrain** are excluded from cost (they still contribute to idle hours).

In the monthly idling chart, each month's cost is that month's idle hours multiplied by the fleet's average cost per idle hour for the period.

**Worked example** — a diesel vehicle idles 40 hours in the period, at an idle rate of 3.0 L/h and a fuel price of 2.15 per litre:

```
Idle Cost = 40 h × 3.0 L/h × 2.15 = 258.00
```

### Safety Score

Each vehicle is scored 0–100 (higher is safer). For every selected rule:

```
Event Rate = Events ÷ Distance (km) × 1000
Rule Score = 100 − (Event Rate × Severity Multiplier × 10)      (clamped to 0–100)
```

- The **Severity Multiplier** increases with event volume — 1.0 for up to 5 events, rising in steps to 1.5 above 50 events — so repeated violations weigh more heavily.
- **Seatbelt** rules use a hybrid instead: `0.3 × event-based score + 0.7 × distance-driven-without-belt score`.
- The vehicle's overall score is the **weighted average** of its rule scores, using the weights you set (normalised to total 100%).

```
Safety Score = Σ (Rule Score × Weight) ÷ Σ (Weight)
```

Bands: **High Risk** < 60, **Medium** 60–75, **Mild** 75–90, **Low** ≥ 90.

### At-Risk Matrix

Every vehicle is checked against **five** independent risk factors. The number of factors it triggers (0–5) determines its risk level.

| Factor | Triggered when |
|--------|----------------|
| Low Utilization | composite utilization score is below 20 |
| Dormant | fewer than 5 active days in the period |
| High Idling | idle hours are in the fleet's top quartile |
| Low Safety | safety score is below 60 |
| High Idle Cost | idle cost is in the fleet's top quartile |

Vehicles are grouped as **Critical (4–5 factors)**, **High (3 factors)**, **Medium (1–2 factors)**, and **Clean (0 factors)**.

### Fault Codes & Battery Health

- **Fault Codes** — engine diagnostic trouble codes (DTCs) are standardised into the familiar `P` / `B` / `C` / `U` format (Powertrain, Body, Chassis, Network). The report ranks the most frequent codes fleet-wide and breaks them down by vehicle and group. "Recurring" means more than one event.
- **Battery Health** — counts battery-related fault events (diagnostic codes 131, 135, and 290). Vehicles are flagged when they show more than one event; groups are flagged above two events.

### Default Fuel Prices & Idle Rates

When a fuel type is detected, the tool pre-fills these defaults. **Prices are indicative baselines — adjust them to your region and currency.** Idle rates are industry estimates and are also editable.

| Fuel Type | Powertrain | Default Price | Default Idle Rate |
|-----------|------------|---------------|-------------------|
| BEV | Electric | 0.546 / kWh | 3.0 kWh/h |
| PHEV | Plug-in | 2.05 / L (+ 0.546 / kWh) | 0.3 L/h (+ 1.5 kWh/h) |
| FCEV | Fuel Cell | 15.0 / kg | 0.3 kg/h |
| Gasoline | ICE | 2.05 / L | 0.6 L/h |
| Diesel | ICE | 2.15 / L | 3.0 L/h |
| Biodiesel | ICE | 2.10 / L | 3.0 L/h |
| Ethanol | ICE | 1.90 / L | 0.7 L/h |
| CNG | ICE | 1.50 / kg | 1.8 kg/h |
| LPG | ICE | 1.80 / L | 2.0 L/h |

> The currency prefix shown next to each price is whatever you select in **Fuel Configuration → Currency**. Vehicles with no valid powertrain assignment are excluded from cost calculations.

### AI-Generated Insights

- Each report section includes a short, AI-written insight, and the report closes with a set of strategic recommendations.
- Insights are generated through the **Geotab GenAI Gateway** using a summary of your fleet's figures for the period. The model is instructed to be specific, cite numbers, and use your currency code (not symbols).
- Insights are **descriptive interpretations of your data**, intended to support — not replace — professional judgement.
- If the AI service is unavailable (or no API key is configured), the report **still generates**, with each section falling back to standard descriptive text.

### Data Sources and Variance

Fleet Insights Tool pulls data directly from the MyGeotab API — including trips, exception events, fault data, status data, devices, groups, rules, and diagnostics. You may notice small variances (typically **1–2%**) compared with MyGeotab's built-in reports. This is expected because:

1. **Active devices only** — the tool analyses currently active devices.
2. **Trip boundary handling** — trips are counted by their **start date** within the selected window.

These variances are proportional across all vehicles and do not materially affect the fleet-level insights.

---

*© 2026 Geotab Inc. All rights reserved. This guide describes Fleet Insights Tool v1.0.0.*
