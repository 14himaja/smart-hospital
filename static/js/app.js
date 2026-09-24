/**
 * ApolloCare Smart Hospital AI — ChatGPT-Style Frontend
 * Full-screen chat with sidebar, slot picker, file upload, markdown rendering,
 * and dedicated Admin Operations Portal.
 */

// ============================================================
// STATE
// ============================================================
const state = {
  currentUser: { user_id: 'P1001', name: 'Rahul Sharma', email: 'rahul@example.com', role: 'patient', token: null },
  sessionId: `WEB-P1001-${Math.random().toString(36).substring(2,8)}`,
  activeAgent: 'hospital_root_agent',
  departments: [],
  doctors: [],
  pendingFiles: [],
  conversations: [{ id: 'current', title: 'Current Session', time: 'Now', messages: [] }],
  activeConvId: 'current',
  selectedDocForModal: null,
  currentReportsFilter: 'all',
  cachedReports: []
};

const PRESEEDED = {
  P1001: { user_id:'P1001', name:'Rahul Sharma', email:'rahul@example.com', password:'password123', role:'patient' },
  P1002: { user_id:'P1002', name:'Priya Patel', email:'priya@example.com', password:'password123', role:'patient' },
  A4001: { user_id:'A4001', name:'Hospital Administrator', email:'admin@hospital.org', password:'adminpass123', role:'admin' }
};

// ============================================================
// DOM REFS
// ============================================================
const $ = id => document.getElementById(id);
const sidebar       = $('sidebar');
const menuBtn       = $('menuBtn');
const sidebarToggle = $('sidebarToggle');
const newChatBtn    = $('newChatBtn');
const convList      = $('conversationList');
const chatMessages  = $('chatMessages');
const welcomeScreen = $('welcomeScreen');
const chatInput     = $('chatInput');
const sendBtn       = $('sendBtn');
const activeAgentBadge = $('activeAgentBadge');
const clearChatBtn  = $('clearChatBtn');
const quickChipsRow = $('quickChipsRow');
const slotPickerPanel = $('slotPickerPanel');
const slotDeptTabs  = $('slotDeptTabs');
const slotDoctorsList = $('slotDoctorsList');
const closeSlotPanel = $('closeSlotPanel');
const slotPickerBtn = $('slotPickerBtn');
const attachBtn     = $('attachBtn');
const fileInput     = $('fileInput');
const uploadPreviewStrip = $('uploadPreviewStrip');
const uploadPreviews = $('uploadPreviews');
const patientNameDisplay = $('patientNameDisplay');
const patientIdDisplay   = $('patientIdDisplay');
const patientAvatarSidebar = $('patientAvatarSidebar');
const openAuthBtn   = $('openAuthBtn');
const authModal     = $('authModal');
const closeAuthModal = $('closeAuthModal');
const authForm      = $('authForm');
const authEmail     = $('authEmail');
const authPassword  = $('authPassword');
const authName      = $('authName');
const authFeedback  = $('authFeedback');
const authRegisterBtn = $('authRegisterBtn');
const docViewModal  = $('docViewModal');
const closeDocViewModal  = $('closeDocViewModal');
const closeDocViewModal2 = $('closeDocViewModal2');
const askAiDocBtn   = $('askAiDocBtn');
const agentDot      = $('agentDot');

// Right-Side Patient Lab Reports Sidebar
const reportsSidebar          = $('reportsSidebar');
const toggleReportsSidebarBtn = $('toggleReportsSidebarBtn');
const closeReportsSidebarBtn  = $('closeReportsSidebarBtn');
const refreshReportsBtn       = $('refreshReportsBtn');
const patientReportsList      = $('patientReportsList');
const reportsFilterRow        = $('reportsFilterRow');
const sidebarUploadReportBtn  = $('sidebarUploadReportBtn');
const sidebarReportFileInput  = $('sidebarReportFileInput');
const reportsCountBadge       = $('reportsCountBadge');
const countFilterAll          = $('countFilterAll');
const countFilterLab          = $('countFilterLab');
const countFilterRx           = $('countFilterRx');

// Portal and Admin views
const portalSelectModal     = $('portalSelectModal');
const closePortalSelectModal = $('closePortalSelectModal');
const selectPatientPortalBtn = $('selectPatientPortalBtn');
const selectAdminPortalBtn   = $('selectAdminPortalBtn');
const adminAuthModal        = $('adminAuthModal');
const closeAdminAuthModal   = $('closeAdminAuthModal');
const adminAuthForm         = $('adminAuthForm');
const adminAuthEmail        = $('adminAuthEmail');
const adminAuthPassword     = $('adminAuthPassword');
const adminAuthFeedback     = $('adminAuthFeedback');
const adminDashboardView    = $('adminDashboardView');
const adminLogoutBtn        = $('adminLogoutBtn');
const chatMain              = document.querySelector('main.chat-main');

function initTheme() {
  const savedTheme = localStorage.getItem('apollocare_theme') || 'cream';
  setTheme(savedTheme);
}

function setTheme(theme) {
  const themeBtn = $('themeToggleBtn');
  const adminThemeBtn = $('adminThemeToggleBtn');
  if (theme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    if (themeBtn) themeBtn.textContent = '🍦';
    if (adminThemeBtn) adminThemeBtn.textContent = '🍦';
    localStorage.setItem('apollocare_theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
    if (themeBtn) themeBtn.textContent = '🌙';
    if (adminThemeBtn) adminThemeBtn.textContent = '🌙';
    localStorage.setItem('apollocare_theme', 'cream');
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  if (current === 'dark') {
    setTheme('cream');
  } else {
    setTheme('dark');
  }
}

// Initialize theme immediately
initTheme();

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  setupEventListeners();
  setupAdminNavigation();
  await loadHospitalData();
  
  // Show initial portal selector
  showModal(portalSelectModal);
});

// ============================================================
// EVENT LISTENERS
// ============================================================
function setupEventListeners() {
  // Theme toggle
  const themeToggleBtn = $('themeToggleBtn');
  if (themeToggleBtn) themeToggleBtn.addEventListener('click', toggleTheme);
  const adminThemeToggleBtn = $('adminThemeToggleBtn');
  if (adminThemeToggleBtn) adminThemeToggleBtn.addEventListener('click', toggleTheme);

  // Sidebar toggle
  if (menuBtn) menuBtn.addEventListener('click', toggleSidebar);
  if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);

  // New chat
  if (newChatBtn) newChatBtn.addEventListener('click', () => startNewConversation());

  // Chat input auto-resize & send enable
  if (chatInput) {
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 200) + 'px';
      sendBtn.disabled = chatInput.value.trim() === '' && state.pendingFiles.length === 0;
    });
    chatInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
    });
  }
  if (sendBtn) sendBtn.addEventListener('click', handleSend);
  if (clearChatBtn) clearChatBtn.addEventListener('click', clearChat);

  // Quick chips
  if (quickChipsRow) {
    quickChipsRow.addEventListener('click', e => {
      const chip = e.target.closest('.qchip');
      if (!chip) return;
      const prompt = chip.dataset.prompt;
      if (chip.id === 'slotChip') {
        toggleSlotPanel(true);
      } else {
        sendMessage(prompt);
      }
    });
  }

  // Welcome suggestion cards
  if (chatMessages) {
    chatMessages.addEventListener('click', e => {
      const card = e.target.closest('.suggestion-card');
      if (card) sendMessage(card.dataset.prompt);
    });
  }

  // Slot picker
  if (slotPickerBtn) slotPickerBtn.addEventListener('click', () => toggleSlotPanel());
  if (closeSlotPanel) closeSlotPanel.addEventListener('click', () => toggleSlotPanel(false));

  const refreshAppointmentsBtn = $('refreshAppointmentsBtn');
  if (refreshAppointmentsBtn) refreshAppointmentsBtn.addEventListener('click', () => loadUserAppointmentsSidebar());

  // Right-Side Lab Reports Sidebar Controls
  if (toggleReportsSidebarBtn) toggleReportsSidebarBtn.addEventListener('click', () => toggleReportsSidebar());
  if (closeReportsSidebarBtn) closeReportsSidebarBtn.addEventListener('click', () => toggleReportsSidebar(false));
  if (refreshReportsBtn) refreshReportsBtn.addEventListener('click', () => loadUserLabReports());

  if (reportsFilterRow) {
    reportsFilterRow.addEventListener('click', e => {
      const btn = e.target.closest('.report-filter-btn');
      if (!btn) return;
      reportsFilterRow.querySelectorAll('.report-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentReportsFilter = btn.dataset.filter || 'all';
      renderUserLabReports();
    });
  }

  if (sidebarUploadReportBtn && sidebarReportFileInput) {
    sidebarUploadReportBtn.addEventListener('click', () => sidebarReportFileInput.click());
    sidebarReportFileInput.addEventListener('change', async () => {
      const files = Array.from(sidebarReportFileInput.files);
      if (!files || files.length === 0) return;
      sidebarUploadReportBtn.disabled = true;
      sidebarUploadReportBtn.innerHTML = '<span>⏳</span> Uploading & Analyzing...';
      const prompt = `[Attached: ${files.map(f => f.name).join(', ')}] Please analyze this medical document / lab report and explain the clinical findings and medicines.`;
      appendUserMessage(prompt, files);
      await sendToBackend(prompt, files);
      sidebarReportFileInput.value = '';
      sidebarUploadReportBtn.disabled = false;
      sidebarUploadReportBtn.innerHTML = '<span style="font-size:1rem">📤</span> Upload Lab Report / Prescription';
      await loadUserLabReports();
    });
  }

  // File upload
  if (attachBtn) attachBtn.addEventListener('click', () => fileInput.click());
  if (fileInput) fileInput.addEventListener('change', handleFileSelect);

  // Patient Auth modal
  if (openAuthBtn) openAuthBtn.addEventListener('click', () => showModal(authModal));
  if (closeAuthModal) closeAuthModal.addEventListener('click', () => {
    hideModal(authModal);
    showModal(portalSelectModal);
  });
  if (authModal) authModal.addEventListener('click', e => {
    if (e.target === authModal) {
      hideModal(authModal);
      showModal(portalSelectModal);
    }
  });
  if (authForm) authForm.addEventListener('submit', handleLogin);
  if (authRegisterBtn) authRegisterBtn.addEventListener('click', handleRegister);
  
  document.querySelectorAll('.qpatient-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      hideModal(authModal);
      await switchToPatientMode(btn.dataset.id);
    });
  });

  // Role Portal Selector modal
  if (selectPatientPortalBtn) {
    selectPatientPortalBtn.addEventListener('click', () => {
      hideModal(portalSelectModal);
      showModal(authModal);
    });
  }
  if (selectAdminPortalBtn) {
    selectAdminPortalBtn.addEventListener('click', () => {
      hideModal(portalSelectModal);
      showModal(adminAuthModal);
    });
  }
  if (closePortalSelectModal) {
    closePortalSelectModal.addEventListener('click', () => {
      hideModal(portalSelectModal);
    });
  }

  // Admin Auth modal
  if (closeAdminAuthModal) closeAdminAuthModal.addEventListener('click', () => {
    hideModal(adminAuthModal);
    showModal(portalSelectModal);
  });
  if (adminAuthModal) adminAuthModal.addEventListener('click', e => {
    if (e.target === adminAuthModal) {
      hideModal(adminAuthModal);
      showModal(portalSelectModal);
    }
  });
  if (adminAuthForm) adminAuthForm.addEventListener('submit', handleAdminLogin);

  // Admin Logout / Switch Portal button
  if (adminLogoutBtn) {
    adminLogoutBtn.addEventListener('click', () => {
      adminDashboardView.style.display = 'none';
      showModal(portalSelectModal);
    });
  }
  const patientSwitchPortalBtn = $('patientSwitchPortalBtn');
  if (patientSwitchPortalBtn) {
    patientSwitchPortalBtn.addEventListener('click', () => {
      showModal(portalSelectModal);
    });
  }

  // Chunk Inspector modal
  const closeChunkInspector = $('closeChunkInspector');
  if (closeChunkInspector) closeChunkInspector.addEventListener('click', () => hideModal($('chunkInspectorModal')));
  const chunkInspectorModal = $('chunkInspectorModal');
  if (chunkInspectorModal) chunkInspectorModal.addEventListener('click', e => { if (e.target === chunkInspectorModal) hideModal(chunkInspectorModal); });

  // Admin File Input Change Listener
  const adminDocFileInput = $('adminDocFileInput');
  if (adminDocFileInput) {
    adminDocFileInput.addEventListener('change', () => {
      const file = adminDocFileInput.files[0];
      if (file) {
        if ($('adminFileInfo')) $('adminFileInfo').textContent = `Selected: ${file.name} (${(file.size/1024).toFixed(1)} KB)`;
        if ($('adminDocTitle') && !$('adminDocTitle').value.trim()) {
          const defaultTitle = file.name.replace(/\.[^/.]+$/, "").replace(/_/g, " ").replace(/-/g, " ");
          $('adminDocTitle').value = defaultTitle;
        }
      }
    });
  }

  // Admin Upload form
  const adminUploadForm = $('adminUploadForm');
  if (adminUploadForm) {
    adminUploadForm.addEventListener('submit', async e => {
      e.preventDefault();
      const title = $('adminDocTitle').value.trim();
      const category = $('adminDocCategory').value.trim() || 'General Guidelines';
      const content = $('adminDocContent').value.trim();
      const fileInput = $('adminDocFileInput');
      const file = fileInput && fileInput.files ? fileInput.files[0] : null;

      if (!content && !file) {
        alert('Please either paste document content OR attach a document file (PDF/TXT).');
        return;
      }

      const btn = $('adminUploadBtn');
      btn.disabled = true;
      btn.textContent = '⏳ Extracting & Processing RAG Chunks...';

      try {
        const formData = new FormData();
        if (title) formData.append('title', title);
        formData.append('category', category);
        if (content) formData.append('content', content);
        if (file) formData.append('file', file);

        const headers = { 'Authorization': `Bearer ${state.currentUser.token}` };
        const res = await fetch('/api/admin/documents/upload', {
          method: 'POST',
          headers,
          body: formData
        });

        if (res.ok) {
          const data = await res.json();
          $('adminDocTitle').value = '';
          $('adminDocCategory').value = '';
          $('adminDocContent').value = '';
          if (fileInput) fileInput.value = '';
          if ($('adminFileInfo')) $('adminFileInfo').textContent = 'Optional - Attach PDF or Text document';
          alert(`✓ Document successfully processed into ${data.document.chunk_count} RAG chunks!`);
          await loadAdminStats();
          await loadAdminDocuments();
        } else {
          const err = await res.json();
          alert(`Upload failed: ${err.detail || 'Unable to process document'}`);
        }
      } catch (err) {
        alert('Connection error uploading document.');
      } finally {
        btn.disabled = false;
        btn.textContent = '🚀 Upload & Process Document';
      }
    });
  }

  // Admin Clean Duplicates Button
  const adminCleanDocsBtn = $('adminCleanDocsBtn');
  if (adminCleanDocsBtn) {
    adminCleanDocsBtn.addEventListener('click', async () => {
      if (!confirm('Clean duplicate test documents in database?')) return;
      try {
        const headers = { 'Authorization': `Bearer ${state.currentUser.token}` };
        const res = await fetch('/api/admin/documents', { headers });
        if (res.ok) {
          const data = await res.json();
          const seen = new Set();
          for (const doc of data.documents) {
            if (seen.has(doc.title)) {
              await fetch(`/api/admin/documents/${doc.id}`, { method: 'DELETE', headers });
            } else {
              seen.add(doc.title);
            }
          }
          await loadAdminStats();
          await loadAdminDocuments();
          alert('✓ Duplicate test documents cleaned successfully.');
        }
      } catch (err) {
        alert('Failed to clean duplicate documents.');
      }
    });
  }

  // Edit Document Modal Listeners
  const editDocModal = $('editDocModal');
  const closeEditDocModal = $('closeEditDocModal');
  const cancelEditDocBtn = $('cancelEditDocBtn');
  const editDocForm = $('editDocForm');

  if (closeEditDocModal) closeEditDocModal.addEventListener('click', () => hideModal(editDocModal));
  if (cancelEditDocBtn) cancelEditDocBtn.addEventListener('click', () => hideModal(editDocModal));
  if (editDocModal) editDocModal.addEventListener('click', e => { if (e.target === editDocModal) hideModal(editDocModal); });

  if (editDocForm) {
    editDocForm.addEventListener('submit', async e => {
      e.preventDefault();
      const docId = $('editDocId').value;
      const title = $('editDocTitleInput').value.trim();
      const category = $('editDocCategoryInput').value.trim();
      const content = $('editDocContentInput').value.trim();

      if (!docId || !title) {
        alert('Please provide a document title.');
        return;
      }

      try {
        const headers = {
          'Authorization': `Bearer ${state.currentUser.token}`,
          'Content-Type': 'application/json'
        };
        const res = await fetch(`/api/admin/documents/${docId}`, {
          method: 'PUT',
          headers,
          body: JSON.stringify({ title, category, content })
        });

        if (res.ok) {
          hideModal(editDocModal);
          alert('✓ Document title & details updated successfully!');
          await loadAdminStats();
          await loadAdminDocuments();
        } else {
          const err = await res.json();
          alert(`Update failed: ${err.detail || 'Error updating document'}`);
        }
      } catch (err) {
        alert('Connection error updating document.');
      }
    });
  }

  // Doc modal
  if (closeDocViewModal) closeDocViewModal.addEventListener('click', () => hideModal(docViewModal));
  if (closeDocViewModal2) closeDocViewModal2.addEventListener('click', () => hideModal(docViewModal));
  if (docViewModal) docViewModal.addEventListener('click', e => { if (e.target === docViewModal) hideModal(docViewModal); });
  if (askAiDocBtn) {
    askAiDocBtn.addEventListener('click', () => {
      hideModal(docViewModal);
      sendMessage(`Please explain the contents of the medical document: "${state.selectedDocForModal?.title}"`);
    });
  }
}

// ============================================================
// ADMIN CONSOLE NAVIGATION & TAB SWITCHING
// ============================================================
function setupAdminNavigation() {
  const tabs = [
    { btn: $('adminTabDocs'), sec: $('adminSecDocs'), action: () => { loadAdminStats(); loadAdminDocuments(); } },
    { btn: $('adminTabPatients'), sec: $('adminSecPatients'), action: () => loadAdminPatientsTable() },
    { btn: $('adminTabAppts'), sec: $('adminSecAppts'), action: () => loadAdminAppointmentsTable() }
  ];

  tabs.forEach(tab => {
    if (tab.btn && tab.sec) {
      tab.btn.addEventListener('click', () => {
        tabs.forEach(t => {
          if (t.btn) t.btn.classList.remove('active');
          if (t.sec) t.sec.style.display = 'none';
        });
        tab.btn.classList.add('active');
        tab.sec.style.display = (tab.sec.id === 'adminSecDocs') ? 'flex' : 'block';
        if (tab.sec.id === 'adminSecDocs') tab.sec.style.flexDirection = 'column';
        if (tab.action) tab.action();
      });
    }
  });

  const refreshApptsBtn = $('adminRefreshApptsBtn');
  if (refreshApptsBtn) {
    refreshApptsBtn.addEventListener('click', async () => {
      refreshApptsBtn.textContent = '⏳ Refreshing...';
      await loadAdminAppointmentsTable();
      await loadAdminStats();
      refreshApptsBtn.textContent = '🔄 Refresh Ledger';
    });
  }

  // Live admin portal sync when appointment is booked, completed, or cancelled
  window.addEventListener('appointmentUpdated', () => {
    if (adminDashboardView && adminDashboardView.style.display !== 'none') {
      loadAdminAppointmentsTable();
      loadAdminStats();
    }
  });

  // Background polling for admin appointments ledger
  setInterval(() => {
    if (adminDashboardView && adminDashboardView.style.display !== 'none') {
      const apptsSec = $('adminSecAppts');
      if (apptsSec && apptsSec.style.display !== 'none') {
        loadAdminAppointmentsTable();
      }
      loadAdminStats();
    }
  }, 10000);
}


// ============================================================
// MODE SWITCHING (PATIENT VS ADMIN)
// ============================================================
async function switchToPatientMode(patientId = 'P1001') {
  adminDashboardView.style.display = 'none';
  if (sidebar) sidebar.style.display = 'flex';
  if (chatMain) chatMain.style.display = 'flex';
  if (reportsSidebar) reportsSidebar.style.display = 'flex';
  if (toggleReportsSidebarBtn) toggleReportsSidebarBtn.style.display = 'inline-flex';

  // If currently authenticated as Admin or missing patient token, switch to requested patient account
  if (!state.currentUser.token || state.currentUser.role === 'admin' || state.currentUser.user_id === 'A4001') {
    await authenticatePatient(patientId);
  } else {
    updatePatientUI();
  }
}

async function switchToAdminMode() {
  if (sidebar) sidebar.style.display = 'none';
  if (chatMain) chatMain.style.display = 'none';
  if (reportsSidebar) reportsSidebar.style.display = 'none';
  if (toggleReportsSidebarBtn) toggleReportsSidebarBtn.style.display = 'none';
  adminDashboardView.style.display = 'flex';

  await loadAdminStats();
  await loadAdminDocuments();
}

// ============================================================
// SIDEBAR
// ============================================================
// ============================================================
// SIDEBAR & CHATGPT-STYLE CONVERSATION HISTORY
// ============================================================
function toggleSidebar() {
  sidebar.classList.toggle('collapsed');
}

function getConvStorageKey() {
  const userId = state.currentUser ? state.currentUser.user_id : 'guest';
  return `apollocare_conversations_${userId}`;
}

function loadConversations() {
  try {
    const stored = localStorage.getItem(getConvStorageKey());
    if (stored) {
      state.conversations = JSON.parse(stored);
    } else {
      state.conversations = [];
    }
  } catch (e) {
    state.conversations = [];
  }

  if (state.conversations.length === 0) {
    startNewConversation(true);
  } else {
    const active = state.conversations[0];
    state.activeConvId = active.id;
    state.sessionId = active.sessionId || `WEB-${state.currentUser.user_id}-${Math.random().toString(36).substring(2,8)}`;
    renderConversationList();
    loadConversationMessages(active);
  }
}

function saveConversations() {
  try {
    localStorage.setItem(getConvStorageKey(), JSON.stringify(state.conversations));
  } catch (err) {
    console.error('Error saving conversations:', err);
  }
}

function startNewConversation(silent = false) {
  const newId = `conv-${Date.now()}-${Math.random().toString(36).substring(2,6)}`;
  const userId = state.currentUser ? state.currentUser.user_id : 'P1001';
  const newSessionId = `WEB-${userId}-${Math.random().toString(36).substring(2,8)}`;

  const newConv = {
    id: newId,
    title: 'New Conversation',
    time: formatTime(new Date()),
    sessionId: newSessionId,
    messages: []
  };

  state.conversations.unshift(newConv);
  state.activeConvId = newId;
  state.sessionId = newSessionId;
  saveConversations();

  renderConversationList();

  chatMessages.querySelectorAll('.message-group').forEach(el => el.remove());
  if (welcomeScreen) welcomeScreen.style.display = 'flex';
  updateAgent('hospital_root_agent');

  if (!silent) {
    scrollToBottom();
  }
}

function switchConversation(convId) {
  const conv = state.conversations.find(c => c.id === convId);
  if (!conv) return;

  state.activeConvId = conv.id;
  state.sessionId = conv.sessionId || `WEB-${state.currentUser.user_id}-${conv.id}`;
  saveConversations();

  renderConversationList();
  loadConversationMessages(conv);
}

function deleteConversation(convId, e) {
  if (e) e.stopPropagation();

  state.conversations = state.conversations.filter(c => c.id !== convId);

  if (state.conversations.length === 0) {
    saveConversations();
    startNewConversation(false);
  } else {
    if (state.activeConvId === convId) {
      const nextConv = state.conversations[0];
      state.activeConvId = nextConv.id;
      state.sessionId = nextConv.sessionId;
      loadConversationMessages(nextConv);
    }
    saveConversations();
    renderConversationList();
  }
}

function renderConversationList() {
  if (!convList) return;

  if (state.conversations.length === 0) {
    convList.innerHTML = '<div style="font-size:0.75rem;color:var(--text-muted);padding:8px">No history yet</div>';
    return;
  }

  convList.innerHTML = state.conversations.map(c => `
    <div class="conv-item ${c.id === state.activeConvId ? 'active' : ''}" data-id="${c.id}">
      <span class="conv-icon">💬</span>
      <div class="conv-meta">
        <span class="conv-title">${escHtml(c.title)}</span>
        <span class="conv-time">${escHtml(c.time || '')}</span>
      </div>
      <button class="conv-delete-btn" data-id="${c.id}" title="Delete conversation">🗑️</button>
    </div>
  `).join('');

  convList.querySelectorAll('.conv-item').forEach(item => {
    item.addEventListener('click', (e) => {
      if (e.target.classList.contains('conv-delete-btn') || e.target.closest('.conv-delete-btn')) {
        return;
      }
      switchConversation(item.dataset.id);
    });
  });

  convList.querySelectorAll('.conv-delete-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      deleteConversation(btn.dataset.id, e);
    });
  });
}

function loadConversationMessages(conv) {
  chatMessages.querySelectorAll('.message-group').forEach(el => el.remove());

  if (!conv.messages || conv.messages.length === 0) {
    if (welcomeScreen) welcomeScreen.style.display = 'flex';
    return;
  }

  if (welcomeScreen) welcomeScreen.style.display = 'none';

  conv.messages.forEach(msg => {
    if (msg.role === 'user') {
      renderUserMessageDOM(msg.text, msg.files);
    } else if (msg.role === 'ai') {
      renderAiMessageDOM(msg.text, msg.agentName, msg.routeInfo, msg.requiresConf, msg.confDetails);
    }
  });

  scrollToBottom();
}

function recordUserMessageInActiveConv(text, files = []) {
  let conv = state.conversations.find(c => c.id === state.activeConvId);
  if (!conv) {
    startNewConversation(true);
    conv = state.conversations.find(c => c.id === state.activeConvId);
  }

  if (!conv.messages) conv.messages = [];

  const fileData = (files || []).map(f => ({ name: f.name }));
  conv.messages.push({ role: 'user', text, files: fileData });

  if (conv.title === 'New Conversation' || conv.title === 'Current Session') {
    const cleanText = text.replace(/\[Attached:.*?\]\n?/, '').trim();
    conv.title = cleanText.length > 26 ? cleanText.substring(0, 26) + '...' : (cleanText || 'Chat Session');
  }

  saveConversations();
  renderConversationList();
}

function recordAiMessageInActiveConv(text, agentName, routeInfo = null, requiresConf = false, confDetails = null) {
  let conv = state.conversations.find(c => c.id === state.activeConvId);
  if (!conv) return;

  if (!conv.messages) conv.messages = [];

  conv.messages.push({ role: 'ai', text, agentName, routeInfo, requiresConf, confDetails });
  saveConversations();
}

// ============================================================
// AUTH
// ============================================================
async function authenticatePatient(patientId) {
  const p = PRESEEDED[patientId];
  if (!p) return;
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: p.email, password: p.password })
    });
    if (res.ok) {
      const data = await res.json();
      state.currentUser = { ...p, token: data.access_token };
      updatePatientUI();
    }
  } catch (err) {
    state.currentUser = { ...p, token: 'mock-token' };
    updatePatientUI();
  }
}

async function loadUserAppointmentsSidebar() {
  const container = $('userAppointmentsList');
  if (!container) return;
  try {
    const headers = state.currentUser && state.currentUser.token ? { 'Authorization': `Bearer ${state.currentUser.token}` } : {};
    const res = await fetch('/api/hospital/appointments', { headers });
    if (res.ok) {
      const appts = await res.json();
      if (!appts || appts.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted); padding:6px 4px; font-size:0.75rem">No booked appointments yet.</div>';
        return;
      }
      container.innerHTML = appts.map(a => {
        const st = (a.status || '').toLowerCase();
        let color = '#10b981';
        let deleteBtn = '';
        if (st === 'cancelled') {
          color = '#ef4444';
          deleteBtn = `<button class="purge-appt-btn" data-id="${escHtml(a.id)}" data-status="${escHtml(st)}" title="Delete cancelled appointment record" style="background:none; border:none; color:var(--danger); cursor:pointer; font-size:0.8rem; padding:0 2px; margin-left:4px">🗑️</button>`;
        } else if (st === 'completed') {
          color = '#8b5cf6';
          deleteBtn = `<button class="purge-appt-btn" data-id="${escHtml(a.id)}" data-status="${escHtml(st)}" title="Delete completed appointment record" style="background:none; border:none; color:var(--danger); cursor:pointer; font-size:0.8rem; padding:0 2px; margin-left:4px">🗑️</button>`;
        }
        return `
          <div style="background:var(--bg-secondary); border:1px solid var(--border-subtle); border-radius:6px; padding:6px 8px; font-size:0.75rem">
            <div style="font-weight:700; color:var(--text-primary); display:flex; justify-content:space-between; align-items:center">
              <span>👨‍⚕️ ${escHtml(a.doctor_name)}</span>
              <div style="display:flex; align-items:center; gap:2px">
                <span style="color:${color}; font-weight:600">${escHtml(st)}</span>
                ${deleteBtn}
              </div>
            </div>
            <div style="color:var(--text-muted); font-size:0.7rem; margin-top:2px">
              🏥 ${escHtml(a.department_name || a.department || 'General')} · 📅 ${escHtml(a.date)} ${escHtml(a.time)}
            </div>
          </div>
        `;
      }).join('');

      container.querySelectorAll('.purge-appt-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          e.stopPropagation();
          const stLabel = btn.dataset.status || 'appointment';
          if (confirm(`Delete this ${stLabel} appointment record from your history?`)) {
            try {
              const headers = state.currentUser && state.currentUser.token ? { 'Authorization': `Bearer ${state.currentUser.token}` } : {};
              await fetch(`/api/hospital/appointments/${btn.dataset.id}/purge`, { method: 'DELETE', headers });
              await loadUserAppointmentsSidebar();
              window.dispatchEvent(new CustomEvent('appointmentUpdated'));
            } catch (err) {
              alert('Failed to delete appointment record.');
            }
          }
        });
      });
    }
  } catch (err) {
    container.innerHTML = '<div style="color:var(--danger); padding:4px; font-size:0.75rem">Error loading appointments.</div>';
  }
}

function updatePatientUI() {
  const u = state.currentUser;
  if (patientNameDisplay) patientNameDisplay.textContent = u.name;
  if (patientIdDisplay) patientIdDisplay.textContent = `${u.user_id} · ${capitalize(u.role)}`;
  if (patientAvatarSidebar) patientAvatarSidebar.textContent = u.name ? u.name.split(' ').map(n => n[0]).join('').substring(0,2) : 'U';

  loadConversations();
  loadUserAppointmentsSidebar();
  loadUserLabReports();
}

// ============================================================
// PATIENT LAB REPORTS & MEDICAL RECORDS (RIGHT SIDEBAR)
// ============================================================
function toggleReportsSidebar(forceState = null) {
  if (!reportsSidebar) return;
  if (forceState === true) {
    reportsSidebar.classList.remove('collapsed');
    if (toggleReportsSidebarBtn) toggleReportsSidebarBtn.classList.add('active');
  } else if (forceState === false) {
    reportsSidebar.classList.add('collapsed');
    if (toggleReportsSidebarBtn) toggleReportsSidebarBtn.classList.remove('active');
  } else {
    const isNowCollapsed = reportsSidebar.classList.toggle('collapsed');
    if (toggleReportsSidebarBtn) {
      if (isNowCollapsed) toggleReportsSidebarBtn.classList.remove('active');
      else toggleReportsSidebarBtn.classList.add('active');
    }
  }
}

async function loadUserLabReports() {
  if (!patientReportsList) return;
  try {
    const headers = state.currentUser && state.currentUser.token ? { 'Authorization': `Bearer ${state.currentUser.token}` } : {};
    const res = await fetch('/api/hospital/documents', { headers });
    if (res.ok) {
      const docs = await res.json();
      state.cachedReports = docs || [];
      updateReportsBadges();
      renderUserLabReports();
    } else {
      patientReportsList.innerHTML = '<div style="color:var(--text-muted); padding:16px; font-size:0.8rem; text-align:center">Unable to load records. Please log in.</div>';
    }
  } catch (err) {
    patientReportsList.innerHTML = '<div style="color:var(--danger); padding:16px; font-size:0.8rem; text-align:center">Connection error loading reports.</div>';
  }
}

function updateReportsBadges() {
  const docs = state.cachedReports || [];
  const labCount = docs.filter(d => d.document_type === 'laboratory_report').length;
  const rxCount = docs.filter(d => d.document_type === 'prescription').length;

  if (reportsCountBadge) reportsCountBadge.textContent = docs.length;
  if (countFilterAll) countFilterAll.textContent = docs.length;
  if (countFilterLab) countFilterLab.textContent = labCount;
  if (countFilterRx) countFilterRx.textContent = rxCount;
}

function renderUserLabReports() {
  if (!patientReportsList) return;
  const docs = state.cachedReports || [];
  const filter = state.currentReportsFilter || 'all';

  let filtered = docs;
  if (filter === 'laboratory_report') {
    filtered = docs.filter(d => d.document_type === 'laboratory_report');
  } else if (filter === 'prescription') {
    filtered = docs.filter(d => d.document_type === 'prescription');
  }

  if (filtered.length === 0) {
    patientReportsList.innerHTML = `
      <div style="text-align:center; padding:36px 16px; color:var(--text-muted)">
        <div style="font-size:2rem; margin-bottom:8px">🧪</div>
        <div style="font-weight:600; font-size:0.88rem; color:var(--text-primary)">No ${filter === 'all' ? 'Lab Reports' : filter.replace('_', ' ')} Found</div>
        <div style="font-size:0.75rem; margin-top:4px">Upload a lab report or prescription below to store and analyze it with AI.</div>
      </div>
    `;
    return;
  }

  patientReportsList.innerHTML = filtered.map(doc => {
    const isLab = doc.document_type === 'laboratory_report';
    const isRx = doc.document_type === 'prescription';
    const badgeClass = isLab ? 'badge-lab' : (isRx ? 'badge-rx' : 'badge-gen');
    const badgeLabel = isLab ? '🧪 Lab Report' : (isRx ? '💊 Prescription' : '📄 Document');
    const previewSummary = doc.summary || (doc.extracted_text ? doc.extracted_text.substring(0, 140) + '...' : 'No summary provided.');
    
    let findingsHtml = '';
    if (doc.key_findings && doc.key_findings.length > 0) {
      findingsHtml = `
        <div class="report-card-findings">
          ${doc.key_findings.slice(0, 3).map(f => `<span class="report-finding-tag">✓ ${escHtml(f)}</span>`).join('')}
        </div>
      `;
    }

    return `
      <div class="report-card" data-id="${escHtml(doc.id)}">
        <div class="report-card-header">
          <div class="report-card-title">${escHtml(doc.title)}</div>
          <span class="report-card-badge ${badgeClass}">${badgeLabel}</span>
        </div>
        <div class="report-card-meta">
          <span>📅 ${escHtml(doc.upload_date || 'Recent')}</span>
          <span>🆔 ${escHtml(doc.id)}</span>
        </div>
        <div class="report-card-summary">${escHtml(previewSummary)}</div>
        ${findingsHtml}
        <div class="report-card-actions">
          <button class="report-action-btn view-btn" data-id="${escHtml(doc.id)}">👁️ View Details</button>
          <button class="report-action-btn ask-btn" data-id="${escHtml(doc.id)}">💬 Ask AI</button>
          <button class="report-action-btn delete-btn" data-id="${escHtml(doc.id)}" style="background:rgba(239,68,68,0.1); color:#ef4444; border:1px solid rgba(239,68,68,0.3)">🗑️ Delete</button>
        </div>
      </div>
    `;
  }).join('');

  // Attach button event listeners
  patientReportsList.querySelectorAll('.view-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const doc = docs.find(d => d.id === btn.dataset.id);
      if (doc) openReportModal(doc);
    });
  });

  patientReportsList.querySelectorAll('.ask-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const doc = docs.find(d => d.id === btn.dataset.id);
      if (doc) {
        sendMessage(`Please explain my lab report "${doc.title}" and provide clinical guidance on the findings.`);
      }
    });
  });

  patientReportsList.querySelectorAll('.delete-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteUserDocument(btn.dataset.id);
    });
  });
}

async function deleteUserDocument(docId) {
  if (!confirm(`Are you sure you want to delete this document (${docId})?`)) return;
  try {
    const res = await apiFetch(`/api/hospital/documents/${docId}`, { method: 'DELETE' });
    if (res.ok) {
      showNotification('Document deleted successfully', 'success');
      if (typeof docViewModal !== 'undefined' && docViewModal && docViewModal.style.display !== 'none') {
        hideModal(docViewModal);
      }
      await loadUserLabReports();
    } else {
      const err = await res.json();
      showNotification(err.detail || 'Failed to delete document', 'error');
    }
  } catch (err) {
    console.error(err);
    showNotification('Error deleting document', 'error');
  }
}

function openReportModal(doc) {
  state.selectedDocForModal = doc;
  const isLab = doc.document_type === 'laboratory_report';
  const isRx = doc.document_type === 'prescription';
  const typeLabel = isLab ? '🧪 Laboratory Report' : (isRx ? '💊 Prescription' : '📄 Medical Record');

  if ($('docModalTitle')) $('docModalTitle').textContent = doc.title;
  if ($('docModalMeta')) $('docModalMeta').textContent = `Document ID: ${doc.id} · Type: ${typeLabel} · Upload Date: ${doc.upload_date}`;
  if ($('docModalSummary')) $('docModalSummary').textContent = doc.summary || 'Summary generated from extracted clinical findings.';
  
  const findingsContainer = $('docModalFindings');
  if (findingsContainer) {
    if (doc.key_findings && doc.key_findings.length > 0) {
      findingsContainer.innerHTML = doc.key_findings.map(f => `
        <span style="font-size:0.75rem; background:rgba(16,185,129,0.15); color:var(--success); border:1px solid rgba(16,185,129,0.3); border-radius:12px; padding:3px 10px; font-weight:600">✓ ${escHtml(f)}</span>
      `).join('');
    } else {
      findingsContainer.innerHTML = '<span style="font-size:0.75rem; color:var(--text-muted)">No specific abnormal tags flagged.</span>';
    }
  }

  if ($('docModalContent')) $('docModalContent').textContent = doc.extracted_text || 'No raw text available.';
  
  const deleteModalBtn = $('deleteDocModalBtn');
  if (deleteModalBtn) {
    deleteModalBtn.onclick = () => deleteUserDocument(doc.id);
  }

  showModal(docViewModal);
}


async function handleLogin(e) {
  e.preventDefault();
  authFeedback.textContent = 'Logging in...';
  authFeedback.style.color = 'var(--text-muted)';
  const emailVal = authEmail.value.trim().toLowerCase();
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: authEmail.value, password: authPassword.value })
    });
    if (res.ok) {
      const data = await res.json();
      const found = Object.values(PRESEEDED).find(p => p.email.toLowerCase() === emailVal);
      if (found) {
        state.currentUser = { ...found, token: data.access_token };
      } else {
        state.currentUser = {
          user_id: data.user_id || 'P1001',
          name: authName.value.trim() || authEmail.value.split('@')[0],
          email: authEmail.value,
          role: 'patient',
          token: data.access_token
        };
      }
      authFeedback.textContent = '✓ Logged in successfully';
      authFeedback.style.color = 'var(--success)';
      setTimeout(async () => {
        hideModal(authModal);
        await switchToPatientMode(state.currentUser.user_id);
      }, 500);
    } else {
      const err = await res.json();
      authFeedback.textContent = err.detail || 'Login failed';
      authFeedback.style.color = 'var(--danger)';
    }
  } catch {
    authFeedback.textContent = 'Connection error';
    authFeedback.style.color = 'var(--danger)';
  }
}

async function handleAdminLogin(e) {
  e.preventDefault();
  adminAuthFeedback.textContent = 'Authenticating admin...';
  adminAuthFeedback.style.color = 'var(--text-muted)';

  const email = adminAuthEmail.value.trim();
  const password = adminAuthPassword.value.trim();

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    if (res.ok) {
      const data = await res.json();
      state.currentUser = {
        user_id: 'A4001',
        name: 'Hospital Administrator',
        email: email,
        role: 'admin',
        token: data.access_token
      };
      adminAuthFeedback.textContent = '✓ Admin Authenticated!';
      adminAuthFeedback.style.color = 'var(--success)';
      setTimeout(async () => {
        hideModal(adminAuthModal);
        await switchToAdminMode();
      }, 500);
    } else {
      const err = await res.json();
      adminAuthFeedback.textContent = err.detail || 'Invalid admin credentials';
      adminAuthFeedback.style.color = 'var(--danger)';
    }
  } catch {
    adminAuthFeedback.textContent = 'Connection error';
    adminAuthFeedback.style.color = 'var(--danger)';
  }
}

async function handleRegister() {
  authFeedback.textContent = 'Registering...';
  authFeedback.style.color = 'var(--text-muted)';
  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: authName.value, email: authEmail.value, password: authPassword.value, role: 'patient' })
    });
    const data = await res.json();
    if (res.ok) {
      authFeedback.textContent = `✓ Registered! OTP: ${data.otp || 'sent'}`;
      authFeedback.style.color = 'var(--success)';
    } else {
      authFeedback.textContent = data.detail || 'Registration failed';
      authFeedback.style.color = 'var(--danger)';
    }
  } catch {
    authFeedback.textContent = 'Connection error';
    authFeedback.style.color = 'var(--danger)';
  }
}

// ============================================================
// HOSPITAL DATA
// ============================================================
async function loadHospitalData() {
  try {
    const res = await fetch('/api/hospital/departments');
    if (res.ok) { state.departments = await res.json(); }
  } catch {}
  try {
    const res = await fetch('/api/hospital/doctors');
    if (res.ok) { state.doctors = await res.json(); }
  } catch {}
  state.slotsByDoc = {};
  await fetchAllSlots();
  renderSlotPanel();
}

async function fetchAllSlots() {
  const promises = state.doctors.map(async doc => {
    try {
      const res = await fetch(`/api/hospital/slots?doctor_id=${encodeURIComponent(doc.id)}`);
      if (res.ok) {
        const slots = await res.json();
        state.slotsByDoc[doc.id] = slots;
      } else {
        state.slotsByDoc[doc.id] = [];
      }
    } catch {
      state.slotsByDoc[doc.id] = [];
    }
  });
  await Promise.all(promises);
}

// ============================================================
// SLOT PICKER PANEL
// ============================================================
async function toggleSlotPanel(force) {
  if (!slotPickerPanel) return;
  const show = force !== undefined ? force : (slotPickerPanel.style.display === 'none');
  slotPickerPanel.style.display = show ? 'block' : 'none';
  if (show) {
    await fetchAllSlots();
    renderSlotPanel();
  }
}

function renderSlotPanel() {
  if (!slotDeptTabs) return;
  const depts = [...new Set(
    state.doctors
      .map(d => d.department_name || d.department)
      .filter(d => d && typeof d === 'string' && d.trim() !== '')
  )];

  if (depts.length === 0) {
    slotDeptTabs.innerHTML = '';
    renderSlotDoctors('All');
    return;
  }

  const allTabs = ['All', ...depts];

  slotDeptTabs.innerHTML = allTabs.map((d, i) =>
    `<button class="dept-tab-btn ${i===0?'active':''}" data-dept="${escHtml(d)}">${escHtml(d)}</button>`
  ).join('');

  slotDeptTabs.querySelectorAll('.dept-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      slotDeptTabs.querySelectorAll('.dept-tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderSlotDoctors(btn.dataset.dept);
    });
  });

  renderSlotDoctors(allTabs[0]);
}

function renderSlotDoctors(dept) {
  if (!slotDoctorsList) return;
  const docs = (!dept || dept === 'All')
    ? state.doctors
    : state.doctors.filter(d => d.department_name === dept || d.department === dept);
  if (docs.length === 0) {
    slotDoctorsList.innerHTML = '<p style="color:var(--text-muted);font-size:0.82rem;padding:8px">No doctors found for this department.</p>';
    return;
  }

  slotDoctorsList.innerHTML = docs.map(doc => {
    const allSlots = (state.slotsByDoc && state.slotsByDoc[doc.id]) || [];
    const byDate = {};
    allSlots.forEach(s => {
      if (!byDate[s.date]) byDate[s.date] = [];
      if (byDate[s.date].length < 4) byDate[s.date].push(s);
    });
    const dateKeys = Object.keys(byDate).sort().slice(0, 3);

    const slotsHtml = dateKeys.length === 0
      ? '<span style="font-size:0.75rem;color:var(--text-muted)">No slots found</span>'
      : dateKeys.map(dateStr => `
          <div style="margin-bottom:8px">
            <span style="font-size:0.74rem;font-weight:600;color:var(--text-secondary);display:block;margin-bottom:4px">📅 ${dateStr}</span>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              ${byDate[dateStr].map(s => {
                const isAvail = s.is_available !== false;
                if (!isAvail) {
                  return `
                    <button class="slot-time-btn booked" disabled aria-disabled="true" title="Already booked by another patient">
                      🕒 ${escHtml(s.time)} <span class="slot-booked-tag">Booked</span>
                    </button>
                  `;
                }
                return `
                  <button class="slot-time-btn" title="Click to book with ${escHtml(doc.name)} at ${escHtml(s.time)}" data-docid="${escHtml(doc.id)}" data-docname="${escHtml(doc.name)}" data-dept="${escHtml(doc.department || doc.department_name)}" data-date="${escHtml(s.date)}" data-time="${escHtml(s.time)}">
                    🕒 ${escHtml(s.time)}
                  </button>
                `;
              }).join('')}
            </div>
          </div>
        `).join('');

    return `
      <div style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;padding:12px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
          <div style="width:36px;height:36px;border-radius:50%;background:var(--accent-color)22;color:var(--accent-color);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:0.85rem">
            ${escHtml(doc.name.replace('Dr. ', '').split(' ').map(n=>n[0]).join(''))}
          </div>
          <div>
            <div style="font-weight:600;font-size:0.88rem">${escHtml(doc.name)}</div>
            <div style="font-size:0.75rem;color:var(--text-muted)">${escHtml(doc.specialty || doc.department || '')} · Room ${escHtml(doc.room || '101')}</div>
          </div>
        </div>
        <div>${slotsHtml}</div>
      </div>
    `;
  }).join('');

  slotDoctorsList.querySelectorAll('.slot-time-btn:not([disabled]):not(.booked)').forEach(btn => {
    btn.addEventListener('click', () => {
      toggleSlotPanel(false);
      sendMessage(`Please book an appointment with ${btn.dataset.docname} (${btn.dataset.dept}) on ${btn.dataset.date} at ${btn.dataset.time}`);
    });
  });
}

// ============================================================
// FILE ATTACHMENTS
// ============================================================
function handleFileSelect(e) {
  const files = Array.from(e.target.files);
  files.forEach(f => {
    state.pendingFiles.push(f);
    renderFilePreview(f);
  });
  uploadPreviewStrip.style.display = 'block';
  sendBtn.disabled = false;
  fileInput.value = '';
}

function renderFilePreview(file) {
  const div = document.createElement('div');
  div.className = 'upload-preview-item';
  div.style.cssText = 'display:inline-flex; align-items:center; gap:6px; background:var(--bg-card-hover); border:1px solid var(--border-subtle); border-radius:16px; padding:4px 10px 4px 6px; font-size:0.78rem; color:var(--text-primary); margin:2px 4px;';

  const isImg = file.type.startsWith('image/');
  let thumbHtml = '<span style="font-size:0.9rem">📄</span>';
  if (isImg) {
    const imgUrl = URL.createObjectURL(file);
    thumbHtml = `<img src="${imgUrl}" style="width:26px; height:26px; border-radius:4px; object-fit:cover; border:1px solid var(--border-subtle)">`;
  } else if (file.name.endsWith('.pdf')) {
    thumbHtml = '<span style="font-size:0.9rem">📜</span>';
  }

  div.innerHTML = `
    ${thumbHtml}
    <span class="upload-name" style="max-width:130px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${escHtml(file.name)}</span>
    <button class="upload-remove" title="Remove file" style="background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:0.85rem; padding:0 2px; margin-left:4px">✕</button>
  `;

  div.querySelector('.upload-remove').addEventListener('click', () => {
    state.pendingFiles = state.pendingFiles.filter(f => f !== file);
    div.remove();
    if (state.pendingFiles.length === 0) {
      uploadPreviewStrip.style.display = 'none';
      sendBtn.disabled = chatInput.value.trim() === '';
    }
  });

  uploadPreviews.appendChild(div);
}

// ============================================================
// CHAT & MESSAGING
// ============================================================
async function handleSend() {
  const text = chatInput.value.trim();
  const files = [...state.pendingFiles];

  if (!text && files.length === 0) return;

  chatInput.value = '';
  chatInput.style.height = 'auto';
  state.pendingFiles = [];
  uploadPreviews.innerHTML = '';
  uploadPreviewStrip.style.display = 'none';
  sendBtn.disabled = true;

  if (welcomeScreen) welcomeScreen.style.display = 'none';

  let fullPrompt = text;
  if (files.length > 0) {
    const filenames = files.map(f => f.name).join(', ');
    fullPrompt = text ? `[Attached: ${filenames}]\n${text}` : `[Attached: ${filenames}] Please analyze these documents.`;
  }

  appendUserMessage(fullPrompt, files);
  await sendToBackend(fullPrompt, files);
}

function sendMessage(promptText) {
  chatInput.value = promptText;
  handleSend();
}

function renderUserMessageDOM(text, files = []) {
  const msgDiv = document.createElement('div');
  msgDiv.className = 'message-group user';

  let filesHtml = '';
  if (files && files.length > 0) {
    filesHtml = files.map(f => `
      <div class="msg-file-chip">
        <span>📄</span>
        <span>${escHtml(f.name)}</span>
      </div>
    `).join('');
  }

  const initial = state.currentUser.name ? state.currentUser.name.split(' ').map(n=>n[0]).join('').substring(0,2) : 'U';

  msgDiv.innerHTML = `
    <div class="message-row user">
      <div class="msg-avatar user">${initial}</div>
      <div class="msg-content">
        <div class="msg-meta"><span class="msg-sender">${escHtml(state.currentUser.name)}</span></div>
        ${filesHtml}
        <div class="msg-bubble">${escHtml(text)}</div>
      </div>
    </div>
  `;

  chatMessages.appendChild(msgDiv);
  scrollToBottom();
}

function appendUserMessage(text, files = []) {
  renderUserMessageDOM(text, files);
  recordUserMessageInActiveConv(text, files);
}

async function sendToBackend(prompt, files = []) {
  const typingId = `typing-${Date.now()}`;
  appendTypingIndicator(typingId);

  try {
    let res;
    if (files.length > 0) {
      const formData = new FormData();
      formData.append('message', prompt);
      formData.append('patient_id', state.currentUser.user_id);
      formData.append('session_id', state.sessionId);
      files.forEach(f => formData.append('files', f));

      res = await fetch('/api/chat/upload', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${state.currentUser.token}` },
        body: formData
      });
    } else {
      res = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${state.currentUser.token}`
        },
        body: JSON.stringify({
          message: prompt,
          patient_id: state.currentUser.user_id,
          session_id: state.sessionId
        })
      });
    }

    removeTyping(typingId);

    if (res.ok) {
      const data = await res.json();
      updateAgent(data.active_agent || 'hospital_root_agent');

      const responseText = data.reply || data.response || "I am here to assist you. How can I help you today?";
      appendAiMessage(responseText, data.active_agent, data.route, data.requires_confirmation, data.confirmation_details);

      // Refresh appointments and lab reports sidebar in case an appointment was booked or document uploaded
      loadUserAppointmentsSidebar();
      loadUserLabReports();
      window.dispatchEvent(new CustomEvent('appointmentUpdated'));
    } else {
      const err = await res.json();
      appendAiMessage(`⚠️ Error: ${err.detail || 'Unable to process request.'}`, 'hospital_root_agent');
    }
  } catch (err) {
    removeTyping(typingId);
    appendAiMessage(`⚠️ Connection Error: Unable to reach ApolloCare AI server. Make sure server is running on localhost:8000.`, 'hospital_root_agent');
  }
}

function renderAiMessageDOM(responseHtml, agentName, routeInfo = null, requiresConf = false, confDetails = null) {
  const msgDiv = document.createElement('div');
  msgDiv.className = 'message-group bot';

  const formattedContent = renderMarkdown(responseHtml);

  let routeBadge = '';
  if (routeInfo && routeInfo.route_type) {
    const routeColors = {
      RAG: 'background:#f59e0b22;color:#fbbf24;border:1px solid #f59e0b55',
      DIRECT_LLM: 'background:#10b98122;color:#6ee7b7;border:1px solid #10b98155',
      HYBRID_RAG_LLM: 'background:#8b5cf622;color:#c4b5fd;border:1px solid #8b5cf655'
    };
    const style = routeColors[routeInfo.route_type] || 'background:var(--bg-secondary);color:var(--text-muted)';
    routeBadge = `<span style="font-size:0.7rem;padding:2px 8px;border-radius:10px;font-weight:600;margin-left:8px;${style}">${routeInfo.route_type}</span>`;
  }

  let confBox = '';
  if (requiresConf && confDetails) {
    confBox = `
      <div class="confirm-box" style="margin-top:12px;padding:12px;background:var(--bg-secondary);border:1px solid var(--accent-color);border-radius:8px">
        <div style="font-weight:600;font-size:0.85rem;color:var(--accent-color);margin-bottom:6px">⚠️ Action Confirmation Required</div>
        <div style="font-size:0.82rem;color:var(--text-muted);margin-bottom:10px">${escHtml(confDetails.prompt || 'Do you confirm this action?')}</div>
        <div style="display:flex;gap:8px">
          <button class="btn-primary confirm-action-btn" data-action="${escHtml(confDetails.action)}" data-params='${JSON.stringify(confDetails.params || {})}'>Yes, Confirm</button>
          <button class="btn-secondary cancel-action-btn">Cancel</button>
        </div>
      </div>
    `;
  }

  msgDiv.innerHTML = `
    <div class="message-row bot">
      <div class="msg-avatar bot">🏥</div>
      <div class="msg-content">
        <div class="msg-meta">
          <span class="msg-sender">${agentLabel(agentName)}</span>
          ${routeBadge}
        </div>
        <div class="msg-bubble">${formattedContent}</div>
        ${confBox}
      </div>
    </div>
  `;

  chatMessages.appendChild(msgDiv);

  if (requiresConf) {
    const confirmBtn = msgDiv.querySelector('.confirm-action-btn');
    const cancelBtn = msgDiv.querySelector('.cancel-action-btn');
    if (confirmBtn) {
      confirmBtn.addEventListener('click', () => {
        const action = confirmBtn.dataset.action;
        const params = JSON.parse(confirmBtn.dataset.params);
        params.confirmed = true;
        msgDiv.querySelector('.confirm-box').remove();
        sendMessage(`Confirmed: ${action} with params ${JSON.stringify(params)}`);
      });
    }
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        msgDiv.querySelector('.confirm-box').remove();
        appendAiMessage('Action cancelled.', agentName);
      });
    }
  }

  scrollToBottom();
}

function appendAiMessage(responseHtml, agentName, routeInfo = null, requiresConf = false, confDetails = null) {
  renderAiMessageDOM(responseHtml, agentName, routeInfo, requiresConf, confDetails);
  recordAiMessageInActiveConv(responseHtml, agentName, routeInfo, requiresConf, confDetails);
}

function appendTypingIndicator(id) {
  const div = document.createElement('div');
  div.className = 'message-group ai';
  div.id = id;
  div.innerHTML = `
    <div class="msg-avatar ai">🏥</div>
    <div class="msg-content">
      <div class="msg-sender">${agentLabel(state.activeAgent)}</div>
      <div class="msg-bubble">
        <div class="typing-indicator">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
      </div>
    </div>
  `;
  chatMessages.appendChild(div);
  scrollToBottom();
}

function removeTyping(id) {
  const el = $(id);
  if (el) el.remove();
}

function clearChat(silent = false) {
  chatMessages.querySelectorAll('.message-group').forEach(el => el.remove());
  if (welcomeScreen) welcomeScreen.style.display = 'flex';
  if (!silent) {
    state.sessionId = `WEB-${state.currentUser.user_id}-${Math.random().toString(36).substring(2,8)}`;
  }
}

function agentLabel(name) {
  const map = {
    hospital_root_agent: 'ApolloCare AI Assistant',
    appointment_agent: 'Appointments Specialist',
    document_agent: 'Medical Records Specialist',
    info_agent: 'Medical Info Specialist',
    history_agent: 'Patient History Specialist',
    report_agent: 'Medical Records Specialist'
  };
  return map[name] || 'ApolloCare AI Assistant';
}

function updateAgent(agentName) {
  state.activeAgent = agentName;
  const friendlyName = agentLabel(agentName);
  if (activeAgentBadge) activeAgentBadge.textContent = friendlyName;

  const colorMap = {
    hospital_root_agent: '#8b5cf6',
    appointment_agent: '#06b6d4',
    document_agent: '#f59e0b',
    info_agent: '#10b981',
    history_agent: '#ec4899',
    report_agent: '#3b82f6'
  };
  const color = colorMap[agentName] || '#8b5cf6';
  if (agentDot) {
    agentDot.style.background = color;
    agentDot.style.boxShadow = `0 0 8px ${color}`;
  }
  if (activeAgentBadge) {
    activeAgentBadge.style.background = `${color}22`;
    activeAgentBadge.style.borderColor = `${color}55`;
    activeAgentBadge.style.color = color === '#8b5cf6' ? '#c4b5fd' : (color === '#06b6d4' ? '#a5f3fc' : color === '#f59e0b' ? '#fbbf24' : color === '#10b981' ? '#6ee7b7' : color === '#ec4899' ? '#f9a8d4' : '#93c5fd');
  }
}

// ============================================================
// MARKDOWN RENDERER
// ============================================================
function renderMarkdown(raw) {
  if (!raw) return '';

  const codeBlocks = [];
  let text = raw.replace(/```([\w]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<pre class="md-pre"><code class="lang-${escHtml(lang)}">${escHtml(code.trim())}</code></pre>`);
    return `\0CODE${idx}\0`;
  });

  const inlineCodes = [];
  text = text.replace(/`([^`\n]+)`/g, (_, c) => {
    const idx = inlineCodes.length;
    inlineCodes.push(`<code class="md-code">${escHtml(c)}</code>`);
    return `\0INLINE${idx}\0`;
  });

  const lines = text.split('\n');
  const output = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (i + 1 < lines.length && /^\|.*\|/.test(line) && /^[\|\s\-:]+$/.test(lines[i+1])) {
      const headers = parsePipeRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\|.*\|/.test(lines[i])) {
        rows.push(parsePipeRow(lines[i]));
        i++;
      }
      const thead = `<tr>${headers.map(h => `<th>${inlineMarkdown(h)}</th>`).join('')}</tr>`;
      const tbody = rows.map(r => `<tr>${r.map(c => `<td>${inlineMarkdown(c)}</td>`).join('')}</tr>`).join('');
      output.push(`<div class="md-table-wrap"><table class="md-table"><thead>${thead}</thead><tbody>${tbody}</tbody></table></div>`);
      continue;
    }

    if (/^---+$/.test(line.trim())) { output.push('<hr class="md-hr">'); i++; continue; }

    const h3 = line.match(/^### (.+)/);
    if (h3) { output.push(`<h3 class="md-h3">${inlineMarkdown(h3[1])}</h3>`); i++; continue; }
    const h2 = line.match(/^## (.+)/);
    if (h2) { output.push(`<h2 class="md-h2">${inlineMarkdown(h2[1])}</h2>`); i++; continue; }
    const h1 = line.match(/^# (.+)/);
    if (h1) { output.push(`<h1 class="md-h1">${inlineMarkdown(h1[1])}</h1>`); i++; continue; }

    if (/^[\-\*\+] (.+)/.test(line)) {
      const items = [];
      while (i < lines.length && /^[\-\*\+] (.+)/.test(lines[i])) {
        items.push(`<li>${inlineMarkdown(lines[i].replace(/^[\-\*\+] /, ''))}</li>`);
        i++;
      }
      output.push(`<ul class="md-ul">${items.join('')}</ul>`);
      continue;
    }

    if (/^\d+\.\s(.+)/.test(line)) {
      const items = [];
      while (i < lines.length && /^\d+\.\s(.+)/.test(lines[i])) {
        items.push(`<li>${inlineMarkdown(lines[i].replace(/^\d+\.\s/, ''))}</li>`);
        i++;
      }
      output.push(`<ol class="md-ol">${items.join('')}</ol>`);
      continue;
    }

    if (line.trim() === '') { output.push('<div class="md-gap"></div>'); i++; continue; }

    output.push(`<p class="md-p">${inlineMarkdown(line)}</p>`);
    i++;
  }

  let html = output.join('');

  codeBlocks.forEach((blk, idx) => { html = html.replace(`\0CODE${idx}\0`, blk); });
  inlineCodes.forEach((blk, idx) => { html = html.replace(`\0INLINE${idx}\0`, blk); });

  return html;
}

function inlineMarkdown(text) {
  let s = escHtml(text);
  s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*([^\*]+)\*/g, '<em>$1</em>');
  return s;
}

function parsePipeRow(line) {
  return line.replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
}

// ============================================================
// UTILITIES
// ============================================================
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatTime(date) {
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

function agentLabel(agentId) {
  const labels = {
    hospital_root_agent: 'ApolloCare AI Assistant',
    appointment_agent: 'ApolloCare AI Assistant',
    document_agent: 'ApolloCare AI Assistant',
    info_agent: 'ApolloCare AI Assistant',
    history_agent: 'ApolloCare AI Assistant',
    report_agent: 'ApolloCare AI Assistant'
  };
  return labels[agentId] || 'ApolloCare AI Assistant';
}

function showModal(modal) {
  if (modal) {
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }
}

function hideModal(modal) {
  if (modal) {
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }
}

function scrollToBottom() {
  if (chatMessages) {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
}

// ============================================================
// ADMIN DASHBOARD & DATA FETCHERS
// ============================================================
async function loadAdminStats() {
  try {
    const headers = { 'Authorization': `Bearer ${state.currentUser.token}` };
    const res = await fetch('/api/admin/stats', { headers });
    if (res.ok) {
      const data = await res.json();
      const s = data.stats;
      if ($('statUsers')) $('statUsers').textContent = s.total_patients;
      if ($('statAppts')) $('statAppts').textContent = s.total_appointments;
      if ($('statHDocs')) $('statHDocs').textContent = s.total_hospital_documents;
      if ($('statChunks')) $('statChunks').textContent = s.total_rag_chunks;
    }
  } catch (err) {
    console.error('Error loading admin stats:', err);
  }
}

async function loadAdminDocuments() {
  const container = $('adminDocList');
  if (!container) return;
  try {
    const headers = { 'Authorization': `Bearer ${state.currentUser.token}` };
    const res = await fetch('/api/admin/documents', { headers });
    if (res.ok) {
      const data = await res.json();
      if (data.documents.length === 0) {
        container.innerHTML = '<p style="font-size:0.85rem;color:var(--text-muted);padding:8px">No hospital documents uploaded yet. Upload a document above to generate chunks.</p>';
        return;
      }

      container.innerHTML = data.documents.map(doc => {
        const fileType = doc.file_type || 'Direct Text Input';
        const isPdf = fileType.toLowerCase().includes('pdf');
        return `
        <div style="background:var(--bg-secondary); border:1px solid var(--border-subtle); padding:14px; border-radius:8px; display:flex; flex-direction:column; gap:8px">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px">
            <div>
              <div style="font-weight:700; font-size:0.95rem; color:var(--text-primary); display:flex; align-items:center; gap:8px; flex-wrap:wrap">
                <span>${escHtml(doc.title)}</span>
                <span style="font-size:0.72rem; padding:2px 8px; border-radius:10px; font-weight:600; background:${isPdf ? 'rgba(59,130,246,0.15)' : 'rgba(16,185,129,0.15)'}; color:${isPdf ? '#3b82f6' : '#10b981'}">
                  ${isPdf ? '📄 PDF Document' : '✍️ Text Input'}
                </span>
              </div>
              <div style="font-size:0.78rem; color:var(--text-muted); margin-top:4px">
                Category: <strong style="color:var(--text-secondary)">${escHtml(doc.category)}</strong> · Uploaded: ${escHtml(doc.upload_date)} · Format: ${escHtml(fileType)}
              </div>
            </div>
            <div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap">
              <span style="background:var(--accent-color); color:#fff; padding:3px 9px; border-radius:12px; font-size:0.75rem; font-weight:600">🧩 ${doc.chunk_count} Chunks</span>
              <button class="btn-secondary toggle-content-btn" data-id="${doc.id}" style="padding:4px 8px; font-size:0.75rem">👁️ View Text</button>
              <button class="btn-secondary inspect-chunks-btn" data-id="${doc.id}" data-title="${escHtml(doc.title)}" style="padding:4px 8px; font-size:0.75rem">🔍 Inspect Chunks</button>
              <button class="btn-secondary edit-hdoc-btn" data-id="${doc.id}" data-title="${escHtml(doc.title)}" data-category="${escHtml(doc.category)}" data-content="${escHtml(doc.content || '')}" style="padding:4px 8px; font-size:0.75rem">✏️ Edit Title</button>
              <button class="btn-secondary delete-hdoc-btn" data-id="${doc.id}" title="Delete document & purge RAG chunks" style="padding:4px 10px; font-size:0.75rem; background:rgba(239,68,68,0.15); color:#ef4444; border:1px solid rgba(239,68,68,0.3); border-radius:6px; cursor:pointer; font-weight:600">🗑️ Delete</button>
            </div>
          </div>
          
          <div id="docContentPreview-${doc.id}" style="display:none; background:var(--bg-primary); border:1px solid var(--border-subtle); border-radius:6px; padding:10px 12px; font-size:0.8rem; color:var(--text-secondary); max-height:200px; overflow-y:auto; white-space:pre-wrap; margin-top:4px">
${escHtml(doc.content || 'No text content available.')}
          </div>
        </div>
      `}).join('');

      container.querySelectorAll('.toggle-content-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const preview = $(`docContentPreview-${btn.dataset.id}`);
          if (preview) {
            const isHidden = preview.style.display === 'none';
            preview.style.display = isHidden ? 'block' : 'none';
            btn.textContent = isHidden ? '🙈 Hide Text' : '👁️ View Text';
          }
        });
      });

      container.querySelectorAll('.inspect-chunks-btn').forEach(btn => {
        btn.addEventListener('click', () => inspectDocumentChunks(btn.dataset.id, btn.dataset.title));
      });

      container.querySelectorAll('.edit-hdoc-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          $('editDocId').value = btn.dataset.id;
          $('editDocTitleInput').value = btn.dataset.title;
          $('editDocCategoryInput').value = btn.dataset.category || 'General Guidelines';
          $('editDocContentInput').value = btn.dataset.content || '';
          showModal($('editDocModal'));
        });
      });

      container.querySelectorAll('.delete-hdoc-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          if (confirm('Delete this hospital document and permanently remove its chunks from User RAG search index?')) {
            const headers = { 'Authorization': `Bearer ${state.currentUser.token}` };
            await fetch(`/api/admin/documents/${btn.dataset.id}`, { method: 'DELETE', headers });
            await loadAdminStats();
            await loadAdminDocuments();
          }
        });
      });
    }
  } catch (err) {
    container.innerHTML = '<p style="font-size:0.85rem;color:var(--danger)">Error loading documents.</p>';
  }
}

async function loadAdminPatientsTable() {
  const container = $('patientTableBody');
  if (!container) return;
  container.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">Loading patients...</td></tr>';
  try {
    const headers = { 'Authorization': `Bearer ${state.currentUser.token}` };
    const res = await fetch('/api/admin/patients', { headers });
    if (res.ok) {
      const data = await res.json();
      if (!data.patients || data.patients.length === 0) {
        container.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">No registered patients found.</td></tr>';
        return;
      }
      container.innerHTML = data.patients.map(p => `
        <tr>
          <td><code style="color:var(--accent-color)">${escHtml(p.user_id || p.id)}</code></td>
          <td><strong>${escHtml(p.name)}</strong></td>
          <td>${escHtml(p.email)}</td>
          <td>${escHtml(p.phone || '—')}</td>
          <td>${p.is_verified ? '✅ Verified' : '⏳ Pending'}</td>
          <td>${escHtml(p.created_at || '—')}</td>
        </tr>
      `).join('');
    }
  } catch (err) {
    container.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--danger)">Error loading patients.</td></tr>';
  }
}

async function loadAdminAppointmentsTable() {
  const container = $('apptTableBody');
  if (!container) return;
  container.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted)">Loading appointments...</td></tr>';
  try {
    const headers = { 'Authorization': `Bearer ${state.currentUser.token}` };
    const res = await fetch('/api/admin/appointments', { headers });
    if (res.ok) {
      const data = await res.json();
      if (!data.appointments || data.appointments.length === 0) {
        container.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted)">No appointments booked yet.</td></tr>';
        return;
      }
      container.innerHTML = data.appointments.map(a => {
        const st = (a.status || '').toLowerCase();
        let bg = '#3b82f622', color = '#60a5fa'; // scheduled (blue)
        if (st === 'confirmed') { bg = '#10b98122'; color = '#10b981'; } // confirmed (green)
        else if (st === 'completed') { bg = '#8b5cf622'; color = '#c4b5fd'; } // completed (purple)
        else if (st === 'cancelled') { bg = '#ef444422'; color = '#f87171'; } // cancelled (red)
        return `
        <tr>
          <td><code style="color:var(--accent-color)">${escHtml(a.id)}</code></td>
          <td><strong>${escHtml(a.patient_name || a.user_id)}</strong> <br><small style="color:var(--text-muted)">(${escHtml(a.user_id)})</small></td>
          <td><strong>${escHtml(a.doctor_name)}</strong></td>
          <td>${escHtml(a.department_name || a.department)}</td>
          <td>${escHtml(a.date)} at ${escHtml(a.time)}</td>
          <td><span style="background:${bg};color:${color};padding:2px 8px;border-radius:10px;font-size:0.75rem;font-weight:600">${escHtml(st)}</span></td>
          <td>${escHtml(a.notes || '—')}</td>
          <td style="white-space:nowrap">
            <div style="display:flex;gap:6px;align-items:center">
              ${st !== 'completed' && st !== 'cancelled' ? `<button class="btn-primary admin-complete-appt-btn" data-id="${escHtml(a.id)}" style="padding:3px 8px;font-size:0.75rem;background:#10b981" title="Mark as completed">✔️ Complete</button>` : ''}
              <button class="upload-remove admin-delete-appt-btn" data-id="${escHtml(a.id)}" title="Delete appointment record" style="padding:3px 7px;font-size:0.75rem">🗑️</button>
            </div>
          </td>
        </tr>
      `;}).join('');

      container.querySelectorAll('.admin-complete-appt-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const apptId = btn.dataset.id;
          btn.disabled = true;
          btn.textContent = '⏳';
          try {
            const r = await fetch(`/api/admin/appointments/${apptId}/complete`, {
              method: 'PATCH',
              headers
            });
            if (r.ok) {
              await loadAdminAppointmentsTable();
              await loadAdminStats();
              window.dispatchEvent(new CustomEvent('appointmentUpdated'));
            } else {
              alert('Failed to mark appointment as completed.');
              btn.disabled = false;
              btn.textContent = '✔️ Complete';
            }
          } catch (err) {
            alert('Network error marking appointment complete.');
            btn.disabled = false;
            btn.textContent = '✔️ Complete';
          }
        });
      });

      container.querySelectorAll('.admin-delete-appt-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const apptId = btn.dataset.id;
          if (confirm(`Permanently delete appointment record ${apptId}?`)) {
            btn.disabled = true;
            btn.textContent = '⏳';
            try {
              const r = await fetch(`/api/admin/appointments/${apptId}`, {
                method: 'DELETE',
                headers
              });
              if (r.ok) {
                await loadAdminAppointmentsTable();
                await loadAdminStats();
                window.dispatchEvent(new CustomEvent('appointmentUpdated'));
              } else {
                alert('Failed to delete appointment.');
                btn.disabled = false;
                btn.textContent = '🗑️';
              }
            } catch (err) {
              alert('Network error deleting appointment.');
              btn.disabled = false;
              btn.textContent = '🗑️';
            }
          }
        });
      });
    }
  } catch (err) {
    container.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--danger)">Error loading appointments.</td></tr>';
  }
}


async function inspectDocumentChunks(docId, title) {
  if ($('chunkInspectorTitle')) $('chunkInspectorTitle').textContent = `🧩 Chunks for: ${title}`;
  const container = $('chunksContainer');
  if (container) container.innerHTML = '<p style="font-size:0.85rem;color:var(--text-muted)">Loading document chunks...</p>';

  showModal($('chunkInspectorModal'));

  try {
    const headers = { 'Authorization': `Bearer ${state.currentUser.token}` };
    const res = await fetch(`/api/admin/documents/${docId}/chunks`, { headers });
    if (res.ok) {
      const data = await res.json();
      if (container) {
        container.innerHTML = data.chunks.map(c => `
          <div style="border:1px solid var(--border-color);border-radius:6px;padding:10px;background:var(--bg-primary)">
            <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:0.8rem;font-weight:600;color:var(--accent-color)">
              <span>Chunk #${c.chunk_index + 1} (${c.word_count} words)</span>
              <span>ID: ${escHtml(c.chunk_id)}</span>
            </div>
            <div style="font-size:0.85rem;color:var(--text-primary);line-height:1.4;white-space:pre-wrap;background:var(--bg-secondary);padding:8px;border-radius:4px">${escHtml(c.chunk_text)}</div>
          </div>
        `).join('');
      }
    }
  } catch (err) {
    if (container) container.innerHTML = '<p style="font-size:0.85rem;color:var(--danger)">Failed to load chunks.</p>';
  }
}
