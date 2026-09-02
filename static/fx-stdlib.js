/**
 * fx-stdlib.js — JavaScript implementations of the Power Fx functions the
 * rule-based transpiler emits (FX.* namespace). Pure JS; runs in the browser
 * and under `node --test`.
 */
(function (global) {
  'use strict';

  function asArray(v) {
    if (Array.isArray(v)) return v;
    if (v == null) return [];
    return [v];
  }
  function rows(t) {
    return asArray(t);
  }
  function isBlank(v) {
    return v === null || v === undefined || v === '';
  }
  function toNum(v) {
    if (typeof v === 'number') return v;
    if (typeof v === 'boolean') return v ? 1 : 0;
    var n = parseFloat(String(v).replace(/[^0-9eE+\-.]/g, ''));
    return isNaN(n) ? 0 : n;
  }
  function toDate(v) {
    if (v instanceof Date) return v;
    return new Date(v);
  }
  function startOfDay(d) {
    var x = new Date(d);
    x.setHours(0, 0, 0, 0);
    return x;
  }

  var FX = {
    // --- predicates / equality -------------------------------------------
    eq: function (a, b) { return a == b; },        // Power Fx compares loosely across text/number
    neq: function (a, b) { return a != b; },
    concatStr: function (a, b) {
      return (a == null ? '' : String(a)) + (b == null ? '' : String(b));
    },
    contains: function (needle, haystack) {
      if (Array.isArray(haystack)) return haystack.indexOf(needle) >= 0;
      return String(haystack).indexOf(String(needle)) >= 0;
    },
    isBlank: isBlank,
    isBlankOrError: function (v) { return isBlank(v); },
    isEmpty: function (t) { return rows(t).length === 0; },
    isNumeric: function (v) { return !isNaN(parseFloat(v)) && isFinite(v); },
    coalesce: function (list) {
      for (var i = 0; i < list.length; i++) if (!isBlank(list[i])) return list[i];
      return null;
    },
    ifError: function (tryFn, catchFn) {
      try { return tryFn(); } catch (e) { return catchFn(); }
    },
    withRow: function (record, fn) { return fn(Object.assign({}, record)); },
    unsupported: function (name) {
      throw new Error('Power Fx function not supported in converted app: ' + name +
        ' (see conversion-report.md)');
    },

    // --- tables ------------------------------------------------------------
    filter: function (t, pred) { return rows(t).filter(pred); },
    forAll: function (t, fn) { return rows(t).map(fn); },
    lookUp: function (t, pred) {
      for (var i = 0; i < rows(t).length; i++) if (pred(rows(t)[i])) return rows(t)[i];
      return null;
    },
    countRows: function (t) { return rows(t).length; },
    countIf: function (t, pred) { return rows(t).filter(pred).length; },
    concat: function (t, fn, sep) {
      return rows(t).map(fn).join(sep == null ? '' : String(sep));
    },
    first: function (t) { return rows(t)[0] || null; },
    last: function (t) { var r = rows(t); return r[r.length - 1] || null; },
    sort: function (t, keyFn, order) {
      var s = rows(t).slice().sort(function (a, b) {
        var ka = keyFn(a), kb = keyFn(b);
        return ka < kb ? -1 : ka > kb ? 1 : 0;
      });
      if (String(order).toLowerCase() === 'sortorder.descending') s.reverse();
      return s;
    },
    sortByColumns: function (t, cols, orders) {
      var c = asArray(cols), o = asArray(orders);
      return rows(t).slice().sort(function (a, b) {
        for (var i = 0; i < c.length; i++) {
          var k = c[i], av = a[k], bv = b[k];
          if (av < bv) return o[i] === 'SortOrder.Descending' ? 1 : -1;
          if (av > bv) return o[i] === 'SortOrder.Descending' ? -1 : 1;
        }
        return 0;
      });
    },
    distinct: function (t, keyFn) {
      var seen = [], out = [];
      rows(t).forEach(function (r) {
        var k = keyFn(r);
        if (seen.indexOf(JSON.stringify(k)) < 0) { seen.push(JSON.stringify(k)); out.push(r); }
      });
      return out;
    },
    addColumns: function (t) {
      // emitter passes [table, name1, fn1, name2, fn2...]
      var args = Array.prototype.slice.call(arguments);
      var table = rows(args[0]).map(function (r) { return Object.assign({}, r); });
      for (var i = 1; i + 1 < args.length; i += 2) {
        var name = args[i], fn = args[i + 1];
        table.forEach(function (r) { r[name] = fn(r); });
      }
      return table;
    },
    sum: function (t, keyFn) {
      return rows(t).reduce(function (acc, r) { return acc + toNum(keyFn(r)); }, 0);
    },
    average: function (t, keyFn) {
      var r = rows(t);
      return r.length ? FX.sum(t, keyFn) / r.length : 0;
    },
    min: function () { return Math.min.apply(null, flattenArgs(arguments).map(toNum)); },
    max: function () { return Math.max.apply(null, flattenArgs(arguments).map(toNum)); },

    // --- numbers -----------------------------------------------------------
    value: toNum,
    mod: function (a, b) { return ((toNum(a) % toNum(b)) + toNum(b)) % toNum(b); },
    round: function (v, places) {
      var p = Math.pow(10, places == null ? 0 : toNum(places));
      return Math.round(toNum(v) * p) / p;
    },
    roundUp: function (v, places) {
      var p = Math.pow(10, places == null ? 0 : toNum(places));
      return Math.ceil(toNum(v) * p) / p;
    },
    roundDown: function (v, places) {
      var p = Math.pow(10, places == null ? 0 : toNum(places));
      return Math.floor(toNum(v) * p) / p;
    },

    // --- text --------------------------------------------------------------
    trim: function (s) { return String(s == null ? '' : s).replace(/\s+/g, ' ').trim(); },
    right: function (s, n) {
      var str = String(s == null ? '' : s);
      var k = toNum(n);
      return k <= 0 ? '' : str.slice(Math.max(0, str.length - k));
    },
    proper: function (s) {
      return String(s == null ? '' : s).replace(/\w\S*/g, function (w) {
        return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
      });
    },
    substitute: function (s, old, rep) {
      return String(s == null ? '' : s).split(String(old)).join(String(rep));
    },
    replace: function (s, start, count, rep) {
      var str = String(s == null ? '' : s);
      return str.slice(0, toNum(start) - 1) + String(rep) + str.slice(toNum(start) - 1 + toNum(count));
    },
    text: function (v, fmt) {
      var str = String(v == null ? '' : v);
      if (!fmt) return str;
      var f = String(fmt);
      if (/0\.00/.test(f)) return toNum(v).toFixed((f.split('.')[1] || '00').length);
      if (/yyyy|mm|dd/i.test(f)) {
        var d = toDate(v);
        if (!isNaN(d.getTime())) {
          return f.replace(/yyyy/i, String(d.getFullYear()))
            .replace(/mm/i, String(d.getMonth() + 1).padStart(2, '0'))
            .replace(/dd/i, String(d.getDate()).padStart(2, '0'));
        }
      }
      if (/^#,#/.test(f)) return toNum(v).toLocaleString();
      return str;
    },
    guid: function () {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = (Math.random() * 16) | 0;
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
      });
    },

    // --- colors / encoding --------------------------------------------------
    rgba: function (r, g, b, a) {
      var hex = function (n) {
        var v = Math.max(0, Math.min(255, Math.round(toNum(n))));
        return v.toString(16).padStart(2, '0');
      };
      return '#' + hex(r) + hex(g) + hex(b);
    },
    colorFade: function (color, percentage) {
      return color; // approximation: fade not implemented, color passes through
    },
    plainText: function (html) {
      var el = typeof document !== 'undefined' ? document.createElement('div') : null;
      if (el) { el.innerHTML = String(html == null ? '' : html); return el.textContent || ''; }
      return String(html == null ? '' : html).replace(/<[^>]*>/g, '');
    },
    sequence: function (count, start, step) {
      var n = Math.max(0, Math.floor(toNum(count))), s = toNum(start == null ? 1 : start),
        d = toNum(step == null ? 1 : step), out = [];
      for (var i = 0; i < n; i++) out.push(s + i * d);
      return out;
    },
    split: function (text, separator) {
      return String(text == null ? '' : text).split(String(separator == null ? '' : separator));
    },
    showColumns: function (t, cols) {
      return FX.forAll(t, function (row) {
        var out = {};
        cols.forEach(function (c) { if (row[c] !== undefined) out[c] = row[c]; });
        return out;
      });
    },
    dropColumns: function (t, cols) {
      return FX.forAll(t, function (row) {
        var out = Object.assign({}, row);
        cols.forEach(function (c) { delete out[c]; });
        return out;
      });
    },
    renameColumns: function (t, pairs) {
      // pairs = [old1, new1, old2, new2, ...]
      return FX.forAll(t, function (row) {
        var out = Object.assign({}, row);
        for (var i = 0; i + 1 < pairs.length; i += 2) {
          if (out[pairs[i]] !== undefined) { out[pairs[i + 1]] = out[pairs[i]]; delete out[pairs[i]]; }
        }
        return out;
      });
    },
    search: function (t, needle, cols) {
      var n = String(needle == null ? '' : needle).toLowerCase();
      return FX.filter(t, function (row) {
        return cols.some(function (c) {
          return String(row[c] == null ? '' : row[c]).toLowerCase().indexOf(n) >= 0;
        });
      });
    },
    colorValue: function (v) {
      if (v == null) return '';
      var s = String(v).trim();
      if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(s)) return s;
      var named = { red: '#f00', green: '#008000', blue: '#00f', yellow: '#ff0',
        white: '#fff', black: '#000', gray: '#808080', grey: '#808080',
        orange: '#ffa500', purple: '#800080', pink: '#ffc0cb', brown: '#a52a2a' };
      var key = s.toLowerCase();
      if (named[key]) return named[key];
      var el = typeof document !== 'undefined' ? document.createElement('div') : null;
      if (el) { el.style.color = s; return el.style.color; }
      return s;
    },
    allOf: function (list) { return list.every(Boolean); },
    anyOf: function (list) { return list.some(Boolean); },
    randBetween: function (lo, hi) {
      var a = Math.ceil(toNum(lo)), b = Math.floor(toNum(hi));
      return a + Math.floor(Math.random() * (b - a + 1));
    },
    firstN: function (t, n) { return rows(t).slice(0, Math.max(0, toNum(n))); },
    lastN: function (t, n) {
      var r = rows(t), k = Math.max(0, toNum(n));
      return k === 0 ? [] : r.slice(Math.max(0, r.length - k));
    },
    removeItems: function (t, remove) {
      var drop = new Set(rows(remove).map(function (r) { return JSON.stringify(r); }));
      return rows(t).filter(function (r) { return !drop.has(JSON.stringify(r)); });
    },
    concurrent: function (fns) { return Promise.all(fns); },

    // --- dates ---------------------------------------------------------------
    today: function () { return startOfDay(new Date()); },
    now: function () { return new Date(); },
    year: function (d) { return toDate(d).getFullYear(); },
    month: function (d) { return toDate(d).getMonth() + 1; },
    day: function (d) { return toDate(d).getDate(); },
    hour: function (d) { return toDate(d).getHours(); },
    minute: function (d) { return toDate(d).getMinutes(); },
    weekday: function (d) { return toDate(d).getDay() + 1; }, // Sunday=1 like Power Fx
    dateAdd: function (d, n, unit) {
      var x = toDate(d), k = toNum(n);
      switch (String(unit || 'days').toLowerCase()) {
        case 'milliseconds': return new Date(x.getTime() + k);
        case 'seconds': return new Date(x.getTime() + k * 1000);
        case 'minutes': return new Date(x.getTime() + k * 60000);
        case 'hours': return new Date(x.getTime() + k * 3600000);
        case 'days': default:
          x.setDate(x.getDate() + k); return x;
        case 'months':
          x.setMonth(x.getMonth() + k); return x;
        case 'quarters':
          x.setMonth(x.getMonth() + k * 3); return x;
        case 'years':
          x.setFullYear(x.getFullYear() + k); return x;
      }
    },
    dateDiff: function (a, b, unit) {
      var ms = toDate(b).getTime() - toDate(a).getTime();
      switch (String(unit || 'days').toLowerCase()) {
        case 'seconds': return ms / 1000;
        case 'minutes': return ms / 60000;
        case 'hours': return ms / 3600000;
        case 'days': default: return Math.round(ms / 86400000);
        case 'months': return (toDate(b).getFullYear() - toDate(a).getFullYear()) * 12 +
          (toDate(b).getMonth() - toDate(a).getMonth());
        case 'quarters': return FX.dateDiff(a, b, 'years') * 4;
        case 'years': return toDate(b).getFullYear() - toDate(a).getFullYear();
      }
    },
    date: function (y, m, d) { return new Date(toNum(y), toNum(m) - 1, toNum(d)); },
    time: function (h, m, s) {
      var d = new Date();
      d.setHours(toNum(h), toNum(m), toNum(s || 0), 0);
      return d;
    },
  };

  function flattenArgs(args) {
    var out = [];
    for (var i = 0; i < args.length; i++) {
      if (Array.isArray(args[i])) out = out.concat(args[i]);
      else out.push(args[i]);
    }
    return out;
  }

  global.FX = FX;
  if (typeof module !== 'undefined' && module.exports) module.exports = FX;
})(typeof window !== 'undefined' ? window : globalThis);
