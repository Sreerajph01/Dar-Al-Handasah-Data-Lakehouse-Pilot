/*
uc1-search/ui/app.js
Client application logic for Dar Al-Handasah Search & RAG UI
*/

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const searchInput = document.getElementById('search-input');
  const btnSearch = document.getElementById('btn-search');
  const hybridToggle = document.getElementById('hybrid-toggle');
  const personaSelect = document.getElementById('persona-select');
  const resultsContainer = document.getElementById('results-container');
  const searchStats = document.getElementById('search-stats');
  const btnResetFilters = document.getElementById('btn-reset-filters');
  const btnTriggerIngest = document.getElementById('btn-trigger-ingest');

  // RAG DOM Elements
  const ragInput = document.getElementById('rag-input');
  const btnAskRag = document.getElementById('btn-ask-rag');
  const ragChatHistory = document.getElementById('rag-chat-history');

  // Modal DOM Elements
  const docModal = document.getElementById('doc-modal');
  const modalClose = document.getElementById('modal-close');
  const modalTitle = document.getElementById('modal-title');
  const modalBadge = document.getElementById('modal-badge');
  const modalMetaGrid = document.getElementById('modal-meta-grid');
  const modalContentText = document.getElementById('modal-content-text');

  // State
  let activeProject = '';
  let activeDiscipline = '';
  let activeDocType = '';

  // Setup Chips
  function setupChipGroup(containerId, stateSetter) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const chips = container.querySelectorAll('.chip');
    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        chips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        stateSetter(chip.getAttribute(`data-${containerId.replace('-chips', '')}`));
        executeSearch();
      });
    });
  }

  setupChipGroup('project-chips', val => activeProject = val);
  setupChipGroup('discipline-chips', val => activeDiscipline = val);
  setupChipGroup('doctype-chips', val => activeDocType = val);

  // Search Function
  async function executeSearch() {
    const query = searchInput.value.trim() || '*';
    const activePersona = personaSelect.value;
    const isHybrid = hybridToggle.checked;

    searchStats.textContent = `Querying OpenSearch... (Persona: ${activePersona})`;

    const params = new URLSearchParams({
      q: query,
      hybrid: isHybrid,
      limit: '20'
    });
    if (activeProject) params.append('project', activeProject);
    if (activeDiscipline) params.append('discipline', activeDiscipline);
    if (activeDocType) params.append('doc_type', activeDocType);

    try {
      const resp = await fetch(`/v1/search/query?${params.toString()}`, {
        headers: {
          'X-User-Role': activePersona
        }
      });

      if (!resp.ok) {
        throw new Error(`HTTP Error: ${resp.status}`);
      }

      const data = await resp.json();
      renderResults(data);
    } catch (err) {
      console.error('Search failed:', err);
      resultsContainer.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">⚠️</div>
          <h3>Search Service Unavailable</h3>
          <p>Could not connect to OpenSearch or Search API: ${err.message}</p>
        </div>
      `;
      searchStats.textContent = 'Error connecting to search service';
    }
  }

  function getFormatBadgeClass(docType) {
    if (docType.includes('CAD')) return 'badge-cad';
    if (docType.includes('BIM')) return 'badge-bim';
    if (docType.includes('Correspondence')) return 'badge-email';
    return 'badge-spec';
  }

  function renderResults(data) {
    searchStats.textContent = `Found ${data.total} documents in ${data.query_ms} ms (Role: ${data.active_role})`;

    if (!data.results || data.results.length === 0) {
      resultsContainer.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔒</div>
          <h3>No Documents Found or Access Restricted</h3>
          <p>No files matched your filters or your current persona (<strong>${data.active_role}</strong>) does not have clearance to view them.</p>
        </div>
      `;
      return;
    }

    resultsContainer.innerHTML = data.results.map(doc => {
      const badgeClass = getFormatBadgeClass(doc.doc_type);
      const highlightSnippet = doc.highlights && doc.highlights.length > 0
        ? doc.highlights.join(' ... ')
        : doc.content_snippet;

      return `
        <div class="result-card" data-doc-id="${doc.doc_id}">
          <div class="result-top-row">
            <div class="result-title-group">
              <span class="doc-format-badge ${badgeClass}">${doc.doc_type}</span>
              <h3 class="result-title">${doc.title}</h3>
            </div>
            <span class="result-score">score: ${doc.score.toFixed(3)}</span>
          </div>

          <div class="result-tags">
            <span class="tag">📁 ${doc.project_code}</span>
            <span class="tag">📐 ${doc.discipline}</span>
            ${doc.doc_id.includes('Confidential') || doc.title.toLowerCase().includes('agreement') ? '<span class="pii-badge">🛡️ PII Scanned & Redacted</span>' : ''}
          </div>

          <div class="result-snippet">${highlightSnippet}</div>
        </div>
      `;
    }).join('');

    // Attach click listeners to cards
    document.querySelectorAll('.result-card').forEach(card => {
      card.addEventListener('click', () => {
        const docId = card.getAttribute('data-doc-id');
        openDocModal(docId);
      });
    });
  }

  // Document Detail Modal
  async function openDocModal(docId) {
    try {
      const resp = await fetch(`/v1/search/${docId}`);
      if (!resp.ok) throw new Error('Failed to load document details');
      const doc = await resp.json();

      modalTitle.textContent = doc.file_name;
      modalBadge.textContent = doc.doc_type;
      modalBadge.className = `badge ${getFormatBadgeClass(doc.doc_type)}`;

      modalMetaGrid.innerHTML = `
        <div><strong>Project:</strong> ${doc.project_code}</div>
        <div><strong>Discipline:</strong> ${doc.discipline}</div>
        <div><strong>Doc ID:</strong> ${doc.doc_id.substring(0, 10)}...</div>
        <div><strong>Total Chunks:</strong> ${doc.total_chunks}</div>
        <div><strong>Allowed Roles:</strong> ${(doc.allowed_roles || []).join(', ')}</div>
        <div><strong>PII Redactions:</strong> ${doc.pii_redacted_count || 0}</div>
      `;

      modalContentText.textContent = doc.full_content || 'No text extracted.';
      docModal.classList.remove('hidden');
    } catch (err) {
      alert(`Error loading document: ${err.message}`);
    }
  }

  modalClose.addEventListener('click', () => docModal.classList.add('hidden'));
  docModal.addEventListener('click', (e) => {
    if (e.target === docModal) docModal.classList.add('hidden');
  });

  // RAG Assistant Function
  async function askRAG(questionText) {
    const q = questionText || ragInput.value.trim();
    if (!q) return;

    // Append User Message
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-message user-message';
    userMsg.textContent = q;
    ragChatHistory.appendChild(userMsg);
    ragInput.value = '';
    ragChatHistory.scrollTop = ragChatHistory.scrollHeight;

    // Append Loading Placeholder
    const loadingMsg = document.createElement('div');
    loadingMsg.className = 'chat-message assistant-message';
    loadingMsg.innerHTML = '<p><em>Consulting project repository & local LLM (Qwen2.5-7B)...</em></p>';
    ragChatHistory.appendChild(loadingMsg);
    ragChatHistory.scrollTop = ragChatHistory.scrollHeight;

    const activePersona = personaSelect.value;
    try {
      const resp = await fetch('/v1/search/rag', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Role': activePersona
        },
        body: JSON.stringify({
          question: q,
          project: activeProject || null,
          discipline: activeDiscipline || null,
          top_k: 4
        })
      });

      if (!resp.ok) throw new Error(`HTTP Error ${resp.status}`);
      const data = await resp.json();

      let citationHtml = '';
      if (data.citations && data.citations.length > 0) {
        citationHtml = `
          <div class="citation-list">
            <strong>Source Citations:</strong>
            ${data.citations.map(c => `
              <div class="citation-item">📄 ${c.title} (${c.project_code} • ${c.discipline})</div>
            `).join('')}
          </div>
        `;
      }

      loadingMsg.innerHTML = `
        <p>${data.answer.replace(/\n/g, '<br>')}</p>
        ${citationHtml}
        <div style="font-size: 0.7rem; color: var(--text-dim); margin-top: 6px;">
          Generated in ${data.latency_ms} ms via local Ollama
        </div>
      `;
    } catch (err) {
      loadingMsg.innerHTML = `<p style="color: var(--accent-red)">Failed to generate answer: ${err.message}</p>`;
    }
    ragChatHistory.scrollTop = ragChatHistory.scrollHeight;
  }

  // Event Listeners
  btnSearch.addEventListener('click', executeSearch);
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') executeSearch();
  });

  personaSelect.addEventListener('change', () => {
    executeSearch();
  });

  hybridToggle.addEventListener('change', executeSearch);

  btnResetFilters.addEventListener('click', () => {
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.chip-container').forEach(cont => {
      cont.querySelector('.chip').classList.add('active');
    });
    activeProject = '';
    activeDiscipline = '';
    activeDocType = '';
    searchInput.value = '';
    executeSearch();
  });

  btnAskRag.addEventListener('click', () => askRAG());
  ragInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      askRAG();
    }
  });

  // Suggested Queries in RAG Drawer
  document.querySelectorAll('.suggest-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const q = btn.getAttribute('data-q');
      askRAG(q);
    });
  });

  // Sync / Ingest Trigger
  btnTriggerIngest.addEventListener('click', async () => {
    btnTriggerIngest.disabled = true;
    btnTriggerIngest.textContent = 'Syncing...';
    try {
      const resp = await fetch('/v1/ingest/run', { method: 'POST' });
      const data = await resp.json();
      alert(`Sync triggered: ${data.message}`);
      setTimeout(executeSearch, 2000);
    } catch (err) {
      alert(`Sync error: ${err.message}`);
    } finally {
      btnTriggerIngest.disabled = false;
      btnTriggerIngest.textContent = '⚡ Sync / Ingest';
    }
  });

  // Initial Search
  executeSearch();
});
