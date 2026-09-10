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
  var screenContexts = Object.create(null);
  var evaluators = [];   // { fn, apply } — re-run on state change
  var cardLayouts = [], cardGeometry = {}, galleryLayouts = [];
  var handlers = {};     // controlName -> { event: fn }
  var controlValues = {}; // control name -> evaluated properties used by dependents
  var controlNodes = new WeakMap();
  var controlProperties = Object.create(null), resolvingProperties = [];
  var galleryTemplates = Object.create(null), resolvingTemplates = [];
  var forms = {};        // form name -> generated DataCard submit configuration
  var timers = {};       // timer name -> resettable scheduling state
  var screenStack = [];
  var CURRENT_SCREEN = null;
  var navigationRevision = 0;
  var launchParameters = {};
  var storageContext = null;
  var canvas = {layout: {}, app: {}, screens: {}, refs: {}, resolving: []};
  var resizeInstalled = false;
  if (typeof document !== 'undefined') {
    var parameterElement = document.getElementById('fx-launch-parameters');
    if (parameterElement) launchParameters = JSON.parse(parameterElement.textContent || '{}');
    var storageElement = document.getElementById('fx-storage-context');
    if (storageElement) storageContext = JSON.parse(storageElement.textContent || '{}');
  }

  function param(name) {
    var key = String(name == null ? '' : name);
    return Object.prototype.hasOwnProperty.call(launchParameters, key)
      ? String(launchParameters[key]) : null;
  }

  function cacheAccess() {
    if (!storageContext || typeof storageContext.appId !== 'string' || !storageContext.appId)
      throw new Error('App storage identity is unavailable; open the deployed app to use SaveData/LoadData');
    var storage;
    try { storage = global.localStorage; } catch (err) {
      throw new Error('Browser storage is unavailable: ' + err.message);
    }
    if (!storage) throw new Error('Browser storage is unavailable');
    return {storage: storage, prefix: 'pfx2gas:cache:v1:' +
      encodeURIComponent(JSON.stringify([storageContext.appId, storageContext.user || ''])) + ':'};
  }

  function cacheName(name) {
    if (typeof name !== 'string' || !name || /[*".?:\\<>|/]/.test(name))
      throw new Error('SaveData/LoadData storage name is empty or contains a forbidden character');
    return encodeURIComponent(name);
  }

  // Tagged values preserve nested records/tables, dates, and Blank without
  // guessing whether ordinary strings happen to look like dates or type tags.
  function packCache(value, ancestors) {
    if (value == null) return ['blank'];
    if (value instanceof Date) {
      if (!isFinite(value.getTime())) throw new Error('Cannot save an invalid date');
      return ['date', value.toISOString()];
    }
    if (typeof value === 'number' && !isFinite(value)) throw new Error('Cannot save a non-finite number');
    if (['string', 'number', 'boolean'].indexOf(typeof value) >= 0) return [typeof value, value];
    if (typeof value !== 'object') throw new Error('Cannot save this value type');
    if (ancestors.indexOf(value) >= 0) throw new Error('Cannot save circular data');
    var path = ancestors.concat([value]);
    if (Array.isArray(value)) return ['table', value.map(function (item) { return packCache(item, path); })];
    return ['record', Object.keys(value).map(function (key) { return [key, packCache(value[key], path)]; })];
  }

  function unpackCache(value) {
    if (!Array.isArray(value)) throw new Error('Invalid cached value');
    var type = value[0], data = value[1];
    if (type === 'blank' && value.length === 1) return null;
    if (value.length !== 2) throw new Error('Invalid cached value');
    if (['string', 'number', 'boolean'].indexOf(type) >= 0 && typeof data === type) {
      if (type === 'number' && !isFinite(data)) throw new Error('Invalid cached number');
      return data;
    }
    if (type === 'date' && typeof data === 'string' && isFinite(new Date(data).getTime())) return new Date(data);
    if (type === 'table' && Array.isArray(data)) return data.map(unpackCache);
    if (type === 'record' && Array.isArray(data)) {
      var record = {};
      data.forEach(function (field) {
        if (!Array.isArray(field) || field.length !== 2 || typeof field[0] !== 'string' ||
            Object.prototype.hasOwnProperty.call(record, field[0])) throw new Error('Invalid cached field');
        Object.defineProperty(record, field[0], {value: unpackCache(field[1]), enumerable: true, writable: true, configurable: true});
      });
      return record;
    }
    throw new Error('Invalid cached value type');
  }

  function saveData(collection, name) {
    var cache = cacheAccess(), key = cache.prefix + cacheName(name);
    if (!Array.isArray(collection)) throw new Error('SaveData requires a collection');
    var text = JSON.stringify({version: 1, rows: packCache(collection, [])});
    if (new TextEncoder().encode(text).length > 1048576)
      throw new Error('SaveData exceeds the 1 MB browser cache limit');
    cache.storage.setItem(key, text); // quota/access failures must reach IfError
    return null;
  }

  function loadData(collectionName, name, ignoreMissing) {
    var cache = cacheAccess(), key = cache.prefix + cacheName(name);
    var text = cache.storage.getItem(key);
    if (text === null) {
      if (!ignoreMissing) throw new Error('No saved data named ' + name);
      return null;
    }
    var saved;
    try {
      var envelope = JSON.parse(text);
      if (!envelope || envelope.version !== 1) throw new Error('Unknown cache version');
      saved = unpackCache(envelope.rows);
      if (!Array.isArray(saved)) throw new Error('Cached data is not a collection');
    } catch (err) { throw new Error('Saved data is corrupt or incompatible: ' + name + ' (' + err.message + ')'); }
    var current = state[collectionName];
    if (current != null && !Array.isArray(current)) throw new Error('LoadData requires a collection');
    var update = {};
    var restored = global.FX.collections.prepare(state, collectionName, saved);
    Object.defineProperty(update, collectionName, {value: (current || []).concat(restored), enumerable: true});
    setState(update); // append atomically only after all cached values validate
    return null;
  }

  function clearData(name) {
    var cache = cacheAccess();
    if (arguments.length) cache.storage.removeItem(cache.prefix + cacheName(name));
    else {
      var keys = [];
      for (var i = 0; i < cache.storage.length; i++) {
        var key = cache.storage.key(i);
        if (key && key.indexOf(cache.prefix) === 0) keys.push(key);
      }
      keys.forEach(function (key) { cache.storage.removeItem(key); });
    }
    return null;
  }

  // google.script.run accepts plain records/arrays, but rejects Date even
  // inside a nested record. Keep the instant as ISO text without mutating
  // client state; malformed values must reach the source's IfError.
  function wireValue(value, ancestors) {
    if (value == null) return null;
    if (value instanceof Date) {
      if (!isFinite(value.getTime())) throw new Error('Cannot send an invalid date');
      return value.toISOString();
    }
    if (typeof value === 'string' || typeof value === 'boolean') return value;
    if (typeof value === 'number' && isFinite(value)) return value;
    if (typeof value !== 'object' || (!Array.isArray(value) && Object.prototype.toString.call(value) !== '[object Object]') || value.nodeType)
      throw new Error('Unsupported Apps Script argument type');
    if (ancestors.indexOf(value) >= 0) throw new Error('Cannot send circular data');
    var path = ancestors.concat([value]);
    if (Array.isArray(value)) return value.map(function (item) { return wireValue(item, path); });
    var record = {};
    Object.keys(value).forEach(function (key) {
      Object.defineProperty(record, key, {value: wireValue(value[key], path), enumerable: true});
    });
    return record;
  }

  function serverRun(fn) {
    var args = Array.prototype.slice.call(arguments, 1);
    return new Promise(function (resolve, reject) {
      args = wireValue(args, []);
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
      try { runner[fn].apply(runner, args); }
      catch (err) { settled = true; clearTimeout(timer); reject(err); }
    });
  }

  var serviceAdapters = Object.create(null), connectorCache = new Map();
  function configureServices(contracts) {
    serviceAdapters = contracts || Object.create(null);
    connectorCache.clear();
  }
  function connectorContract(service, operation, args) {
    var adapter = Object.prototype.hasOwnProperty.call(serviceAdapters, service) && serviceAdapters[service];
    var contract = adapter && Object.prototype.hasOwnProperty.call(adapter.operations, operation) && adapter.operations[operation];
    if (!contract) throw new Error('Google adapter operation is not configured: ' + service + '.' + operation);
    if (!Array.isArray(args) || contract.arity.indexOf(args.length) < 0) throw new Error('Wrong number of connector arguments: ' + operation);
    return contract;
  }
  function refreshConnector(service) {
    connectorCache.forEach(function (entry, key) { if (entry.service === service) connectorCache.delete(key); });
    updateBindings();
    return null;
  }
  async function connectorCall(service, operation, args) {
    var contract = connectorContract(service, operation, args);
    try { return await serverRun('connector', service, operation, args); }
    finally {
      // A failed transport/flush can follow a successful write. Invalidate,
      // but never retry a mutation implicitly and risk duplicate task creation.
      if (contract.write) refreshConnector(service);
    }
  }
  function connectorRead(service, operation, args) {
    if (connectorContract(service, operation, args).write) throw new Error('Connector writes require a behavior formula');
    var wire = wireValue(args, []), key = JSON.stringify([service, operation, wire]);
    var entry = connectorCache.get(key);
    if (!entry) {
      entry = {service:service, value:null, error:null};
      connectorCache.set(key, entry);
      serverRun('connector', service, operation, wire).then(function (value) {
        if (connectorCache.get(key) !== entry) return; // Discard stale in-flight snapshots.
        entry.value = value;
        updateBindings();
      }, function (error) {
        if (connectorCache.get(key) !== entry) return;
        entry.error = error instanceof Error ? error : new Error(error && error.message || String(error));
        // Re-evaluation throws into the source's IfError (when present).
        // Unhandled failures reach the ordinary binding-error reporting path.
        updateBindings();
      });
    }
    if (entry.error) throw entry.error;
    return entry.value;
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
    updateCanvas();
    var changed, pass = 0;
    do {
      evaluators.forEach(function (e) {
        try {
          var result = e.apply();
          if (result && typeof result.catch === 'function') {
            result.catch(function (err) { console.error('binding error', err); });
          }
        } catch (err) { console.error('binding error', err); }
      });
      galleryLayouts.forEach(function (layout) {
        try { layout(); } catch (error) { console.error('gallery layout error', error); }
      });
      changed = false;
      cardLayouts.forEach(function (layout) {
        try { changed = layout() || changed; }
        catch (error) { console.error('card layout error', error); }
      });
    } while (changed && ++pass < 8);
    if (changed) console.error('card layout did not settle after 8 passes');
  }

  function setState(patch) {
    Object.keys(patch).forEach(function (k) { state[k] = patch[k]; });
    updateBindings();
    return state;
  }

  function configureContexts(definitions) {
    screenContexts = Object.create(null);
    Object.keys(definitions || {}).forEach(function (screen) {
      var context = screenContexts[screen] = Object.create(null);
      definitions[screen].forEach(function (name) { context[String(name).toLowerCase()] = null; });
    });
  }

  function variable(screen, key, fallback) {
    var context = screenContexts[screen], name = String(key).toLowerCase();
    return context && Object.prototype.hasOwnProperty.call(context, name) ? context[name]
      : typeof fallback === 'function' ? fallback() : null;
  }

  function applyContext(screen, patch) {
    if (!screen) throw new Error('UpdateContext requires a screen');
    if (!patch || typeof patch !== 'object' || Array.isArray(patch) || patch instanceof Date)
      throw new Error('Screen context must be a record');
    var context = screenContexts[screen] || (screenContexts[screen] = Object.create(null));
    Object.keys(patch).forEach(function (name) { context[name.toLowerCase()] = patch[name]; });
  }

  function updateContext(screen, patch) {
    applyContext(screen || CURRENT_SCREEN, patch);
    updateBindings();
    return null;
  }

  function navigationTarget(target) {
    if (target && typeof target === 'object') {
      var el = target.el;
      var screen = el && typeof el.closest === 'function' && el.closest('[data-screen]');
      target = screen ? screen.getAttribute('data-screen') : target.name;
    }
    if (typeof target !== 'string' || !target) return null;
    if (Object.keys(canvas.screens).length && !Object.prototype.hasOwnProperty.call(canvas.screens, target)) return null;
    return target;
  }

  function go(name, contextPatch) {
    name = navigationTarget(name);
    if (!name) return false;
    // Evaluate the source record at the call site, then update only the target
    // screen before any target bindings or OnVisible handler can read it.
    if (contextPatch !== undefined) applyContext(name, contextPatch);
    if (CURRENT_SCREEN) screenStack.push(CURRENT_SCREEN);
    showScreen(name);
    return true;
  }

  function goBack() {
    var prev = screenStack.pop();
    if (!prev) return false;
    showScreen(prev);
    return true;
  }

  function showScreen(name) {
    if (!name) return;
    var previous = CURRENT_SCREEN, revision = ++navigationRevision;
    document.querySelectorAll('[data-screen]').forEach(function (el) {
      el.style.display = el.getAttribute('data-screen') === name ? '' : 'none';
    });
    CURRENT_SCREEN = name;
    var hidden = previous && previous !== name && handlers['__hidden__' + previous];
    var visible = handlers['__screen__' + name];
    if (hidden || visible) {
      Promise.resolve().then(function () {
        if (hidden) return hidden(val, val(previous), val('App'));
      }).then(function () {
        // A later navigation owns the visible screen. Never run an obsolete
        // OnVisible after an earlier screen's awaited exit work completes.
        if (visible && revision === navigationRevision) return visible(val, val(name), val('App'));
      }).then(updateBindings).catch(function (e) {
        console.error(e);
        toast('Error: ' + (e && e.message ? e.message : e), true);
      });
    }
    updateBindings();
  }

  function listen(el, event, callback) {
    (el.__fxListeners || (el.__fxListeners = [])).push({event:event, callback:callback});
    el.addEventListener(event, callback);
  }

  function bind(name, event, fn, parentName) {
    var el = controlElement(name);
    if (!el) { console.warn('control not found for binding:', name); return; }
    listen(el, event === 'OnSelect' ? 'click' : 'change', function () {
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

  function dateInputText(value) {
    if (value === null || value === undefined || value === '') return '';
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
      dateInputValue({value:value}); return value;
    }
    var date = value instanceof Date ? value :
      typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value) ? new Date(value) : null;
    if (!date || !Number.isFinite(date.getTime())) throw new Error('Date picker requires a valid date');
    return String(date.getFullYear()).padStart(4, '0') + '-' + String(date.getMonth()+1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
  }

  function dateInputValue(el) {
    if (!el.value) return null;
    var parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(el.value);
    if (!parts) throw new Error('Invalid date picker value');
    var date = new Date(0); date.setFullYear(Number(parts[1]), Number(parts[2])-1, Number(parts[3]));
    date.setHours(0,0,0,0);
    if (dateInputText(date) !== el.value) throw new Error('Invalid date picker value');
    return date;
  }

  function val(name, element) {
    if (name === 'App') {
      return canvasRef('App');
    }
    if (!element && Object.prototype.hasOwnProperty.call(canvas.screens, name)) return canvasRef(name);
    var el = element || controlElement(name)
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
    var bounds, measured = false;
    function numericStyle(name, dimension) {
      var parsed = parseFloat(el.style && el.style[name]);
      if (Number.isFinite(parsed)) return parsed;
      // Generated controls usually have all four dimensions inline. Measuring
      // every reference after style writes forces a layout for every formula,
      // even when its measured rectangle would never be used.
      if (!measured) {
        bounds = typeof el.getBoundingClientRect === 'function' ? el.getBoundingClientRect() : null;
        measured = true;
      }
      var fallback = bounds && bounds[dimension];
      return Number.isFinite(fallback) ? fallback : 0;
    }
    var standard = {
      text: ['INPUT', 'SELECT', 'TEXTAREA'].indexOf(el.tagName) >= 0 ? el.value : (el.textContent || ''),
      value: el.type === 'date' && el.getAttribute('data-fx-date-value') === 'local' ? dateInputValue(el)
        : el.type === 'checkbox' ? !!el.checked : el.type === 'range' ? Number(el.value)
        : el.value !== undefined ? el.value : el.textContent,
      checked: !!el.checked,
      selected: selectedRows[0] || null,
      selected_items: selectedRows,
      selected_text: selectedRows[0] ? { value: selectedInfo.label } : null,
      selected_date: el.type === 'date' ? dateInputValue(el) : el.value ? el.value : null,
      width: numericStyle('width', 'width'),
      height: numericStyle('height', 'height'),
      x: numericStyle('left', 'left'),
      y: numericStyle('top', 'top'),
      fill: el.style && el.style.backgroundColor || '',
      color: el.style && el.style.color || '',
      accessible_label: typeof el.getAttribute === 'function' ? el.getAttribute('aria-label') || '' : '',
      tooltip: typeof el.getAttribute === 'function' ? el.getAttribute('title') || '' : '',
      visible: !el.style || el.style.display !== 'none',
      el: el,
    };
    var liveProperties = new Set(Object.keys(standard));
    ['template_size','template_width','template_height','template_padding'].forEach(function (key) { liveProperties.add(key); });
    Object.assign(standard, element ? (element.__fxValues || {}) : (controlValues[name] || {}),
      el.__fxValues || {}, element ? {} : (cardGeometry[name] || {}));
    var scoped = el.__fxProperties;
    var definitions = scoped || (!element && controlProperties[name]);
    if (scoped && ['INPUT','SELECT','TEXTAREA'].indexOf(el.tagName) < 0) {
      // A label's Text is a formula, including when a later sibling has not
      // painted yet. Editable input text must continue to come from the DOM.
      liveProperties.delete('text');
    }
    if (definitions) Object.keys(definitions.fns).forEach(function (key) {
      if (liveProperties.has(key)) return; // DOM input values and geometry retain their live contract.
      var resolved = false, value;
      Object.defineProperty(standard, key, {enumerable:true, configurable:true, get:function () {
        if (resolved) return value;
        var label = name + '.' + key;
        var reference = scoped ? (scoped.tokens[key] || (scoped.tokens[key] = {})) : label;
        if (resolvingProperties.includes(reference)) throw new Error('Circular control property: ' + label);
        resolvingProperties.push(reference);
        try {
          value = scoped ? definitions.fns[key](scoped.read, standard, scoped.read(definitions.parent))
            : inControlContext(name, definitions.parent, definitions.fns[key]);
          resolved = true; return value;
        }
        finally { resolvingProperties.pop(); }
      }});
    });
    if (el.__fxAllItems) {
      Object.defineProperties(standard, {
        all_items: {enumerable:true, get:el.__fxAllItems},
        all_items_count: {enumerable:true, get:function () { return el.__fxAllItems().length; }},
      });
    }
    // Resolve TemplateSize lazily, before Items mounts rows and independently
    // of control registration order. Responsive formulas must also update the
    // derived dimensions; a stale/absent HTML attribute is not their source.
    var template = el.__fxGalleryTemplate || (!element && galleryTemplates[name]);
    if (template || (typeof el.getAttribute === 'function' && el.getAttribute('data-template-size') !== null)) {
      Object.defineProperty(standard, 'template_size', {enumerable: true, get: function () {
        if (!template) return Number(el.getAttribute('data-template-size')) || 0;
        var token = el.__fxGalleryTemplate ? el : name;
        if (resolvingTemplates.indexOf(token) >= 0) throw new Error('Circular gallery TemplateSize: ' + name);
        resolvingTemplates.push(token);
        try {
          var read = template.read || val;
          var size = Number(template.fn(read, standard, read(template.parent)));
          if (!Number.isFinite(size)) throw new Error('Non-finite gallery TemplateSize: ' + name);
          return Math.max(1, size);
        } finally { resolvingTemplates.pop(); }
      }});
      standard.template_padding = Number(el.getAttribute('data-template-padding')) || 0;
      var horizontal = el.getAttribute('data-gallery-layout') === 'horizontal';
      var wraps = Math.max(1, Number(el.getAttribute('data-wrap-count')) || 1);
      Object.defineProperties(standard, {
        template_width: {enumerable: true, get: function () { return horizontal ? standard.template_size : standard.width; }},
        template_height: {enumerable: true, get: function () { return horizontal
          ? Math.max(0,(standard.height-standard.template_padding*(wraps+1))/wraps) : standard.template_size; }},
      });
    }
    var primary = typeof el.getAttribute === 'function' ? el.getAttribute('data-fx-primary-output') : null;
    return primary ? FX.controlReference(standard, primary) : standard;
  }

  function registerGalleryTemplate(name, parentName, sizeFn) {
    galleryTemplates[name] = {parent: parentName, fn: sizeFn};
  }

  function registerCardLayout(name, cards, columnsFn, parentName) {
    var previous = '';
    cardLayouts.push(function () {
      var host = controlElement(name);
      if (!host) return false;
      var hostRef = val(name), width = Math.max(0, Number(hostRef.width) || 0);
      var columns = Math.max(1, Number(columnsFn(val, hostRef, val(parentName))) || 1);
      var entries = cards.map(function (card, index) {
        var self = val(card.name), props = card.properties;
        function get(key, fallback) { return props[key] ? props[key](val, self, hostRef) : fallback; }
        function number(key, fallback) {
          var value = Number(get(key, fallback));
          if (!Number.isFinite(value)) throw new Error('Nonfinite card property: ' + card.name + '.' + key);
          return value;
        }
        return {name:card.name, index:index, x:number('X', 0), y:number('Y', index),
          width:Math.max(0, number('Width', width / columns)), height:Math.max(0, number('Height', 100)),
          fit:!!get('WidthFit', false), visible:!!get('Visible', true), el:self.el};
      }).sort(function (a,b) { return a.y - b.y || a.x - b.x || a.index - b.index; });
      var row = [], used = 0, top = 0, logicalY, geometry = [];
      function flush() {
        if (!row.length) return;
        var fits = row.filter(function (card) { return card.fit; }).length;
        var extra = fits ? Math.max(0, width - used) / fits : 0;
        var height = Math.max.apply(Math, row.map(function (card) { return card.height; }));
        var left = 0;
        row.forEach(function (card) {
          var actualWidth = card.width + (card.fit ? extra : 0);
          cardGeometry[card.name] = {x:card.x, y:card.y, width:actualWidth, height:height};
          if (card.el) Object.assign(card.el.style, {left:left+'px', top:top+'px',
            width:actualWidth+'px', height:height+'px', display:''});
          geometry.push([card.name, left, top, actualWidth, height, true]);
          left += actualWidth;
        });
        top += height;
        row = []; used = 0;
      }
      entries.forEach(function (card) {
        if (!card.visible) {
          cardGeometry[card.name] = {x:card.x, y:card.y, width:card.width, height:card.height};
          if (card.el) card.el.style.display = 'none';
          geometry.push([card.name, 0, 0, card.width, card.height, false]);
          return;
        }
        if (row.length && (card.y !== logicalY || used + card.width > width + 0.01)) flush();
        logicalY = card.y; row.push(card); used += card.width;
      });
      flush();
      var next = JSON.stringify(geometry), changed = previous !== next;
      previous = next;
      return changed;
    });
  }

  // Source canvas properties are lazy so hidden screens and forward references
  // have their logical dimensions even before CSS has been laid out. Getters
  // also let Self.Width be read while evaluating that screen's Size formula.
  function canvasRef(name) {
    if (canvas.refs[name]) return canvas.refs[name];
    var ref = {};
    var defaults = name === 'App'
      ? ['active_screen', 'width', 'height', 'design_width', 'design_height', 'min_screen_width', 'min_screen_height', 'size_breakpoints']
      : ['name', 'width', 'height', 'size', 'orientation', 'fill', 'visible', 'el'];
    var properties = name === 'App' ? canvas.app : canvas.screens[name] || {};
    defaults.concat(Object.keys(properties)).forEach(function (key) {
      if (Object.prototype.hasOwnProperty.call(ref, key)) return;
      Object.defineProperty(ref, key, {enumerable: true, get: function () { return canvasProperty(name, key); }});
    });
    canvas.refs[name] = ref;
    return ref;
  }
  function canvasProperty(name, key) {
    var properties = name === 'App' ? canvas.app : canvas.screens[name] || {};
    var token = name + '.' + key;
    if (canvas.resolving.indexOf(token) >= 0) throw new Error('Circular canvas property: ' + token);
    canvas.resolving.push(token);
    try {
      if (typeof properties[key] === 'function')
        return properties[key](val, canvasRef(name), name === 'App' ? null : canvasRef('App'));
      var layout = canvas.layout, app = canvasRef('App'), screen = name === 'App' ? null : canvasRef(name);
      if (name === 'App') {
        if (key === 'active_screen') return CURRENT_SCREEN;
        if (key === 'design_width') return Number(layout.designWidth) || 1366;
        if (key === 'design_height') return Number(layout.designHeight) || 768;
        if (key === 'width') return layout.scaleToFit === true ? app.design_width : Number(global.innerWidth) || app.design_width;
        if (key === 'height') return layout.scaleToFit === true ? app.design_height : Number(global.innerHeight) || app.design_height;
        if (key === 'min_screen_width') return Number(layout.designWidth) || 0;
        if (key === 'min_screen_height') return Number(layout.designHeight) || 0;
        if (key === 'size_breakpoints') return [600, 900, 1200];
      } else {
        if (key === 'name') return name;
        if (key === 'width') return Math.max(app.width, app.min_screen_width);
        if (key === 'height') return Math.max(app.height, app.min_screen_height);
        if (key === 'size') return 1 + app.size_breakpoints.filter(function (v) { return screen.width > Number(v && typeof v === 'object' ? v.value : v); }).length;
        if (key === 'orientation') return screen.width > screen.height ? 'Horizontal' : 'Vertical';
        if (key === 'fill') return 'transparent';
        if (key === 'visible') return CURRENT_SCREEN === name;
        if (key === 'el') return document.querySelector('[data-screen="' + name + '"]');
      }
      return null;
    } finally { canvas.resolving.pop(); }
  }
  function updateCanvas() {
    Object.keys(canvas.screens).forEach(function (name) {
      try {
        var screen = canvasRef(name), el = screen.el;
        if (!el) return;
        el.style.width = screen.width + 'px';
        el.style.height = screen.height + 'px';
        el.style.backgroundColor = screen.fill || '';
        var layout = canvas.layout, app = canvasRef('App');
        var sx = layout.scaleToFit === true ? (Number(global.innerWidth) || app.design_width) / app.design_width : 1;
        var sy = layout.scaleToFit === true ? (Number(global.innerHeight) || app.design_height) / app.design_height : 1;
        if (layout.lockAspectRatio === true) sx = sy = Math.min(sx, sy);
        el.style.transformOrigin = 'top left';
        el.style.transform = sx === 1 && sy === 1 ? '' : 'scale(' + sx + ',' + sy + ')';
        if (name === CURRENT_SCREEN) {
          var host = document.getElementById('fx-canvas');
          if (host) {
            host.style.width = screen.width * sx + 'px';
            host.style.height = screen.height * sy + 'px';
            host.style.overflow = layout.scaleToFit === true ? 'hidden' : 'visible';
          }
        }
      } catch (error) { console.error('canvas layout error', name, error); }
    });
  }
  function configureCanvas(layout, appProperties, screens) {
    canvas = {layout: layout || {}, app: appProperties || {}, screens: screens || {}, refs: {}, resolving: []};
    if (!resizeInstalled && typeof global.addEventListener === 'function') {
      resizeInstalled = true;
      global.addEventListener('resize', function () { updateBindings(); });
    }
    updateCanvas();
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
    var preferred = Array.isArray(displayFields) ? displayFields : typeof displayFields === 'string' ? [displayFields] : [];
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
    var matched = false;
    Array.prototype.forEach.call(el.options || [], function (option, index) {
      var selected = wanted.some(function (candidate) {
        return sameRecord(rows[index], candidate);
      });
      option.selected = selected;
      matched = matched || selected;
    });
    // A native single select may reselect its first option as other options
    // are deselected. Blank must explicitly leave it without a selection.
    if (!matched) el.selectedIndex = -1;
  }

  function registerControlProps(name, parentName, propertyFns) {
    controlProperties[name] = {parent:parentName, fns:propertyFns || {}};
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

  function registerRowProps(row, name, parentName, propertyFns) {
    var el = findControl(row, name);
    if (!el) return;
    el.__fxProperties = {parent:parentName, fns:propertyFns || {}, tokens:{},
      read:function (control) { return rowValue(row, control); }};
  }

  function styleControl(name, cssProp, valueFn, unit, parentName) {
    evaluators.push({
      apply: function () {
        var el = controlElement(name);
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
        var el = controlElement(name);
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
        var el = controlElement(name);
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

  function rowElement(row, name) {
    for (var scope = row; scope; scope = scope.__fxParentRow) {
      var el = findControl(scope, name);
      if (el) return el;
    }
    return null;
  }

  function rowValue(row, name) {
    return val(name, rowElement(row, name));
  }

  function inputMode(el, mode) {
    if (['SingleLine', 'MultiLine', 'Password'].indexOf(mode) < 0)
      throw new Error('Unsupported TextMode: ' + mode);
    var tag = mode === 'MultiLine' ? 'TEXTAREA' : 'INPUT';
    var type = mode === 'Password' ? 'password' : 'text';
    if (el.tagName === tag) {
      if (tag === 'INPUT' && el.type !== type) el.type = type;
      return el;
    }
    var focused = document.activeElement === el, start = el.selectionStart, end = el.selectionEnd;
    var replacement = document.createElement(tag.toLowerCase());
    Array.prototype.forEach.call(el.attributes, function (attribute) {
      if (attribute.name !== 'type') replacement.setAttribute(attribute.name, attribute.value);
    });
    if (tag === 'INPUT') replacement.type = type;
    replacement.value = el.value;
    Object.keys(el).forEach(function (key) {
      if (key.indexOf('__fx') === 0 && key !== '__fxListeners') replacement[key] = el[key];
    });
    (el.__fxListeners || []).forEach(function (listener) { listen(replacement, listener.event, listener.callback); });
    el.replaceWith(replacement);
    if (focused) {
      replacement.focus({preventScroll:true});
      if (start !== null && start !== undefined) replacement.setSelectionRange(start, end);
    }
    return replacement;
  }

  function rowControl(row, name, parentName, propertyFns) {
    if (!row || typeof row.querySelector !== 'function') return;
    var el = findControl(row, name);
    if (!el) return;
    var read = function (control) { return rowValue(row, control); };
    var px = { left: true, top: true, width: true, height: true };
    try {
      Object.keys(propertyFns || {}).forEach(function (key) {
        if (key === 'templateSize') {
          el.__fxGalleryTemplate = {fn:propertyFns[key], read:read, parent:parentName};
          return;
        }
        var value = propertyFns[key](read, read(name), read(parentName));
        if (key === 'mode') {
          el = inputMode(el, value);
        } else if (key === 'text') {
          el.textContent = value == null ? '' : String(value);
        } else if (key === 'default') {
          if (el.tagName === 'SELECT') el.__fxDefaultSelection = value;
          var signature = JSON.stringify(value == null ? '' : value);
          if (el.__fxDefaultSignature !== signature) {
            el.__fxDefaultSignature = signature;
            if (el.type === 'date') value = dateInputText(value);
            el.setAttribute('data-fx-default', value == null ? '' : String(value));
            if (el.type === 'checkbox') el.checked = !!value;
            else if (el.tagName === 'SELECT') applyDefaultSelection(el, value);
            else el.value = value == null ? '' : String(value);
          }
        } else if (key === 'items') {
          var rows = Array.isArray(value) ? value : [];
          var selected = selectedRecords(el);
          el.__fxRecords = rows;
          var options = rows.map(function (record, index) {
            var option = optionRecord(record, el.__fxDisplayFields);
            return '<option data-fx-index="' + index + '" value="' + global.esc(option.value)
              + '">' + global.esc(option.label) + '</option>';
          }).join('');
          if (el.__fxOpts !== options) {
            el.__fxOpts = options; el.innerHTML = options;
            if (selected.length) applyDefaultSelection(el, selected);
            else delete el.__fxDefaultSignature;
          }
        } else if (key === 'displayFields') {
          el.__fxDisplayFields = value;
        } else if (key === 'src') {
          var source = value == null ? '' : String(value).trim();
          if (/^(?:javascript|vbscript):/i.test(source)) source = '';
          if (!source) el.removeAttribute('src');
          else if (el.getAttribute('src') !== source) el.setAttribute('src', source);
        } else if (key === 'disabled') {
          el.disabled = /^(disabled|view)$/i.test(String(value));
        } else if (key === 'acceptsFocus') {
          el.tabIndex = value ? 0 : -1;
        } else if (key === 'ariaLabel' || key === 'title') {
          el.setAttribute(key === 'ariaLabel' ? 'aria-label' : 'title', value == null ? '' : String(value));
        } else if (key === 'reset') {
          var rising = value && !el.__fxReset;
          el.__fxReset = !!value;
          if (rising) resetControl(name, el);
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
  }

  /**
   * Gallery rendering: itemsFn returns the row array, rowFn fills a cloned
   * row template, handlers maps control names to event descriptors. Reconcile
   * stable record identities so state updates retain live inputs and focus.
   */
  function galleryRecord(item) {
    // Typed collections carry logical/display-name aliases as non-enumerable
    // accessors. A row's UI properties must not discard those record fields.
    var record = Object.defineProperties({}, Object.getOwnPropertyDescriptors(selectionRecord(item) || {}));
    var source = item && typeof item === 'object' && relationshipRecords.get(item);
    if (source) tagRelationshipRecord(source, record);
    return record;
  }

  function createGallery(name, getHost, parentRow) {
    var itemsFn, rowFn, handlers, controlFields, config = {};
    var mounted = new Map();
    var identities = new WeakMap(), nextIdentity = 0;
    var resetRequested = false, defaultSignature;
    function layout() {
      var host = getHost();
      if (!rowFn || !host || host.getAttribute('data-gallery-layout') !== 'horizontal') return;
      // Ordinary style bindings may size the gallery after its Items binding.
      // Reapply row geometry against the final size without rerunning Items or
      // remounting controls, so Parent.TemplateHeight is correct on first paint.
      mounted.forEach(function (row) { rowFn(row.__fxScope,row); });
    }
    function identity(item) {
      if (item && typeof item === 'object') {
        for (var key of ['id', 'ID', 'key']) {
          if (item[key] != null) return key + ':' + String(item[key]);
        }
        if (!identities.has(item)) identities.set(item, ++nextIdentity);
        return 'object:' + identities.get(item);
      }
      return typeof item + ':' + String(item);
    }
    function valueKey(item) {
      // Formula-created records can be equal values but new objects on each
      // evaluation. Match only JSON-like Power Fx data, with typed dates and
      // sorted record fields; never merge unsupported/cyclic values by accident.
      var seen = new Set();
      function encode(value) {
        if (value === null) return ['blank'];
        if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('nonfinite value');
        if (['string','boolean','number'].includes(typeof value)) return [typeof value,value];
        if (value instanceof Date) {
          if (!Number.isFinite(value.getTime())) throw new Error('invalid date');
          return ['date',value.toISOString()];
        }
        if (!value || typeof value !== 'object' || seen.has(value)) throw new Error('unsupported value');
        if (!Array.isArray(value) && Object.prototype.toString.call(value) !== '[object Object]') throw new Error('unsupported record');
        seen.add(value);
        var result = Array.isArray(value) ? ['table',value.map(encode)] :
          ['record',Object.keys(value).sort().map(function (key) { return [key,encode(value[key])]; })];
        seen.delete(value);
        return result;
      }
      try { return JSON.stringify(encode(item)); } catch (_) { return null; }
    }
    function choose(row) {
      var host = getHost();
      host.__fxValues = Object.assign({}, host.__fxValues || {}, {
        selected: row.__fxItem, selected_items: [row.__fxItem],
      });
    }
    function invoke(row, control, event) {
      var descriptor = (handlers || {})[control];
      var fn = descriptor && (typeof descriptor === 'function' ? descriptor : descriptor[event]);
      if (!fn) return Promise.resolve();
      var queued = [];
      return Promise.resolve().then(function () {
        return fn(row.__fxScope, row, function (target) {
          queued.push(target === 'Parent' ? descriptor.parent : target === 'Self' ? control : target);
        });
      }).then(function () {
        updateBindings();
        return queued.reduce(function (previous, target) {
          return previous.then(function () {
            if (target === name || (handlers || {})[target]) {
              choose(row);
              return invoke(row, target, 'OnSelect');
            }
            for (var ancestor=row.__fxParentRow;ancestor;ancestor=ancestor.__fxParentRow) {
              if (ancestor.__fxGalleryName===target) return ancestor.__fxGalleryController.select(ancestor);
            }
            var targetElement = rowElement(row,target);
            if (targetElement) targetElement.click();
            else global.selectControl(target);
          });
        }, Promise.resolve());
      }).catch(function (err) {
        console.error(err);
        toast('Error: ' + (err && err.message ? err.message : err), true);
      });
    }
    var controller = {
      configure: function (items, render, events, fields, options) {
        itemsFn=items; rowFn=render; handlers=events; controlFields=fields; config=options || {};
      },
      reset: function () {
        resetRequested=true;
        var host=getHost();
        if (host) {host.scrollTop=0;host.scrollLeft=0;}
      },
      select: function (row) {choose(row);return invoke(row,name,'OnSelect').then(updateBindings);},
      layout: layout,
      apply: function () {
        var host = getHost();
        if (!host || typeof host.querySelector !== 'function') return;
        // A mounted row can contain another gallery. Its template must never
        // replace this gallery's own template when additional rows are added.
        var tpl = host.querySelector(':scope > template');
        var rowsEl = host.querySelector(':scope > .fx-rows');
        if (!tpl || !rowsEl) return;
        var items;
        try { items = itemsFn() || []; } catch (e) { console.error('gallery Items error', name, e); items = []; }
        if (!Array.isArray(items)) items = [];
        var current = host.__fxValues && host.__fxValues.selected;
        var initial = config.Default ? config.Default() : null;
        var signature = valueKey(initial);
        var reset = resetRequested || defaultSignature !== signature;
        defaultSignature=signature; resetRequested=false;
        if (reset || current == null) current=initial;
        var selected = items.find(function (item) { return sameRecord(item, current); }) || items[0] || null;
        host.__fxValues = Object.assign({}, host.__fxValues || {}, {
          selected: selected,
          selected_items: selected ? [selected] : [],
        });
        var rowMarkup = String(tpl.innerHTML || '').trim();
        var focused = document.activeElement;
        var restoreFocus = focused && typeof rowsEl.contains === 'function' && rowsEl.contains(focused);
        var selectionStart = restoreFocus ? focused.selectionStart : null;
        var selectionEnd = restoreFocus ? focused.selectionEnd : null;
        var used = new Map(), next = new Map(), retainedRows = new Set();
        var rowKeys = items.map(function (item) {
          var base = identity(item), occurrence = used.get(base) || 0;
          used.set(base, occurrence + 1);
          return base + ':' + occurrence;
        });
        var requestedKeys = new Set(rowKeys), reusable = new Map();
        if (rowKeys.some(function (key) { return key.startsWith('object:') && !mounted.has(key); })) {
          mounted.forEach(function (row,key) {
            // Reserve existing object identities before matching new equal
            // records, so a clone cannot steal a later row's unsaved controls.
            if (!key.startsWith('object:') || requestedKeys.has(key)) return;
            var signature = valueKey(row.__fxItem);
            if (signature === null) return;
            if (!reusable.has(signature)) reusable.set(signature,[]);
            reusable.get(signature).push(row);
          });
        }
        var renderedRows = items.map(function (item, index) {
          var key = rowKeys[index];
          var row = mounted.get(key);
          if (!row && key.startsWith('object:')) {
            var candidates = reusable.get(valueKey(item));
            if (candidates && candidates.length) row = candidates.shift();
          }
          if (!row) {
            var holder = document.createElement('div');
            holder.innerHTML = rowMarkup;
            row = holder.firstElementChild;
            if (!row) return null;
            row.addEventListener('click', function (event) {
              if (event) event.stopPropagation();
              choose(row);
              invoke(row, name, 'OnSelect').then(updateBindings);
            });
            Object.keys(handlers || {}).forEach(function (control) {
              if (control === name) return;
              var el = row.querySelector('[data-control="' + control + '"]');
              if (!el) return;
              ['OnSelect', 'OnChange'].forEach(function (event) {
                var descriptor = handlers[control];
                if (!(typeof descriptor === 'function' && event === 'OnSelect') && !descriptor[event]) return;
                listen(el, event === 'OnSelect' ? 'click' : 'change', function (domEvent) {
                  if (domEvent) domEvent.stopPropagation();
                  choose(row);
                  invoke(row, control, event);
                });
              });
            });
            row.querySelectorAll('input, textarea, select').forEach(function (el) {
              // Native editing must not invoke the gallery's OnSelect through
              // DOM bubbling. A source OnSelect/Select(Parent) remains explicit.
              listen(el, 'click', function (event) { if (event) event.stopPropagation(); });
              listen(el, 'input', updateBindings);
            });
          }
          row.__fxItem = item;
          row.__fxParentRow = parentRow;
          row.__fxGalleryName = name;
          row.__fxGalleryController = controller;
          row.__fxScope = galleryRecord(item);
          Object.defineProperty(row.__fxScope,'is_selected',{configurable:true,get:function () {
            return sameRecord(row.__fxItem,host.__fxValues.selected);
          }});
          next.set(key, row);
          retainedRows.add(row);
          // Avoid moving an already correctly placed node: moving a focused
          // input's ancestor blurs it in Chromium even if the node is reused.
          if (rowsEl.children[index] !== row) rowsEl.insertBefore(row, rowsEl.children[index] || null);
          return row;
        });
        mounted.forEach(function (row) { if (!retainedRows.has(row)) row.remove(); });
        mounted = next;
        // AllItems is the loaded records plus their own control references.
        // Resolve a control when it is read so input edits and replacement
        // nodes remain current, including after an awaited action. Never put
        // DOM nodes into the record/JSON data transport.
        host.__fxAllItems = function () {
          return renderedRows.filter(Boolean).map(function (row) {
            var item = row.__fxItem;
            var record = galleryRecord(item);
            Object.keys(controlFields || {}).forEach(function (control) {
              if (!row.querySelector('[data-control="' + control + '"]')) return;
              Object.defineProperty(record, controlFields[control], {enumerable:true, configurable:true, get:function () {
                var value = Object.assign({}, rowValue(row, control));
                delete value.el;
                return value;
              }});
            });
            return record;
          });
        };
        var templateSize = (parentRow ? val(name,host) : val(name)).template_size;
        var templatePadding = parseFloat(host.getAttribute('data-template-padding'));
        var wrapCount = parseInt(host.getAttribute('data-wrap-count'), 10);
        var horizontal = host.getAttribute('data-gallery-layout') === 'horizontal';
        // Read template dimensions directly from current metadata/geometry in
        // val(). Caching the whole gallery width as TemplateWidth creates a
        // feedback loop for a horizontal gallery sized from its own template.
        if (horizontal && rowsEl.style) {
          if (!Number.isFinite(templateSize) || templateSize < 1) throw new Error('Horizontal gallery requires a positive TemplateSize: ' + name);
          Object.assign(rowsEl.style,{display:'grid',gridAutoFlow:'column',
            gridTemplateRows:'repeat(' + (Number.isFinite(wrapCount) && wrapCount>0 ? wrapCount : 1) + ', minmax(0, 1fr))',
            gridAutoColumns:templateSize+'px',height:'100%',boxSizing:'border-box',
            gap:(Number.isFinite(templatePadding) ? Math.max(0,templatePadding) : 0)+'px',
            padding:(Number.isFinite(templatePadding) ? Math.max(0,templatePadding) : 0)+'px'});
        } else if (rowsEl.style && Number.isFinite(wrapCount) && wrapCount > 1) {
          rowsEl.style.display = 'grid';
          rowsEl.style.gridTemplateColumns = 'repeat(' + wrapCount + ', minmax(0, 1fr))';
        }
        items.forEach(function (item, index) {
          var row = renderedRows[index];
          if (!row) return;
          row.style.position = 'relative';
          if (horizontal) {
            Object.assign(row.style,{width:templateSize+'px',minWidth:'0',minHeight:'0',padding:'0'});
          } else if (Number.isFinite(templateSize) && templateSize > 0) {
            row.style.minHeight = templateSize + 'px';
            row.style.boxSizing = 'border-box';
          }
          if (!horizontal && Number.isFinite(templatePadding) && templatePadding >= 0) {
            row.style.padding = templatePadding + 'px';
          }
          if (rowFn) {
            try { rowFn(row.__fxScope, row); } catch (e) { console.error('gallery row error', e); }
          }
        });
        if (restoreFocus && rowsEl.contains(focused) && document.activeElement !== focused) {
          focused.focus({preventScroll: true});
          if (typeof focused.setSelectionRange === 'function' && selectionStart !== null) {
            focused.setSelectionRange(selectionStart, selectionEnd);
          }
        }
      },
    };
    return controller;
  }

  function gallery(name, itemsFn, rowFn, handlers, controlFields, config) {
    var getHost=function () {return controlElement(name);};
    var controller=createGallery(name,getHost,null);
    controller.configure(itemsFn,rowFn,handlers,controlFields,config);
    var host=getHost();
    if (host) host.__fxGallery=controller;
    evaluators.push(controller);
    galleryLayouts.push(controller.layout);
  }

  function rowGallery(row, name, itemsFn, rowFn, handlers, controlFields, config) {
    var host=row.querySelector('[data-control="'+name+'"]');
    if (!host) return;
    if (!host.__fxGallery) host.__fxGallery=createGallery(name,function () {return host;},row);
    host.__fxGallery.configure(itemsFn,rowFn,handlers,controlFields,config);
    host.__fxGallery.apply();
  }

  function renderChart(name, rows, cfg) {
    var el = controlElement(name);
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
    return findControl(document, name);
  }

  function findControl(root, name) {
    var cache = controlNodes.get(root);
    if (!cache) {cache = new Map(); controlNodes.set(root, cache);}
    function owned(el) {
      if (!el || !el.isConnected || typeof el.closest !== 'function') return false;
      var row = el.closest('.fx-row');
      return root === document ? !row : row === root;
    }
    var el = cache.get(name);
    if (owned(el)) return el;
    el = root.querySelector('[data-control="' + name + '"]');
    // Never cache a descendant row as a document/parent control: sorting and
    // remounting change which instance a global query would find first.
    if (owned(el)) cache.set(name, el);
    else cache.delete(name);
    return el;
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
    else if (el.type === 'date') el.value = dateInputText(value);
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

  function registerTimer(name, screen, config) {
    var elapsed = 0, epoch = null, pending = null, busy = false;
    var completed = false, started = false, wasActive = false, auto = false;
    var resetHigh = false, generation = 0, manual = null, previousStart = false, previousAuto = false;
    function read(key, fallback) { return config[key] ? config[key]() : fallback; }
    function publish() {
      controlValues[name] = Object.assign({}, controlValues[name] || {}, {
        value: elapsed, duration: duration(), running: epoch !== null,
      });
    }
    function duration() {
      var value = Number(read('Duration', 60000));
      return Number.isFinite(value) ? Math.max(1, Math.min(86400000, value)) : 60000;
    }
    function pause() {
      if (epoch !== null) elapsed = Math.min(duration(), elapsed + Date.now() - epoch);
      epoch = null;
      if (pending !== null) clearTimeout(pending);
      pending = null;
    }
    function reset() {
      pause(); elapsed = 0; completed = false; started = false; generation++;
      publish();
    }
    function run(event) {
      busy = true;
      var version = generation, failed = false;
      Promise.resolve().then(function () { if (config[event]) return config[event](); })
        .catch(function (err) {
          failed = true;
          console.error('timer event error', name + '.' + event, err);
          toast('Timer error: ' + (err && err.message ? err.message : err), true);
          completed = true;
        }).then(function () {
          busy = false;
          if (!failed && event === 'OnTimerEnd' && generation === version && read('Repeat', false)) reset();
          updateBindings();
        }).catch(function (err) { console.error('timer scheduling error', name, err); });
    }
    function apply() {
      var active = CURRENT_SCREEN === screen;
      var start = !!read('Start', false), autoStart = !!read('AutoStart', false);
      if (completed && ((start && !previousStart) || (active && autoStart && !previousAuto))) reset();
      if (start !== previousStart) manual = null;
      previousStart = start;
      previousAuto = autoStart;
      if (active && !wasActive && autoStart) {
        auto = true; manual = null;
        if (completed) reset();
      }
      if (!autoStart) auto = false;
      // AutoStart can itself be reactive (the Microsoft focus timers use it).
      if (active && autoStart) auto = true;
      wasActive = active;
      var requestedReset = !!read('Reset', false);
      if (requestedReset && !resetHigh) reset();
      resetHigh = requestedReset;
      var wantsRun = manual === null ? start || auto : manual;
      if (requestedReset || busy || completed || !wantsRun || (read('AutoPause', true) && !active)) {
        pause(); publish(); return;
      }
      if (!started) {
        started = true;
        run('OnTimerStart');
        publish(); return;
      }
      if (epoch === null) epoch = Date.now();
      if (pending === null) {
        pending = setTimeout(function () {
          pending = null;
          var now = Date.now();
          elapsed = Math.min(duration(), elapsed + now - epoch);
          epoch = now;
          if (elapsed >= duration()) {
            pause(); completed = true; publish(); run('OnTimerEnd');
          }
          updateBindings();
        }, Math.max(1, Math.min(50, duration() - elapsed)));
      }
      publish();
    }
    timers[name] = { reset: reset };
    var el = controlElement(name);
    if (el) el.addEventListener('click', function () {
      var wasRunning = epoch !== null || busy;
      if (completed) reset();
      manual = !wasRunning;
      updateBindings();
    });
    evaluators.push({apply: apply});
    publish();
  }

  function resetControl(name, element) {
    if (timers[name]) {
      timers[name].reset(); updateBindings(); return 0;
    }
    var el = element || controlElement(name);
    if (!el) throw new Error('control not found for Reset: ' + name);
    if (el.__fxGallery) {
      el.__fxGallery.reset(); updateBindings(); return null;
    }
    var value = el.getAttribute('data-fx-default');
    if (el.tagName === 'SELECT' && Object.prototype.hasOwnProperty.call(el, '__fxDefaultSelection'))
      applyDefaultSelection(el, el.__fxDefaultSelection);
    else if (el.type === 'checkbox') el.checked = value === 'true';
    else el.value = value === null ? '' : value;
    updateBindings();
    return value;
  }

  function inputControl(name, parentName, propertyFns) {
    var evaluator = {apply: function () { rowControl(document, name, parentName, propertyFns); }};
    var el = controlElement(name);
    if (el && !el.__fxInputUpdates) {
      el.__fxInputUpdates = true;
      listen(el, 'input', updateBindings);
      listen(el, 'change', updateBindings);
    }
    evaluators.push(evaluator);
    evaluator.apply();
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
  var _cachedUser = { email: '', full_name: '', image: '' }, _userPromise = null;
  function loadUser() {
    if (_userPromise) return _userPromise;
    _userPromise = serverRun('whoami').then(function (info) {
      _cachedUser = {
        email: info && info.email || '',
        full_name: info && info.fullName || '',
        image: info && info.pictureUrl || '',
      };
      updateBindings();
      return _cachedUser;
    });
    return _userPromise;
  }
  function fxUser() {
    return _cachedUser;
  }

  var relationshipContracts = {}, relationshipCache = {}, relationshipReferences = new WeakMap();
  var relationshipRecords = new WeakMap();
  function configureRelationships(contracts) {
    relationshipContracts = contracts || {};
    relationshipCache = {};
    relationshipReferences = new WeakMap();
    relationshipRecords = new WeakMap();
  }
  function tagRelationshipRecord(ds, record) {
    if (record && typeof record === 'object' && !Array.isArray(record)) relationshipRecords.set(record, ds);
    return record;
  }
  function relationshipIdentity(ds, record) {
    var contract = relationshipContracts[ds];
    if (!contract || !record || typeof record !== 'object' || Array.isArray(record)) return null;
    var present = contract.keys.filter(function (key) { return record[key] != null && record[key] !== ''; });
    if (!present.length) return null;
    var id = record[present[0]];
    if (typeof id !== 'string' || present.some(function (key) { return record[key] !== id; }))
      throw new Error('conflicting or invalid relationship primary key: ' + ds);
    return id;
  }
  function relationshipField(record, key) {
    if (!record || typeof record !== 'object' || Array.isArray(record)) return;
    var known = relationshipRecords.get(record);
    var sources = (known ? [known] : Object.keys(relationshipContracts)).filter(function (ds) {
      return Object.prototype.hasOwnProperty.call(relationshipContracts[ds].navigation, key) &&
        relationshipIdentity(ds, record) !== null;
    });
    if (!sources.length) return;
    if (sources.length !== 1) throw new Error('ambiguous relationship record: ' + key);
    var ds = sources[0], spec = relationshipContracts[ds].navigation[key];
    if (spec.error) throw new Error(spec.error + ': ' + ds + '.' + key);
    var id = relationshipIdentity(ds, record), snapshot = relationshipCache[ds];
    if (!snapshot || !Array.isArray(snapshot.links) || !Array.isArray(snapshot.targets[spec.target]))
      throw new Error('relationship data has not loaded: ' + ds + '.' + key);
    if ((state[ds] || []).filter(function (row) { return relationshipIdentity(ds, row) === id; }).length !== 1)
      throw new Error('relationship source record is missing or ambiguous: ' + ds);
    var related = spec.kind === 'one-to-many' ? snapshot.targets[spec.target].filter(function (row, index) {
      return snapshot.parents[key][index] === id;
    }) : snapshot.links.filter(function (link) { return link[0] === spec.schema && link[spec.side] === id; })
      .map(function (link) {
        var matches = snapshot.targets[spec.target].filter(function (row) {
          return relationshipIdentity(spec.target, row) === link[3-spec.side];
        });
        if (matches.length !== 1) throw new Error('related record is missing or ambiguous: ' + spec.target);
        return matches[0];
      });
    relationshipReferences.set(related, {source:ds, key:key, id:id});
    return {value:related};
  }
  function refreshData(ds) {
    var contract = relationshipContracts[ds];
    var needsLinks = contract && Object.keys(contract.navigation).some(function (key) {
      var spec = contract.navigation[key]; return !spec.error;
    });
    return Promise.all([serverRun('api', ds, 'list', {}),
      needsLinks ? serverRun('api', ds, 'relationshipSnapshot', {}) : Promise.resolve({links:[],targets:{}})]).then(function (results) {
      var data = results[0];
      if (Array.isArray(data)) data.forEach(function (row) { tagRelationshipRecord(ds, row); });
      Object.keys(results[1].targets).forEach(function (target) {
        results[1].targets[target].forEach(function (row) { tagRelationshipRecord(target, row); });
      });
      relationshipCache[ds] = results[1];
      state[ds] = data || [];
      updateBindings();
      return state[ds];
    });
  }

  // server data API used by transpiled Patch/Remove/Collect calls
  global.apiRelate = function (related, record, remove) {
    var reference = related && relationshipReferences.get(related);
    if (!reference) return Promise.reject(new Error('Relate/Unrelate requires a direct exported relationship table'));
    var base = {}; base[relationshipContracts[reference.source].primaryKey] = reference.id;
    return serverRun('api', reference.source, remove ? 'unrelate' : 'relate', {
      relationship:reference.key, base:base, record:record,
    }).then(function () { return refreshData(reference.source); }).then(function () { return null; });
  };
  global.apiPatch = function (ds, base, record) {
    return serverRun('api', ds, 'patch', { base: base, record: record }).then(function (r) {
      return refreshData(ds).then(function () { return tagRelationshipRecord(ds, r); });
    });
  };
  global.apiPatchRecord = function (ds, record) {
    return serverRun('api', ds, 'patchRecord', {record: record}).then(function (saved) {
      return refreshData(ds).then(function () { return tagRelationshipRecord(ds, saved); });
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
      return refreshData(ds).then(function () { return tagRelationshipRecord(ds, r); });
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
    var arr = global.FX.collections.collect.apply(null, arguments);
    updateBindings();
    return arr;
  };
  global.powerapps_clearCollect = function (st, ds) {
    var arr = global.FX.collections.clearCollect.apply(null, arguments);
    updateBindings();
    return arr;
  };
  global.powerapps_remove = function (st, ds, record) {
    var arr = global.FX.collections.dropRecord(st, ds, record);
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
    configureServices: configureServices,
    connectorCall: connectorCall,
    connectorRead: connectorRead,
    refreshConnector: refreshConnector,
    configureRelationships: configureRelationships,
    relationshipField: relationshipField,
    param: param,
    saveData: saveData,
    loadData: loadData,
    clearData: clearData,
    inputControl: inputControl,
    language: function () { return global.navigator && global.navigator.language || 'en-US'; },
    state: state,
    serverRun: serverRun,
    toast: toast,
    go: go,
    goBack: goBack,
    showScreen: showScreen,
    bind: bind,
    val: val,
    configureCanvas: configureCanvas,
    configureContexts: configureContexts,
    variable: variable,
    updateContext: updateContext,
    registerForm: registerForm,
    submitForm: submitForm,
    refreshData: refreshData,
    updateBindings: updateBindings,
    setState: setState,
    controlElement: controlElement,
    registerRowProps: registerRowProps,
    registerControlProps: registerControlProps,
    registerGalleryTemplate: registerGalleryTemplate,
    registerCardLayout: registerCardLayout,
    styleControl: styleControl,
    attrControl: attrControl,
    htmlControl: htmlControl,
    sanitizeHtml: sanitizeHtml,
    rowControl: rowControl,
    rowValue: rowValue,
    resetRowControl: function (row, name) {
      return resetControl(name, rowElement(row, name));
    },
    optionRecord: optionRecord,
    applyDefaultSelection: applyDefaultSelection,
    gallery: gallery,
    rowGallery: rowGallery,
    renderChart: renderChart,
    setFormMode: setFormMode,
    resetForm: resetForm,
    resetControl: resetControl,
    registerTimer: registerTimer,
    focusControl: function (name) {
      var el = controlElement(name);
      if (el && !el.disabled && typeof el.focus === 'function') el.focus();
    },
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
    registerScreenHiddenHandler: function (name, fn) { handlers['__hidden__' + name] = fn; },
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
    var el = controlElement(name);
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
        ? Promise.resolve().then(loadUser).then(function () { return global.APP_MAIN(); })
        : Promise.resolve();
      return startup.catch(function (e) {
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
