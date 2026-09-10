/* Light / dark toggle shared by every page. The stored theme is applied by an
   inline script in <head> before first paint; this only handles the button. */
(function () {
  'use strict';

  var button = document.getElementById('theme-toggle');
  if (!button) return;

  button.addEventListener('click', function () {
    var root = document.documentElement;
    var next = (root.getAttribute('data-theme') || 'dark') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', next === 'dark' ? '#07090d' : '#f3f5f9');
    try { localStorage.setItem('rp-theme', next); } catch (e) { /* storage blocked */ }
  });
}());
