// Mocked-DOM test for the hard-safety override banner (Section 14s):
// renderRiskCard() (chat.js) must visibly explain WHY overall_level and
// overall_score can look inconsistent (e.g. "CRITICAL - 55/100") whenever
// risk.override_fired is true (PROJECT_CONTEXT.md Section 14n's override
// layer), using the same colored-callout-at-the-top-of-the-card pattern
// as the existing route boundary-warning banner (Section 14e).
//
// UPDATE (Section 14t): this file originally also confirmed that Route
// Planner result cards could NEVER receive override data, since
// route_planning_agent only called calculate_all_metrics() and never
// apply_safety_override(). Section 14t deliberately closed that exact
// gap - route scoring now runs the SAME hard-safety override using each
// route's own worst waypoint (see route_planning.py and
// backend/tests/test_route_override.py), and renderRouteInfoPanel() now
// shows this same banner too (see test_route_override_banner_ui.js for
// that dedicated coverage). Knowledge Base's policy_answer still carries
// no risk data at all, so knowledgebase.js remains correctly untouched.
//
// Same Node `vm`-mocked-DOM technique as test_tabs_ui.js/
// test_boundary_warning_ui.js.
//
// Usage:
//   node frontend/tests/test_risk_override_banner_ui.js

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

const allElements = [];
class FakeElement {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.id = '';
    this.className = '';
    this.children = [];
    this.style = {};
    this.innerHTML = '';
    this.textContent = '';
    allElements.push(this);
  }
  appendChild(child) { this.children.push(child); return child; }
  querySelectorAll() { return []; }
  querySelector() { return null; }
}
function makeElement(tag) { return new FakeElement(tag); }

const document_ = {
  getElementById: (id) => allElements.find((el) => el.id === id) || null,
  createElement: (tag) => makeElement(tag),
  createTextNode: (text) => ({ nodeType: 3, textContent: text }),
  querySelectorAll: () => [],
  querySelector: () => null,
};

const messages = makeElement('div'); messages.id = 'messages';
const mapDiv = makeElement('div'); mapDiv.id = 'map';

const L = {
  latLngBounds: (pts) => ({ _points: pts }),
  map: () => ({ setView() { return this; }, removeLayer() {}, fitBounds() {}, on() { return this; }, invalidateSize() {} }),
  tileLayer: () => ({ addTo() { return this; } }),
  control: () => { const c = {}; c.addTo = () => c; return c; },
  DomUtil: { create: (tag) => makeElement(tag) },
  circleMarker: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
  marker: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
  polyline: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
};

const sandbox = {
  console: { log: () => {}, warn: () => {}, error: () => {} },
  document: document_,
  L,
  fetch: () => Promise.reject(new Error('network disabled in this offline UI test')),
  requestAnimationFrame: (fn) => fn(),
};
sandbox.window = sandbox;
vm.createContext(sandbox);

// chat.js alone needs config.js (API_URL - unused here) and depends on
// STAKEHOLDER_DASHBOARD_TITLES/LEVEL_EMOJIS/scoreToColor which live in
// map.js - load the real production files in their real order.
const jsDir = path.join(__dirname, '..', 'js');
const bundle = ['config.js', 'map.js', 'chat.js']
  .map((f) => fs.readFileSync(path.join(jsDir, f), 'utf8'))
  .join('\n;\n');
vm.runInContext(bundle, sandbox, { filename: 'chat-bundle.js' });

console.log('='.repeat(70));
console.log('SCENARIO 1: Chennai-style cyclone override (real bug report scenario)');

const chennaiStakeholder = { type: 'fisherman' };
const chennaiRisk = {
  overall_score: 55,
  overall_level: 'CRITICAL',
  pre_override_level: 'HIGH',
  override_fired: true,
  override_reasons: [
    'Active cyclone alert (weather.cyclone_alert) forces CRITICAL, regardless of the weighted score.',
    'Lightning activity detected (weather.lightning_alert) - forces at least MODERATE.',
  ],
  metrics: [],
  recommendation: 'Do not go to sea. Conditions are extremely hazardous.',
};

sandbox.renderRiskCard(chennaiStakeholder, chennaiRisk);
const card1 = messages.children[messages.children.length - 1];

check('a risk card was rendered', !!card1 && card1.className === 'risk-card');
check('override banner is present in the card HTML', card1.innerHTML.includes('risk-override-banner'));
check('banner explicitly states the escalation direction (HIGH -> CRITICAL)',
  card1.innerHTML.includes('Escalated from HIGH to CRITICAL'), card1.innerHTML);
check('banner includes the real override_reasons text (cyclone alert)',
  card1.innerHTML.includes('Active cyclone alert'));
check('banner includes BOTH reasons when multiple fired (lightning too)',
  card1.innerHTML.includes('Lightning activity detected'));
check('banner never silently drops the reason list (join produced non-empty text)',
  !card1.innerHTML.includes('Escalated from HIGH to CRITICAL: <') &&
  !/Escalated from HIGH to CRITICAL:\s*<\/div>/.test(card1.innerHTML));
check('banner appears BEFORE the risk-card-title (same "top of card" placement as the boundary banner)',
  card1.innerHTML.indexOf('risk-override-banner') < card1.innerHTML.indexOf('risk-card-title'));
check('the overall badge still shows the real inconsistent-looking score (55/100) - not hidden or altered',
  card1.innerHTML.includes('55/100'));

console.log();
console.log('='.repeat(70));
console.log('SCENARIO 2: Normal query, no override (Kochi) - banner must NOT appear');

const kochiRisk = {
  overall_score: 21,
  overall_level: 'LOW',
  pre_override_level: 'LOW',
  override_fired: false,
  override_reasons: [],
  metrics: [],
  recommendation: 'Conditions are currently suitable for fishing.',
};
sandbox.renderRiskCard({ type: 'fisherman' }, kochiRisk);
const card2 = messages.children[messages.children.length - 1];

check('no override banner rendered for a normal non-escalated query',
  !card2.innerHTML.includes('risk-override-banner'));
check('no stray "Escalated from" text leaks in for a normal query',
  !card2.innerHTML.includes('Escalated from'));

console.log();
console.log('='.repeat(70));
console.log('UPDATED FINDING (Section 14t superseded the Section 14s note above):');
console.log('route scoring now DOES run the hard-safety override, using each');
console.log('route\'s own worst waypoint - see backend/tests/test_route_override.py');
console.log('and frontend/tests/test_route_override_banner_ui.js for full coverage.');
const routePlanningSrc = fs.readFileSync(
  path.join(__dirname, '..', '..', 'backend', 'app', 'graph', 'agents', 'route_planning.py'), 'utf8');
check('route_planning.py now imports AND calls apply_safety_override (Section 14t closed the gap Section 14s flagged)',
  routePlanningSrc.includes('apply_safety_override'));

console.log();
console.log('='.repeat(70));
console.log(`RESULTS: ${passed} passed, ${failed} failed`);
if (failed === 0) {
  console.log('All risk-override-banner checks pass.');
} else {
  console.log('Some checks failed - review the FAIL lines above.');
  process.exitCode = 1;
}
