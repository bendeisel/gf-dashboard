// Applies the saved theme before first paint to avoid a flash. Kept external so the
// page's Content-Security-Policy can forbid inline scripts.
(function () {
  try {
    var t = localStorage.getItem('gf-theme');
    document.documentElement.setAttribute('data-theme', t === 'dark' ? 'dark' : 'light');
  } catch (e) {}
})();
