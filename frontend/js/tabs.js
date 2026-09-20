// ---------- Tab navigation ----------
// Depends on map.js having already run (for the `map` variable) - must
// load LAST, after config.js/map.js/voice.js/chat.js/routeplanner.js/
// knowledgebase.js.
//
// map.js's `L.map('map', ...)` runs immediately at page load, regardless
// of which tab is visible. If a map-hosting tab isn't the default tab
// (it isn't - "Home" is), #map starts out display:none, so Leaflet
// measures its container as zero-size at construction time. Calling
// map.invalidateSize() the moment a map-hosting tab actually becomes
// visible is the standard, documented fix for a Leaflet map inside a
// hidden/tabbed container - without it, the map tiles render blank or
// mis-sized until something else (e.g. a manual window resize) forces
// Leaflet to recompute. requestAnimationFrame gives the browser one frame
// to finish the display:none -> flex layout change before Leaflet
// measures the now-visible container.

// Tabs that host the single shared Leaflet `map` instance (Section 14q
// added Risk Map and Route Planner alongside Stage 1's Ask ORCA). All
// three legitimately need the same live map (zone heatmap / route
// polylines), and Leaflet only supports one map per container - so rather
// than creating 3 separate map instances (3x the tile requests, 3x the
// /zones fetches, 3 copies of the legend/"Show All Zones" control),
// the SAME #map DOM node is relocated between tabs on switch. Moving a
// container element via appendChild does NOT reset Leaflet's internal
// state (zoom, center, layers all persist) - it just needs the same
// invalidateSize() nudge afterward.
//
// 'tab-ask' maps to the tab-ask SECTION itself, since that's #map's
// original static position in index.html (as the last child, after
// #chat-panel) - appending it there when it's not already there restores
// exactly that original position.
const MAP_HOST_SLOTS = {
  'tab-ask': 'tab-ask',
  'tab-riskmap': 'riskmap-map-slot',
  'tab-routeplanner': 'routeplanner-map-slot',
};

function relocateMapIfNeeded(tabId) {
  const slotId = MAP_HOST_SLOTS[tabId];
  if (!slotId || typeof map === 'undefined' || !map) return;

  const mapDiv = document.getElementById('map');
  const targetContainer = document.getElementById(slotId);
  if (mapDiv && targetContainer && mapDiv.parentElement !== targetContainer) {
    targetContainer.appendChild(mapDiv);
  }
  requestAnimationFrame(() => map.invalidateSize());
}

function showTab(tabId) {
  document.querySelectorAll('.tab-panel').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));

  const panel = document.getElementById(tabId);
  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  if (panel) panel.classList.add('active');
  if (btn) btn.classList.add('active');

  relocateMapIfNeeded(tabId);

  // Risk Map (Section 14q) is meant to read as a clean dashboard, not a
  // leftover chat/route session - reset to the full south-India view (same
  // coordinates as the existing "Show All Zones" control) and clear any
  // route polylines/markers left over from a previous Ask ORCA or Route
  // Planner session, so only the zone heatmap is visible.
  if (tabId === 'tab-riskmap' && typeof map !== 'undefined' && map) {
    map.setView([13, 79], 6);
    if (typeof clearRouteLayers === 'function') clearRouteLayers();
    if (typeof clearMarkers === 'function') clearMarkers();
  }
}

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => showTab(btn.dataset.tab));
});

// "Home" is the default landing tab - a single source of truth here in
// JS (rather than also hardcoding an "active" class in index.html) so
// there's only one place that decides the default.
showTab('tab-home');
