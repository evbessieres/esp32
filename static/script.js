// ═══════════════════════════════════════════
//  PORTAIL OS — Script principal
// ═══════════════════════════════════════════

const API = '';  // Même domaine, pas besoin de préfixe

// ── ÉTAT ──
let currentRole = null;
let currentPortailId = null;

// ═══════════════════════════════════
//  AUTH
// ═══════════════════════════════════
function switchTab(tab) {
  document.querySelectorAll('.auth-tab').forEach((t, i) => {
    t.classList.toggle('active', (i === 0 && tab === 'login') || (i === 1 && tab === 'register'));
  });
  document.getElementById('tab-login').classList.toggle('hidden', tab !== 'login');
  document.getElementById('tab-register').classList.toggle('hidden', tab !== 'register');
}

async function doLogin() {
  const id  = document.getElementById('login-id').value.trim();
  const mdp = document.getElementById('login-mdp').value;
  const err = document.getElementById('login-error');

  if (!id || !mdp) { showError(err, 'Remplis tous les champs'); return; }

  try {
    const res  = await fetch(`${API}/api/auth/connexion`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifiant: id, mot_de_passe: mdp })
    });
    const data = await res.json();

    if (!res.ok) { showError(err, data.error); return; }

    err.classList.add('hidden');
    currentRole      = data.role;
    currentPortailId = data.portail_id;
    loadDashboard();
  } catch (e) { showError(err, 'Erreur de connexion au serveur'); }
}

async function doRegister() {
  const portail = document.getElementById('reg-portail').value.trim().toUpperCase();
  const id      = document.getElementById('reg-id').value.trim();
  const mdp     = document.getElementById('reg-mdp').value;
  const err     = document.getElementById('register-error');
  const suc     = document.getElementById('register-success');

  if (!portail || !id || !mdp) { showError(err, 'Remplis tous les champs'); return; }

  try {
    const res  = await fetch(`${API}/api/auth/inscription`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code_portail: portail, identifiant: id, mot_de_passe: mdp })
    });
    const data = await res.json();

    if (!res.ok) { showError(err, data.error); suc.classList.add('hidden'); return; }

    err.classList.add('hidden');
    suc.classList.remove('hidden');
    suc.textContent = data.message;

    if (data.role === 'chef') {
      setTimeout(() => { switchTab('login'); }, 1500);
    }
  } catch (e) { showError(err, 'Erreur de connexion au serveur'); }
}

async function doLogout() {
  await fetch(`${API}/api/auth/deconnexion`, { method: 'POST', credentials: 'include' });
  location.reload();
}

// ═══════════════════════════════════
//  DASHBOARD
// ═══════════════════════════════════
async function loadDashboard() {
  // Récupère les infos utilisateur
  const res  = await fetch(`${API}/api/auth/moi`, { credentials: 'include' });
  const user = await res.json();

  currentRole      = user.role;
  currentPortailId = user.portail_id;

  // Affichage
  document.getElementById('user-name').textContent   = user.identifiant;
  document.getElementById('user-avatar').textContent = user.identifiant.charAt(0).toUpperCase();
  document.getElementById('user-role').textContent   = roleLabel(user.role);
  document.getElementById('portail-id-display').textContent = user.portail_id;

  // Droits selon le rôle
  if (user.role === 'chef' || user.role === 'admin') {
    document.getElementById('nav-users').classList.remove('hidden');
  } else {
    document.body.classList.add('role-habitant');
  }

  // Afficher le dashboard
  document.getElementById('page-auth').classList.add('hidden');
  document.getElementById('page-dashboard').classList.remove('hidden');

  // Charger le mode
  loadMode();
  if (user.role === 'chef' || user.role === 'admin') loadPending();
}

function roleLabel(role) {
  return { admin: 'Admin', chef: 'Chef de maison', habitant: 'Habitant' }[role] || role;
}

// ═══════════════════════════════════
//  NAVIGATION
// ═══════════════════════════════════
const sectionTitles = {
  mode:       'Contrôle',
  badges:     'Badges RFID',
  empreintes: 'Empreintes digitales',
  codes:      'Codes',
  logs:       'Journaux d\'accès',
  users:      'Utilisateurs'
};

const sectionLoaders = {
  badges:     loadBadges,
  empreintes: loadEmpreintes,
  codes:      loadCodes,
  logs:       loadLogs,
  users:      loadPending
};

function showSection(name) {
  // Nav items
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  const navBtn = document.querySelector(`[onclick="showSection('${name}')"]`);
  if (navBtn) navBtn.classList.add('active');

  // Sections
  document.querySelectorAll('.section').forEach(s => {
    s.classList.remove('active');
    s.classList.add('hidden');
  });
  const sec = document.getElementById(`section-${name === 'mode' ? 'mode' : name}`);
  if (sec) { sec.classList.remove('hidden'); sec.classList.add('active'); }

  // Titre
  document.getElementById('section-title').textContent = sectionTitles[name] || name;

  // Charger les données
  if (sectionLoaders[name]) sectionLoaders[name]();
}

// ═══════════════════════════════════
//  MODE
// ═══════════════════════════════════
async function loadMode() {
  const res  = await fetch(`${API}/api/mode`, { credentials: 'include' });
  const data = await res.json();
  updateModeDisplay(data.mode);
}

async function setMode(mode) {
  const res = await fetch(`${API}/api/mode`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode })
  });
  if (res.ok) { updateModeDisplay(mode); showToast(`Mode → ${mode}`, 'success'); }
  else { const d = await res.json(); showToast(d.error || 'Erreur', 'error'); }
}

function updateModeDisplay(mode) {
  const icons = { STANDBY: '⏸', SCAN_BADGES: '📡', SCAN_EMPREINTES: '👆' };
  document.getElementById('mode-name').textContent  = mode;
  document.getElementById('mode-badge').textContent = mode;
  document.getElementById('mode-icon').textContent  = icons[mode] || '⚙️';
}

// ═══════════════════════════════════
//  PULSE
// ═══════════════════════════════════
async function doPulse() {
  const btn = document.getElementById('btn-pulse');
  btn.classList.add('firing');
  btn.disabled = true;

  const res = await fetch(`${API}/api/pulse`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' }, body: '{}'
  });

  setTimeout(() => {
    btn.classList.remove('firing');
    btn.disabled = false;
  }, 600);

  if (res.ok) showToast('Signal envoyé au portail !', 'success');
  else { const d = await res.json(); showToast(d.error || 'Erreur', 'error'); }
}

// ═══════════════════════════════════
//  BADGES
// ═══════════════════════════════════
async function loadBadges() {
  const tbody = document.getElementById('badges-tbody');
  tbody.innerHTML = '<tr><td colspan="5" class="table-empty">Chargement…</td></tr>';

  const res  = await fetch(`${API}/api/badges`, { credentials: 'include' });
  const data = await res.json();

  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="table-empty">Aucun badge enregistré</td></tr>';
    return;
  }

  const isChef = currentRole === 'chef' || currentRole === 'admin';

  tbody.innerHTML = data.map(b => `
    <tr>
      <td class="mono" style="font-size:12px;color:var(--primary)">${b.uid}</td>
      <td id="badge-nom-${b.id}">${b.nom}</td>
      <td><span class="tag-autorise ${b.autorise ? 'yes' : 'no'}" id="badge-auth-${b.id}">
        ${b.autorise ? 'Autorisé' : 'Non autorisé'}
      </span></td>
      <td style="color:var(--muted);font-size:12px">${formatDate(b.date)}</td>
      ${isChef ? `<td>
        <button class="btn-table" onclick="editBadge(${b.id}, '${b.nom}', ${b.autorise})">✏️ Modifier</button>
      </td>` : '<td>—</td>'}
    </tr>
  `).join('');
}

async function editBadge(id, nomActuel, autoriseActuel) {
  const nom      = prompt('Nom associé à ce badge :', nomActuel);
  if (nom === null) return;
  const autorise = confirm('Autoriser ce badge ?');

  const res = await fetch(`${API}/api/badges/${id}`, {
    method: 'PUT', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nom, autorise })
  });

  if (res.ok) { showToast('Badge mis à jour', 'success'); loadBadges(); }
  else showToast('Erreur lors de la mise à jour', 'error');
}

// ═══════════════════════════════════
//  EMPREINTES
// ═══════════════════════════════════
async function loadEmpreintes() {
  const tbody = document.getElementById('empreintes-tbody');
  tbody.innerHTML = '<tr><td colspan="3" class="table-empty">Chargement…</td></tr>';

  const res  = await fetch(`${API}/api/empreintes`, { credentials: 'include' });
  const data = await res.json();

  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="table-empty">Aucune empreinte enregistrée</td></tr>';
    return;
  }

  tbody.innerHTML = data.map(e => `
    <tr>
      <td class="mono" style="color:var(--primary)">#${e.id_capteur}</td>
      <td>${e.nom}</td>
      <td style="color:var(--muted);font-size:12px">${formatDate(e.date)}</td>
    </tr>
  `).join('');
}

// ═══════════════════════════════════
//  CODES
// ═══════════════════════════════════
async function loadCodes() {
  const tbody = document.getElementById('codes-tbody');
  tbody.innerHTML = '<tr><td colspan="3" class="table-empty">Chargement…</td></tr>';

  const res  = await fetch(`${API}/api/codes`, { credentials: 'include' });
  const data = await res.json();

  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="table-empty">Aucun code enregistré</td></tr>';
    return;
  }

  tbody.innerHTML = data.map(c => `
    <tr>
      <td style="font-weight:600">${c.nom}</td>
      <td class="mono" style="font-size:12px;color:var(--primary)">${c.contenu}</td>
      <td style="color:var(--muted);font-size:12px">${formatDate(c.date)}</td>
    </tr>
  `).join('');
}

function toggleAddCode() {
  const form = document.getElementById('add-code-form');
  form.classList.toggle('hidden');
}

async function addCode() {
  const nom     = document.getElementById('code-nom').value.trim();
  const contenu = document.getElementById('code-contenu').value.trim();

  if (!nom || !contenu) { showToast('Remplis tous les champs', 'warning'); return; }

  const res = await fetch(`${API}/api/codes`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nom, contenu })
  });

  if (res.ok) {
    showToast('Code enregistré !', 'success');
    document.getElementById('code-nom').value    = '';
    document.getElementById('code-contenu').value = '';
    toggleAddCode();
    loadCodes();
  } else showToast('Erreur', 'error');
}

// ═══════════════════════════════════
//  LOGS
// ═══════════════════════════════════
async function loadLogs() {
  const tbody = document.getElementById('logs-tbody');
  tbody.innerHTML = '<tr><td colspan="5" class="table-empty">Chargement…</td></tr>';

  const res  = await fetch(`${API}/api/logs`, { credentials: 'include' });
  const data = await res.json();

  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="table-empty">Aucun accès enregistré</td></tr>';
    return;
  }

  tbody.innerHTML = data.map(l => `
    <tr>
      <td><span class="tag-type">${l.type}</span></td>
      <td class="mono" style="font-size:12px">${l.identifiant}</td>
      <td>${l.nom || '—'}</td>
      <td><span class="tag-autorise ${l.acces_accorde ? 'yes' : 'no'}">
        ${l.acces_accorde ? '✓ Accordé' : '✗ Refusé'}
      </span></td>
      <td style="color:var(--muted);font-size:12px">${formatDate(l.date)}</td>
    </tr>
  `).join('');
}

// ═══════════════════════════════════
//  UTILISATEURS
// ═══════════════════════════════════
async function loadPending() {
  const res  = await fetch(`${API}/api/utilisateurs/en_attente`, { credentials: 'include' });
  const data = await res.json();

  const badge = document.getElementById('badge-attente');
  if (data.length > 0) {
    badge.textContent = data.length;
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }

  const list = document.getElementById('users-pending-list');
  if (!list) return;

  if (!data.length) {
    list.innerHTML = '<p class="table-empty">Aucun utilisateur en attente</p>';
    return;
  }

  list.innerHTML = data.map(u => `
    <div class="user-pending-item">
      <div>
        <div class="u-name">${u.identifiant}</div>
        <div class="u-id">ID #${u.id} · ${formatDate(u.inscription)}</div>
      </div>
      <div class="user-pending-actions">
        <button class="btn-approve" onclick="approuver(${u.id})">✓ Approuver</button>
        <button class="btn-refuse"  onclick="refuser(${u.id})">✗ Refuser</button>
      </div>
    </div>
  `).join('');
}

async function approuver(id) {
  const res = await fetch(`${API}/api/utilisateurs/${id}/approuver`, {
    method: 'POST', credentials: 'include'
  });
  if (res.ok) { showToast('Utilisateur approuvé !', 'success'); loadPending(); }
  else showToast('Erreur', 'error');
}

async function refuser(id) {
  if (!confirm('Refuser et supprimer cet utilisateur ?')) return;
  const res = await fetch(`${API}/api/utilisateurs/${id}/refuser`, {
    method: 'POST', credentials: 'include'
  });
  if (res.ok) { showToast('Utilisateur refusé', 'warning'); loadPending(); }
  else showToast('Erreur', 'error');
}

async function accorderDroit() {
  const userId = document.getElementById('droit-user-id').value;
  const droit  = document.getElementById('droit-select').value;

  if (!userId) { showToast('Entre un ID utilisateur', 'warning'); return; }

  const res = await fetch(`${API}/api/utilisateurs/${userId}/droits`, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ droit })
  });

  if (res.ok) showToast(`Droit "${droit}" accordé !`, 'success');
  else { const d = await res.json(); showToast(d.error || 'Erreur', 'error'); }
}

// ═══════════════════════════════════
//  UTILITAIRES
// ═══════════════════════════════════
function showError(el, msg) {
  el.textContent = msg;
  el.classList.remove('hidden');
}

let toastTimeout;
function showToast(msg, type = 'info') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className   = `toast ${type}`;
  t.classList.remove('hidden');
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => t.classList.add('hidden'), 3000);
}

function formatDate(str) {
  if (!str) return '—';
  const d = new Date(str);
  return d.toLocaleDateString('fr-FR') + ' ' + d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

// ═══════════════════════════════════
//  INIT — Vérifie si déjà connecté
// ═══════════════════════════════════
(async () => {
  try {
    const res = await fetch(`${API}/api/auth/moi`, { credentials: 'include' });
    if (res.ok) { loadDashboard(); }
  } catch (e) { /* non connecté, page auth déjà visible */ }
})();
