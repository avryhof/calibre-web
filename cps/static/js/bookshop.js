/* Book Shop search front-end.
 * Fetches results from the FastAPI endpoint mounted under /api and renders
 * result cards. Supports title/author search modes and, when the current user
 * may upload, an "Add to library" action that imports a free/public-domain
 * ebook directly into the library.
 * All user-visible strings are written via textContent so that provider
 * content cannot inject markup (XSS). */
(function () {
  'use strict';

  var PREFERRED_FORMATS = ['EPUB', 'PDF', 'MOBI', 'AZW3', 'KEPUB', 'TXT'];

  document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('bookshop-search');
    var queryInput = document.getElementById('bookshop-query');
    var statusEl = document.getElementById('bookshop-status');
    var grid = document.getElementById('bookshop-results');

    if (!form || !queryInput || !statusEl || !grid) {
      return;
    }

    var apiBase = grid.getAttribute('data-api-base') || '/api';
    var allowUpload = grid.getAttribute('data-allow-upload') === 'true';
    var scriptRoot = apiBase.replace(/\/api$/, '');

    function selectedProviders() {
      var checks = form.querySelectorAll('input[name="providers"]:checked');
      return Array.prototype.map.call(checks, function (c) {
        return c.value;
      });
    }

    function selectedSearchType() {
      var checked = form.querySelector('input[name="search_type"]:checked');
      return (checked && checked.value) || 'title';
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
      params.set('search_type', selectedSearchType());
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

    function pickFormat(item) {
      var formats = item.formats || {};
      for (var i = 0; i < PREFERRED_FORMATS.length; i++) {
        if (formats[PREFERRED_FORMATS[i]]) {
          return PREFERRED_FORMATS[i];
        }
      }
      return Object.keys(formats)[0];
    }

    function addToLibrary(item, button) {
      var format = pickFormat(item);
      if (!format) {
        return;
      }
      button.disabled = true;
      button.textContent = 'Adding...';
      fetch(apiBase + '/bookshop/add', {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          provider: item.source.id,
          format: format,
          url: item.formats[format],
          title: item.title || '',
          authors: item.authors || [],
          description: (item.description || '').slice(0, 5000)
        })
      }).then(function (response) {
        if (response.status === 401) {
          throw new Error('not-authenticated');
        }
        if (response.status === 403) {
          throw new Error('no-permission');
        }
        if (!response.ok) {
          throw new Error('http-' + response.status);
        }
        return response.json();
      }).then(function (data) {
        var link = document.createElement('a');
        link.className = 'btn btn-success btn-xs bookshop-added';
        link.href = scriptRoot + (data.url || ('/book/' + data.book_id));
        link.textContent = 'Added - View in library';
        if (button.parentNode) {
          button.parentNode.replaceChild(link, button);
        }
      }).catch(function (err) {
        button.disabled = false;
        button.textContent = 'Add to library';
        var msg = 'Could not add this book.';
        if (err && err.message === 'not-authenticated') {
          msg = 'Your session has expired. Please sign in again.';
        } else if (err && err.message === 'no-permission') {
          msg = 'You do not have permission to add books to the library.';
        } else if (err && err.message === 'http-413') {
          msg = 'This book file is too large to add.';
        } else if (err && err.message === 'http-429') {
          msg = 'Too many requests. Please try again later.';
        }
        var status = document.createElement('span');
        status.className = 'bookshop-error bookshop-add-error';
        status.textContent = msg;
        if (button.parentNode) {
          button.parentNode.appendChild(status);
        }
      });
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

      if (allowUpload && formatKeys.length) {
        var actions = document.createElement('div');
        actions.className = 'bookshop-actions';
        var addButton = document.createElement('button');
        addButton.type = 'button';
        addButton.className = 'btn btn-success btn-xs bookshop-add';
        addButton.textContent = 'Add to library';
        addButton.addEventListener('click', function () {
          addToLibrary(item, addButton);
        });
        actions.appendChild(addButton);
        body.appendChild(actions);
      }

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
