/* Fleet Insights Tool — SPA state machine.
 *
 * Single-page frontend for the report generator. Four screens (login → config
 * → generating → done) are toggled by showScreen(); `state` holds the session
 * token + selections. Flow: authenticate (/api/auth) → load groups/rules/fuel
 * types → POST /api/generate → stream progress over SSE (/api/progress) →
 * download the HTML report (/api/download). See USER_GUIDE.md.
 */
'use strict';

// ── State ───────────────────────────────────────────────
const state = {
  token: sessionStorage.getItem('fig_token') || null,
  username: sessionStorage.getItem('fig_user') || null,
  database: sessionStorage.getItem('fig_db') || null,
  currency: sessionStorage.getItem('fig_currency') || 'USD',
  jobId: null,
  reportBlob: null,
  reportFilename: null,
  lastRequest: null,
  availableRules: [],
};

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

const SLIDE_DEFS = [
  // [key, icon, name, desc, group-container-id]
  ['portfolio',      'demography',        'Group Overview',         'Vehicle distribution across groups',                  'slides-overview'],
  ['heatmap',        'map_search',        'Geographic Coverage',    'Trip heatmap across operating zones',                 'slides-overview'],
  ['utilization',    'calendar_month',    'Days Driven',            'Days in service per vehicle, table',                  'slides-utilization'],
  ['utilization',    'route',             'Distance Travelled',     'Total km per vehicle over the period',                'slides-utilization'],
  ['utilization',    'schedule',          'Driving Duration',       'Engine-on hours per vehicle',                         'slides-utilization'],
  ['utilization',    'trending_up',       'Utilization Trend',      'Monthly composite utilization score',                 'slides-utilization'],
  ['utilization',    'pie_chart',         'Utilization Distribution','Under / Optimum / Over breakdown',                  'slides-utilization'],
  ['utilization',    'directions_car',    'Utilization by Vehicle', 'Composite score ranked per vehicle',                  'slides-utilization'],
  ['idling',         'timer_off',         'Idling Trend',           'Monthly idle hours and estimated fuel cost',          'slides-efficiency'],
  ['idling',         'local_fire_department','Top Idling Vehicles', '15 highest-idling vehicles ranked',                  'slides-efficiency'],
  ['safety',         'security',          'Safety Overview',        'Risk level distribution across the fleet',            'slides-safety'],
  ['safety',         'warning',           'Safety Events',          'Event type breakdown by rule',                        'slides-safety'],
  ['safety',         'person_alert',      'Bottom-Scoring Vehicles','15 vehicles with the lowest safety scores',           'slides-safety'],
  ['battery',        'battery_alert',     'Battery Health',   'Per-vehicle battery fault events',                     'slides-health'],
  ['battery',        'business',          'Battery by Group',       'Which groups are most affected',                      'slides-health'],
  ['faults',         'build',             'Fault Codes',            'Top diagnostic fault codes across the fleet',         'slides-health'],
  ['risk',           'report',            'At-Risk Vehicles',       'Vehicles flagged by multiple risk signals',           'slides-health'],
  ['risk',           'groups',            'At-Risk by Group',       'Group impact of at-risk vehicles',                    'slides-health'],
  ['recommendations','lightbulb',         'Key Recommendations',    'Data-driven strategic action items',                  'slides-summary'],
];

const PIPELINE_STEPS = [
  {key:'auth',        label:'Authenticating'},
  {key:'devices',     label:'Loading fleet devices'},
  {key:'trips',       label:'Fetching trip data'},
  {key:'utilization', label:'Computing utilization'},
  {key:'idling',      label:'Calculating idle costs'},
  {key:'safety',      label:'Analysing safety events'},
  {key:'battery',     label:'Checking battery health'},
  {key:'faults',      label:'Processing fault codes'},
  {key:'risk',        label:'Building risk matrix'},
  {key:'recommendations', label:'Compiling recommendations'},
  {key:'render',      label:'Rendering HTML report'},
];

// ── Utility ─────────────────────────────────────────────
// Show one screen (login | config | generating | done), hiding the others.
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById('screen-' + id).classList.add('active');
}

function authHeaders() {
  return { 'Authorization': 'Bearer ' + state.token, 'Content-Type': 'application/json' };
}

// UNUSED / dead code — retained for reference. Date handling now happens inline
// in buildDateSelectors() and the generate handler.
function getMonthYear(mSel, ySel) {
  const m = parseInt(mSel.value, 10); // 1-based
  const y = parseInt(ySel.value, 10);
  // first/last day of that month
  return { m, y };
}

const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

function calcPeriodLabel() {
  const sm = parseInt(document.getElementById('sel-start-month').value, 10);
  const sy = parseInt(document.getElementById('sel-start-year').value, 10);
  const em = parseInt(document.getElementById('sel-end-month').value, 10);
  const ey = parseInt(document.getElementById('sel-end-year').value, 10);
  const months = (ey - sy) * 12 + (em - sm) + 1;
  const lblEl = document.getElementById('period-label');
  if (months <= 0) {
    lblEl.textContent = 'End date must be on or after start date';
    return;
  }
  const lastDay = new Date(ey, em, 0).getDate();
  const startStr = MONTHS_SHORT[sm-1] + ' 1, ' + sy;
  const endStr = MONTHS_SHORT[em-1] + ' ' + lastDay + ', ' + ey;
  lblEl.textContent = 'Analysis period: ' + startStr + ' – ' + endStr;
}

function updateWeightBar() {
  // Only count table inputs, not mobile card inputs
  const inputs = document.querySelectorAll('#rules-tbody .rule-weight-input');
  let total = 0;
  inputs.forEach(i => { total += parseFloat(i.value) || 0; });
  total = Math.round(total * 10) / 10;
  const pct = Math.min(100, total);
  const fillEl = document.getElementById('wt-fill');
  const valEl = document.getElementById('wt-val');
  const msgEl = document.getElementById('wt-msg');

  fillEl.style.width = pct + '%';
  valEl.textContent = total.toFixed(1) + '% / 100%';

  // Reset classes
  fillEl.classList.remove('complete', 'over');
  valEl.classList.remove('complete', 'over');

  // Within ±0.5 of 100 counts as complete (rounding tolerance; mirrors the
  // backend validator in schemas/generate.py).
  if (Math.abs(total - 100) < 0.5) {
    fillEl.classList.add('complete');
    valEl.classList.add('complete');
    msgEl.textContent = '';
  } else if (total > 100) {
    fillEl.classList.add('over');
    valEl.classList.add('over');
    msgEl.textContent = 'Exceeds 100%';
  } else {
    msgEl.textContent = 'Must equal 100%';
  }
  updateGenerateButton();
}

function updateSlideCount() {
  const checked = document.querySelectorAll('.slide-checkbox:checked').length;
  document.getElementById('slide-count').textContent = checked + ' of ' + SLIDE_DEFS.length + ' selected';
  updateGenerateButton();
}

function isPeriodValid() {
  const sm = parseInt(document.getElementById('sel-start-month').value, 10);
  const sy = parseInt(document.getElementById('sel-start-year').value, 10);
  const em = parseInt(document.getElementById('sel-end-month').value, 10);
  const ey = parseInt(document.getElementById('sel-end-year').value, 10);
  if (isNaN(sm) || isNaN(sy) || isNaN(em) || isNaN(ey)) return false;
  const months = (ey - sy) * 12 + (em - sm) + 1;
  return months > 0;
}

// Enable "Generate Report" only when all preconditions hold (see USER_GUIDE.md
// → Generating & Downloading): a group is selected, the period is valid, at
// least one section is chosen, and — only if Safety & Risk is included — the
// rule weights total 100%.
function updateGenerateButton() {
  const weightOk = (() => {
    // If no Safety & Risk slide is selected the scorecard doesn't apply, so
    // weights are irrelevant and this check auto-passes.
    const safetySelected = document.querySelectorAll('.slide-checkbox[data-key="safety"]:checked').length > 0;
    if (!safetySelected) return true;
    const inputs = document.querySelectorAll('#rules-tbody .rule-weight-input');
    if (inputs.length === 0) return false;
    let total = 0;
    inputs.forEach(i => { total += parseFloat(i.value) || 0; });
    return Math.abs(total - 100) < 0.5;
  })();
  const slidesOk = document.querySelectorAll('.slide-checkbox:checked').length > 0;
  const groupOk = !!document.getElementById('sel-group').value;
  const periodOk = isPeriodValid();
  document.getElementById('btn-generate').disabled = !(weightOk && slidesOk && groupOk && periodOk);
}

// ── Slide checkboxes ─────────────────────────────────────
// Render the report-section selector cards from SLIDE_DEFS, grouped into the
// six containers (Overview/Utilization/Efficiency/Safety/Health/Summary),
// de-duplicating by card id. All start checked.
function buildSlideGrid() {
  // Clear all slide containers first to avoid duplication on re-entry
  ['slides-overview','slides-utilization','slides-efficiency','slides-safety','slides-health','slides-summary'].forEach(id => {
    const c = document.getElementById(id);
    if (c) c.innerHTML = '';
  });

  const groups = {};
  SLIDE_DEFS.forEach(([key, icon, name, desc, containerId]) => {
    if (!groups[containerId]) groups[containerId] = [];
    groups[containerId].push({ key, icon, name, desc });
  });

  // Track which keys already rendered (to deduplicate)
  const rendered = {};
  SLIDE_DEFS.forEach(([key, icon, name, desc, containerId]) => {
    const container = document.getElementById(containerId);
    if (!container) return;
    const cardId = 'sl-' + key + '-' + name.replace(/\s/g,'-');
    if (rendered[cardId]) return;
    rendered[cardId] = true;

    const label = document.createElement('label');
    label.className = 'sl-card on';
    label.innerHTML = `
      <input type="checkbox" class="slide-checkbox" data-key="${key}" checked>
      <span class="material-symbols-rounded sl-ico">${icon}</span>
      <div class="sl-info"><div class="sl-nm">${name}</div><div class="sl-ds">${desc}</div></div>
    `;
    label.querySelector('input').addEventListener('change', () => {
      label.classList.toggle('on', label.querySelector('input').checked);
      updateSlideCount();
    });
    container.appendChild(label);
  });
  updateSlideCount();
}

document.getElementById('btn-all').addEventListener('click', () => {
  document.querySelectorAll('.slide-checkbox').forEach(c => { c.checked = true; c.closest('.sl-card').classList.add('on'); });
  updateSlideCount();
});
document.getElementById('btn-none').addEventListener('click', () => {
  document.querySelectorAll('.slide-checkbox').forEach(c => { c.checked = false; c.closest('.sl-card').classList.remove('on'); });
  updateSlideCount();
});

// ── Rules table ──────────────────────────────────────────
async function loadAvailableRules() {
  try {
    const resp = await fetch('/api/rules/all', { headers: authHeaders() });
    if (resp.ok) {
      const data = await resp.json();
      state.availableRules = data.rules || [];
      rebuildRulesTable();
    }
  } catch (e) {
    console.error('Failed to load available rules:', e);
  }
}

function buildRuleOptions(selectedId = '') {
  let html = '<option value="">Select rule name</option>';
  state.availableRules.forEach(rule => {
    const selected = rule.id === selectedId ? ' selected' : '';
    html += `<option value="${rule.id}" data-name="${rule.name}"${selected}>${rule.name}</option>`;
  });
  return html;
}

function rebuildRulesTable() {
  document.getElementById('rules-tbody').innerHTML = '';
  document.getElementById('rules-cards').innerHTML = '';
  updateWeightBar();
  updateAddRuleButton();
}

// Add one safety-scorecard rule row (max 6), kept in sync between the desktop
// table and the mobile card layout. Weights must total 100% (see updateWeightBar).
function addRuleRow(ruleId = '', weight = '') {
  const tbody = document.getElementById('rules-tbody');
  const cardsContainer = document.getElementById('rules-cards');
  if (tbody.rows.length >= 6) return;

  const rowIndex = tbody.rows.length;

  // Desktop table row
  const tr = document.createElement('tr');
  tr.dataset.ruleId = ruleId;
  tr.dataset.rowIndex = rowIndex;
  tr.innerHTML = `
    <td data-label="Rule Name"><select class="ri rule-name-select">${buildRuleOptions(ruleId)}</select></td>
    <td data-label="Rule ID"><span class="rule-id-cell">${ruleId || '—'}</span></td>
    <td data-label="Weight (%)"><input class="ri ri-mono rule-weight-input" type="number" value="${weight}" min="0" max="100" step="1"></td>
    <td data-label=""><button class="btn-rm" title="Remove rule"><span class="material-symbols-rounded">remove_circle_outline</span></button></td>
  `;

  const nameSelect = tr.querySelector('.rule-name-select');
  const idCell = tr.querySelector('.rule-id-cell');
  const weightInput = tr.querySelector('.rule-weight-input');
  const rmBtn = tr.querySelector('.btn-rm');

  nameSelect.addEventListener('change', () => {
    const newRuleId = nameSelect.value;
    idCell.textContent = newRuleId || '—';
    tr.dataset.ruleId = newRuleId;
    const card = cardsContainer.querySelector(`[data-row-index="${rowIndex}"]`);
    if (card) {
      const cardSelect = card.querySelector('.rule-name-select');
      const cardIdCell = card.querySelector('.rule-id-cell');
      if (cardSelect) cardSelect.value = newRuleId;
      if (cardIdCell) cardIdCell.textContent = newRuleId || '—';
      card.dataset.ruleId = newRuleId;
    }
  });

  weightInput.addEventListener('input', () => {
    updateWeightBar();
    const card = cardsContainer.querySelector(`[data-row-index="${rowIndex}"]`);
    if (card) {
      const cardWeightInput = card.querySelector('.rule-weight-input');
      if (cardWeightInput) cardWeightInput.value = weightInput.value;
    }
  });

  rmBtn.addEventListener('click', () => {
    tr.remove();
    const card = cardsContainer.querySelector(`[data-row-index="${rowIndex}"]`);
    if (card) card.remove();
    updateWeightBar();
    updateAddRuleButton();
  });

  tbody.appendChild(tr);

  // Mobile card
  const card = document.createElement('div');
  card.className = 'rule-card';
  card.dataset.ruleId = ruleId;
  card.dataset.rowIndex = rowIndex;
  card.innerHTML = `
    <div class="rule-card-header">
      <select class="ri rule-name-select">${buildRuleOptions(ruleId)}</select>
      <button class="btn-rm" title="Remove rule"><span class="material-symbols-rounded">remove_circle_outline</span></button>
    </div>
    <div class="rule-card-row">
      <span class="rule-card-label">Rule ID</span>
      <span class="rule-card-value rule-id-cell">${ruleId || '—'}</span>
    </div>
    <div class="rule-card-row">
      <span class="rule-card-label">Weight (%)</span>
      <input class="ri ri-mono rule-weight-input" type="number" value="${weight}" min="0" max="100" step="1" style="width:80px;text-align:right">
    </div>
  `;

  const cardNameSelect = card.querySelector('.rule-name-select');
  const cardIdCell = card.querySelector('.rule-id-cell');
  const cardWeightInput = card.querySelector('.rule-weight-input');
  const cardRmBtn = card.querySelector('.btn-rm');

  cardNameSelect.addEventListener('change', () => {
    const newRuleId = cardNameSelect.value;
    cardIdCell.textContent = newRuleId || '—';
    card.dataset.ruleId = newRuleId;
    const tableRow = tbody.querySelector(`[data-row-index="${rowIndex}"]`);
    if (tableRow) {
      const tableSelect = tableRow.querySelector('.rule-name-select');
      const tableIdCell = tableRow.querySelector('.rule-id-cell');
      if (tableSelect) tableSelect.value = newRuleId;
      if (tableIdCell) tableIdCell.textContent = newRuleId || '—';
      tableRow.dataset.ruleId = newRuleId;
    }
  });

  cardWeightInput.addEventListener('input', () => {
    weightInput.value = cardWeightInput.value;
    updateWeightBar();
  });

  cardRmBtn.addEventListener('click', () => {
    card.remove();
    tr.remove();
    updateWeightBar();
    updateAddRuleButton();
  });

  cardsContainer.appendChild(card);
  updateWeightBar();
  updateAddRuleButton();
}

function updateAddRuleButton() {
  const tbody = document.getElementById('rules-tbody');
  const btn = document.getElementById('btn-add-rule');
  btn.disabled = tbody.rows.length >= 6;
}

document.getElementById('btn-add-rule').addEventListener('click', () => {
  addRuleRow();
});


// ── Date selectors ───────────────────────────────────────
function buildDateSelectors() {
  const now = new Date();
  const curYear = now.getFullYear();
  const curMonth = now.getMonth() + 1; // 1-based

  ['sel-start-month','sel-end-month'].forEach(id => {
    const sel = document.getElementById(id);
    MONTHS.forEach((m, i) => {
      const opt = document.createElement('option');
      opt.value = i + 1;
      opt.textContent = m;
      sel.appendChild(opt);
    });
  });

  ['sel-start-year','sel-end-year'].forEach(id => {
    const sel = document.getElementById(id);
    for (let y = curYear; y >= curYear - 3; y--) {
      const opt = document.createElement('option');
      opt.value = y;
      opt.textContent = y;
      sel.appendChild(opt);
    }
  });

  // Default: last 6 complete months ending on the previous month
  // (current month may be incomplete, so end = last month)
  const endDate = new Date(curYear, curMonth - 2, 1); // first day of previous month
  const startDate = new Date(endDate.getFullYear(), endDate.getMonth() - 5, 1); // 6 months back
  document.getElementById('sel-start-month').value = startDate.getMonth() + 1;
  document.getElementById('sel-start-year').value = startDate.getFullYear();
  document.getElementById('sel-end-month').value = endDate.getMonth() + 1;
  document.getElementById('sel-end-year').value = endDate.getFullYear();

  ['sel-start-month','sel-start-year','sel-end-month','sel-end-year'].forEach(id => {
    document.getElementById(id).addEventListener('change', () => {
      calcPeriodLabel();
      updateGenerateButton();
    });
  });
  calcPeriodLabel();
}

// ── Groups (Simple Select) ───────────────────────────────
let groupsData = [];

async function loadGroups() {
  const sel = document.getElementById('sel-group');
  sel.innerHTML = '<option value="">Loading groups…</option>';

  try {
    const resp = await fetch('/api/groups', { headers: authHeaders() });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    groupsData = data.groups || [];

    sel.innerHTML = '<option value="">Select a group</option>';
    groupsData.forEach(g => {
      const opt = document.createElement('option');
      opt.value = g.id;
      opt.textContent = g.name + ' (' + g.vehicle_count + ' vehicles)';
      opt.dataset.vehicleCount = g.vehicle_count;
      sel.appendChild(opt);
    });

    // Default to Company Group (GroupCompanyId) if available, else first group
    const companyGroup = groupsData.find(g => g.id === 'GroupCompanyId');
    if (companyGroup) {
      sel.value = companyGroup.id;
      updateGroupHint();
      loadFuelTypes();
    } else if (groupsData.length > 0) {
      sel.value = groupsData[0].id;
      updateGroupHint();
      loadFuelTypes();
    }
  } catch (e) {
    sel.innerHTML = '<option value="">Failed to load groups</option>';
    console.error(e);
  }
}

function updateGroupHint() {
  const sel = document.getElementById('sel-group');
  const selected = sel.selectedOptions[0];
  const hint = document.getElementById('group-hint-txt');
  if (selected && selected.value) {
    const count = selected.dataset.vehicleCount || '0';
    hint.textContent = count + ' vehicles detected';
  } else {
    hint.textContent = 'Select a group to analyse';
  }
  updateGenerateButton();
}

document.getElementById('sel-group').addEventListener('change', () => {
  updateGroupHint();
  loadFuelTypes();
});

// Fetch auto-detected fuel types for the selected group and render the fuel
// settings table; shows a banner for vehicles with no valid powertrain.
async function loadFuelTypes() {
  const groupId = document.getElementById('sel-group').value;
  const loadingEl = document.getElementById('fuel-loading');
  const loadingText = document.getElementById('fuel-loading-text');
  const tableEl = document.getElementById('fuel-table');
  const cardsEl = document.getElementById('fuel-cards');

  if (!groupId) {
    // Show idle state
    loadingEl.classList.add('idle');
    loadingEl.classList.remove('hidden');
    loadingText.textContent = 'Select a group to load fuel types…';
    tableEl.style.display = 'none';
    cardsEl.innerHTML = '';
    document.getElementById('fuel-unconfigured-banner').style.display = 'none';
    return;
  }

  // Show loading state
  loadingEl.classList.remove('idle', 'hidden');
  loadingText.textContent = 'Loading fuel types…';
  tableEl.style.display = 'none';

  try {
    const resp = await fetch('/api/fuel-types?group_id=' + encodeURIComponent(groupId), { headers: authHeaders() });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    buildFuelTable(data.fuel_types);
    loadingEl.classList.add('hidden');
    tableEl.style.display = '';

    // Show unconfigured vehicles banner if any
    const bannerEl = document.getElementById('fuel-unconfigured-banner');
    const bannerText = document.getElementById('fuel-unconfigured-text');
    if (data.unconfigured_count > 0) {
      const plural = data.unconfigured_count === 1 ? '' : 's';
      bannerText.textContent = data.unconfigured_count + ' vehicle' + plural + ' have no valid powertrain assigned and will be excluded from cost calculations.';
      bannerEl.style.display = '';
    } else {
      bannerEl.style.display = 'none';
    }
  } catch(e) {
    loadingEl.classList.add('idle');
    loadingText.textContent = 'Could not load fuel types. Please try again.';
    document.getElementById('fuel-unconfigured-banner').style.display = 'none';
    console.error(e);
  }
}

function getSelectedCurrency() {
  return document.getElementById('sel-currency').value;
}

// Render the fuel settings rows. Each powertrain gets editable price + idle
// inputs; PHEV gets dual (electricity + liquid) inputs. The currency prefix is
// applied live from the currency selector.
function buildFuelTable(fuelTypes) {
  const tbody = document.getElementById('fuel-tbody');
  const cardsContainer = document.getElementById('fuel-cards');
  const currency = getSelectedCurrency();
  tbody.innerHTML = '';
  cardsContainer.innerHTML = '';

  const BADGE_MAP = {
    'BEV': 'fb-bev', 'PHEV': 'fb-phev', 'FCEV': 'fb-fcev',
    'Gasoline': 'fb-gasoline', 'Petrol': 'fb-petrol',
    'Diesel': 'fb-diesel', 'Biodiesel': 'fb-biodiesel',
    'Ethanol': 'fb-ethanol', 'CNG': 'fb-cng', 'LPG': 'fb-lpg',
    'Unknown': 'fb-unknown',
  };

  fuelTypes.forEach(ft => {
    const badgeClass = BADGE_MAP[ft.label] || 'fb-other';
    // price_unit is "/L", "/kWh", "/kg" etc — strip leading slash for display
    const priceUnit = ft.price_unit.replace(/^\//, '') || 'unit';
    const isPHEV = ft.label === 'PHEV';

    // PHEV gets dual inputs (kWh + L for price, kWh/h + L/h for idle rate)
    const priceCell = isPHEV
      ? `<div style="display:flex;gap:.5rem;flex-wrap:wrap">
          <div class="if-sm">
            <input type="number" class="fuel-price-input fuel-price-elec" data-group-id="${ft.group_id}" value="0.546" step="0.01" min="0">
            <span class="unit"><span class="currency-unit">${currency}</span>/kWh</span>
          </div>
          <div class="if-sm">
            <input type="number" class="fuel-price-input fuel-price-liq" data-group-id="${ft.group_id}" value="${ft.default_price}" step="0.01" min="0">
            <span class="unit"><span class="currency-unit">${currency}</span>/L</span>
          </div>
        </div>`
      : `<div class="if-sm">
          <input type="number" class="fuel-price-input" data-group-id="${ft.group_id}" value="${ft.default_price}" step="0.01" min="0">
          <span class="unit"><span class="currency-unit">${currency}</span>/${priceUnit}</span>
        </div>`;

    const idleCell = isPHEV
      ? `<div style="display:flex;gap:.5rem;flex-wrap:wrap">
          <div class="if-sm">
            <input type="number" class="fuel-idle-input fuel-idle-elec" data-group-id="${ft.group_id}" value="1.5" step="0.1" min="0">
            <span class="unit">kWh/h</span>
          </div>
          <div class="if-sm">
            <input type="number" class="fuel-idle-input fuel-idle-liq" data-group-id="${ft.group_id}" value="${ft.default_idle_rate}" step="0.1" min="0">
            <span class="unit">L/h</span>
          </div>
        </div>`
      : `<div class="if-sm">
          <input type="number" class="fuel-idle-input" data-group-id="${ft.group_id}" value="${ft.default_idle_rate}" step="0.1" min="0">
          <span class="unit">${ft.idle_unit}</span>
        </div>`;

    // Desktop table row
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td data-label="Fuel Type"><span class="fbadge ${badgeClass}">${ft.label}</span></td>
      <td data-label="Powertrain"><strong style="font-size:.83rem">${ft.powertrain}</strong></td>
      <td data-label="Vehicles"><span style="font-family:'IBM Plex Mono',monospace;font-size:.83rem">${ft.vehicle_count}</span></td>
      <td data-label="Price / Unit">${priceCell}</td>
      <td data-label="Idle Rate">${idleCell}</td>
    `;
    tr.dataset.groupId = ft.group_id;
    tr.dataset.label = ft.label;
    tr.dataset.priceUnit = ft.price_unit;
    tr.dataset.idleUnit = ft.idle_unit;
    tbody.appendChild(tr);
  });
}

function updateCurrencyDisplay() {
  const currency = getSelectedCurrency();
  document.querySelectorAll('.currency-unit').forEach(el => {
    el.textContent = currency;
  });
}

document.getElementById('sel-currency').addEventListener('change', updateCurrencyDisplay);

// ── Login ────────────────────────────────────────────────
function showLoginModal(loading = true, error = null) {
  const modal = document.getElementById('login-modal');
  const spinner = document.getElementById('login-spinner');
  const icon = document.getElementById('login-modal-icon');
  const title = document.getElementById('login-modal-title');
  const sub = document.getElementById('login-modal-sub');
  const closeBtn = document.getElementById('login-modal-close');

  if (loading) {
    spinner.style.display = 'block';
    icon.style.display = 'none';
    title.textContent = 'Signing In';
    title.classList.remove('error');
    sub.textContent = 'Authenticating with MyGeotab...';
    closeBtn.style.display = 'none';
  } else if (error) {
    spinner.style.display = 'none';
    icon.style.display = 'block';
    title.textContent = 'Sign In Failed';
    title.classList.add('error');
    sub.textContent = error;
    closeBtn.style.display = 'block';
  }

  modal.classList.add('active');
}

function hideLoginModal() {
  document.getElementById('login-modal').classList.remove('active');
  // Reset to loading state for next use
  document.getElementById('login-spinner').style.display = 'block';
  document.getElementById('login-modal-icon').style.display = 'none';
  document.getElementById('login-modal-title').classList.remove('error');
  document.getElementById('login-modal-close').style.display = 'none';
}

document.getElementById('login-modal-close').addEventListener('click', () => {
  hideLoginModal();
  document.getElementById('btn-login').disabled = false;
});

document.getElementById('btn-login').addEventListener('click', async () => {
  const btn = document.getElementById('btn-login');
  btn.disabled = true;

  // Show login modal in loading state
  showLoginModal(true);

  const body = {
    username: document.getElementById('inp-username').value.trim(),
    password: document.getElementById('inp-password').value,
    database: document.getElementById('inp-database').value.trim(),
    server: 'my.geotab.com',
  };

  try {
    const resp = await fetch('/api/auth', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({detail: 'Authentication failed'}));
      throw new Error(err.detail || 'Authentication failed');
    }
    const data = await resp.json();
    state.token = data.token;
    state.username = data.username;
    state.database = data.database;
    state.currency = data.currency || 'USD';
    sessionStorage.setItem('fig_token', state.token);
    sessionStorage.setItem('fig_user', state.username);
    sessionStorage.setItem('fig_db', state.database);
    sessionStorage.setItem('fig_currency', state.currency);
    hideLoginModal();
    showNotify('success', 'Signed In', 'Welcome back, ' + state.username + '!', () => {
      initConfigScreen();
    });
  } catch (e) {
    // Show error in modal
    showLoginModal(false, e.message);
  }
});

// Allow Enter key on login form
document.getElementById('inp-password').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('btn-login').click();
});

// ── Config screen init ───────────────────────────────────
async function initConfigScreen() {
  document.getElementById('nav-email').textContent = state.username;
  document.getElementById('nav-dbid').textContent = state.database;

  // Set currency from user profile
  const currencySelect = document.getElementById('sel-currency');
  if (currencySelect) {
    // Check if the currency option exists
    const option = currencySelect.querySelector(`option[value="${state.currency}"]`);
    if (option) {
      currencySelect.value = state.currency;
    }
  }

  buildDateSelectors();
  buildSlideGrid();
  showScreen('config');

  // Load data in parallel
  await Promise.all([
    loadGroups(),
    loadAvailableRules(),
  ]);
}

// ── Logout dropdown & toast ──────────────────────────────
const navUser = document.getElementById('nav-user');
const logoutDropdown = document.getElementById('logout-dropdown');

navUser.addEventListener('click', (e) => {
  e.stopPropagation();
  logoutDropdown.classList.toggle('active');
});

document.addEventListener('click', () => {
  logoutDropdown.classList.remove('active');
});

logoutDropdown.addEventListener('click', (e) => {
  e.stopPropagation();
});

// ── Notification Modal ───────────────────────────────────
let notifActionCallback = null;

function showNotif(cfg) {
  document.getElementById('notif-icon-wrap').className = 'notif-icon-wrap ni-' + cfg.type;
  document.getElementById('notif-icon').textContent    = cfg.icon;
  document.getElementById('notif-title').textContent   = cfg.title;
  document.getElementById('notif-msg').innerHTML       = cfg.msg;

  const ab = document.getElementById('notif-action-btn');
  const db = document.getElementById('notif-dismiss-btn');

  if (cfg.actionLabel) {
    ab.textContent   = cfg.actionLabel;
    ab.style.display = '';
  } else {
    ab.style.display = 'none';
  }

  if (cfg.hideDismiss) {
    db.style.display = 'none';
  } else {
    db.style.display = '';
    db.textContent = cfg.dismissLabel || 'Close';
  }

  notifActionCallback = cfg.action || null;
  document.getElementById('notif-overlay').classList.add('active');
}

function closeNotif() {
  document.getElementById('notif-overlay').classList.remove('active');
  notifActionCallback = null;
}

function notifAction() {
  const cb = notifActionCallback;
  closeNotif();
  if (cb) cb();
}

function showNotify(type, title, message, callback = null) {
  const icons = { success: 'check_circle', error: 'error', warning: 'warning', info: 'info' };
  showNotif({
    type: type,
    icon: icons[type] || 'info',
    title: title,
    msg: message,
    actionLabel: callback ? 'Continue' : null,
    action: callback,
    hideDismiss: !!callback,
    dismissLabel: 'Close',
  });
}

document.getElementById('notif-action-btn').addEventListener('click', notifAction);
document.getElementById('notif-dismiss-btn').addEventListener('click', closeNotif);

document.getElementById('btn-logout').addEventListener('click', () => {
  sessionStorage.clear();
  state.token = null;
  logoutDropdown.classList.remove('active');
  showNotify('success', 'Logged Out', 'You have been successfully logged out.', () => {
    document.getElementById('btn-login').disabled = false;
    showScreen('login');
  });
});

// ── Generate ─────────────────────────────────────────────
document.getElementById('btn-generate').addEventListener('click', async () => {
  // Collect slide keys (unique)
  const slideKeys = [...new Set(
    [...document.querySelectorAll('.slide-checkbox:checked')].map(c => c.dataset.key)
  )];

  // Collect rules
  const rules = [];
  document.querySelectorAll('#rules-tbody tr').forEach(tr => {
    const id = tr.dataset.ruleId;
    const nameSelect = tr.querySelector('.rule-name-select');
    const name = nameSelect ? (nameSelect.selectedOptions[0]?.textContent || '') : '';
    const w = parseFloat(tr.querySelector('.rule-weight-input').value) || 0;
    if (id && id !== '—') rules.push({ rule_id: id, name: name, weight: w });
  });

  // Collect fuel settings
  const fuelSettings = [];
  document.querySelectorAll('#fuel-tbody tr').forEach(tr => {
    const priceInputs = tr.querySelectorAll('.fuel-price-input');
    const idleInputs = tr.querySelectorAll('.fuel-idle-input');
    if (priceInputs.length === 0) return;

    const isPHEV = tr.dataset.label === 'PHEV';
    if (isPHEV && priceInputs.length >= 2 && idleInputs.length >= 2) {
      // PHEV is dual-fuel: send both the electricity side (price_per_unit_elec /
      // idle_rate_elec) and the liquid side. The backend sums both into idle
      // cost (see schemas/generate.py, analytics/idling.py, USER_GUIDE.md).
      fuelSettings.push({
        group_id: tr.dataset.groupId,
        label: tr.dataset.label,
        price_per_unit: parseFloat(priceInputs[1].value) || 0,
        price_per_unit_elec: parseFloat(priceInputs[0].value) || 0,
        idle_rate: parseFloat(idleInputs[1].value) || 0,
        idle_rate_elec: parseFloat(idleInputs[0].value) || 0,
        price_unit: tr.dataset.priceUnit,
      });
    } else {
      fuelSettings.push({
        group_id: tr.dataset.groupId,
        label: tr.dataset.label,
        price_per_unit: parseFloat(priceInputs[0].value) || 0,
        idle_rate: parseFloat(idleInputs[0].value) || 0,
        price_unit: tr.dataset.priceUnit,
      });
    }
  });

  // Build dates: first day of start month, last day of end month
  const sm = parseInt(document.getElementById('sel-start-month').value, 10);
  const sy = parseInt(document.getElementById('sel-start-year').value, 10);
  const em = parseInt(document.getElementById('sel-end-month').value, 10);
  const ey = parseInt(document.getElementById('sel-end-year').value, 10);
  const startDate = new Date(sy, sm - 1, 1);
  const endDate = new Date(ey, em, 0); // day 0 of next month = last day of this month

  const pad = n => String(n).padStart(2, '0');
  const fmt = d => d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate());

  const groupSel = document.getElementById('sel-group');
  const groupId = groupSel.value;
  const groupName = groupSel.selectedOptions[0]?.textContent.replace(/\s*\(\d+\s*vehicles\)$/, '') || 'Fleet';

  const reqBody = {
    group_id: groupId,
    group_name: groupName,
    start_date: fmt(startDate),
    end_date: fmt(endDate),
    currency: document.getElementById('sel-currency').value,
    slides: slideKeys,
    safety_rules: rules,
    fuel_settings: fuelSettings,
  };
  state.lastRequest = reqBody;

  // Build pipeline steps UI
  const stepsEl = document.getElementById('gen-steps-list');
  stepsEl.innerHTML = '';
  PIPELINE_STEPS.forEach(step => {
    const el = document.createElement('div');
    el.className = 'gen-step gs-pending';
    el.id = 'step-' + step.key;
    el.innerHTML = `<span class="material-symbols-rounded">radio_button_unchecked</span><span>${step.label}</span>`;
    stepsEl.appendChild(el);
  });

  showScreen('generating');

  try {
    const resp = await fetch('/api/generate', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(reqBody),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({detail:'Failed to start generation'}));
      throw new Error(err.detail || 'Generation failed');
    }
    const data = await resp.json();
    state.jobId = data.job_id;
    watchProgress(data.job_id, reqBody);
  } catch (e) {
    showScreen('config');
    showNotify('error', 'Generation Failed', e.message);
  }
});

// ── SSE Progress ─────────────────────────────────────────
// Subscribe to the server's progress stream and drive the step checklist.
// `activeSteps`/`doneSteps` track which pipeline steps are running vs finished;
// a terminal {type:"done"} triggers the report fetch and {type:"error"} aborts.
// On SSE failure we fall back to polling the download endpoint (see onerror).
function watchProgress(jobId, req) {
  const es = new EventSource('/api/progress/' + jobId);
  const msgEl = document.getElementById('gen-current-msg');
  const activeSteps = new Set();
  const doneSteps = new Set();

  function setStep(key, status) {
    const el = document.getElementById('step-' + key);
    if (!el) return;
    el.className = 'gen-step gs-' + status;
    if (status === 'active') {
      el.innerHTML = `<span class="material-symbols-rounded">pending</span><span>${el.querySelector('span:last-child').textContent}</span>`;
    } else if (status === 'done') {
      el.innerHTML = `<span class="material-symbols-rounded">check_circle</span><span>${el.querySelector('span:last-child').textContent}</span>`;
    }
  }

  es.addEventListener('message', (e) => {
    let evt;
    try { evt = JSON.parse(e.data); } catch { return; }

    const step = evt.step;
    const msg = evt.message || '';

    if (evt.type === 'done') {
      es.close();
      PIPELINE_STEPS.forEach(s => { if (!doneSteps.has(s.key)) setStep(s.key, 'done'); });
      doneSteps.add('render');
      fetchReport(jobId, req);
      return;
    }

    if (evt.type === 'error') {
      es.close();
      showScreen('config');
      showNotify('error', 'Generation Failed', msg || 'An error occurred during report generation.');
      return;
    }

    if (step && !doneSteps.has(step)) {
      if (!activeSteps.has(step)) {
        activeSteps.add(step);
        setStep(step, 'active');
      }
    }

    if (evt.done && step) {
      doneSteps.add(step);
      activeSteps.delete(step);
      setStep(step, 'done');
    }

    msgEl.textContent = msg;
  });

  es.onerror = () => {
    es.close();
    // Check if done
    setTimeout(async () => {
      const r = await fetch('/api/download/' + jobId, { headers: authHeaders() }).catch(() => null);
      if (r && r.ok) {
        fetchReport(jobId, req);
      } else {
        showScreen('config');
        showNotify('error', 'Connection Lost', 'Connection to server lost during generation. Please try again.');
      }
    }, 1000);
  };
}

// Download the finished report blob, name it Fleet Insights_<DB>_<period>.html,
// and show the "Report Ready" screen.
async function fetchReport(jobId, req) {
  try {
    const resp = await fetch('/api/download/' + jobId, { headers: authHeaders() });
    if (!resp.ok) throw new Error('Report not available');
    const blob = await resp.blob();
    const dbName = (state.database || 'report').toUpperCase();
    const periodCode = (req.start_date.slice(2).replace(/-/g,'')) + '-' + (req.end_date.slice(2).replace(/-/g,''));
    const filename = 'Fleet Insights_' + dbName + '_' + periodCode + '.html';
    state.reportBlob = blob;
    state.reportFilename = filename;

    // Update done screen
    document.getElementById('done-group').textContent = req.group_name;
    document.getElementById('done-period').textContent = req.start_date + ' → ' + req.end_date;
    document.getElementById('done-slides').textContent = req.slides.length + ' sections';

    showScreen('done');
  } catch(e) {
    showScreen('config');
    showNotify('error', 'Download Failed', 'Report generation succeeded but download failed: ' + e.message);
  }
}

// ── Done screen actions ───────────────────────────────────
document.getElementById('btn-download').addEventListener('click', () => {
  if (!state.reportBlob) {
    showNotify('error', 'Download Failed', 'Report file is not available. Please generate a new report.');
    return;
  }
  try {
    const url = URL.createObjectURL(state.reportBlob);
    const a = document.createElement('a');
    a.href = url;
    a.download = state.reportFilename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    showNotify('success', 'Download Started', 'Your report is being downloaded as ' + state.reportFilename);
  } catch (e) {
    showNotify('error', 'Download Failed', 'Could not download the report: ' + e.message);
  }
});

document.getElementById('btn-open').addEventListener('click', () => {
  if (!state.reportBlob) {
    showNotify('error', 'Open Failed', 'Report file is not available. Please generate a new report.');
    return;
  }
  try {
    const url = URL.createObjectURL(state.reportBlob);
    window.open(url, '_blank');
    showNotify('success', 'Report Opened', 'Your report has been opened in a new browser tab.');
  } catch (e) {
    showNotify('error', 'Open Failed', 'Could not open the report: ' + e.message);
  }
});

document.getElementById('btn-new').addEventListener('click', () => {
  state.jobId = null;
  state.reportBlob = null;
  showScreen('config');
});

// ── Auto-restore session ─────────────────────────────────
if (state.token) {
  initConfigScreen();
}
