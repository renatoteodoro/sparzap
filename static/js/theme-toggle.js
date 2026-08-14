// Alternancia de tema (claro/escuro). O valor inicial ja foi aplicado pelo
// script anti-flash inline no <head> de base.html; este arquivo so cuida do
// clique no botao e da persistencia em localStorage.
(function () {
  function applyTheme(theme) {
    document.documentElement.classList.remove('light', 'dark');
    document.documentElement.classList.add(theme);
    document.documentElement.setAttribute('data-theme', theme);
  }

  function currentTheme() {
    return document.documentElement.classList.contains('light') ? 'light' : 'dark';
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var next = currentTheme() === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        localStorage.setItem('sparzap-theme', next);
      });
    });
  });
})();
