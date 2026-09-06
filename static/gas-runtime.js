/**
 * gas-runtime.js — client runtime generated apps depend on.
 * - serverRun(): promise shim over google.script.run (async, 30s web-app budget)
 * - go()/goBack(): screen router
 * - state + updateBindings(): manual reactivity for transpiled property formulas
 * - val(): control accessor used by transpiled control references
 */
(function (global) {
  'use strict';

  var state = {};
  var evaluators = [];   // { fn, apply } — re-run on state change
  var handlers = {};     // controlName -> { event: fn }
  var controlValues = {}; // control name -> evaluated properties used by dependents
  var forms = {};        // form name -> generated DataCard submit configuration
  var screenStack = [];
  var CURRENT_SCREEN = null;
  var launchParameters = {};
  if (typeof document !== 'undefined') {
    var parameterElement = document.getElementById('fx-launch-parameters');
    if (parameterElement) launchParameters = JSON.parse(parameterElement.textContent || '{}');
  }

  function param(name) {
    var key = String(name == null ? '' : name);
    return Object.prototype.hasOwnProperty.call(launchParameters, key)
      ? String(launchParameters[key]) : null;
  }

  function serverRun(fn) {
    var args = Array.prototype.slice.call(arguments, 1);
    return new Promise(function (resolve, reject) {
      var settled = false;
      var timer = setTimeout(function () {
        if (!settled) { settled = true; reject(new Error('server call timed out (30s web-app budget): ' + fn)); }
      }, 29000);
      var runner = google.script.run
        .withSuccessHandler(function (result) {
          if (!settled) { settled = true; clearTimeout(timer); resolve(result); }
        })
        .withFailureHandler(function (err) {
          if (!settled) { settled = true; clearTimeout(timer); reject(err); }
        });
      runner[fn].apply(runner, args);
    });
  }

  function toast(msg, isError) {
    var el = document.getElementById('fx-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'fx-toast';
      document.body.appendChild(el);
    }
    el.textContent = String(msg == null ? '' : msg);
    el.className = isError ? 'fx-toast error' : 'fx-toast';
    el.style.display = 'block';
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { el.style.display = 'none'; }, 3500);
  }

  function updateBindings() {
    evaluators.forEach(function (e) {
      try {
        var result = e.apply();
        if (result && typeof result.catch === 'function') {
          result.catch(function (err) { console.error('binding error', err); });
        }
      } catch (err) { console.error('binding error', err); }
    });
  }

  function setState(patch) {
    Object.keys(patch).forEach(function (k) { state[k] = patch[k]; });
    updateBindings();
    return state;
  }

  function go(name) {
    if (CURRENT_SCREEN) screenStack.push(CURRENT_SCREEN);
    showScreen(name);
  }

  function goBack() {
    var prev = screenStack.pop();
    showScreen(prev || (document.querySelector('[data-screen]') || {}).getAttribute
      ? (prev || (document.querySelector('[data-screen]') || { getAttribute: function () { return null; } }).getAttribute('data-screen'))
      : null);
  }

  function showScreen(name) {
    if (!name) return;
    document.querySelectorAll('[data-screen]').forEach(function (el) {
      el.style.display = el.getAttribute('data-screen') === name ? '' : 'none';
    });
    CURRENT_SCREEN = name;
    var fn = handlers['__screen__' + name];
    if (fn) {
      Promise.resolve().then(fn).then(updateBindings).catch(function (e) {
        console.error(e);
        toast('Error: ' + (e && e.message ? e.message : e), true);
      });
    }
    updateBindings();
  }

  function bind(name, event, fn, parentName) {
    var el = document.querySelector('[data-control="' + name + '"]');
    if (!el) { console.warn('control not found for binding:', name); return; }
    el.addEventListener(event === 'OnSelect' ? 'click' : 'change', function () {
      var previousSelf = global.selfRef;
      var previousParent = global.parentRef;
      global.selfRef = val(name);
      global.parentRef = val(parentName);
      Promise.resolve().then(fn).then(updateBindings).catch(function (e) {
        console.error(e);
        toast('Error: ' + (e && e.message ? e.message : e), true);
      }).then(function () {
        global.selfRef = previousSelf;
        global.parentRef = previousParent;
      });
    });
  }

  function selectionRecord(row) {
    if (row === null || row === undefined) return null;
    return typeof row === 'object' ? row : { value: row };
  }

  function sameRecord(left, right) {
    left = selectionRecord(left); right = selectionRecord(right);
    if (!left || !right) return left === right;
    for (var i = 0; i < ['id', 'value', 'key'].length; i++) {
      var key = ['id', 'value', 'key'][i];
      if (left[key] !== undefined && right[key] !== undefined) {
        return String(left[key]) === String(right[key]);
      }
    }
    return JSON.stringify(left) === JSON.stringify(right);
  }

  function selectedRecords(el) {
    var rows = Array.isArray(el.__fxRecords) ? el.__fxRecords : [];
    var selected = [];
    Array.prototype.forEach.call(el.selectedOptions || [], function (option) {
      var raw = typeof option.getAttribute === 'function'
        ? option.getAttribute('data-fx-index') : null;
      var index = raw === null ? option.index : Number(raw);
      if (Number.isFinite(index) && rows[index] !== undefined) {
        selected.push(selectionRecord(rows[index]));
      }
    });
    if (!selected.length && Number.isFinite(el.selectedIndex) && el.selectedIndex >= 0
        && rows[el.selectedIndex] !== undefined) {
      selected.push(selectionRecord(rows[el.selectedIndex]));
    }
    if (!selected.length && el.value !== undefined) {
      var match = rows.find(function (row) {
        return String(optionRecord(row).value) === String(el.value);
      });
      if (match !== undefined) selected.push(selectionRecord(match));
    }
    return selected;
  }

  function val(name) {
    if (name === 'App') {
      return { active_screen: CURRENT_SCREEN };
    }
    var el = document.querySelector('[data-control="' + name + '"]')
      || document.querySelector('[data-screen="' + name + '"]');
    if (!el) return Object.assign(
      { text: '', value: '', selected: null, checked: false,
        width: 0, height: 0, x: 0, y: 0, fill: '', color: '', visible: false },
      controlValues[name] || {}
    );
    var isSelect = el.tagName === 'SELECT';
    var selectedRows = isSelect ? selectedRecords(el) : [];
    var selectedInfo = isSelect && selectedRows[0]
      ? optionRecord(selectedRows[0]) : { value: '', label: '' };
    var bounds = typeof el.getBoundingClientRect === 'function'
      ? el.getBoundingClientRect() : null;
    function numericStyle(name, fallback) {
      var parsed = parseFloat(el.style && el.style[name]);
      if (Number.isFinite(parsed)) return parsed;
      return Number.isFinite(fallback) ? fallback : 0;
    }
    var standard = {
      text: 'value' in el ? el.value : (el.textContent || ''),
      value: el.value !== undefined ? el.value : el.textContent,
      checked: !!el.checked,
      selected: selectedRows[0] || null,
      selected_items: selectedRows,
      selected_text: selectedRows[0] ? { value: selectedInfo.label } : null,
      selected_date: el.value ? el.value : null,
      width: numericStyle('width', bounds && bounds.width),
      height: numericStyle('height', bounds && bounds.height),
      x: numericStyle('left', bounds && bounds.left),
      y: numericStyle('top', bounds && bounds.top),
      fill: el.style && el.style.backgroundColor || '',
      color: el.style && el.style.color || '',
      visible: !el.style || el.style.display !== 'none',
      el: el,
    };
    return Object.assign(standard, controlValues[name] || {});
  }

  function optionRecord(row, displayFields) {
    if (row === null || row === undefined) return { value: '', label: '' };
    if (typeof row !== 'object') {
      var scalar = String(row);
      return { value: scalar, label: scalar };
    }
    function scalarAt(key) {
      var value = row[key];
      return value !== null && value !== undefined && typeof value !== 'object'
        ? String(value) : null;
    }
    function first(keys) {
      for (var i = 0; i < keys.length; i++) {
        var key = String(keys[i]);
        var variants = [key, key.charAt(0).toLowerCase() + key.slice(1),
          key.replace(/([a-z0-9])([A-Z])/g, '$1_$2').replace(/[^A-Za-z0-9]+/g, '_').toLowerCase()];
        for (var v = 0; v < variants.length; v++) {
          if (Object.prototype.hasOwnProperty.call(row, variants[v])) {
            var found = scalarAt(variants[v]);
            if (found !== null) return found;
          }
        }
      }
      return null;
    }
    var preferred = Array.isArray(displayFields) ? displayFields : [];
    var label = first(preferred.concat(['name', 'Name', 'label', 'Label', 'title', 'Title',
      'value', 'Value', 'category', 'Category', 'type', 'Type']));
    if (label === null) {
      var ownKeys = Object.keys(row).filter(function (key) { return key.slice(0, 2) !== '__'; });
      label = first(ownKeys);
    }
    if (label === null) label = JSON.stringify(row);
    var value = first(['value', 'Value', 'id', 'ID', 'key', 'Key']);
    return { value: value === null ? label : value, label: label };
  }

  function applyDefaultSelection(el, defaults) {
    var wanted = Array.isArray(defaults) ? defaults : [defaults];
    var rows = Array.isArray(el.__fxRecords) ? el.__fxRecords : [];
    Array.prototype.forEach.call(el.options || [], function (option, index) {
      option.selected = wanted.some(function (candidate) {
        return sameRecord(rows[index], candidate);
      });
    });
  }

  function registerControlProps(name, parentName, propertyFns) {
    var evaluator = {
      apply: function () {
        var next = Object.assign({}, controlValues[name] || {});
        controlValues[name] = next;
        var previousSelf = global.selfRef;
        var previousParent = global.parentRef;
        global.selfRef = val(name);
        global.parentRef = val(parentName);
        Object.keys(propertyFns || {}).forEach(function (key) {
          try { next[key] = propertyFns[key](); }
          catch (err) { console.error('control property error', name + '.' + key, err); }
        });
        global.selfRef = previousSelf;
        global.parentRef = previousParent;
        return next;
      },
    };
    evaluators.push(evaluator);
    evaluator.apply();
  }

  function styleControl(name, cssProp, valueFn, unit, parentName) {
    evaluators.push({
      apply: function () {
        var el = document.querySelector('[data-control="' + name + '"]');
        if (!el) return;
        var v;
        var previousSelf = global.selfRef;
        var previousParent = global.parentRef;
        global.selfRef = val(name);
        global.parentRef = val(parentName);
        try { v = valueFn(); } catch (e) { return; }
        finally { global.selfRef = previousSelf; global.parentRef = previousParent; }
        if (v === null || v === undefined || (v === '' && cssProp !== 'display')) return;
        if ((unit === 'px' || unit === 'pt') && /^\d+(\.\d+)?$/.test(String(v))) {
          v = String(v) + unit;
        }
        else if (unit === 'lower') v = String(v).toLowerCase();
        el.style[cssProp] = String(v);
      },
    });
  }

  function attrControl(name, attr, valueFn, parentName) {
    var evaluator = {
      apply: function () {
        var el = document.querySelector('[data-control="' + name + '"]');
        if (!el) return;
        var previousSelf = global.selfRef;
        var previousParent = global.parentRef;
        global.selfRef = val(name);
        global.parentRef = val(parentName);
        var value;
        try { value = valueFn(); }
        catch (err) { console.error('control attribute error', name + '.' + attr, err); return; }
        finally { global.selfRef = previousSelf; global.parentRef = previousParent; }
        value = value == null ? '' : String(value).trim();
        if (attr === 'src' && /^(?:javascript|vbscript):/i.test(value)) value = '';
        if (!value) {
          if (typeof el.removeAttribute === 'function') el.removeAttribute(attr);
          return;
        }
        if (el.getAttribute(attr) !== value && typeof el.setAttribute === 'function') {
          el.setAttribute(attr, value);
        }
        if (attr === 'src' && !el.__fxImageFallback) {
          el.__fxImageFallback = true;
          el.addEventListener('error', function () { el.removeAttribute('src'); });
        }
      },
    };
    evaluators.push(evaluator);
    evaluator.apply();
  }

  function sanitizeHtml(value) {
    var content = String(value == null ? '' : value);
    var previous = null;
    var unsafeBlock = /<(script|iframe|object|embed|link|meta)\b[^>]*>[\s\S]*?<\/\1\s*>/gi;
    while (previous !== content) {
      previous = content;
      content = content.replace(unsafeBlock, '');
    }
    content = content.replace(/<\/?(?:script|iframe|object|embed|link|meta)\b[^>]*>/gi, '');
    content = content.replace(/\s+on[a-z0-9_-]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '');
    content = content.replace(
      /\s+style\s*=\s*("[^"]*(?:javascript\s*:|expression\s*\()[^"]*"|'[^']*(?:javascript\s*:|expression\s*\()[^']*')/gi,
      ''
    );
    content = content.replace(
      /\s+(href|src)\s*=\s*(["']?)\s*(?:javascript|vbscript|data\s*:\s*text\/html)[^\s>]*\2/gi,
      ''
    );
    return content;
  }

  function htmlControl(name, valueFn, parentName) {
    var evaluator = {
      apply: function () {
        var el = document.querySelector('[data-control="' + name + '"]');
        if (!el) return;
        var previousSelf = global.selfRef;
        var previousParent = global.parentRef;
        global.selfRef = val(name);
        global.parentRef = val(parentName);
        try {
          var next = sanitizeHtml(valueFn());
          if (el.__fxHtml !== next) { el.__fxHtml = next; el.innerHTML = next; }
        } catch (err) { console.error('control html error', name, err); }
        finally { global.selfRef = previousSelf; global.parentRef = previousParent; }
      },
    };
    evaluators.push(evaluator);
    evaluator.apply();
  }

  function rowControl(row, name, parentName, propertyFns) {
    if (!row || typeof row.querySelector !== 'function') return;
    var el = row.querySelector('[data-control="' + name + '"]');
    if (!el) return;
    var previousSelf = global.selfRef;
    var previousParent = global.parentRef;
    global.selfRef = val(name);
    global.parentRef = val(parentName);
    var px = { left: true, top: true, width: true, height: true };
    try {
      Object.keys(propertyFns || {}).forEach(function (key) {
        var value = propertyFns[key]();
        if (key === 'text') {
          el.textContent = value == null ? '' : String(value);
        } else if (key === 'display') {
          el.style.display = value ? '' : 'none';
        } else if (key === 'fontSize') {
          el.style.fontSize = String(value == null ? '' : value) + 'pt';
        } else if (px[key]) {
          el.style[key] = String(value == null ? 0 : value) + 'px';
        } else {
          el.style[key] = value == null ? '' : String(value).toLowerCase();
        }
      });
    } catch (err) { console.error('gallery row property error', name, err); }
    finally { global.selfRef = previousSelf; global.parentRef = previousParent; }
  }

  /**
   * Gallery rendering: itemsFn returns the row array, rowFn fills a cloned
   * row template, handlers maps child control name -> async fn(item).
   * Re-renders on every state change (registered as an evaluator).
   */
  function gallery(name, itemsFn, rowFn, handlers) {
    evaluators.push({
      apply: function () {
        var host = document.querySelector('[data-control="' + name + '"]');
        if (!host || typeof host.querySelector !== 'function') return;
        var tpl = host.querySelector('template');
        var rowsEl = host.querySelector('.fx-rows');
        if (!tpl || !rowsEl) return;
        var items;
        try { items = itemsFn() || []; } catch (e) { items = []; }
        if (!Array.isArray(items)) items = [];
        var current = controlValues[name] && controlValues[name].selected;
        var selected = items.find(function (item) { return sameRecord(item, current); }) || null;
        controlValues[name] = Object.assign({}, controlValues[name] || {}, {
          all_items: items,
          selected: selected,
          selected_items: selected ? [selected] : [],
        });
        var rowMarkup = String(tpl.innerHTML || '').trim();
        rowsEl.innerHTML = items.map(function () { return rowMarkup; }).join('');
        var renderedRows = Array.prototype.slice.call(rowsEl.children || []);
        var templateSize = parseFloat(host.getAttribute('data-template-size'));
        var templatePadding = parseFloat(host.getAttribute('data-template-padding'));
        var wrapCount = parseInt(host.getAttribute('data-wrap-count'), 10);
        var galleryValue = val(name);
        controlValues[name] = Object.assign({}, controlValues[name] || {}, {
          template_size: Number.isFinite(templateSize) ? templateSize : 0,
          template_height: Number.isFinite(templateSize) ? templateSize : 0,
          template_width: galleryValue.width || 0,
          template_padding: Number.isFinite(templatePadding) ? templatePadding : 0,
        });
        if (rowsEl.style && Number.isFinite(wrapCount) && wrapCount > 1) {
          rowsEl.style.display = 'grid';
          rowsEl.style.gridTemplateColumns = 'repeat(' + wrapCount + ', minmax(0, 1fr))';
        }
        items.forEach(function (item, index) {
          var row = renderedRows[index];
          if (!row) return;
          row.style.position = 'relative';
          if (Number.isFinite(templateSize) && templateSize > 0) {
            row.style.minHeight = templateSize + 'px';
          }
          if (Number.isFinite(templatePadding) && templatePadding >= 0) {
            row.style.padding = templatePadding + 'px';
          }
          row.addEventListener('click', function () {
            controlValues[name] = Object.assign({}, controlValues[name] || {}, {
              selected: item,
              selected_items: [item],
            });
            updateBindings();
          });
          if (rowFn) {
            try { rowFn(item, row); } catch (e) { console.error('gallery row error', e); }
          }
          Object.keys(handlers || {}).forEach(function (ctrl) {
            var el = row.querySelector('[data-control="' + ctrl + '"]');
            if (el) {
              el.addEventListener('click', function () {
                Promise.resolve().then(function () { return handlers[ctrl](item); })
                  .catch(function (err) {
                    console.error(err);
                    toast('Error: ' + (err && err.message ? err.message : err), true);
                  });
              });
            }
          });
        });
      },
    });
  }

  function renderChart(name, rows, cfg) {
    var el = document.querySelector('[data-control="' + name + '"]');
    if (!el || !global.FXCharts) return null;
    rows = Array.isArray(rows) ? rows : [];
    cfg = cfg || {};
    var chart = global.FXCharts.model(rows, cfg);
    controlValues[name] = Object.assign({}, controlValues[name] || {}, {
      series_labels: chart.series,
      item_color_set: chart.series.map(function (entry) { return entry.color; }),
    });
    el.innerHTML = global.FXCharts.svg(rows, cfg);
    return chart;
  }

  function controlElement(name) {
    return document.querySelector('[data-control="' + name + '"]');
  }

  function formMode(value) {
    var mode = String(value == null ? 'edit' : value).toLowerCase();
    return mode === 'new' || mode === 'view' ? mode : 'edit';
  }

  function inControlContext(name, parentName, fn) {
    var previousSelf = global.selfRef;
    var previousParent = global.parentRef;
    global.selfRef = val(name);
    global.parentRef = val(parentName);
    try { return fn(); }
    finally {
      global.selfRef = previousSelf;
      global.parentRef = previousParent;
    }
  }

  function setInputValue(name, value, mode) {
    var el = controlElement(name);
    if (!el) return;
    if (el.__fxFormDisabled === undefined) el.__fxFormDisabled = !!el.disabled;
    if (el.__fxFormReadOnly === undefined) el.__fxFormReadOnly = !!el.readOnly;
    if (el.type === 'checkbox') el.checked = !!value;
    else el.value = value === null || value === undefined ? '' : String(value);
    el.disabled = mode === 'view' ? true : el.__fxFormDisabled;
    el.readOnly = mode === 'view' ? true : el.__fxFormReadOnly;
  }

  function setCardError(card, message) {
    var input = controlElement(card.input);
    var host = controlElement(card.name);
    if (input && typeof input.setAttribute === 'function') {
      input.setAttribute('aria-invalid', message ? 'true' : 'false');
    }
    if (host) {
      if (message && typeof host.setAttribute === 'function') host.setAttribute('data-fx-error', message);
      else if (typeof host.removeAttribute === 'function') host.removeAttribute('data-fx-error');
    }
    controlValues[card.name] = Object.assign({}, controlValues[card.name] || {}, {
      error: message || '',
    });
  }

  function currentFormItem(form) {
    var item = null;
    try { item = form.config.item ? form.config.item() : null; }
    catch (err) { console.error('form item error', form.name, err); }
    return item && typeof item === 'object' ? item : null;
  }

  function applyFormRecord(form, record) {
    record = record && typeof record === 'object' ? record : {};
    form.item = record;
    form.config.cards.forEach(function (card) {
      var required = false;
      try {
        required = !!inControlContext(card.name, form.name, card.required || function () { return false; });
      } catch (err) { console.error('form required error', card.name, err); }
      var value = Object.prototype.hasOwnProperty.call(record, card.field) ? record[card.field] : '';
      controlValues[card.name] = Object.assign({}, controlValues[card.name] || {}, {
        data_field: card.field,
        display_name: card.displayName || card.field,
        required: required,
        default: value,
        error: '',
        display_mode: form.mode === 'view' ? 'View' : 'Edit',
      });
      setInputValue(card.input, value, form.mode);
      setCardError(card, '');
    });
    controlValues[form.name] = Object.assign({}, controlValues[form.name] || {}, {
      mode: form.mode,
      valid: true,
      error: '',
      item: record,
      last_submit: form.lastSubmit || null,
    });
    state['__formMode_' + form.name] = form.mode;
  }

  function registerForm(name, config) {
    config = config || {};
    config.cards = Array.isArray(config.cards) ? config.cards : [];
    var initialMode = state['__formMode_' + name] || 'edit';
    try { initialMode = formMode(config.defaultMode ? config.defaultMode() : 'edit'); }
    catch (err) { console.error('form mode error', name, err); }
    if (state['__formMode_' + name]) initialMode = formMode(state['__formMode_' + name]);
    var form = forms[name] = {
      name: name,
      config: config,
      mode: initialMode,
      item: null,
      lastSubmit: null,
    };
    applyFormRecord(form, initialMode === 'new' ? {} : currentFormItem(form));
    return form;
  }

  function blankFormValue(value) {
    return value === null || value === undefined || value === ''
      || (Array.isArray(value) && value.length === 0);
  }

  function runFormCallback(form, name) {
    var callback = form.config[name];
    if (!callback) return Promise.resolve();
    return Promise.resolve().then(function () {
      return inControlContext(form.name, null, callback);
    });
  }

  async function submitForm(name) {
    var form = forms[name];
    if (!form) throw new Error('form not registered for SubmitForm: ' + name);
    if (form.mode === 'view') {
      controlValues[name].valid = false;
      controlValues[name].error = 'A view-only form cannot be submitted.';
      await runFormCallback(form, 'onFailure');
      updateBindings();
      return { ok: false, error: controlValues[name].error };
    }
    var record = {};
    var errors = [];
    form.config.cards.forEach(function (card) {
      var required = false;
      var value;
      try {
        required = !!inControlContext(card.name, name,
          card.required || function () { return false; });
        value = inControlContext(card.name, name, card.update);
      } catch (err) {
        errors.push((card.displayName || card.field) + ': ' + (err.message || err));
        return;
      }
      record[card.field] = value;
      var message = required && blankFormValue(value)
        ? (card.displayName || card.field) + ' is required.' : '';
      setCardError(card, message);
      if (message) errors.push(message);
    });
    if (errors.length) {
      controlValues[name].valid = false;
      controlValues[name].error = errors.join(' ');
      await runFormCallback(form, 'onFailure');
      updateBindings();
      return { ok: false, validation: true, error: controlValues[name].error };
    }
    try {
      var saved = form.mode === 'new'
        ? await global.apiCreate(form.config.dataSource, record)
        : await global.apiPatch(form.config.dataSource, form.item || {}, record);
      if (!saved || typeof saved !== 'object' || saved.ok === true) {
        saved = Object.assign({}, form.item || {}, record);
      }
      form.lastSubmit = saved;
      form.mode = 'edit';
      applyFormRecord(form, saved);
      await runFormCallback(form, 'onSuccess');
      updateBindings();
      return saved;
    } catch (err) {
      controlValues[name].valid = false;
      controlValues[name].error = err && err.message ? err.message : String(err);
      await runFormCallback(form, 'onFailure');
      updateBindings();
      return { ok: false, error: controlValues[name].error };
    }
  }

  function resetControl(name) {
    var el = document.querySelector('[data-control="' + name + '"]');
    if (!el) throw new Error('control not found for Reset: ' + name);
    var value = el.getAttribute('data-fx-default');
    if (el.type === 'checkbox') el.checked = value === 'true';
    else el.value = value === null ? '' : value;
    updateBindings();
    return value;
  }

  function setFormMode(name, mode) {
    var normalized = formMode(mode);
    var form = forms[name];
    if (!form) {
      state['__formMode_' + name] = normalized;
      updateBindings();
      return;
    }
    form.mode = normalized;
    applyFormRecord(form, normalized === 'new' ? {} : currentFormItem(form));
    updateBindings();
  }

  function resetForm(name) {
    var form = forms[name];
    if (!form) throw new Error('form not registered for ResetForm: ' + name);
    applyFormRecord(form, form.mode === 'new' ? {} : currentFormItem(form));
    updateBindings();
  }

  function exitApp() {
    // Web apps cannot close their tab reliably; show a farewell overlay.
    toast('You may now close this window.');
  }

  // User() equivalent. The server side injects the identity at deploy time:
  // Session.getActiveUser().getEmail() (empty for anonymous deployments).
  var _cachedUser = null;
  function fxUser() {
    if (_cachedUser) return _cachedUser;
    _cachedUser = { email: '', full_name: '', image: '' };
    serverRun('whoami').then(function (info) {
      _cachedUser = {
        email: info && info.email || '',
        full_name: info && info.fullName || '',
        image: info && info.pictureUrl || '',
      };
      updateBindings();
    }).catch(function () { /* anonymous deployment: blanks stand */ });
    return _cachedUser;
  }

  function refreshData(ds) {
    return serverRun('api', ds, 'list', {}).then(function (data) {
      state[ds] = data || [];
      updateBindings();
      return state[ds];
    });
  }

  // server data API used by transpiled Patch/Remove/Collect calls
  global.apiPatch = function (ds, base, record) {
    return serverRun('api', ds, 'patch', { base: base, record: record }).then(function (r) {
      return refreshData(ds).then(function () { return r; });
    });
  };
  global.apiRemove = function (ds, record) {
    return serverRun('api', ds, 'remove', { record: record }).then(function () { return refreshData(ds); });
  };
  global.apiRemoveIf = function (ds, pred) {
    if (typeof pred !== 'function') return Promise.reject(new Error('RemoveIf requires a predicate'));
    // Functions cannot cross google.script.run. Refresh the bounded local
    // table, evaluate the deterministic predicate client-side, then send only
    // explicit IDs. Empty matches never call the mutation endpoint.
    return refreshData(ds).then(function (rows) {
      var matches = (rows || []).filter(pred);
      if (!matches.length) return [];
      var ids = matches.map(function (row) { return row && row.id; });
      if (ids.some(function (id) { return id === undefined || id === null || id === ''; })) {
        throw new Error('RemoveIf requires an id column on every matching row');
      }
      return serverRun('api', ds, 'removeIf', { ids: ids })
        .then(function () { return refreshData(ds); });
    });
  };
  global.apiChoices = function (ds, field) {
    return serverRun('apiChoices', ds, field);
  };
  global.apiCreate = function (ds, record) {
    return serverRun('api', ds, 'create', { record: record }).then(function (r) {
      return refreshData(ds).then(function () { return r; });
    });
  };
  global.apiClearCollect = function (ds, record) {
    return apiCreate(ds, record);
  };

  // --- collection mutations (Power Apps collections are client-side state) --
  // The transpiler routes Collect/ClearCollect/Remove/RemoveIf against
  // collections to these; each takes (state, name, ...) so the generated
  // calls read powerapps_collect(state, 'Name', record), then fires a
  // binding update.
  global.powerapps_collect = function (st, ds) {
    var arr = st[ds] = st[ds] || [];
    for (var i = 2; i < arguments.length; i++) {
      var v = arguments[i];
      if (v == null) continue;
      if (Array.isArray(v)) { for (var j = 0; j < v.length; j++) arr.push(v[j]); }
      else arr.push(v);
    }
    updateBindings();
    return arr;
  };
  global.powerapps_clearCollect = function (st, ds) {
    st[ds] = [];
    return global.powerapps_collect.apply(null, arguments);
  };
  global.powerapps_remove = function (st, ds, record) {
    var arr = st[ds] = st[ds] || [];
    var idx = -1;
    for (var i = 0; i < arr.length; i++) { if (arr[i] === record) { idx = i; break; } }
    if (idx < 0) {
      for (var j = 0; j < arr.length; j++) {
        if (JSON.stringify(arr[j]) === JSON.stringify(record)) { idx = j; break; }
      }
    }
    if (idx >= 0) arr.splice(idx, 1);
    updateBindings();
    return arr;
  };
  global.powerapps_removeIf = function (st, ds, pred) {
    var arr = st[ds] = st[ds] || [];
    st[ds] = arr.filter(function (x) { return !pred(x); });
    updateBindings();
    return st[ds];
  };

  global.FXRuntime = {
    param: param,
    language: function () { return global.navigator && global.navigator.language || 'en-US'; },
    state: state,
    serverRun: serverRun,
    toast: toast,
    go: go,
    goBack: goBack,
    showScreen: showScreen,
    bind: bind,
    val: val,
    registerForm: registerForm,
    submitForm: submitForm,
    refreshData: refreshData,
    updateBindings: updateBindings,
    setState: setState,
    registerControlProps: registerControlProps,
    styleControl: styleControl,
    attrControl: attrControl,
    htmlControl: htmlControl,
    sanitizeHtml: sanitizeHtml,
    rowControl: rowControl,
    optionRecord: optionRecord,
    applyDefaultSelection: applyDefaultSelection,
    gallery: gallery,
    renderChart: renderChart,
    setFormMode: setFormMode,
    resetForm: resetForm,
    exitApp: exitApp,
    fxUser: fxUser,
    addEvaluator: function (apply) {
      evaluators.push({ apply: apply });
      try {
        var result = apply();
        if (result && typeof result.catch === 'function') {
          result.catch(function (err) { console.error('binding error', err); });
        }
      } catch (err) { console.error('binding error', err); }
    },
    registerScreenHandler: function (name, fn) { handlers['__screen__' + name] = fn; },
  };
  global.go = go;
  global.goBack = goBack;
  global.toast = toast;
  global.state = state;
  global.val = val;
  global.bind = bind;   // generated App.js calls bind('Ctrl', 'OnSelect', fn)
  global.submitForm = submitForm;
  global.resetForm = resetForm;
  global.resetControl = resetControl;
  global.refreshData = refreshData;
  global.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  global.selectControl = function (name) {
    var el = document.querySelector('[data-control="' + name + '"]');
    if (el) el.click();
  };
  global.selfRef = null; // bound per-control during evaluator registration
  global.parentRef = null;
  global.FXUser = fxUser;
  global.exitApp = exitApp;
  global.setFormMode = setFormMode;

  if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
      // A synchronous crash in APP_MAIN must not leave a blank page: catch,
      // surface, and still reveal the first screen (Power Apps start screen).
      var startup = typeof global.APP_MAIN === 'function'
        ? Promise.resolve().then(function () { return global.APP_MAIN(); })
        : Promise.resolve();
      startup.catch(function (e) {
        console.error(e);
        toast('Startup error: ' + (e && e.message ? e.message : e), true);
      }).then(function () {
        if (!CURRENT_SCREEN) {
          var first = document.querySelector('[data-screen]');
          if (first) showScreen(first.getAttribute('data-screen'));
        }
      });
    });
  }
})(typeof window !== 'undefined' ? window : globalThis);
