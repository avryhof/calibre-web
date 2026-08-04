/* Book Shop search front-end.
 * Fetches results from the FastAPI endpoint mounted under /api and renders
 * result cards. All user-visible strings are written via textContent so that
 * provider content cannot inject markup (XSS). */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('bookshop-search');
    var queryInput = document.getElementById('bookshop-query');
    var statusEl = document.getElementById('bookshop-status');
    var grid = document.getElementById('bookshop-results');

    if (!form || !queryInput || !statusEl || !grid) {
      return;
    }

    var apiBase = grid.getAttribute('data-api-base') || '/api';

    function selectedProviders() {
      var checks = form.querySelectorAll('input[name="providers"]:checked');
      return Array.prototype.map.call(checks, function (c) {
        return c.value;
      });
    }

    function runSearch(q) {
      statusEl.textContent = '';
      grid.innerHTML = '';
      grid.classList.add('loading');
      statusEl.textContent = '';
      var status = document.createElement('span');
      status.textContent = window.gettext ? window.gettext('Searching...') : 'Searching...';
      statusEl.appendChild(status);
      grid.setAttribute('aria-busy', 'true');

      var params = new URLSearchParams();
      params.set('q', q);
      var providers = selectedProviders();
      if (providers.length) {
        params.set('providers', providers.join(','));
      }
      params.set('limit', '24');
      var url = apiBase + '/bookshop/search?' + params.toString();

      fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
        .then(function (response) {
          if (response.status === 401) {
            throw new Error('not-authenticated');
          }
          if (!response.ok) {
            throw new Error('http-' + response.status);
          }
          return response.json();
        })
        .then(function (data) {
          renderResults(data);
        })
        .catch(function (err) {
          grid.classList.remove('loading');
          grid.setAttribute('aria-busy', 'false');
          var msg = (err && err.message === 'not-authenticated')
            ? 'Your session has expired. Please sign in again.'
            : 'Search failed. Please try again.';
          statusEl.textContent = '';
          var span = document.createElement('span');
          span.className = 'bookshop-error';
          span.textContent = msg;
          statusEl.appendChild(span);
        });
    }

    function renderResults(data) {
      grid.classList.remove('loading');
      grid.setAttribute('aria-busy', 'false');
      statusEl.textContent = '';
      var results = (data && data.results) || [];
      var status = document.createElement('span');
      if (!results.length) {
        status.textContent = 'No free ebooks found. Try different terms or more catalogs.';
        statusEl.appendChild(status);
        return;
      }
      status.textContent = results.length + (results.length === 1 ? ' result' : ' results');
      statusEl.appendChild(status);

      var fragment = document.createDocumentFragment();
      results.forEach(function (item) {
        fragment.appendChild(renderCard(item));
      });
      grid.appendChild(fragment);
    }

    function renderCard(item) {
      var card = document.createElement('article');
      card.className = 'bookshop-card';
      card.setAttribute('data-source', (item.source && item.source.id) || '');

      var coverLink = document.createElement('a');
      coverLink.className = 'bookshop-cover';
      coverLink.href = item.url || '#';
      coverLink.target = '_blank';
      coverLink.rel = 'noopener noreferrer';
      var cover = document.createElement('img');
      cover.className = 'bookshop-cover-img';
      cover.alt = item.title || '';
      cover.loading = 'lazy';
      if (item.cover) {
        cover.src = item.cover;
      } else {
        cover.classList.add('no-cover');
      }
      cover.addEventListener('error', function () {
        cover.classList.add('no-cover');
      });
      coverLink.appendChild(cover);
      card.appendChild(coverLink);

      var body = document.createElement('div');
      body.className = 'bookshop-body';

      var badge = document.createElement('span');
      badge.className = 'bookshop-badge';
      badge.textContent = (item.source && item.source.name) || '';
      body.appendChild(badge);

      var titleLink = document.createElement('a');
      titleLink.className = 'bookshop-title';
      titleLink.href = item.url || '#';
      titleLink.target = '_blank';
      titleLink.rel = 'noopener noreferrer';
      titleLink.textContent = item.title || '';
      body.appendChild(titleLink);

      if (item.authors && item.authors.length) {
        var authors = document.createElement('p');
        authors.className = 'bookshop-authors';
        authors.textContent = item.authors.join(', ');
        body.appendChild(authors);
      }

      if (item.description) {
        var description = document.createElement('p');
        description.className = 'bookshop-description';
        description.textContent = item.description;
        body.appendChild(description);
      }

      var formats = item.formats || {};
      var formatKeys = Object.keys(formats);
      if (formatKeys.length) {
        var downloads = document.createElement('div');
        downloads.className = 'bookshop-downloads';
        formatKeys.forEach(function (label) {
          var link = document.createElement('a');
          link.className = 'btn btn-primary btn-xs bookshop-download';
          link.href = formats[label];
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = label;
          downloads.appendChild(link);
        });
        body.appendChild(downloads);
      }

      var footer = document.createElement('p');
      footer.className = 'bookshop-footer';
      var details = document.createElement('a');
      details.href = item.url || '#';
      details.target = '_blank';
      details.rel = 'noopener noreferrer';
      details.textContent = 'Details';
      footer.appendChild(details);
      body.appendChild(footer);

      card.appendChild(body);
      return card;
    }

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var q = queryInput.value.trim();
      if (q) {
        runSearch(q);
      }
    });
  });
})();
