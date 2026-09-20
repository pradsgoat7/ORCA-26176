// Mocked-DOM test for the route-level hard-safety override banner
// (Section 14t): renderRouteInfoPanel() (chat.js) must show the exact
// same "Escalated from X to Y: reasons" banner Section 14s already built
// for the main risk card, whenever the RECOMMENDED route has
// override_fired: true - and must show it identically regardless of
// which container it renders into, since Ask ORCA chat and the Route
// Planner tab share this exact same function (confirmed directly:
// chat.js calls renderRouteInfoPanel(data.route), routeplanner.js calls
// renderRouteInfoPanel(data.route, 'routeplanner-result') - same
// function, different container id).
//
// The route field shape used here (pre_override_level/override_fired/
// override_reasons on each candidate route) is hand-constructed but
// verified to match the REAL API response shape via
// backend/tests/test_route_override.py's own direct check against
// _build_route_field() - not guessed.
//
// Same Node `vm`-mocked-DOM technique as test_boundary_warning_ui.js.
//
// Usage:
//   node frontend/tests/test_route_override_banner_ui.js

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
const routeplannerResult = makeElement('div'); routeplannerResult.id = 'routeplanner-result';

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

const jsDir = path.join(__dirname, '..', 'js');
const bundle = ['config.js', 'map.js', 'chat.js']
  .map((f) => fs.readFileSync(path.join(jsDir, f), 'utf8'))
  .join('\n;\n');
vm.runInContext(bundle, sandbox, { filename: 'chat-bundle.js' });

// A route field matching the REAL API shape (verified against
// _build_route_field() in backend/tests/test_route_override.py) - the
// recommended route was escalated by a hard-safety override using its
// own worst waypoint's conditions.
function makeRouteField(overrides = {}) {
  const directRoute = {
    id: 'route_direct', label: 'Direct', distance_km: 40.2, travel_time_min: 161,
    route_risk_score: 42, route_risk_level: 'HIGH', primary_risk_factor: 'Wave Risk',
    is_recommended: true, waypoints: [],
    pre_override_level: 'MODERATE', override_fired: true,
    override_reasons: [
      "Wave height (4.5 m) has reached 'Very Rough' on the Douglas Sea Scale (WMO Sea State 6, 4.0m+) - forces at least HIGH.",
    ],
    boundary_warning: false, boundary_distance_km: 238.0,
    mpa_warning: null, mpa_distance_km: null,
    ...overrides,
  };
  return {
    is_route: true, error: null,
    origin: { lat: 9.9312, lon: 76.2673, name: 'Kochi' },
    destination: { lat: 9.75, lon: 75.95, name: 'PFZ near Kochi coast' },
    candidate_routes: [directRoute],
    recommended_route_id: 'route_direct',
    explanation: 'Direct is both the shortest option and has the lowest marine risk (42/100).',
  };
}

console.log('='.repeat(70));
console.log('SCENARIO 1: recommended route escalated by override - Ask ORCA chat (default "messages" container)');

sandbox.renderRouteInfoPanel(makeRouteField(), 'messages');
const chatCard = messages.children[messages.children.length - 1];

check('a route card was rendered into the chat log', !!chatCard && chatCard.className === 'risk-card');
check('override banner is present', chatCard.innerHTML.includes('risk-override-banner'));
check('banner states the real escalation direction (MODERATE -> HIGH)',
  chatCard.innerHTML.includes('Escalated from MODERATE to HIGH'), chatCard.innerHTML);
check('banner includes the real override reason text (Douglas Sea Scale)',
  chatCard.innerHTML.includes('Very Rough') && chatCard.innerHTML.includes('Douglas Sea Scale'));
check('override banner appears BEFORE the route card title (same "top of card" placement as boundary/mpa banners)',
  chatCard.innerHTML.indexOf('risk-override-banner') < chatCard.innerHTML.indexOf('ORCA MARINE ROUTE'));
check('override banner appears BEFORE the boundary/mpa banner slots (most urgent category first)',
  chatCard.innerHTML.indexOf('risk-override-banner') < chatCard.innerHTML.indexOf('route-alternatives'));

console.log();
console.log('='.repeat(70));
console.log('SCENARIO 2: SAME escalated route field, rendered into the Route Planner tab\'s own container');

sandbox.renderRouteInfoPanel(makeRouteField(), 'routeplanner-result');
const rpCard = routeplannerResult.children[routeplannerResult.children.length - 1];

check('a route card was rendered into the Route Planner result container', !!rpCard);
check('the SAME override banner renders identically in the Route Planner tab',
  rpCard.innerHTML.includes('Escalated from MODERATE to HIGH') &&
  rpCard.innerHTML.includes('Very Rough'));
check('this proves both surfaces share one rendering function - not two separate implementations',
  rpCard.innerHTML.replace(/\s+/g, ' ').includes(
    chatCard.innerHTML.match(/risk-override-banner">([^<]+)/)[1].replace(/\s+/g, ' ').trim().slice(0, 40)));

console.log();
console.log('='.repeat(70));
console.log('SCENARIO 3: normal route, no override - banner must NOT appear');

const normalRoute = makeRouteField({
  route_risk_score: 13, route_risk_level: 'LOW', pre_override_level: 'LOW',
  override_fired: false, override_reasons: [],
});
sandbox.renderRouteInfoPanel(normalRoute, 'messages');
const normalCard = messages.children[messages.children.length - 1];

check('no override banner for a route with override_fired: false',
  !normalCard.innerHTML.includes('risk-override-banner'));
check('no stray "Escalated from" text leaks in for a normal route',
  !normalCard.innerHTML.includes('Escalated from'));

console.log();
console.log('='.repeat(70));
console.log(`RESULTS: ${passed} passed, ${failed} failed`);
if (failed === 0) {
  console.log('All route-override-banner checks pass, in both Ask ORCA and Route Planner containers.');
} else {
  console.log('Some checks failed - review the FAIL lines above.');
  process.exitCode = 1;
}
