// Mocked-DOM test for the tab-switching shell (Stage 1) - same technique
// as test_boundary_warning_ui.js / test_mpa_warning_ui.js: concatenate the
// real config.js/map.js/voice.js/chat.js/tabs.js as ONE unit via node's vm
// module (exact production <script> order), against a hand-rolled DOM
// mock rich enough to support the real querySelectorAll/classList/dataset
// calls tabs.js actually makes - not a browser, but exercises the real
// logic, not a reimplementation of it.
//
// This test focuses on STRUCTURE (tab switching itself, and that moving
// the chat UI into a tab didn't break the functions it depends on) - it
// cannot verify real visual Leaflet rendering behavior (e.g. whether
// invalidateSize() actually produces correctly-sized tiles in a real
// browser) since L is mocked here, same limitation as the existing
// boundary/MPA UI tests. See PROJECT_CONTEXT.md for the separate real-
// browser verification of that specific risk.
//
// Usage:
//   node frontend/tests/test_tabs_ui.js

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

// ---------- Minimal but real-enough DOM mock ----------
const allElements = [];

function matchesSimpleSelector(el, selector) {
  // Supports exactly the selector shapes this codebase's JS actually uses:
  // ".class", "#id", ".class[data-attr=\"value\"]"
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
    allElements.push(this);
  }
  appendChild(child) { this.children.push(child); return child; }
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

// ---------- Build the REAL production tab structure (mirrors index.html) ----------
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

// Real IDs the existing chat.js/voice.js code actually looks up, nested
// "inside" tab-ask (parent/child relationship doesn't matter for these
// mocks since getElementById searches the flat registry either way,
// exactly like a real document does).
const messagesEl = makeElement('div'); messagesEl.id = 'messages';
const queryInput = makeElement('input'); queryInput.id = 'query-input';
const micBtn = makeElement('button'); micBtn.id = 'mic-btn';
const voiceOutputBtn = makeElement('button'); voiceOutputBtn.id = 'voice-output-btn';
const langBtnEn = makeElement('button'); langBtnEn.classList.add('lang-btn', 'active'); langBtnEn.dataset.lang = 'en-IN';
const langBtnHi = makeElement('button'); langBtnHi.classList.add('lang-btn'); langBtnHi.dataset.lang = 'hi-IN';

// ---------- Minimal Leaflet mock (same shape as the other UI tests) ----------
const createdLayers = [];
let invalidateSizeCallCount = 0;

function mockLayer(type, options) {
  const layer = { type, options, popupContent: null };
  layer.addTo = () => { createdLayers.push(layer); return layer; };
  layer.bindPopup = (html) => { layer.popupContent = html; return layer; };
  layer.on = () => layer;
  return layer;
}

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
  circleMarker: (latlng, opts) => mockLayer('circleMarker', { latlng, ...opts }),
  marker: (latlng, opts) => mockLayer('marker', { latlng, ...opts }),
  polyline: (latlngs, opts) => mockLayer('polyline', { latlngs, ...opts }),
};

// ---------- Capture console errors during load/execution ----------
const consoleErrors = [];
const capturingConsole = {
  log: () => {},
  warn: () => {},
  error: (...args) => consoleErrors.push(args.join(' ')),
};

// Minimal Web Speech API mock - real browsers provide window.speechSynthesis;
// voice.js's toggleVoiceOutput()/speak() call into it directly.
const SpeechSynthesisUtterance = function (text) { this.text = text; this.lang = ''; };
const speechSynthesis = { cancel: () => {}, speak: () => {} };

const sandbox = {
  console: capturingConsole,
  document: document_,
  L,
  fetch: () => Promise.reject(new Error('network disabled in this offline UI test')),
  requestAnimationFrame: (fn) => fn(), // run synchronously so invalidateSize() is observable immediately in this test
  setTimeout,
  speechSynthesis,
  SpeechSynthesisUtterance,
};
sandbox.window = sandbox;
vm.createContext(sandbox);

const jsDir = path.join(__dirname, '..', 'js');
const bundle = ['config.js', 'map.js', 'voice.js', 'chat.js', 'tabs.js']
  .map((f) => fs.readFileSync(path.join(jsDir, f), 'utf8'))
  .join('\n;\n');

let loadError = null;
try {
  vm.runInContext(bundle, sandbox, { filename: 'frontend-bundle.js' });
} catch (e) {
  loadError = e;
}

// ---------- Tests ----------
console.log('='.repeat(70));
console.log('TEST: bundle loads with no console.error and no thrown exception');
check('all 5 scripts (config/map/voice/chat/tabs) loaded without throwing', loadError === null, loadError && loadError.stack);
check('no console.error calls during load', consoleErrors.length === 0, JSON.stringify(consoleErrors));
console.log();

console.log('='.repeat(70));
console.log('TEST: default tab on load is Home, not Ask ORCA');
check("tab-home has 'active' class by default", tabPanels['tab-home'].classList.contains('active'));
check("tab-ask does NOT have 'active' class by default", !tabPanels['tab-ask'].classList.contains('active'));
check('exactly one tab-panel is active on load', TAB_IDS.filter((id) => tabPanels[id].classList.contains('active')).length === 1);
check('exactly one tab-btn is active on load', TAB_IDS.filter((id) => navButtons[id].classList.contains('active')).length === 1);
check("the active tab-btn on load is Home's", navButtons['tab-home'].classList.contains('active'));
console.log();

console.log('='.repeat(70));
console.log('TEST: clicking each nav button shows only that tab and hides the rest');
TAB_IDS.forEach((targetId) => {
  navButtons[targetId].dispatchClick();
  const activePanels = TAB_IDS.filter((id) => tabPanels[id].classList.contains('active'));
  const activeBtns = TAB_IDS.filter((id) => navButtons[id].classList.contains('active'));
  check(`clicking "${targetId}" shows only "${targetId}"`, activePanels.length === 1 && activePanels[0] === targetId, `got active panels: ${activePanels}`);
  check(`clicking "${targetId}" highlights only its own nav button`, activeBtns.length === 1 && activeBtns[0] === targetId, `got active buttons: ${activeBtns}`);
});
console.log();

console.log('='.repeat(70));
console.log('TEST: map.invalidateSize() is called when (and only when) switching TO Ask ORCA');
invalidateSizeCallCount = 0;
navButtons['tab-home'].dispatchClick();
check("switching to Home does NOT call invalidateSize", invalidateSizeCallCount === 0, `count=${invalidateSizeCallCount}`);
navButtons['tab-ask'].dispatchClick();
check('switching to Ask ORCA DOES call invalidateSize (Leaflet-in-hidden-tab fix)', invalidateSizeCallCount === 1, `count=${invalidateSizeCallCount}`);
navButtons['tab-about'].dispatchClick();
check('switching away to About does NOT call invalidateSize again', invalidateSizeCallCount === 1, `count=${invalidateSizeCallCount}`);
console.log();

console.log('='.repeat(70));
console.log('TEST: relocated chat functions still exist and are callable (structural regression check)');
check('sendQuery is defined', typeof sandbox.sendQuery === 'function');
check('renderRiskCard is defined', typeof sandbox.renderRiskCard === 'function');
check('renderRouteInfoPanel is defined', typeof sandbox.renderRouteInfoPanel === 'function');
check('addMessage is defined and appends to #messages', (() => {
  const before = messagesEl.children.length;
  sandbox.addMessage('test message', 'bot');
  return messagesEl.children.length === before + 1;
})());
console.log();

console.log('='.repeat(70));
console.log('TEST: voice input/output functions still exist and are callable (structural regression check)');
check('toggleVoiceOutput is defined and does not throw', (() => {
  try { sandbox.toggleVoiceOutput(voiceOutputBtn); return true; } catch (e) { console.log(e); return false; }
})());
check('setSpeechLang is defined and updates the active language button', (() => {
  sandbox.setSpeechLang(langBtnHi);
  return langBtnHi.classList.contains('active') && !langBtnEn.classList.contains('active');
})());
check('toggleListening is defined and does not throw even with no SpeechRecognition mocked', (() => {
  try { sandbox.toggleListening(); return true; } catch (e) { return false; }
})());
console.log();

console.log('='.repeat(70));
console.log('TEST: no console.error calls accumulated across all tab switches and function calls');
check('still zero console.error calls after full interaction sequence', consoleErrors.length === 0, JSON.stringify(consoleErrors));
console.log();

console.log('='.repeat(70));
console.log(`RESULTS: ${passed} passed, ${failed} failed`);
if (failed === 0) {
  console.log('All tab-shell UI checks pass.');
} else {
  console.log('Some checks failed - review the FAIL lines above.');
  process.exitCode = 1;
}
