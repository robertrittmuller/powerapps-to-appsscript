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
      try { e.apply(); } catch (err) { console.error('binding error', err); }
    });
  }

  function setState(patch) {
    Object.keys(patch).forEach(function (k) { state[k] = patch[k]; });
    updateBindings();
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
    if (fn) { try { fn(); } catch (e) { console.error(e); } }
    updateBindings();
  }

  function bind(name, event, fn) {
    var el = document.querySelector('[data-control="' + name + '"]');
    if (!el) { console.warn('control not found for binding:', name); return; }
    el.addEventListener(event === 'OnSelect' ? 'click' : 'change', function () {
      Promise.resolve().then(fn).catch(function (e) {
        console.error(e);
        toast('Error: ' + (e && e.message ? e.message : e), true);
      });
    });
  }

  function val(name) {
    var el = document.querySelector('[data-control="' + name + '"]');
    if (!el) return { text: '', value: '', selected: null, checked: false };
    var isSelect = el.tagName === 'SELECT';
    return {
      text: 'value' in el ? el.value : (el.textContent || ''),
      value: el.value !== undefined ? el.value : el.textContent,
      checked: !!el.checked,
      selected: isSelect && el.selectedOptions[0] ? el.selectedOptions[0].value : null,
      selectedDate: el.value ? el.value : null,
      el: el,
    };
  }

  function submitForm(name) {
    // Converted apps do not use real <form> posts; the generated handler
    // calls apiCreate/apiPatch directly. Kept for formula compatibility.
    return Promise.resolve();
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
    return serverRun('api', ds, 'removeIf', {}).then(function () { return refreshData(ds); });
  };
  global.apiCreate = function (ds, record) {
    return serverRun('api', ds, 'create', { record: record }).then(function (r) {
      return refreshData(ds).then(function () { return r; });
    });
  };
  global.apiClearCollect = function (ds, record) {
    return apiCreate(ds, record);
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
    addEvaluator: function (apply) { evaluators.push({ apply: apply }); apply(); },
    registerScreenHandler: function (name, fn) { handlers['__screen__' + name] = fn; },
  };
  global.go = go;
  global.goBack = goBack;
  global.toast = toast;
  global.state = state;
  global.val = val;
  global.submitForm = submitForm;
  global.refreshData = refreshData;

  if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
      if (typeof global.APP_MAIN === 'function') global.APP_MAIN();
    });
  }
})(typeof window !== 'undefined' ? window : globalThis);
