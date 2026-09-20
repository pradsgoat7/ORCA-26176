// ---------- Knowledge Base tab (Section 14q) ----------
// Depends on config.js (API_URL) - must load before tabs.js. Calls the
// SAME /ask endpoint as everything else - no new backend work. The one
// genuinely NEW thing here is displaying policy_answer.sources (document
// title + page number): that field already existed in the API response
// since the policy RAG feature was built, but no UI ever rendered it
// until now - see PROJECT_CONTEXT.md Section 14q.

async function submitKnowledgeBaseQuery(customQuery) {
  const input = document.getElementById('kb-input');
  const query = (customQuery !== undefined ? customQuery : input.value).trim();
  if (!query) return;
  input.value = query;

  const resultEl = document.getElementById('kb-result');
  resultEl.innerHTML = '<div class="kb-loading">Searching the knowledge base…</div>';

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
    renderKnowledgeBaseResult(query, data);
  } catch (err) {
    clearTimeout(timeoutId);
    const message = (err.name === 'AbortError')
      ? 'This is taking longer than expected (over 35s) - please try again.'
      : 'Could not reach the backend. Is it running on localhost:8000?';
    resultEl.innerHTML = `<div class="kb-error">${message}</div>`;
  }
}

function askKnowledgeBaseExample(text) {
  document.getElementById('kb-input').value = text;
  submitKnowledgeBaseQuery(text);
}

function renderKnowledgeBaseResult(query, data) {
  const resultEl = document.getElementById('kb-result');

  // A pure policy question with no location deliberately has NO top-level
  // "error" (Section 14h) - but a genuinely malformed query still could.
  if (data.error && !data.policy_answer) {
    resultEl.innerHTML = `<div class="kb-error">${data.answer || data.error}</div>`;
    return;
  }

  if (!data.policy_answer) {
    // Honest, not a fabricated answer - policy_detection.py's keyword
    // rules (Section 14h/14k/14m) didn't recognize this as a policy
    // question, so it was never routed to the document-retrieval path.
    resultEl.innerHTML = `
      <div class="kb-no-match">
        ORCA didn't recognize this as a policy or safety-practices question, so it wasn't answered
        from the document library. Try mentioning something like "why", "regulation", "ban",
        "safety equipment", or "best practices".
      </div>`;
    return;
  }

  const pa = data.policy_answer;

  const modeNote = pa.mode === 'fallback_raw_chunks'
    ? '<div class="kb-mode-note">⚠️ AI summarization was unavailable for this answer — showing the raw retrieved document text below, unprocessed.</div>'
    : pa.mode === 'no_index_or_no_results'
      ? '<div class="kb-mode-note">⚠️ The document index was unavailable for this query.</div>'
      : '';

  // Sources - genuinely NEW UI (Section 14q). This data (document title +
  // page number) already existed in every policy_answer response, it just
  // was never displayed anywhere before now.
  const sourcesHtml = (pa.sources || []).map(s => `
    <li class="kb-source-item">
      <span class="kb-source-title">${s.title}</span>
      <span class="kb-source-page">page ${s.page}</span>
      ${s.source_url ? `<a class="kb-source-link" href="${s.source_url}" target="_blank" rel="noopener">View source ↗</a>` : ''}
    </li>
  `).join('');

  resultEl.innerHTML = `
    <div class="kb-answer-card">
      <div class="kb-answer-query">"${query}"</div>
      ${modeNote}
      <div class="kb-answer-text">${pa.answer}</div>
      ${sourcesHtml ? `<div class="kb-sources-title">📚 Sources</div><ul class="kb-sources-list">${sourcesHtml}</ul>` : ''}
    </div>
  `;
}
