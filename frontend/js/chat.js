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

  // The government/hard-safety override layer (PROJECT_CONTEXT.md Section
  // 14n) can force overall_level UP without changing overall_score, which
  // otherwise looks like a contradiction on screen (e.g. "CRITICAL \u2014
  // 55/100" against the stated 0-24/25-49/50-74/75-100 bands). Surface
  // WHY whenever it fired - same visual pattern as the existing route
  // boundary-warning banner (Section 14e): a colored callout at the very
  // top of the card, never silent.
  const overrideBannerHtml = risk.override_fired
    ? `<div class="risk-override-banner">\u26a0\ufe0f Escalated from ${risk.pre_override_level} to ${level}: ${(risk.override_reasons || []).join(' ')}</div>`
    : '';

  const card = document.createElement('div');
  card.className = 'risk-card';
  card.innerHTML = `
    ${overrideBannerHtml}
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
// containerId defaults to 'messages' (the Ask ORCA chat log, unchanged
// behavior - appends and scrolls, since chat is a running conversation).
// Route Planner (Section 14q) passes 'routeplanner-result' instead, which
// gets a "replace" behavior below - that tab shows ONE result at a time,
// not an accumulating log, so a second search should replace the first
// rather than stack underneath it.
function renderRouteInfoPanel(routeField, containerId = 'messages') {
  const recommended = routeField.candidate_routes.find(r => r.is_recommended);
  if (!recommended) return;

  const emoji = LEVEL_EMOJIS[recommended.route_risk_level] || '';
  const levelClass = 'risk-badge-' + recommended.route_risk_level.toLowerCase();

  const altListHtml = routeField.candidate_routes.map(r => {
    const icon = r.is_recommended ? '\u2705' : (r.route_risk_level === 'HIGH' || r.route_risk_level === 'CRITICAL' ? '\u274c' : '\u26a0\ufe0f');
    const recTag = r.is_recommended ? ' <i>Recommended</i>' : '';
    const boundaryTag = r.boundary_warning
      ? ` <span class="boundary-warning-popup">\ud83e\udded\u26a0\ufe0f ${r.boundary_distance_km} km to EEZ boundary</span>`
      : '';
    // mpa_warning is a SEPARATE field from boundary_warning (Section 14o) -
    // kept as its own tag, own color, own icon, never merged with the
    // boundary tag, so a fisherman can tell "international boundary" apart
    // from "protected conservation area" even in this compact list. It can
    // also be `null` (not just true/false) when MPA data hasn't been
    // fetched yet (see services/marine_protected_areas.py) - only render
    // the tag when it's actually `true`, not merely truthy-ish.
    const mpaTag = r.mpa_warning === true
      ? ` <span class="mpa-warning-popup">\ud83c\udf3f\u26a0\ufe0f ${r.mpa_distance_km} km to protected area</span>`
      : '';
    return `<div class="route-alt-item">${icon} <b>${r.label}</b> \u2014 ${r.distance_km} km, risk ${r.route_risk_score}/100 (${r.route_risk_level})${recTag}${boundaryTag}${mpaTag}</div>`;
  }).join('');

  // Hard-safety override layer, now applied to routes too (Section 14t) -
  // exact same banner pattern as renderRiskCard()'s overrideBannerHtml
  // (Section 14s), just reading the recommended route's own
  // override_fired/pre_override_level/override_reasons fields instead of
  // the main risk object's. Placed first/topmost among the route's
  // banners - a hard-safety concern (active cyclone, genuinely rough
  // seas, lightning) is a more urgent category of warning than a
  // territorial/conservation-area proximity note.
  const overrideBannerHtml = recommended.override_fired
    ? `<div class="risk-override-banner">⚠️ Escalated from ${recommended.pre_override_level} to ${recommended.route_risk_level}: ${(recommended.override_reasons || []).join(' ')}</div>`
    : '';

  // A route can score LOW/MODERATE on weather risk alone while ALSO
  // running close to India's EEZ boundary - that's genuinely important,
  // separate information a fisherman needs to see, not something the
  // risk-level badge communicates. Surface it as its own banner at the
  // top of the card whenever the RECOMMENDED route is the one flagged,
  // rather than only in the map popup where it could be missed.
  const boundaryBannerHtml = recommended.boundary_warning
    ? `<div class="route-boundary-banner">\u26a0\ufe0f MARITIME BOUNDARY WARNING: the recommended route comes within
       ${recommended.boundary_distance_km} km of India's EEZ boundary, even though its weather/sea-state risk is
       ${recommended.route_risk_level}. Exercise caution near international waters.</div>`
    : '';

  // Same reasoning, SEPARATE banner (Section 14o) - a Marine Protected
  // Area warning is an environmental/fishing-restriction concern, not a
  // territorial one, so it gets its own distinctly-colored banner rather
  // than being appended to or merged with the boundary banner above. Both
  // banners can appear together if a route is flagged for both.
  const mpaBannerHtml = recommended.mpa_warning === true
    ? `<div class="route-mpa-banner">\ud83c\udf3f MARINE PROTECTED AREA WARNING: the recommended route comes within
       ${recommended.mpa_distance_km} km of a protected conservation area, even though its weather/sea-state risk is
       ${recommended.route_risk_level}. Fishing may be restricted or banned in this area.</div>`
    : '';

  const card = document.createElement('div');
  card.className = 'risk-card'; // reuse existing card styling for visual consistency
  card.innerHTML = `
    ${overrideBannerHtml}
    ${boundaryBannerHtml}
    ${mpaBannerHtml}
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

  const container = document.getElementById(containerId);
  if (containerId === 'messages') {
    container.appendChild(card);
    container.scrollTop = container.scrollHeight;
  } else {
    container.innerHTML = ''; // dedicated result area - replace, don't accumulate
    container.appendChild(card);
  }
}

// ---------- Main query flow ----------
async function sendQuery() {
  const input = document.getElementById('query-input');
  const query = input.value.trim();
  if (!query) return;

  addMessage(query, 'user');
  input.value = '';

  // Client-side timeout via AbortController. Set ABOVE the backend's own
  // 30s Gemini timeout (35s here) so a legitimate slow-but-successful
  // Gemini call never gets cut off by the client - this only protects
  // against a genuine hang (dead server, network issue), not normal
  // Gemini latency.
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

    if (data.error) {
      addMessage(data.answer, 'bot');
      speak(data.answer, data.language);
      // Clear any stale route visuals from a previous successful route
      // query - otherwise an old route line would linger on screen while
      // showing an unrelated error for the current query.
      clearRouteLayers();
      return;
    }

    addMessage(data.answer, 'bot', data.risk_level);
    speak(data.answer, data.language);

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

    // Guard: data.map is null for the "no location_data" response shape
    // (a pure policy question or a greeting/help message - see
    // PROJECT_CONTEXT.md Section 14h/14r) - there's genuinely no
    // location to show on the map for these, unlike the pfz-may-be-null
    // case below which still has a real user location. Found as a real
    // bug while testing the new greeting/help feature: without this
    // guard, "hello" got a correct onboarding answer bubble immediately
    // followed by a bogus second "Could not reach the backend" bubble,
    // because this code unconditionally read data.map.user_location and
    // threw, landing in the catch block below.
    if (data.map) {
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
    }

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
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      addMessage("This is taking longer than expected (over 35s) - the server might be busy or unreachable. Please try again in a moment.", 'bot');
    } else {
      addMessage("Could not reach the backend. Is it running on localhost:8000?", 'bot');
    }
  }
}