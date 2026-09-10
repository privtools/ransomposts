/* Home page table.

   Loaded with `defer` after jQuery and Bootstrap-Table, so this file initialises the
   table itself: the data-toggle auto-init could fire before the formatters exist. */

/* ── Cell formatters (global: Bootstrap-Table resolves them by name) ─── */

/* Post cell: keep the value as-is (it may already be an <a>) and add the sector. */
function titleFormatter(value, row) {
  var title = value || '<span class="shot-none">&mdash;</span>';
  var sector = row && row.activity ? String(row.activity) : '';
  var sub = sector
    ? '<span class="cell-sub">' + sector.replace(/[<>&]/g, '') + '</span>'
    : '';
  return '<span class="cell-title">' + title + '</span>' + sub;
}

/* Date cell: split the raw ISO timestamp into date + time. */
function dateFormatter(value) {
  if (!value) return '<span class="shot-none">&mdash;</span>';
  var s = String(value);
  var day = s.slice(0, 10);
  var time = s.length > 15 ? s.slice(11, 16) : '';
  return '<span class="cell-date">' + day + '</span>' +
         (time ? '<span class="cell-time">' + time + ' UTC</span>' : '');
}

/* Screenshot cell: turn the raw "🖵" anchor into an icon button. */
function shotFormatter(value) {
  if (!value) return '<span class="shot-none">&mdash;</span>';
  var m = String(value).match(/href=['"]([^'"]+)['"]/);
  if (!m) return value;
  return '<a class="shot-link" href="' + m[1] + '" target="_blank" rel="nofollow noopener noreferrer" ' +
         'title="Open screenshot" aria-label="Open screenshot"><i class="bi bi-image"></i></a>';
}

(function () {
  'use strict';

  var FULL_URL = './assets/victims-lite.json';

  var $table = $('#table');
  var loader = document.getElementById('loading-indicator');
  var loadButton = document.getElementById('load-full');
  var scope = document.getElementById('data-scope');
  var fullHistory = false;

  /* Only the last 30 days load first, so an empty search usually means "older". */
  $.extend($.fn.bootstrapTable.defaults, {
    formatNoMatches: function () {
      return fullHistory
        ? 'No matching posts found'
        : 'No matching posts in the last 30 days. ' +
          '<button type="button" class="chip js-load-full">Search the full history</button>';
    }
  });

  function loadFullHistory() {
    if (fullHistory) return;
    fullHistory = true;
    var searchText = $table.bootstrapTable('getOptions').searchText || '';
    if (loadButton) {
      loadButton.disabled = true;
      loadButton.textContent = 'Loading…';
    }
    if (scope) scope.textContent = 'Loading the full history…';
    $table.bootstrapTable('refreshOptions', { url: FULL_URL, searchText: searchText });
  }

  /* Outbound links open in a new tab and pass no ranking; internal ones stay as they are.
     Bootstrap-Table's pagination uses href="javascript:void(0)", which crawlers flag as
     uncrawlable — point it at the table instead (its click handlers are unaffected). */
  function fixLinks() {
    var links = document.querySelectorAll('#table tbody a[href^="http"]');
    for (var i = 0; i < links.length; i++) {
      if (!links[i].getAttribute('target')) {
        links[i].setAttribute('target', '_blank');
        links[i].setAttribute('rel', 'nofollow noopener noreferrer');
      }
    }
    var pageLinks = document.querySelectorAll('.fixed-table-pagination a[href^="javascript"]');
    for (var j = 0; j < pageLinks.length; j++) {
      pageLinks[j].setAttribute('href', '#table');
    }
  }

  $table.on('load-success.bs.table', function () {
    if (loader) loader.setAttribute('data-visible', 'false');
    if (!fullHistory) return;
    if (scope) scope.innerHTML = '<b>Showing:</b> full history (2022 &rarr; present)';
    if (loadButton) loadButton.hidden = true;
  });

  $table.on('load-error.bs.table', function () {
    if (loader) loader.setAttribute('data-visible', 'false');
    if (!fullHistory) return;
    fullHistory = false;
    if (scope) scope.innerHTML = '<b>Showing:</b> last 30 days';
    if (loadButton) {
      loadButton.disabled = false;
      loadButton.textContent = 'Retry loading full history';
    }
  });

  $table.on('post-body.bs.table', fixLinks);

  if (loadButton) loadButton.addEventListener('click', loadFullHistory);
  $(document).on('click', '.js-load-full', loadFullHistory);

  if (loader) loader.setAttribute('data-visible', 'true');
  $table.bootstrapTable();
}());
