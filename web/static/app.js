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
})();
