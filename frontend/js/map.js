// ---------- Map setup ----------
// Depends on config.js (levelColor, LEVEL_EMOJIS, ZONES_URL) - must load after it.

// View is locked to south/central India (where all demo locations are)
// so the map never scrolls up to the Kashmir region, whose boundary
// rendering differs between global map providers and India's official map.
const southIndiaBounds = L.latLngBounds([5, 70], [21, 90]);

const map = L.map('map', {
  maxBounds: southIndiaBounds,
  maxBoundsViscosity: 1.0,
  minZoom: 6
}).setView([13, 79], 6);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

let markers = [];

function clearMarkers() {
  markers.forEach(m => map.removeLayer(m));
  markers = [];
}

// ---------- Risk Zones: multi-zone map visualization ----------
let zoneMarkers = [];

function clearZoneMarkers() {
  zoneMarkers.forEach(m => map.removeLayer(m));
  zoneMarkers = [];
}

function renderZones(zonesData) {
  clearZoneMarkers();
  zonesData.forEach(z => {
    const color = levelColor(z.overall_level);
    // Radius is deliberately large (35px) so the zone shows as a visible
    // colored halo around the location pin, rather than being completely
    // hidden underneath it - Leaflet always draws markers above circles,
    // so a small circle at the same coordinates as a pin is invisible.
    const circle = L.circleMarker([z.lat, z.lon], {
      radius: 35,
      color: color,
      fillColor: color,
      fillOpacity: 0.35,
      weight: 2,
    }).addTo(map);

    circle.bindPopup(`
      <b>${z.name} Coastal Zone</b><br>
      ${LEVEL_EMOJIS[z.overall_level] || ''} ${z.overall_level} \u2014 ${z.overall_score}/100<br>
      Primary driver: ${z.primary_driver}<br>
      Wave: ${z.wave_height_m} m &nbsp; Wind: ${z.wind_speed_kmph} km/h<br>
      <i>${z.recommendation}</i>
    `);

    zoneMarkers.push(circle);
  });

  updateRiskMapSummary(zonesData);
}

// ---------- Risk Map tab (Section 14q): client-side summary strip ----------
// Computed from the SAME zonesData already fetched above for the circles -
// no second network call. Guarded with `if (el)` since these elements only
// exist on the real page (not in the Node-based mocked-DOM tests), and
// since this runs on every fetchZones() call regardless of which tab is
// currently visible - updating a hidden tab's DOM is harmless and means
// the numbers are already correct the moment a user switches to Risk Map.
function updateRiskMapSummary(zonesData) {
  const counts = { LOW: 0, MODERATE: 0, HIGH: 0, CRITICAL: 0 };
  zonesData.forEach(z => {
    if (Object.prototype.hasOwnProperty.call(counts, z.overall_level)) counts[z.overall_level]++;
  });

  const lowEl = document.getElementById('riskmap-count-low');
  const modEl = document.getElementById('riskmap-count-moderate');
  const highEl = document.getElementById('riskmap-count-high');
  const critEl = document.getElementById('riskmap-count-critical');
  if (lowEl) lowEl.textContent = counts.LOW;
  if (modEl) modEl.textContent = counts.MODERATE;
  if (highEl) highEl.textContent = counts.HIGH;
  if (critEl) critEl.textContent = counts.CRITICAL;
}

async function fetchZones(stakeholderType) {
  try {
    const type = stakeholderType || 'general';
    const res = await fetch(`${ZONES_URL}?stakeholder=${encodeURIComponent(type)}`);
    const data = await res.json();
    renderZones(data.zones || []);
  } catch (err) {
    // Zones are a supplementary map visualization, not core chat
    // functionality - fail silently here rather than interrupting the
    // user's conversation over a secondary feature.
    console.warn('Could not load risk zones:', err);
  }
}

// Static legend control - colors match levelColor() above exactly.
const legendControl = L.control({ position: 'bottomright' });
legendControl.onAdd = function () {
  const div = L.DomUtil.create('div', 'map-legend');
  div.innerHTML = `
    <div class="map-legend-title">RISK LEVEL</div>
    <div><span class="legend-swatch" style="background:#28a745;"></span>LOW</div>
    <div><span class="legend-swatch" style="background:#ffc107;"></span>MODERATE</div>
    <div><span class="legend-swatch" style="background:#fd7e14;"></span>HIGH</div>
    <div><span class="legend-swatch" style="background:#dc3545;"></span>CRITICAL</div>
  `;
  return div;
};
legendControl.addTo(map);

// "Show all zones" control - since every chat query zooms tightly to that
// one city, the other zones can end up off-screen. This gives a one-click
// way back to the full south-India view where all zones are visible.
const resetViewControl = L.control({ position: 'topright' });
resetViewControl.onAdd = function () {
  const div = L.DomUtil.create('div', 'map-legend');
  div.style.cursor = 'pointer';
  div.innerHTML = `<div class="map-legend-title" style="margin-bottom:0;">🗺️ Show All Zones</div>`;
  div.onclick = () => map.setView([13, 79], 6);
  return div;
};
resetViewControl.addTo(map);

// Load zones once at page load, using the default 'general' stakeholder
// context until the first query gives us a detected stakeholder.
fetchZones('general');

// ---------- Route Optimization: route polyline visualization ----------
let routeLayers = [];

function clearRouteLayers() {
  routeLayers.forEach(l => map.removeLayer(l));
  routeLayers = [];
}

function renderRoute(routeField) {
  clearRouteLayers();
  const allLatLngs = [];

  routeField.candidate_routes.forEach(route => {
    const latlngs = route.waypoints.map(wp => [wp.lat, wp.lon]);
    allLatLngs.push(...latlngs);

    const color = levelColor(route.route_risk_level);
    const isRecommended = route.is_recommended;
    const hasBoundaryWarning = !!route.boundary_warning;
    const hasMpaWarning = !!route.mpa_warning;

    // Recommended: solid, thick, high opacity. Alternatives: dashed,
    // thinner, lower opacity - color still reflects each route's OWN
    // risk level, so a risky alternative is visually obvious too.
    const polyline = L.polyline(latlngs, {
      color: color,
      weight: isRecommended ? 5 : 3,
      opacity: isRecommended ? 0.9 : 0.5,
      dashArray: isRecommended ? null : '6, 8',
    }).addTo(map);

    // Maritime boundary geofencing warning: this is a DIFFERENT kind of
    // hazard than the usual wave/wind/cyclone risk (which the color above
    // already encodes), so it gets its own overlay rather than reusing a
    // risk-level color - a CRITICAL-risk route is already red, and a
    // boundary warning must never be mistaken for "just very risky
    // weather". A second dashed magenta line, pulsing via CSS
    // (.boundary-warning-overlay, see style.css), is drawn on top of the
    // normal route line so the distinction is unmistakable at a glance.
    if (hasBoundaryWarning) {
      const boundaryOverlay = L.polyline(latlngs, {
        color: '#d500f9',
        weight: (isRecommended ? 5 : 3) + 5,
        opacity: 0.85,
        dashArray: '2, 14',
        lineCap: 'round',
        className: 'boundary-warning-overlay',
      }).addTo(map);
      routeLayers.push(boundaryOverlay);
    }

    // Marine Protected Area geofencing warning (Section 14o): a
    // DIFFERENT kind of hazard than both the risk-level color AND the
    // maritime boundary warning above - crossing an international
    // boundary is a legal/territorial problem, entering a protected
    // conservation area is an environmental/fishing-restriction problem.
    // Deliberately NOT reusing the boundary warning's magenta - teal is
    // distinct from magenta, from the green/yellow/orange/red risk
    // palette, and conventionally reads as "environmental/conservation".
    // Both overlays can appear on the same route simultaneously without
    // being confused for one another (offset slightly wider so a route
    // flagged for BOTH still shows two visibly separate stripes).
    if (hasMpaWarning) {
      const mpaOverlay = L.polyline(latlngs, {
        color: '#00bfa5',
        weight: (isRecommended ? 5 : 3) + (hasBoundaryWarning ? 9 : 5),
        opacity: 0.85,
        dashArray: '1, 10',
        lineCap: 'round',
        className: 'mpa-warning-overlay',
      }).addTo(map);
      routeLayers.push(mpaOverlay);
    }

    const recTag = isRecommended ? ' \u2705 RECOMMENDED' : '';
    const boundaryWarningHtml = hasBoundaryWarning
      ? `<br><span class="boundary-warning-popup">\u26a0\ufe0f MARITIME BOUNDARY WARNING \u2014 comes within ${route.boundary_distance_km} km of India's EEZ boundary</span>`
      : '';
    const mpaWarningHtml = hasMpaWarning
      ? `<br><span class="mpa-warning-popup">\ud83c\udf3f MARINE PROTECTED AREA WARNING \u2014 comes within ${route.mpa_distance_km} km of a protected conservation area</span>`
      : '';
    polyline.bindPopup(`
      <b>${route.label}</b>${recTag}<br>
      ${LEVEL_EMOJIS[route.route_risk_level] || ''} ${route.route_risk_level} \u2014 ${route.route_risk_score}/100<br>
      Distance: ${route.distance_km} km &nbsp; Time: ~${route.travel_time_min} min<br>
      Primary risk factor: ${route.primary_risk_factor}${boundaryWarningHtml}${mpaWarningHtml}
    `);

    routeLayers.push(polyline);
  });

  // Start (green) and destination (red) markers - visually distinct from
  // the normal chat location/PFZ pins so START vs DESTINATION vs ROUTE
  // are all clearly separate at a glance.
  const startMarker = L.circleMarker([routeField.origin.lat, routeField.origin.lon], {
    radius: 8, color: '#155724', fillColor: '#28a745', fillOpacity: 1, weight: 2,
  }).addTo(map).bindPopup(`<b>Start:</b> ${routeField.origin.name}`);

  const destMarker = L.circleMarker([routeField.destination.lat, routeField.destination.lon], {
    radius: 8, color: '#721c24', fillColor: '#dc3545', fillOpacity: 1, weight: 2,
  }).addTo(map).bindPopup(`<b>Destination:</b> ${routeField.destination.name}`);

  routeLayers.push(startMarker, destMarker);

  // Fit the map to show the ENTIRE route - overrides the tighter per-city
  // zoom used for normal (non-route) queries, since a route can easily
  // span further than a single city's zoom level would show.
  if (allLatLngs.length > 0) {
    map.fitBounds(L.latLngBounds(allLatLngs), { padding: [40, 40] });
  }
}
