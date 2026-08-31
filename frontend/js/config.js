// ---------- Shared configuration and helpers ----------
// Loaded FIRST - map.js and chat.js both depend on these constants.

const API_URL = "http://localhost:8000/ask";
const ZONES_URL = "http://localhost:8000/zones";

const LEVEL_EMOJIS = { LOW: '🟢', MODERATE: '🟡', HIGH: '🟠', CRITICAL: '🔴' };

const STAKEHOLDER_DASHBOARD_TITLES = {
  fisherman: '🎣 ORCA Fishing Safety',
  coast_guard: '🛟 ORCA Maritime Risk',
  disaster_management: '🚨 ORCA Disaster Risk',
  general: '📊 ORCA Risk Analysis',
};

function levelColor(level) {
  switch (level) {
    case 'CRITICAL': return '#dc3545';
    case 'HIGH': return '#fd7e14';
    case 'MODERATE': return '#ffc107';
    default: return '#28a745'; // LOW
  }
}

function scoreToColor(score) {
  if (score >= 75) return '#dc3545'; // red
  if (score >= 50) return '#fd7e14'; // orange
  if (score >= 25) return '#ffc107'; // yellow
  return '#28a745'; // green
}
