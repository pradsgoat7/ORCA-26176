// ---------- Route Planner tab (Section 14q) ----------
// Depends on config.js (API_URL) and map.js/chat.js (renderRoute,
// renderRouteInfoPanel) - must load after both, before tabs.js.
//
// IMPORTANT: this does NOT call a new backend endpoint. It builds the
// exact same kind of natural-language sentence the Ask ORCA chat already
// handles correctly ("Find the safest route from X to Y..."), calls the
// SAME /ask endpoint, and reuses the SAME renderRoute()/renderRouteInfoPanel()
// rendering functions already built for the chat - this form is just a
// friendlier way to construct that sentence, not a second implementation
// of route planning.

const STAKEHOLDER_QUERY_HINTS = {
  fisherman: 'for fishing',
  coast_guard: 'for coast guard patrol and vessel monitoring, assessing rescue readiness',
  disaster_management: 'for disaster management preparedness and emergency response, assessing hazard level',
  general: '',
};

function setRoutePlannerDestinationToPFZ() {
  // "the fishing zone" is one of route_detection.py's own recognized PFZ
  // destination phrases (PFZ_DESTINATION_KEYWORDS) - using this exact
  // wording is what makes the backend resolve the ALREADY-KNOWN nearest_pfz
  // for the origin city, rather than trying to geocode "fishing zone" as
  // a place name.
  document.getElementById('rp-to').value = 'the fishing zone';
}

// Builds the natural-language query the backend's existing route_detection.py
// + stakeholder.py already know how to parse - no new backend parameter
// exists for "stakeholder", so this steers the backend's own keyword-based
// detect_stakeholder() toward the selected category by including enough of
// its real trigger keywords (see stakeholder.py's STAKEHOLDER_KEYWORDS).
//
// KNOWN LIMITATION, documented rather than hidden: detect_stakeholder()
// picks whichever category scores the MOST keyword hits in the whole
// query text, not an explicit override - so a "general" selection combined
// with a "the fishing zone" destination will still classify as "fisherman"
// server-side, since "fishing zone" is itself a fisherman keyword and
// "general" has no keyword list of its own to compete with it (it's the
// zero-match fallback category). This is a genuine content-based-detection
// edge case, not a bug introduced here - see PROJECT_CONTEXT.md Section 14q.
function buildRoutePlannerQuery(from, to, stakeholderType) {
  const hint = STAKEHOLDER_QUERY_HINTS[stakeholderType] || '';
  let query = `Find the safest route from ${from} to ${to}`;
  if (hint) query += ` ${hint}`;
  return query;
}

async function submitRoutePlanner() {
  const from = document.getElementById('rp-from').value.trim();
  const to = document.getElementById('rp-to').value.trim();
  const stakeholderType = document.getElementById('rp-stakeholder').value;
  const statusEl = document.getElementById('routeplanner-status');
  const resultEl = document.getElementById('routeplanner-result');

  if (!from || !to) {
    statusEl.textContent = 'Please fill in both "From" and "To".';
    return;
  }

  statusEl.textContent = 'Finding the safest route…';
  resultEl.innerHTML = '';

  const query = buildRoutePlannerQuery(from, to, stakeholderType);

  // Same 35s client-side timeout convention as sendQuery() in chat.js -
  // set above the backend's own 30s Gemini timeout.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 35000);

  try {
    const res = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    const data = await res.json();

    if (!data.route || data.route.error) {
      statusEl.textContent = (data.route && data.route.error) || data.answer ||
        'Could not compute a route for that request. Try known coastal towns like Kochi, Chennai, or Visakhapatnam.';
      return;
    }

    statusEl.textContent = '';
    renderRoute(data.route);                              // same map rendering as chat
    renderRouteInfoPanel(data.route, 'routeplanner-result'); // same info panel, own container
  } catch (err) {
    clearTimeout(timeoutId);
    statusEl.textContent = (err.name === 'AbortError')
      ? 'This is taking longer than expected (over 35s) - please try again.'
      : 'Could not reach the backend. Is it running on localhost:8000?';
  }
}
