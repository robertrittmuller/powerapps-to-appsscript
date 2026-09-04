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
  var screenStack = [];
  var CURRENT_SCREEN = null;

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
      selected: isSelect && el.selectedOptions[0] ? el.selectedOptions[0].value : null,
      selectedDate: el.value ? el.value : null,
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

  function optionRecord(row) {
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
        if (Object.prototype.hasOwnProperty.call(row, keys[i])) {
          var found = scalarAt(keys[i]);
          if (found !== null) return found;
        }
      }
      return null;
    }
    var label = first(['name', 'Name', 'label', 'Label', 'title', 'Title',
      'value', 'Value', 'category', 'Category', 'type', 'Type']);
    if (label === null) {
      var ownKeys = Object.keys(row).filter(function (key) { return key.slice(0, 2) !== '__'; });
      label = first(ownKeys);
    }
    if (label === null) label = JSON.stringify(row);
    var value = first(['value', 'Value', 'id', 'ID', 'key', 'Key']);
    return { value: value === null ? label : value, label: label };
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

  /**
   * Gallery rendering: itemsFn returns the row array, rowFn fills a cloned
   * row template, handlers maps child control name -> async fn(item).
   * Re-renders on every state change (registered as an evaluator).
   */
  function gallery(name, itemsFn, rowFn, handlers) {
    evaluators.push({
      apply: function () {
        var host = document.querySelector('[data-control="' + name + '"]');
        if (!host) return;
        var tpl = host.querySelector('template');
        var rowsEl = host.querySelector('.fx-rows');
        if (!tpl || !rowsEl) return;
        var items;
        try { items = itemsFn() || []; } catch (e) { items = []; }
        if (!Array.isArray(items)) items = [];
        rowsEl.innerHTML = '';
        items.forEach(function (item) {
          var row = tpl.content.firstElementChild.cloneNode(true);
          row.style.position = 'relative';
          rowsEl.appendChild(row);
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

  function submitForm(name) {
    throw new Error('SubmitForm is not implemented for generated forms: ' + name);
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
    // Approximation: NewForm/EditForm/ViewForm set a mode flag on state.
    // Data-entry behavior is driven by the generated apiCreate/apiPatch calls.
    state['__formMode_' + name] = mode;
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
    state: state,
    serverRun: serverRun,
    toast: toast,
    go: go,
    goBack: goBack,
    showScreen: showScreen,
    bind: bind,
    val: val,
    submitForm: submitForm,
    refreshData: refreshData,
    updateBindings: updateBindings,
    setState: setState,
    registerControlProps: registerControlProps,
    styleControl: styleControl,
    attrControl: attrControl,
    optionRecord: optionRecord,
    gallery: gallery,
    setFormMode: setFormMode,
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
