/* Bulk edit screen: search books, apply filename patterns, fetch metadata, save.
 * jQuery ajax is pre-configured by main.js to attach the CSRF header. */
/* global _ */

$(function () {
  'use strict';

  var bulkBase = window.bulkBase || '';
  var patterns = [];
  var metaTarget = null;

  function postJSON(url, data) {
    return $.ajax({
      url: bulkBase + url,
      type: 'POST',
      contentType: 'application/json; charset=utf-8',
      dataType: 'json',
      data: JSON.stringify(data || {})
    });
  }

  function badge(text) {
    var span = document.createElement('span');
    span.className = 'bulk-badge';
    span.textContent = text;
    return span;
  }

  function missingBadges(book) {
    var out = [];
    if (!book.isbn) { out.push('No ISBN'); }
    if (!book.authors) { out.push('No author'); }
    if (!book.has_cover) { out.push('No cover'); }
    return out;
  }

  function appendMissingBadges(container, book) {
    missingBadges(book).forEach(function (text) {
      var b = badge(text);
      b.classList.add('bulk-badge-missing');
      container.appendChild(b);
    });
  }

  function fieldRow(labelText, name, value, bookId) {
    var id = 'bulk-' + bookId + '-' + name;
    var wrap = document.createElement('div');
    wrap.className = 'bulk-field';
    var label = document.createElement('label');
    label.setAttribute('for', id);
    label.textContent = labelText;
    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-control';
    input.id = id;
    input.name = name;
    input.setAttribute('data-field', name);
    input.value = value || '';
    wrap.appendChild(label);
    wrap.appendChild(input);
    return wrap;
  }

  function fieldArea(labelText, name, value, bookId) {
    var id = 'bulk-' + bookId + '-' + name;
    var wrap = document.createElement('div');
    wrap.className = 'bulk-field bulk-field-wide';
    var label = document.createElement('label');
    label.setAttribute('for', id);
    label.textContent = labelText;
    var input = document.createElement('textarea');
    input.className = 'form-control';
    input.id = id;
    input.name = name;
    input.rows = 3;
    input.setAttribute('data-field', name);
    input.textContent = value || '';
    wrap.appendChild(label);
    wrap.appendChild(input);
    return wrap;
  }

  function actionButton(text, cls) {
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-default btn-xs bulk-btn ' + cls;
    button.textContent = text;
    return button;
  }

  function applyPatternControl() {
    var group = document.createElement('div');
    group.className = 'btn-group bulk-apply-group';

    var main = actionButton('Apply pattern', 'bulk-apply');

    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'btn btn-default btn-xs dropdown-toggle';
    toggle.setAttribute('data-toggle', 'dropdown');
    toggle.setAttribute('aria-haspopup', 'true');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Choose pattern to apply');
    var caret = document.createElement('span');
    caret.className = 'caret';
    var srLabel = document.createElement('span');
    srLabel.className = 'sr-only';
    srLabel.textContent = 'Select pattern';
    toggle.appendChild(caret);
    toggle.appendChild(srLabel);

    var menu = document.createElement('ul');
    menu.className = 'dropdown-menu bulk-apply-menu';
    menu.setAttribute('aria-label', 'Patterns to apply');

    group.appendChild(main);
    group.appendChild(toggle);
    group.appendChild(menu);
    return group;
  }

  function renderApplyMenus(scope) {
    $(scope || document).find('.bulk-apply-menu').each(function () {
      var menu = this;
      menu.innerHTML = '';
      if (!patterns.length) {
        var emptyLi = document.createElement('li');
        var emptyA = document.createElement('a');
        emptyA.href = '#';
        emptyA.textContent = 'No patterns yet';
        emptyLi.appendChild(emptyA);
        menu.appendChild(emptyLi);
        return;
      }
      patterns.forEach(function (p) {
        var li = document.createElement('li');
        var a = document.createElement('a');
        a.href = '#';
        a.setAttribute('data-pattern-id', p.id);
        a.textContent = p.name;
        li.appendChild(a);
        menu.appendChild(li);
      });
    });
  }

  function renderCard(book) {
    var card = document.createElement('article');
    card.className = 'bulk-card';
    card.setAttribute('data-book-id', book.book_id);

    var head = document.createElement('div');
    head.className = 'bulk-card-head';

    var titleLink = document.createElement('a');
    titleLink.className = 'bulk-card-title';
    titleLink.href = book.edit_url || '#';
    titleLink.target = '_blank';
    titleLink.rel = 'noopener noreferrer';
    titleLink.textContent = book.title || '';
    head.appendChild(titleLink);

    var badges = document.createElement('div');
    badges.className = 'bulk-card-badges';
    appendMissingBadges(badges, book);
    if (book.author_sort) {
      badges.appendChild(badge(book.author_sort));
    }
    if (book.series) {
      badges.appendChild(badge(book.series + (book.series_index ? ' #' + book.series_index : '')));
    }
    if (book.publisher || book.year) {
      badges.appendChild(badge([book.publisher, book.year].filter(Boolean).join(' \u00B7 ')));
    }
    if (book.filename) {
      var fileBadge = badge(book.filename);
      fileBadge.classList.add('bulk-badge-file');
      badges.appendChild(fileBadge);
    }
    head.appendChild(badges);
    card.appendChild(head);

    var actions = document.createElement('div');
    actions.className = 'bulk-card-actions';
    actions.appendChild(actionButton('Edit fields', 'bulk-toggle'));
    actions.appendChild(applyPatternControl());
    actions.appendChild(actionButton('Fetch metadata', 'bulk-meta'));
    card.appendChild(actions);

    var fields = document.createElement('form');
    fields.className = 'bulk-fields';
    fields.hidden = true;
    fields.appendChild(fieldRow('Title', 'title', book.title, book.book_id));
    fields.appendChild(fieldRow('Authors', 'authors', book.authors, book.book_id));
    fields.appendChild(fieldRow('ISBN', 'isbn', book.isbn, book.book_id));
    fields.appendChild(fieldRow('Series', 'series', book.series, book.book_id));
    fields.appendChild(fieldRow('Index', 'series_index', book.series_index, book.book_id));
    fields.appendChild(fieldRow('Publisher', 'publisher', book.publisher, book.book_id));
    fields.appendChild(fieldRow('Year', 'year', book.year || '', book.book_id));
    fields.appendChild(fieldArea('Description', 'description', book.description || '', book.book_id));

    var saveRow = document.createElement('div');
    saveRow.className = 'bulk-fields-actions';
    saveRow.appendChild(actionButton('Save', 'bulk-save btn-primary'));
    saveRow.appendChild(actionButton('Cancel', 'bulk-cancel'));
    fields.appendChild(saveRow);

    var statusP = document.createElement('p');
    statusP.className = 'bulk-row-status';
    statusP.id = 'bulk-status-' + book.book_id;
    statusP.setAttribute('role', 'status');
    statusP.setAttribute('aria-live', 'polite');
    statusP.setAttribute('aria-atomic', 'true');
    fields.appendChild(statusP);

    card.appendChild(fields);
    return card;
  }

  function renderCards(books) {
    var list = $('#bulk-results');
    list.empty();
    var fragment = document.createDocumentFragment();
    (books || []).forEach(function (book) {
      fragment.appendChild(renderCard(book));
    });
    list.append(fragment);
    renderApplyMenus(list.get(0));
    $('#bulk-status').text((books || []).length + ((books || []).length === 1 ? ' result' : ' results'));
  }

  function showRowStatus(card, message, isError) {
    var status = $(card).find('.bulk-row-status');
    status.text(message);
    status.toggleClass('bulk-row-status-error', !!isError);
  }

  function clearFieldErrors(card) {
    $(card).find('[data-field]').removeAttr('aria-invalid').removeAttr('aria-describedby');
  }

  function markFieldError(card, name, message) {
    var status = $(card).find('.bulk-row-status');
    var input = $(card).find('[data-field="' + name + '"]');
    input.attr('aria-invalid', 'true');
    if (status.length) { input.attr('aria-describedby', status.attr('id')); }
    showRowStatus(card, message, true);
  }

  function openFields(card) {
    $(card).find('.bulk-fields').prop('hidden', false);
    $(card).find('.bulk-fields input[data-field="title"]').trigger('focus');
  }

  function closeFields(card) {
    $(card).find('.bulk-fields').prop('hidden', true);
  }

  function fillFields(card, fields) {
    var $card = $(card);
    if (fields.title) { $card.find('input[data-field="title"]').val(fields.title); }
    if (fields.author) { $card.find('input[data-field="authors"]').val(fields.author); }
    if (fields.isbn) { $card.find('input[data-field="isbn"]').val(fields.isbn); }
    if (fields.series) { $card.find('input[data-field="series"]').val(fields.series); }
    if (fields.series_index) { $card.find('input[data-field="series_index"]').val(fields.series_index); }
    if (fields.publisher) { $card.find('input[data-field="publisher"]').val(fields.publisher); }
    if (fields.year) { $card.find('input[data-field="year"]').val(fields.year); }
  }

  function updateCardSummary(card, book) {
    var $card = $(card);
    $card.find('.bulk-card-title').text(book.title || '').attr('href', book.edit_url || '#');
    var badges = $card.find('.bulk-card-badges').empty();
    appendMissingBadges(badges.get(0), book);
    if (book.author_sort) { badges.append(badge(book.author_sort)); }
    if (book.series) { badges.append(badge(book.series + (book.series_index ? ' #' + book.series_index : ''))); }
    if (book.publisher || book.year) {
      badges.append(badge([book.publisher, book.year].filter(Boolean).join(' \u00B7 ')));
    }
    if (book.filename) {
      var fileBadge = badge(book.filename);
      fileBadge.classList.add('bulk-badge-file');
      badges.append(fileBadge);
    }
  }

  function extractError(xhr) {
    var msg = 'Something went wrong. Please try again.';
    if (xhr && xhr.responseJSON && xhr.responseJSON.error) {
      msg = xhr.responseJSON.error;
    } else if (xhr && xhr.responseText) {
      msg = xhr.responseText.slice(0, 300);
    }
    return msg;
  }

  function activeFilters() {
    return $('.bulk-filter-input:checked').map(function () {
      return this.value;
    }).get();
  }

  function searchBooks(term) {
    $('#bulk-status').text('Searching...');
    $('#bulk-results').empty().addClass('loading');
    postJSON('/admin/bulk/search', {term: term, filters: activeFilters()})
      .done(function (books) {
        $('#bulk-results').removeClass('loading');
        renderCards(books);
      })
      .fail(function (xhr) {
        $('#bulk-results').removeClass('loading');
        $('#bulk-status').text(extractError(xhr));
      });
  }

  function refreshResults() {
    var term = $('#bulk-query').val().trim();
    searchBooks(term);
  }

  // ---- filename patterns --------------------------------------------------

  function activePattern() {
    var id = $('#pattern-select').val();
    return patterns.filter(function (p) { return String(p.id) === String(id); })[0] || null;
  }

  function loadPatterns() {
    return $.getJSON(bulkBase + '/admin/bulk/patterns').done(function (data) {
      patterns = data || [];
      var $select = $('#pattern-select').empty();
      if (!patterns.length) {
        $select.append($('<option>').text('No patterns yet - add one below'));
      }
      patterns.forEach(function (p) {
        $select.append($('<option>').val(p.id).text(p.name + ' \u2014 ' + p.pattern));
      });
      renderPatternList();
      renderApplyMenus(document);
    }).fail(function () {
      $('#pattern-list').empty();
    });
  }

  function renderPatternList() {
    var $list = $('#pattern-list').empty();
    patterns.forEach(function (p) {
      var li = document.createElement('li');
      li.className = 'bulk-pattern-item';
      var name = document.createElement('span');
      name.className = 'bulk-pattern-name';
      name.textContent = p.name;
      var pat = document.createElement('code');
      pat.className = 'bulk-pattern-code';
      pat.textContent = p.pattern;
      var del = document.createElement('button');
      del.type = 'button';
      del.className = 'btn btn-danger btn-xs bulk-pattern-delete';
      del.textContent = 'Delete';
      del.setAttribute('data-pattern-id', p.id);
      li.appendChild(name);
      li.appendChild(pat);
      li.appendChild(del);
      $list.append(li);
    });
  }

  function testPattern() {
    var filename = $('#pattern-test-filename').val().trim();
    var pattern = activePattern();
    if (!filename) {
      $('#pattern-test-result').text('Enter a file name to test.');
      return;
    }
    if (!pattern) {
      $('#pattern-test-result').text('Select a pattern first.');
      return;
    }
    postJSON('/admin/bulk/parse', {pattern: pattern.pattern, filename: filename})
      .done(function (resp) {
        $('#pattern-test-filename').removeAttr('aria-invalid').removeAttr('aria-describedby');
        if (resp.error) {
          markInlineError('#pattern-test-filename', '#pattern-test-result', resp.error);
          return;
        }
        var parts = Object.keys(resp.fields || {}).map(function (key) {
          return key + ' = "' + resp.fields[key] + '"';
        });
        $('#pattern-test-result').text(parts.length ? parts.join(', ') : 'No fields parsed');
      })
      .fail(function (xhr) {
        markInlineError('#pattern-test-filename', '#pattern-test-result', extractError(xhr));
      });
  }

  function markInlineError(inputSel, statusSel, message) {
    $(inputSel).attr('aria-invalid', 'true').attr('aria-describedby', $(statusSel).attr('id'));
    $(statusSel).text(message);
  }

  // ---- card actions -------------------------------------------------------

  $(document).on('click', '.bulk-toggle', function () {
    var card = $(this).closest('.bulk-card');
    var form = card.find('.bulk-fields');
    form.prop('hidden', !form.prop('hidden'));
  });

  $(document).on('click', '.bulk-cancel', function () {
    closeFields($(this).closest('.bulk-card'));
  });

  function applyPatternToCard(card, pattern, button) {
    if (!pattern) {
      showRowStatus(card, 'Select a filename pattern first.', true);
      return;
    }
    var filename = card.find('.bulk-badge-file').text();
    if (!filename) {
      showRowStatus(card, 'This book has no file to match.', true);
      return;
    }
    if (button) { button.disabled = true; }
    var reenable = function () { if (button) { button.disabled = false; } };
    postJSON('/admin/bulk/parse', {pattern: pattern.pattern, filename: filename})
      .done(function (resp) {
        reenable();
        if (resp.error) {
          showRowStatus(card, resp.error, true);
          return;
        }
        fillFields(card, resp.fields);
        openFields(card);
        showRowStatus(card, 'Fields filled from file name - review and save.', false);
      })
      .fail(function (xhr) {
        reenable();
        showRowStatus(card, extractError(xhr), true);
      });
  }

  $(document).on('click', '.bulk-apply', function () {
    var card = $(this).closest('.bulk-card');
    applyPatternToCard(card, activePattern(), this);
  });

  $(document).on('click', '.bulk-apply-menu a[data-pattern-id]', function (e) {
    e.preventDefault();
    var card = $(this).closest('.bulk-card');
    var id = this.getAttribute('data-pattern-id');
    var pattern = patterns.filter(function (p) { return String(p.id) === String(id); })[0];
    applyPatternToCard(card, pattern, null);
  });

  $(document).on('click', '.bulk-save', function () {
    var card = $(this).closest('.bulk-card');
    var fields = {};
    ['title', 'authors', 'isbn', 'series', 'series_index', 'publisher', 'year', 'description'].forEach(function (name) {
      var el = card.find('[data-field="' + name + '"]');
      if (el.length) { fields[name] = el.val(); }
    });
    var seriesIndex = String(fields.series_index || '').trim();
    if (seriesIndex && !/^[0-9]*\.?[0-9]+$/.test(seriesIndex)) {
      markFieldError(card, 'series_index', 'Series index must be a number - not saved.');
      return;
    }
    clearFieldErrors(card);
    var button = this;
    button.disabled = true;
    postJSON('/admin/bulk/save', {book_id: card.data('book-id'), fields: fields})
      .done(function (book) {
        button.disabled = false;
        updateCardSummary(card, book);
        closeFields(card);
        if (activeFilters().length) {
          // A filter is active: the book may no longer match, so refresh the queue.
          showRowStatus(card, 'Saved.', false);
          refreshResults();
        } else {
          showRowStatus(card, 'Saved.', false);
        }
      })
      .fail(function (xhr) {
        button.disabled = false;
        showRowStatus(card, extractError(xhr), true);
      });
  });

  // ---- metadata fetch -----------------------------------------------------

  function loadProviders() {
    $('#bulk-metadata-provider').empty();
    $.getJSON(bulkBase + '/metadata/provider').done(function (data) {
      (data || []).forEach(function (provider) {
        var label = document.createElement('label');
        label.className = 'bulk-pill';
        var input = document.createElement('input');
        input.type = 'checkbox';
        input.className = 'bulk-pill-input';
        input.checked = !!provider.active;
        input.setAttribute('data-provider', provider.id);
        var span = document.createElement('span');
        span.textContent = provider.name;
        label.appendChild(input);
        label.appendChild(span);
        $('#bulk-metadata-provider').append(label);
      });
    });
  }

  $(document).on('change', '.bulk-pill-input', function () {
    var id = this.getAttribute('data-provider');
    postJSON('/metadata/provider/' + id, {id: id, value: this.checked});
  });

  function renderMetaResults(data) {
    var $info = $('#bulk-meta-info');
    if (!(data && data.length)) {
      $info.html('<p class="text-danger">No results found.</p>');
      return;
    }
    var template = _.template($('#template-bulk-meta-result').html());
    var $list = $('<ul class="media-list bulk-meta-list"></ul>');
    data.forEach(function (book) {
      var $item = $(template(book));
      $item.data('record', book);
      $list.append($item);
    });
    $info.empty().append($list);
  }

  function doMetaSearch(keyword) {
    if (!keyword) { return; }
    $('#bulk-meta-info').text('Loading...');
    $.post(bulkBase + '/metadata/search', {query: keyword})
      .done(renderMetaResults)
      .fail(function () {
        $('#bulk-meta-info').html('<p class="text-danger">Search failed. Please try again.</p>');
      });
  }

  $(document).on('click', '.bulk-meta', function () {
    metaTarget = $(this).closest('.bulk-card');
    var title = metaTarget.find('input[data-field="title"]').val() ||
      metaTarget.find('.bulk-card-title').text().trim();
    $('#bulk-keyword').val(title);
    loadProviders();
    $('#bulkMetaModal').modal('show');
    doMetaSearch(title);
  });

  $('#bulk-meta-search').on('submit', function (e) {
    e.preventDefault();
    doMetaSearch($('#bulk-keyword').val().trim());
  });

  $(document).on('click', '.bulk-meta-apply', function () {
    if (!metaTarget) { return; }
    var $item = $(this).closest('.bulk-meta-item');
    var data = $item.data('record');
    if (!data) { return; }
    var fill = {};
    if (data.title) { fill.title = data.title; }
    if (data.authors && data.authors.length) { fill.author = data.authors.join(' & '); }
    if (data.series) { fill.series = data.series; }
    if (data.series_index) { fill.series_index = String(data.series_index); }
    if (data.publisher) { fill.publisher = data.publisher; }
    if (data.identifiers && data.identifiers.isbn) { fill.isbn = String(data.identifiers.isbn); }
    if (data.publishedDate) { fill.year = String(data.publishedDate).slice(0, 4); }
    fillFields(metaTarget, fill);
    if (data.description) { metaTarget.find('textarea[data-field="description"]').val(data.description); }
    openFields(metaTarget);
    $('#bulkMetaModal').modal('hide');
    showRowStatus(metaTarget, 'Metadata filled from catalog - review and save.', false);
  });

  // ---- events -------------------------------------------------------------

  $('#bulk-search').on('submit', function (e) {
    e.preventDefault();
    searchBooks($('#bulk-query').val().trim());
  });

  $('#pattern-select').on('change', function () {
    // Nothing to do; the selected pattern is read at apply time.
  });

  $('.bulk-filter-input').on('change', function () {
    refreshResults();
  });

  $('#pattern-test').on('click', testPattern);

  $('#pattern-add').on('submit', function (e) {
    e.preventDefault();
    var name = $('#pattern-name').val().trim();
    var pattern = $('#pattern-text').val().trim();
    $('#pattern-text').removeAttr('aria-invalid').removeAttr('aria-describedby');
    if (!name || !pattern) {
      markInlineError('#pattern-text', '#pattern-add-status', 'Name and pattern are required.');
      return;
    }
    postJSON('/admin/bulk/patterns', {name: name, pattern: pattern})
      .done(function () {
        $('#pattern-name').val('');
        $('#pattern-text').val('');
        $('#pattern-add-status').text('');
        $('#pattern-text').removeAttr('aria-invalid').removeAttr('aria-describedby');
        loadPatterns();
      })
      .fail(function (xhr) {
        markInlineError('#pattern-text', '#pattern-add-status', extractError(xhr));
      });
  });

  $(document).on('click', '.bulk-pattern-delete', function () {
    var id = this.getAttribute('data-pattern-id');
    var button = this;
    $.ajax({
      url: bulkBase + '/admin/bulk/patterns/' + id,
      type: 'DELETE',
      dataType: 'json'
    }).done(function () {
      loadPatterns();
    }).fail(function (xhr) {
      $(button).closest('.bulk-pattern-item').append(
        $('<span class="bulk-hint bulk-hint-error">').text(extractError(xhr))
      );
    });
  });

  $('#bulkMetaModal').on('hidden.bs.modal', function () {
    metaTarget = null;
  });

  // Initial state: show the most recent books so the screen is immediately useful.
  loadPatterns();
  searchBooks('');
});
