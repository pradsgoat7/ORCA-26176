const API_URL = "http://localhost:8000/ask";

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

function addMessage(text, sender, riskLevel) {
  const messages = document.getElementById('messages');
  const div = document.createElement('div');
  div.className = 'msg ' + sender;
  if (riskLevel) {
    const tag = document.createElement('div');
    tag.className = 'risk-tag risk-' + riskLevel;
    tag.textContent = riskLevel.toUpperCase();
    div.appendChild(tag);
    div.appendChild(document.createElement('br'));
  }
  div.appendChild(document.createTextNode(text));
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function askExample(text) {
  document.getElementById('query-input').value = text;
  sendQuery();
}

// ---------- Phase 2 (Risk Zones): multi-zone map visualization ----------
const ZONES_URL = "http://localhost:8000/zones";

let zoneMarkers = [];

function clearZoneMarkers() {
  zoneMarkers.forEach(m => map.removeLayer(m));
  zoneMarkers = [];
}

function levelColor(level) {
  switch (level) {
    case 'CRITICAL': return '#dc3545';
    case 'HIGH': return '#fd7e14';
    case 'MODERATE': return '#ffc107';
    default: return '#28a745'; // LOW
  }
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

// ---------- Phase 6: dynamic stakeholder risk dashboard ----------
const STAKEHOLDER_DASHBOARD_TITLES = {
  fisherman: '🎣 ORCA Fishing Safety',
  coast_guard: '🛟 ORCA Maritime Risk',
  disaster_management: '🚨 ORCA Disaster Risk',
  general: '📊 ORCA Risk Analysis',
};

const LEVEL_EMOJIS = { LOW: '🟢', MODERATE: '🟡', HIGH: '🟠', CRITICAL: '🔴' };

function scoreToColor(score) {
  if (score >= 75) return '#dc3545'; // red
  if (score >= 50) return '#fd7e14'; // orange
  if (score >= 25) return '#ffc107'; // yellow
  return '#28a745'; // green
}

function renderRiskCard(stakeholder, risk) {
  const stakeholderType = (stakeholder && stakeholder.type) || 'general';
  const title = STAKEHOLDER_DASHBOARD_TITLES[stakeholderType] || STAKEHOLDER_DASHBOARD_TITLES.general;
  const level = risk.overall_level || 'LOW';
  const emoji = LEVEL_EMOJIS[level] || '⚪';
  const levelClass = 'risk-badge-' + level.toLowerCase();

  // Bars are built entirely from the backend's numeric scores below -
  // never hardcoded. If wave_risk = 20, this renders a 20%-wide bar;
  // if it's 90, the bar is 90% wide, automatically.
  const metricsHtml = (risk.metrics || []).map(m => `
    <div class="risk-metric-row">
      <div class="risk-metric-label"><span>${m.name}</span><span>${m.score}%</span></div>
      <div class="risk-bar-track">
        <div class="risk-bar-fill" style="width: ${m.score}%; background: ${scoreToColor(m.score)};"></div>
      </div>
    </div>
  `).join('');

  const card = document.createElement('div');
  card.className = 'risk-card';
  card.innerHTML = `
    <div class="risk-card-title">${title}</div>
    <div class="risk-overall-row">
      <span class="risk-overall-badge ${levelClass}">${emoji} ${level} \u2014 ${risk.overall_score}/100</span>
    </div>
    ${metricsHtml}
    <div class="risk-recommendation"><b>Recommendation:</b> ${risk.recommendation || ''}</div>
  `;

  const messages = document.getElementById('messages');
  messages.appendChild(card);
  messages.scrollTop = messages.scrollHeight;
}

// ---------- Route Optimization Phase 5: route map visualization ----------
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

    // Recommended: solid, thick, high opacity. Alternatives: dashed,
    // thinner, lower opacity - color still reflects each route's OWN
    // risk level, so a risky alternative is visually obvious too.
    const polyline = L.polyline(latlngs, {
      color: color,
      weight: isRecommended ? 5 : 3,
      opacity: isRecommended ? 0.9 : 0.5,
      dashArray: isRecommended ? null : '6, 8',
    }).addTo(map);

    const recTag = isRecommended ? ' \u2705 RECOMMENDED' : '';
    polyline.bindPopup(`
      <b>${route.label}</b>${recTag}<br>
      ${LEVEL_EMOJIS[route.route_risk_level] || ''} ${route.route_risk_level} \u2014 ${route.route_risk_score}/100<br>
      Distance: ${route.distance_km} km &nbsp; Time: ~${route.travel_time_min} min<br>
      Primary risk factor: ${route.primary_risk_factor}
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

function renderRouteInfoPanel(routeField) {
  const recommended = routeField.candidate_routes.find(r => r.is_recommended);
  if (!recommended) return;

  const emoji = LEVEL_EMOJIS[recommended.route_risk_level] || '';
  const levelClass = 'risk-badge-' + recommended.route_risk_level.toLowerCase();

  const altListHtml = routeField.candidate_routes.map(r => {
    const icon = r.is_recommended ? '\u2705' : (r.route_risk_level === 'HIGH' || r.route_risk_level === 'CRITICAL' ? '\u274c' : '\u26a0\ufe0f');
    const recTag = r.is_recommended ? ' <i>Recommended</i>' : '';
    return `<div class="route-alt-item">${icon} <b>${r.label}</b> \u2014 ${r.distance_km} km, risk ${r.route_risk_score}/100 (${r.route_risk_level})${recTag}</div>`;
  }).join('');

  const card = document.createElement('div');
  card.className = 'risk-card'; // reuse existing card styling for visual consistency
  card.innerHTML = `
    <div class="risk-card-title">\ud83e\udded ORCA MARINE ROUTE</div>
    <div class="risk-overall-row">
      <span class="risk-overall-badge ${levelClass}">${emoji} ${recommended.route_risk_level} \u2014 ${recommended.route_risk_score}/100</span>
    </div>
    <div class="risk-metric-row"><b>Distance:</b> ${recommended.distance_km} km</div>
    <div class="risk-metric-row"><b>Estimated Travel Time:</b> ${recommended.travel_time_min} min</div>
    <div class="risk-metric-row"><b>Primary Risk Factor:</b> ${recommended.primary_risk_factor}</div>
    <div class="risk-recommendation"><b>Why this route?</b> ${routeField.explanation}</div>
    <div class="route-alternatives">${altListHtml}</div>
    <div class="route-disclaimer">Prototype recommendation based on currently available environmental data \u2014 not certified maritime navigation.</div>
  `;

  const messages = document.getElementById('messages');
  messages.appendChild(card);
  messages.scrollTop = messages.scrollHeight;
}

// ---------- Voice input (Web Speech API - built into Chrome/Edge, free, no API key) ----------
let selectedSpeechLang = 'en-IN';
let recognition = null;
let isListening = false;

const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;

function setSpeechLang(btn) {
  selectedSpeechLang = btn.dataset.lang;
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

function toggleListening() {
  if (!SpeechRecognitionAPI) {
    addMessage("Voice input isn't supported in this browser. Please try Chrome or Edge, or type your question instead.", 'bot');
    return;
  }

  if (isListening) {
    recognition.stop();
    return;
  }

  recognition = new SpeechRecognitionAPI();
  recognition.lang = selectedSpeechLang;
  recognition.continuous = false;
  recognition.interimResults = false;

  const micBtn = document.getElementById('mic-btn');

  recognition.onstart = () => {
    isListening = true;
    micBtn.classList.add('listening');
    micBtn.textContent = '⏺';
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    // Populate the input field so the user can review/edit before sending,
    // rather than auto-submitting straight from voice - gives a chance to
    // correct any misheard words before it goes to the backend.
    document.getElementById('query-input').value = transcript;
  };

  recognition.onerror = (event) => {
    addMessage(`Voice input error: ${event.error}. Please try again or type your question.`, 'bot');
  };

  recognition.onend = () => {
    isListening = false;
    micBtn.classList.remove('listening');
    micBtn.textContent = '🎤';
  };

  recognition.start();
}

async function sendQuery() {
  const input = document.getElementById('query-input');
  const query = input.value.trim();
  if (!query) return;

  addMessage(query, 'user');
  input.value = '';

  try {
    const res = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    const data = await res.json();

    if (data.error) {
      addMessage(data.answer, 'bot');
      // Clear any stale route visuals from a previous successful route
      // query - otherwise an old route line would linger on screen while
      // showing an unrelated error for the current query.
      clearRouteLayers();
      return;
    }

    addMessage(data.answer, 'bot', data.risk_level);

    // Phase 6: render the stakeholder-specific risk dashboard, if present
    // (it won't be, on the error path, since risk is null there).
    if (data.risk && data.stakeholder) {
      renderRiskCard(data.stakeholder, data.risk);
    }

    // Phase 2 (Risk Zones): refresh the zone circles using the same
    // stakeholder context just detected for this query, so the zone
    // weighting stays consistent with the chat response.
    if (data.stakeholder) {
      fetchZones(data.stakeholder.type);
    }

    clearMarkers();
    const userLoc = data.map.user_location;
    const pfz = data.map.nearest_pfz;

    const userMarker = L.marker([userLoc.lat, userLoc.lon])
      .addTo(map)
      .bindPopup(`<b>${data.map.location_name}</b>`);
    markers.push(userMarker);

    // Guard: nearest_pfz can now be null for a non-demo geocoded city
    // (Phase 4's live-geocoding feature), so only render this marker
    // when PFZ data actually exists.
    if (pfz) {
      const pfzMarker = L.marker([pfz.lat, pfz.lon])
        .addTo(map)
        .bindPopup(`<b>${pfz.name}</b><br>${pfz.distance_km} km away`);
      markers.push(pfzMarker);
    }

    map.setView([userLoc.lat, userLoc.lon], 8);

    // Route Optimization Phase 5: render route polylines + info panel if
    // this was a successful route request. fitBounds() inside renderRoute()
    // runs AFTER the setView() above, so it correctly overrides the tighter
    // per-city zoom when the route spans further than one city.
    if (data.route && !data.route.error) {
      renderRoute(data.route);
      renderRouteInfoPanel(data.route);
    } else {
      // Not a route request (or a route request that failed) - clear any
      // stale route visuals from a previous successful route query.
      clearRouteLayers();
    }

  } catch (err) {
    addMessage("Could not reach the backend. Is it running on localhost:8000?", 'bot');
  }
}