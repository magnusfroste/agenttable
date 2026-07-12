// AgentTable client-side enhancements
// Loaded on every page via base.html

(function () {
  'use strict';

  // === Theme toggle (light/dark/auto) ===
  const THEME_KEY = 'at-theme';
  const root = document.documentElement;

  function applyTheme(theme) {
    if (theme === 'auto') {
      root.removeAttribute('data-theme');
    } else {
      root.setAttribute('data-theme', theme);
    }
  }

  function currentTheme() {
    return localStorage.getItem(THEME_KEY) || 'auto';
  }

  function setTheme(theme) {
    localStorage.setItem(THEME_KEY, theme);
    applyTheme(theme);
    updateToggleIcon();
  }

  function nextTheme() {
    const cycle = ['auto', 'light', 'dark'];
    const cur = currentTheme();
    setTheme(cycle[(cycle.indexOf(cur) + 1) % cycle.length]);
  }

  function updateToggleIcon() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    const t = currentTheme();
    btn.textContent = t === 'dark' ? '☀' : t === 'light' ? '◐' : '◑';
    btn.title = 'Tema: ' + t + ' (klicka för att växla)';
  }

  applyTheme(currentTheme());
  updateToggleIcon();

  document.getElementById('theme-toggle')?.addEventListener('click', nextTheme);

  // === Admin key (localStorage, prompted on first use — agentanbud pattern) ===
  const ADMIN_KEY_STORAGE = 'at-admin-key';

  function getAdminKey() {
    let key = localStorage.getItem(ADMIN_KEY_STORAGE);
    if (!key) {
      key = prompt('Admin-nyckel (ADMIN_API_KEY):') || '';
      if (key) localStorage.setItem(ADMIN_KEY_STORAGE, key);
    }
    return key;
  }

  // Shared with page-level scripts (dataset.html)
  window.atGetAdminKey = getAdminKey;
  window.atClearAdminKey = function () { localStorage.removeItem(ADMIN_KEY_STORAGE); };

  // Delete a dataset (keyed). Called from index.html.
  window.atDeleteDataset = async function (slug, name) {
    if (!confirm('Radera "' + name + '" och alla dess rader?')) return;
    const res = await fetch('/api/datasets/' + encodeURIComponent(slug), {
      method: 'DELETE',
      headers: { 'X-Admin-Key': getAdminKey() },
    });
    if (res.status === 401) {
      localStorage.removeItem(ADMIN_KEY_STORAGE);
      alert('Fel admin-nyckel — försök igen.');
      return;
    }
    if (!res.ok) {
      alert('Kunde inte radera (HTTP ' + res.status + ').');
      return;
    }
    location.reload();
  };
})();
