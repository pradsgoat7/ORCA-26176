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
