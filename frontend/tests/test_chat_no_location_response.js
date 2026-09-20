// Mocked-DOM regression test for a real bug found while building Section
// 14r's greeting/help feature: sendQuery() (chat.js) unconditionally read
// data.map.user_location, but the "no location_data" response shape
// (data.map: null - used for pure policy questions since Section 14h, and
// now also for greeting/help messages, Section 14r) has no map field at
// all. Without a guard, this threw a TypeError inside the try block,
// landing in the catch handler and silently replacing the correct
// onboarding/policy answer with a bogus second "Could not reach the
// backend" message - confirmed live in a real browser session before the
// fix (typing "hello" produced the right answer immediately followed by
// that spurious error).
//
// Same Node `vm`-mocked-DOM technique as test_tabs_ui.js/
// test_stage2_tabs_ui.js.
//
// Usage:
//   node frontend/tests/test_chat_no_location_response.js

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
    this._classes = new Set();
    this.children = [];
    this.style = {};
    this.innerHTML = '';
    this.textContent = '';
    this.value = '';
    const self = this;
    this.classList = {
      add: (c) => self._classes.add(c),
      remove: (c) => self._classes.delete(c),
      contains: (c) => self._classes.has(c),
    };
    allElements.push(this);
  }
  appendChild(child) {
    this.children.push(child);
    if (child && child.textContent) this.textContent += child.textContent;
    return child;
  }
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

const queryInput = makeElement('input'); queryInput.id = 'query-input';
const messages = makeElement('div'); messages.id = 'messages';

let invalidateSizeCalls = 0;
const L = {
  latLngBounds: (pts) => ({ _points: pts }),
  map: () => ({ setView() { return this; }, removeLayer() {}, fitBounds() {}, on() { return this; }, invalidateSize() { invalidateSizeCalls++; } }),
  tileLayer: () => ({ addTo() { return this; } }),
  control: () => { const c = {}; c.addTo = () => c; return c; },
  DomUtil: { create: (tag) => makeElement(tag) },
  circleMarker: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
  marker: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
  polyline: () => ({ addTo() { return this; }, bindPopup() { return this; } }),
};

// The "no location_data" response shape (routes.py's own branch for a
// pure policy question or a greeting/help message) - map/risk/route are
// all null, but answer/language/stakeholder are real.
const NO_LOCATION_RESPONSE = {
  answer: "Hi! I'm ORCA, a marine intelligence assistant...",
  risk_level: null,
  risk_reasons: [],
  weather: null,
  ocean: null,
  map: null,
  stakeholder: null,
  language: 'en',
  risk: null,
  route: null,
  policy_answer: null,
  confidence: null,
};

const consoleErrors = [];
const sandbox = {
  console: { log: () => {}, warn: () => {}, error: (...a) => consoleErrors.push(a.join(' ')) },
  document: document_,
  L,
  fetch: () => Promise.resolve({ json: () => Promise.resolve(NO_LOCATION_RESPONSE) }),
  requestAnimationFrame: (fn) => fn(),
  setTimeout,
  clearTimeout,
  AbortController: class { constructor() { this.signal = {}; } abort() {} },
  speechSynthesis: { speak() {}, cancel() {}, getVoices: () => [] },
  SpeechSynthesisUtterance: function () {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);

const jsDir = path.join(__dirname, '..', 'js');
const bundle = ['config.js', 'map.js', 'voice.js', 'chat.js']
  .map((f) => fs.readFileSync(path.join(jsDir, f), 'utf8'))
  .join('\n;\n');
vm.runInContext(bundle, sandbox, { filename: 'chat-bundle.js' });

console.log('='.repeat(70));
console.log('TEST: sendQuery() handles the "no location_data" response shape (data.map === null)');

queryInput.value = 'hello';

(async () => {
  await sandbox.sendQuery();
  // Let any unhandled promise rejection inside sendQuery's try/catch settle.
  await new Promise((resolve) => setTimeout(resolve, 10));

  const botMessages = messages.children.filter((el) => (el.className || '').split(' ').includes('bot'));
  const userMessages = messages.children.filter((el) => (el.className || '').split(' ').includes('user'));

  check('exactly one user message was added', userMessages.length === 1, `got ${userMessages.length}`);
  check('exactly ONE bot message was added (not a second spurious error)',
    botMessages.length === 1, `got ${botMessages.length}: ${botMessages.map((m) => m.textContent).join(' | ')}`);
  check('the single bot message is the real onboarding answer, not a network error',
    botMessages[0] && botMessages[0].textContent.includes('ORCA'));
  check('no "Could not reach the backend" bogus error appeared',
    !botMessages.some((m) => m.textContent.includes('Could not reach the backend')));
  check('no console.error calls during the whole flow', consoleErrors.length === 0, JSON.stringify(consoleErrors));

  console.log();
  console.log('='.repeat(70));
  console.log(`RESULTS: ${passed} passed, ${failed} failed`);
  if (failed === 0) {
    console.log('The data.map-null crash is fixed and stays fixed.');
  } else {
    console.log('Some checks failed - review the FAIL lines above.');
    process.exitCode = 1;
  }
})();
