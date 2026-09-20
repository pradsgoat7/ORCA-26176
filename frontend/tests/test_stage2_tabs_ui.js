// Mocked-DOM test for the Stage 2 tab content (Section 14q): Risk Map,
// Route Planner, Knowledge Base. Same Node `vm`-based technique as
// test_tabs_ui.js/test_boundary_warning_ui.js - concatenates the real
// production script files as ONE unit, against a hand-rolled DOM mock.
//
// This test focuses on the STRUCTURAL/logic pieces that don't require a
// real network call or real Leaflet rendering (already verified in a real
// browser - see PROJECT_CONTEXT.md Section 14q): map relocation between
// tabs, the risk-map summary-strip math, the route-planner query-string
// construction (including the documented stakeholder-detection edge
// case), and the knowledge-base source-citation rendering (the genuinely
// NEW UI this task added).
//
// Usage:
//   node frontend/tests/test_stage2_tabs_ui.js

const fs = require('fs');
const path = require('path');
const vm = require('vm');

let passed = 0;
let failed = 0;
function check(label, condition, detail) {
  if (condition) {
    console.log(`  PASS: ${label}`);
    passed++;
  } else {
    console.log(`  FAIL: ${label}${detail ? ' - ' + detail : ''}`);
    failed++;
  }
}

// ---------- DOM mock (same shape as test_tabs_ui.js) ----------
const allElements = [];

function matchesSimpleSelector(el, selector) {
  const attrMatch = selector.match(/^(\.[\w-]+)\[data-(\w[\w-]*)="([^"]*)"\]$/);
  if (attrMatch) {
    const [, classSel, dataKey, dataVal] = attrMatch;
    return el.classList.contains(classSel.slice(1)) && el.dataset[toCamel(dataKey)] === dataVal;
  }
  if (selector.startsWith('.')) return el.classList.contains(selector.slice(1));
  if (selector.startsWith('#')) return el.id === selector.slice(1);
  return false;
}
function toCamel(s) { return s.replace(/-([a-z])/g, (_, c) => c.toUpperCase()); }

class FakeElement {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.id = '';
    this._classes = new Set();
    this.dataset = {};
    this.children = [];
    this.style = {};
    this.innerHTML = '';
    this.textContent = '';
    this.value = '';
    this._listeners = {};
    const self = this;
    this.classList = {
      add: (c) => self._classes.add(c),
      remove: (c) => self._classes.delete(c),
      contains: (c) => self._classes.has(c),
      toggle: (c) => (self._classes.has(c) ? self._classes.delete(c) : self._classes.add(c)),
    };
    Object.defineProperty(this, 'parentElement', { value: null, writable: true });
    allElements.push(this);
  }
  appendChild(child) { this.children.push(child); child.parentElement = this; return child; }
  addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); }
  dispatchClick() { (this._listeners.click || []).forEach((fn) => fn()); }
  querySelectorAll(selector) { return allElements.filter((el) => matchesSimpleSelector(el, selector)); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

function makeElement(tag) { return new FakeElement(tag); }

const document_ = {
  getElementById: (id) => allElements.find((el) => el.id === id) || null,
  createElement: (tag) => makeElement(tag),
  createTextNode: (text) => ({ nodeType: 3, textContent: text }),
  querySelectorAll: (selector) => allElements.filter((el) => matchesSimpleSelector(el, selector)),
  querySelector: (selector) => allElements.find((el) => matchesSimpleSelector(el, selector)) || null,
};

// ---------- Build the real production element tree ----------
const TAB_IDS = ['tab-home', 'tab-ask', 'tab-riskmap', 'tab-routeplanner', 'tab-knowledge', 'tab-about'];
const navButtons = {};
TAB_IDS.forEach((tabId) => {
  const btn = makeElement('button');
  btn.classList.add('tab-btn');
  btn.dataset.tab = tabId;
  navButtons[tabId] = btn;
});
const tabPanels = {};
TAB_IDS.forEach((tabId) => {
  const panel = makeElement('section');
  panel.id = tabId;
  panel.classList.add('tab-panel');
  tabPanels[tabId] = panel;
});

// #map starts as a child of #tab-ask, matching the real index.html.
const mapDiv = makeElement('div'); mapDiv.id = 'map';
tabPanels['tab-ask'].appendChild(mapDiv);

// Risk Map elements
const riskmapSlot = makeElement('div'); riskmapSlot.id = 'riskmap-map-slot';
const countLow = makeElement('span'); countLow.id = 'riskmap-count-low';
const countMod = makeElement('span'); countMod.id = 'riskmap-count-moderate';
const countHigh = makeElement('span'); countHigh.id = 'riskmap-count-high';
const countCrit = makeElement('span'); countCrit.id = 'riskmap-count-critical';

// Route Planner elements
const routeplannerSlot = makeElement('div'); routeplannerSlot.id = 'routeplanner-map-slot';
const rpFrom = makeElement('input'); rpFrom.id = 'rp-from';
const rpTo = makeElement('input'); rpTo.id = 'rp-to';
const rpStakeholder = makeElement('select'); rpStakeholder.id = 'rp-stakeholder'; rpStakeholder.value = 'fisherman';
const rpStatus = makeElement('div'); rpStatus.id = 'routeplanner-status';
const rpResult = makeElement('div'); rpResult.id = 'routeplanner-result';

// Knowledge Base elements
const kbInput = makeElement('input'); kbInput.id = 'kb-input';
const kbResult = makeElement('div'); kbResult.id = 'kb-result';

// ---------- Minimal Leaflet mock ----------
let invalidateSizeCallCount = 0;
const L = {
  latLngBounds: (pts) => ({ _points: pts }),
  map: () => ({
    setView() { return this; },
    removeLayer() {},
    fitBounds() {},
    on() { return this; },
    invalidateSize() { invalidateSizeCallCount++; },
  }),
  tileLayer: () => ({ addTo() { return this; } }),
  control: () => { const c = {}; c.addTo = () => c; return c; },
  DomUtil: { create: (tag) => makeElement(tag) },
  circleMarker: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
  marker: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
  polyline: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
};

const consoleErrors = [];
const capturingConsole = { log: () => {}, warn: () => {}, error: (...a) => consoleErrors.push(a.join(' ')) };

const sandbox = {
  console: capturingConsole,
  document: document_,
  L,
  fetch: () => Promise.reject(new Error('network disabled in this offline UI test')),
  requestAnimationFrame: (fn) => fn(),
  setTimeout,
  AbortController: class { constructor() { this.signal = {}; } abort() {} },
};
sandbox.window = sandbox;
vm.createContext(sandbox);

const jsDir = path.join(__dirname, '..', 'js');
const bundle = ['config.js', 'map.js', 'voice.js', 'chat.js', 'routeplanner.js', 'knowledgebase.js', 'tabs.js']
  .map((f) => fs.readFileSync(path.join(jsDir, f), 'utf8'))
  .join('\n;\n');

let loadError = null;
try {
  vm.runInContext(bundle, sandbox, { filename: 'frontend-bundle.js' });
} catch (e) {
  loadError = e;
}

console.log('='.repeat(70));
console.log('TEST: bundle (including routeplanner.js + knowledgebase.js) loads cleanly');
check('all 7 scripts loaded without throwing', loadError === null, loadError && loadError.stack);
check('no console.error calls during load', consoleErrors.length === 0, JSON.stringify(consoleErrors));
console.log();

// ---------- Risk Map: map relocation + summary strip ----------
console.log('='.repeat(70));
console.log('TEST: Risk Map - map relocates into riskmap-map-slot, summary strip updates');
invalidateSizeCallCount = 0;
sandbox.showTab('tab-riskmap');
check('map moved into riskmap-map-slot', mapDiv.parentElement === riskmapSlot);
check('invalidateSize was called on switching to Risk Map', invalidateSizeCallCount === 1, `count=${invalidateSizeCallCount}`);

const sampleZones = [
  { overall_level: 'LOW' }, { overall_level: 'LOW' }, { overall_level: 'LOW' },
  { overall_level: 'MODERATE' }, { overall_level: 'MODERATE' },
  { overall_level: 'HIGH' },
  { overall_level: 'CRITICAL' },
];
sandbox.updateRiskMapSummary(sampleZones);
check('LOW count computed correctly from zonesData', countLow.textContent === 3, `got ${countLow.textContent}`);
check('MODERATE count computed correctly', countMod.textContent === 2, `got ${countMod.textContent}`);
check('HIGH count computed correctly', countHigh.textContent === 1, `got ${countHigh.textContent}`);
check('CRITICAL count computed correctly', countCrit.textContent === 1, `got ${countCrit.textContent}`);
console.log();

// ---------- Route Planner: map relocation + query construction ----------
console.log('='.repeat(70));
console.log('TEST: Route Planner - map relocates, query construction, PFZ quick-fill');
invalidateSizeCallCount = 0;
sandbox.showTab('tab-routeplanner');
check('map moved into routeplanner-map-slot', mapDiv.parentElement === routeplannerSlot);
check('invalidateSize was called on switching to Route Planner', invalidateSizeCallCount === 1);

sandbox.setRoutePlannerDestinationToPFZ();
check("PFZ quick-fill sets 'the fishing zone' (a real PFZ_DESTINATION_KEYWORDS phrase)", rpTo.value === 'the fishing zone');

const fishermanQuery = sandbox.buildRoutePlannerQuery('Kochi', 'the fishing zone', 'fisherman');
check("fisherman query matches route_detection.py's 'from X to' pattern",
  /from\s+Kochi\s+to/i.test(fishermanQuery), fishermanQuery);
check("fisherman query contains 'route' (matches ROUTE_KEYWORDS)", /route/i.test(fishermanQuery));

const coastGuardQuery = sandbox.buildRoutePlannerQuery('Kochi', 'Chennai', 'coast_guard');
check("coast_guard query embeds real STAKEHOLDER_KEYWORDS ('coast guard', 'patrol', 'vessel', 'monitoring', 'rescue')",
  ['coast guard', 'patrol', 'vessel', 'monitoring', 'rescue'].every((kw) => coastGuardQuery.toLowerCase().includes(kw)),
  coastGuardQuery);

const disasterQuery = sandbox.buildRoutePlannerQuery('Kochi', 'Chennai', 'disaster_management');
check("disaster_management query embeds real STAKEHOLDER_KEYWORDS ('disaster', 'preparedness', 'emergency response', 'hazard level')",
  ['disaster', 'preparedness', 'emergency response', 'hazard level'].every((kw) => disasterQuery.toLowerCase().includes(kw)),
  disasterQuery);

const generalQuery = sandbox.buildRoutePlannerQuery('Kochi', 'Chennai', 'general');
check("general query adds no extra stakeholder hint (documented detection-content limitation, Section 14q)",
  generalQuery === 'Find the safest route from Kochi to Chennai', generalQuery);
console.log();

// ---------- Knowledge Base: source citation rendering (the NEW UI) ----------
console.log('='.repeat(70));
console.log('TEST: Knowledge Base - source citations (title + page) render correctly');

sandbox.renderKnowledgeBaseResult('Why is fishing banned before a cyclone?', {
  policy_answer: {
    is_policy_answer: true,
    answer: 'Fishing is suspended when wind speeds exceed 45 kmph or sea state becomes very rough.',
    mode: 'llm',
    sources: [
      { title: 'Cyclone Warning in India: Standard Operation Procedure', page: 212, source_url: 'https://mausam.imd.gov.in/imd_latest/contents/pdf/cyclone_sop.pdf' },
      { title: 'Cyclone Warning in India: Standard Operation Procedure', page: 225, source_url: 'https://mausam.imd.gov.in/imd_latest/contents/pdf/cyclone_sop.pdf' },
    ],
  },
});
check('answer text is rendered', kbResult.innerHTML.includes('Fishing is suspended when wind speeds'));
check('BOTH source titles are rendered', (kbResult.innerHTML.match(/Cyclone Warning in India/g) || []).length === 2);
check('BOTH page numbers are rendered', kbResult.innerHTML.includes('page 212') && kbResult.innerHTML.includes('page 225'));
check('source link uses the real backend-provided URL (not invented)', kbResult.innerHTML.includes('mausam.imd.gov.in'));
check("mode 'llm' shows no degraded-mode warning note", !kbResult.innerHTML.includes('kb-mode-note'));

sandbox.renderKnowledgeBaseResult('best practices while fishing', {
  policy_answer: { is_policy_answer: true, answer: 'Raw chunk text.', mode: 'fallback_raw_chunks', sources: [] },
});
check("mode 'fallback_raw_chunks' shows the degraded-mode warning note", kbResult.innerHTML.includes('kb-mode-note'));

sandbox.renderKnowledgeBaseResult('What is the weather in Kochi?', { policy_answer: null, risk: {} });
check('non-policy query shows an honest no-match message, not a fabricated answer', kbResult.innerHTML.includes('kb-no-match'));

sandbox.renderKnowledgeBaseResult('some query', { error: 'Could not identify a known location in the query.', policy_answer: null, answer: 'Sorry, could not identify a known location.' });
check('a genuine error response is shown honestly', kbResult.innerHTML.includes('kb-error'));
console.log();

console.log('='.repeat(70));
console.log(`RESULTS: ${passed} passed, ${failed} failed`);
if (failed === 0) {
  console.log('All Stage 2 tab checks pass.');
} else {
  console.log('Some checks failed - review the FAIL lines above.');
  process.exitCode = 1;
}
