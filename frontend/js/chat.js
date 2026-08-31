// ---------- Chat orchestration ----------
// Depends on config.js and map.js - must load after both.

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

// ---------- Dynamic stakeholder risk dashboard ----------
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

// ---------- Route info panel ----------
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

// ---------- Main query flow ----------
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

    // Render the stakeholder-specific risk dashboard, if present (it
    // won't be, on the error path, since risk is null there).
    if (data.risk && data.stakeholder) {
      renderRiskCard(data.stakeholder, data.risk);
    }

    // Refresh the zone circles using the same stakeholder context just
    // detected for this query, so the zone weighting stays consistent
    // with the chat response.
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

    // Guard: nearest_pfz can be null for a non-demo geocoded city (the
    // live-geocoding feature), so only render this marker when PFZ data
    // actually exists.
    if (pfz) {
      const pfzMarker = L.marker([pfz.lat, pfz.lon])
        .addTo(map)
        .bindPopup(`<b>${pfz.name}</b><br>${pfz.distance_km} km away`);
      markers.push(pfzMarker);
    }

    map.setView([userLoc.lat, userLoc.lon], 8);

    // Render route polylines + info panel if this was a successful route
    // request. fitBounds() inside renderRoute() runs AFTER the setView()
    // above, so it correctly overrides the tighter per-city zoom when the
    // route spans further than one city.
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
