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
  var handlers = {};     // controlName -> { event: fn }
  var controlValues = {}; // control name -> evaluated properties used by dependents
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
    Object.defineProperty(update, collectionName, {value: (current || []).concat(saved), enumerable: true});
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

  function val(name, element) {
    if (name === 'App') {
      return canvasRef('App');
    }
    if (!element && Object.prototype.hasOwnProperty.call(canvas.screens, name)) return canvasRef(name);
    var el = element || document.querySelector('[data-control="' + name + '"]')
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
      text: ['INPUT', 'SELECT', 'TEXTAREA'].indexOf(el.tagName) >= 0 ? el.value : (el.textContent || ''),
      value: el.type === 'checkbox' ? !!el.checked : el.type === 'range' ? Number(el.value)
        : el.value !== undefined ? el.value : el.textContent,
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
    return Object.assign(standard, element ? (element.__fxValues || {}) : (controlValues[name] || {}));
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

  function rowValue(row, name) {
    var el = row && row.querySelector('[data-control="' + name + '"]');
    return val(name, el);
  }

  function rowControl(row, name, parentName, propertyFns) {
    if (!row || typeof row.querySelector !== 'function') return;
    var el = row.querySelector('[data-control="' + name + '"]');
    if (!el) return;
    var read = function (control) { return rowValue(row, control); };
    var px = { left: true, top: true, width: true, height: true };
    try {
      Object.keys(propertyFns || {}).forEach(function (key) {
        var value = propertyFns[key](read, read(name), read(parentName));
        if (key === 'text') {
          el.textContent = value == null ? '' : String(value);
        } else if (key === 'default') {
          var signature = JSON.stringify(value == null ? '' : value);
          if (el.__fxDefaultSignature !== signature) {
            el.__fxDefaultSignature = signature;
            if (el.type === 'date' && value instanceof Date) {
              value = value.getFullYear() + '-' + String(value.getMonth() + 1).padStart(2, '0') + '-' + String(value.getDate()).padStart(2, '0');
            }
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
  function gallery(name, itemsFn, rowFn, handlers) {
    var mounted = new Map();
    var identities = new WeakMap(), nextIdentity = 0;
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
    function choose(row) {
      controlValues[name] = Object.assign({}, controlValues[name] || {}, {
        selected: row.__fxItem, selected_items: [row.__fxItem],
      });
    }
    function invoke(row, control, event) {
      var descriptor = (handlers || {})[control];
      var fn = descriptor && (typeof descriptor === 'function' ? descriptor : descriptor[event]);
      if (!fn) return Promise.resolve();
      var queued = [];
      return Promise.resolve().then(function () {
        return fn(row.__fxItem, row, function (target) {
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
            var targetElement = row.querySelector('[data-control="' + target + '"]');
            if (targetElement) targetElement.click();
            else global.selectControl(target);
          });
        }, Promise.resolve());
      }).catch(function (err) {
        console.error(err);
        toast('Error: ' + (err && err.message ? err.message : err), true);
      });
    }
    evaluators.push({
      apply: function () {
        var host = document.querySelector('[data-control="' + name + '"]');
        if (!host || typeof host.querySelector !== 'function') return;
        var tpl = host.querySelector('template');
        var rowsEl = host.querySelector('.fx-rows');
        if (!tpl || !rowsEl) return;
        var items;
        try { items = itemsFn() || []; } catch (e) { console.error('gallery Items error', name, e); items = []; }
        if (!Array.isArray(items)) items = [];
        var current = controlValues[name] && controlValues[name].selected;
        var selected = items.find(function (item) { return sameRecord(item, current); }) || null;
        controlValues[name] = Object.assign({}, controlValues[name] || {}, {
          all_items: items,
          selected: selected,
          selected_items: selected ? [selected] : [],
        });
        var rowMarkup = String(tpl.innerHTML || '').trim();
        var focused = document.activeElement;
        var restoreFocus = focused && typeof rowsEl.contains === 'function' && rowsEl.contains(focused);
        var selectionStart = restoreFocus ? focused.selectionStart : null;
        var selectionEnd = restoreFocus ? focused.selectionEnd : null;
        var used = new Map(), next = new Map();
        var renderedRows = items.map(function (item, index) {
          var base = identity(item), occurrence = used.get(base) || 0;
          used.set(base, occurrence + 1);
          var key = base + ':' + occurrence;
          var row = mounted.get(key);
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
                el.addEventListener(event === 'OnSelect' ? 'click' : 'change', function (domEvent) {
                  if (domEvent) domEvent.stopPropagation();
                  choose(row);
                  invoke(row, control, event);
                });
              });
            });
            row.querySelectorAll('input, textarea, select').forEach(function (el) {
              el.addEventListener('input', updateBindings);
            });
          }
          row.__fxItem = item;
          next.set(key, row);
          // Avoid moving an already correctly placed node: moving a focused
          // input's ancestor blurs it in Chromium even if the node is reused.
          if (rowsEl.children[index] !== row) rowsEl.insertBefore(row, rowsEl.children[index] || null);
          return row;
        });
        mounted.forEach(function (row, key) { if (!next.has(key)) row.remove(); });
        mounted = next;
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
          if (rowFn) {
            try { rowFn(item, row); } catch (e) { console.error('gallery row error', e); }
          }
        });
        if (restoreFocus && rowsEl.contains(focused) && document.activeElement !== focused) {
          focused.focus({preventScroll: true});
          if (typeof focused.setSelectionRange === 'function' && selectionStart !== null) {
            focused.setSelectionRange(selectionStart, selectionEnd);
          }
        }
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
    var el = document.querySelector('[data-control="' + name + '"]');
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
    var el = element || document.querySelector('[data-control="' + name + '"]');
    if (!el) throw new Error('control not found for Reset: ' + name);
    var value = el.getAttribute('data-fx-default');
    if (el.type === 'checkbox') el.checked = value === 'true';
    else el.value = value === null ? '' : value;
    updateBindings();
    return value;
  }

  function inputControl(name, parentName, propertyFns) {
    var evaluator = {apply: function () { rowControl(document, name, parentName, propertyFns); }};
    var el = document.querySelector('[data-control="' + name + '"]');
    if (el && !el.__fxInputUpdates) {
      el.__fxInputUpdates = true;
      el.addEventListener('input', updateBindings);
      el.addEventListener('change', updateBindings);
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
    registerControlProps: registerControlProps,
    styleControl: styleControl,
    attrControl: attrControl,
    htmlControl: htmlControl,
    sanitizeHtml: sanitizeHtml,
    rowControl: rowControl,
    rowValue: rowValue,
    resetRowControl: function (row, name) {
      return resetControl(name, row.querySelector('[data-control="' + name + '"]'));
    },
    optionRecord: optionRecord,
    applyDefaultSelection: applyDefaultSelection,
    gallery: gallery,
    renderChart: renderChart,
    setFormMode: setFormMode,
    resetForm: resetForm,
    resetControl: resetControl,
    registerTimer: registerTimer,
    focusControl: function (name) {
      var el = document.querySelector('[data-control="' + name + '"]');
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
