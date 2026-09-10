// Mocked-DOM test for the maritime boundary warning UI (map.js renderRoute()
// + chat.js renderRouteInfoPanel()), following the same "concatenate the
// real script files and run them as ONE unit" approach already documented
// for this frontend in PROJECT_CONTEXT.md Section 7 (top-level let/const
// across separate <script> tags only stays shared in the same real
// execution the way a browser does it - so all 4 files are loaded together
// here via node's vm module, in the exact production script order:
// config.js, map.js, voice.js, chat.js).
//
// No real browser/jsdom dependency (none is installed in this repo) - a
// minimal hand-rolled Leaflet + DOM mock is enough, since renderRoute() and
// renderRouteInfoPanel() only ever call a small, fixed set of Leaflet/DOM
// methods (addTo, bindPopup, appendChild, innerHTML, etc).
//
// Route data is NOT hand-typed fake JSON - it's frozen output from the
// REAL backend pipeline (route_engine + risk_engine + maritime_boundary,
// including real live weather sampling at generation time), captured in
// route_fixtures.json by scripts/generate_route_fixtures.py equivalent
// (see PROJECT_CONTEXT.md Section 14e for how it was produced).
//
// Usage:
//   node frontend/tests/test_boundary_warning_ui.js

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

// ---------- Minimal Leaflet mock ----------
// Every layer created via L.polyline/circleMarker/marker records itself
// into `createdLayers` the moment .addTo() is called - mirroring how the
// real map accumulates visible layers - so the test can inspect exactly
// what was drawn without needing to reach into the sandbox's internal
// `routeLayers` variable.
const createdLayers = [];

function mockLayer(type, options) {
  const layer = { type, options, popupContent: null };
  layer.addTo = () => { createdLayers.push(layer); return layer; };
  layer.bindPopup = (html) => { layer.popupContent = html; return layer; };
  layer.on = () => layer;
  return layer;
}

const L = {
  latLngBounds: (pts) => ({ _points: pts }),
  map: () => ({ setView() { return this; }, removeLayer() {}, fitBounds() {}, on() { return this; } }),
  tileLayer: () => ({ addTo() { return this; } }),
  control: () => { const c = {}; c.addTo = () => c; return c; },
  DomUtil: { create: (tag) => makeElement(tag) },
  circleMarker: (latlng, opts) => mockLayer('circleMarker', { latlng, ...opts }),
  marker: (latlng, opts) => mockLayer('marker', { latlng, ...opts }),
  polyline: (latlngs, opts) => mockLayer('polyline', { latlngs, ...opts }),
};

// ---------- Minimal DOM mock ----------
function makeElement(tag) {
  return {
    tagName: tag,
    className: '',
    innerHTML: '',
    style: {},
    textContent: '',
    children: [],
    appendChild(child) { this.children.push(child); return child; },
    querySelectorAll: () => [],
    addEventListener() {},
  };
}

const messagesEl = makeElement('div');
const document_ = {
  getElementById: (id) => (id === 'messages' ? messagesEl : makeElement('div')),
  createElement: (tag) => makeElement(tag),
  createTextNode: (text) => ({ nodeType: 3, textContent: text }),
  querySelectorAll: () => [],
};

// ---------- Sandbox: load config.js, map.js, voice.js, chat.js as ONE unit,
// exactly the production <script> order documented in PROJECT_CONTEXT.md ----------
const sandbox = {
  console,
  document: document_,
  L,
  fetch: () => Promise.reject(new Error('network disabled in this offline UI test')),
};
sandbox.window = sandbox; // voice.js checks 'speechSynthesis' in window / window.SpeechRecognition at load time
vm.createContext(sandbox);

const jsDir = path.join(__dirname, '..', 'js');
const bundle = ['config.js', 'map.js', 'voice.js', 'chat.js']
  .map((f) => fs.readFileSync(path.join(jsDir, f), 'utf8'))
  .join('\n;\n');
vm.runInContext(bundle, sandbox, { filename: 'frontend-bundle.js' });

// ---------- Real backend-generated fixtures ----------
const fixtures = JSON.parse(fs.readFileSync(path.join(__dirname, 'route_fixtures.json'), 'utf8'));

function resetCapture() {
  createdLayers.length = 0;
  messagesEl.children.length = 0;
}

function runScenario(label, routeField, expectWarning) {
  console.log('='.repeat(70));
  console.log(label);
  resetCapture();

  sandbox.renderRoute(routeField);
  sandbox.renderRouteInfoPanel(routeField);

  const overlays = createdLayers.filter((l) => l.type === 'polyline' && l.options.className === 'boundary-warning-overlay');
  const basePolylines = createdLayers.filter((l) => l.type === 'polyline' && l.options.className !== 'boundary-warning-overlay');
  const warnedRoutes = routeField.candidate_routes.filter((r) => r.boundary_warning);

  console.log(`  candidate routes: ${routeField.candidate_routes.length}, boundary_warning=true on: ${warnedRoutes.length}`);
  console.log(`  base polylines drawn: ${basePolylines.length}, magenta overlay lines drawn: ${overlays.length}`);

  check(
    'one magenta .boundary-warning-overlay polyline per boundary_warning route',
    overlays.length === warnedRoutes.length,
    `expected ${warnedRoutes.length}, got ${overlays.length}`
  );

  if (overlays.length > 0) {
    check('overlay color is the distinct magenta (#d500f9), not a risk-level color', overlays.every((o) => o.options.color === '#d500f9'));
    check('overlay uses a dashed pattern (visually distinct stripe)', overlays.every((o) => typeof o.options.dashArray === 'string'));
  }

  const popupsWithWarning = basePolylines.filter((p) => p.popupContent && p.popupContent.includes('MARITIME BOUNDARY WARNING'));
  check(
    'route popup text includes the boundary warning + distance for every warned route',
    popupsWithWarning.length === warnedRoutes.length,
    `expected ${warnedRoutes.length}, got ${popupsWithWarning.length}`
  );
  if (warnedRoutes.length > 0) {
    const expectedKm = String(warnedRoutes[0].boundary_distance_km);
    check(
      `popup includes the actual distance value (${expectedKm} km)`,
      popupsWithWarning.some((p) => p.popupContent.includes(expectedKm))
    );
  }

  const infoCard = messagesEl.children[messagesEl.children.length - 1];
  const recommended = routeField.candidate_routes.find((r) => r.is_recommended);
  const bannerExpected = !!(recommended && recommended.boundary_warning);
  check(
    'route info panel shows a prominent boundary banner iff the RECOMMENDED route is flagged',
    infoCard.innerHTML.includes('route-boundary-banner') === bannerExpected
  );
  if (bannerExpected) {
    check(
      `info panel banner mentions the recommended route's own distance (${recommended.boundary_distance_km} km)`,
      infoCard.innerHTML.includes(String(recommended.boundary_distance_km))
    );
    check(
      "info panel banner explicitly says the risk level alone doesn't tell the full story",
      infoCard.innerHTML.includes(recommended.route_risk_level)
    );
  }

  check(
    `overall: this scenario ${expectWarning ? 'DOES' : 'does NOT'} visually flag a boundary warning, as expected`,
    (overlays.length > 0) === expectWarning
  );
  console.log();
}

runScenario(
  'SCENARIO 1: Rameswaram -> Palk Strait / India-Sri Lanka boundary (real backend fixture, expect visual warning)',
  fixtures.boundary_warning,
  true
);

runScenario(
  "SCENARIO 2: Kochi -> Kochi's nearest_pfz (real backend fixture, expect NO visual warning)",
  fixtures.no_warning,
  false
);

console.log('='.repeat(70));
console.log(`RESULTS: ${passed} passed, ${failed} failed`);
if (failed === 0) {
  console.log('All boundary-warning UI checks pass.');
} else {
  console.log('Some checks failed - review the FAIL lines above.');
  process.exitCode = 1;
}
