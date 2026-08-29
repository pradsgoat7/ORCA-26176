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
      return;
    }

    addMessage(data.answer, 'bot', data.risk_level);

    // Phase 6: render the stakeholder-specific risk dashboard, if present
    // (it won't be, on the error path, since risk is null there).
    if (data.risk && data.stakeholder) {
      renderRiskCard(data.stakeholder, data.risk);
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

  } catch (err) {
    addMessage("Could not reach the backend. Is it running on localhost:8000?", 'bot');
  }
}