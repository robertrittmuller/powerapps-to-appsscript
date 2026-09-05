/**
 * fx-charts.js — dependency-free SVG chart renderer for converted apps.
 * Power Apps chart controls (pie/bar/line/column) bind to a table via Items;
 * this renders the same shape as static SVG and is re-run by the runtime
 * whenever the bound data changes. Pure functions; testable under node --test.
 */
(function (global) {
  'use strict';

  var PALETTE = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f',
                 '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac'];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function num(v) {
    var n = parseFloat(v);
    return isNaN(n) ? 0 : n;
  }

  /** Auto-detect category (first string-ish) and value (first numeric) columns. */
  function pickColumns(rows) {
    var cat = null, val = null;
    if (!rows.length) return { cat: null, val: null };
    var keys = Object.keys(rows[0]);
    keys.forEach(function (k) {
      if (cat === null) {
        var sample = rows.slice(0, 5).every(function (r) {
          return r[k] === null || r[k] === undefined || typeof r[k] === 'string';
        });
        if (sample) cat = k;
      }
      if (val === null) {
        var numeric = rows.slice(0, 5).some(function (r) {
          return typeof r[k] === 'number' || (typeof r[k] === 'string' && r[k] !== '' && !isNaN(parseFloat(r[k])));
        });
        if (numeric && k !== cat) val = k;
      }
    });
    return { cat: cat, val: val };
  }

  function model(rows, cfg) {
    cfg = cfg || {};
    rows = Array.isArray(rows) ? rows : [];
    var cat = cfg.cat, val = cfg.val;
    if (!cat || !val) {
      var picked = pickColumns(rows);
      cat = cat || picked.cat;
      val = val || picked.val;
    }
    var cats = rows.map(function (r) { return cat && r[cat] != null ? r[cat] : ''; });
    var vals = rows.map(function (r) { return num(val ? r[val] : 0); });
    return {
      cat: cat,
      val: val,
      cats: cats,
      vals: vals,
      series: cats.map(function (label, i) {
        return {
          label: label,
          value: vals[i],
          color: rows[i] && rows[i].color || PALETTE[i % PALETTE.length],
        };
      }),
    };
  }

  function emptySvg(w, h, foreground) {
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
      '<text x="' + (w / 2) + '" y="' + (h / 2) + '" text-anchor="middle" ' +
      'font-family="system-ui" font-size="12" fill="' + esc(foreground || '#888') +
      '">No data</text></svg>';
  }

  function barSvg(cats, vals, w, h, foreground) {
    var padL = 30, padB = 22, padT = 10;
    var innerW = w - padL - 10, innerH = h - padB - padT;
    var max = Math.max.apply(null, vals.concat([1]));
    var slot = innerW / vals.length;
    var bw = Math.min(72, Math.max(4, slot * 0.65));
    var parts = [];
    vals.forEach(function (v, i) {
      var bh = Math.max(0, (v / max) * innerH);
      var x = padL + i * slot + (slot - bw) / 2;
      var y = padT + innerH - bh;
      parts.push('<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) +
        '" width="' + bw.toFixed(1) + '" height="' + Math.max(bh, 1).toFixed(1) +
        '" fill="' + PALETTE[i % PALETTE.length] + '"/>');
      parts.push('<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (h - 8) +
        '" text-anchor="middle" font-family="system-ui" font-size="9" fill="' +
        esc(foreground || '#555') + '">' +
        esc(cats[i]) + '</text>');
      parts.push('<text x="' + (x + bw / 2).toFixed(1) + '" y="' + Math.max(9, y - 4).toFixed(1) +
        '" text-anchor="middle" font-family="system-ui" font-size="9" fill="' +
        esc(foreground || '#555') + '">' +
        esc(v) + '</text>');
    });
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
      parts.join('') + '</svg>';
  }

  function lineSvg(cats, vals, w, h, foreground) {
    var padL = 30, padB = 22, padT = 10;
    var innerW = w - padL - 10, innerH = h - padB - padT;
    var max = Math.max.apply(null, vals.concat([1]));
    var min = Math.min.apply(null, vals.concat([0]));
    var range = max - min || 1;
    var pts = vals.map(function (v, i) {
      var x = padL + (vals.length === 1 ? innerW / 2 : (i / (vals.length - 1)) * innerW);
      var y = padT + innerH - ((v - min) / range) * innerH;
      return [x, y];
    });
    var parts = ['<polyline fill="none" stroke="' + PALETTE[0] + '" stroke-width="2" points="' +
      pts.map(function (p) { return p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join(' ') + '"/>'];
    pts.forEach(function (p, i) {
      parts.push('<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) +
        '" r="3" fill="' + PALETTE[0] + '"/>');
      parts.push('<text x="' + p[0].toFixed(1) + '" y="' + (h - 8) +
        '" text-anchor="middle" font-family="system-ui" font-size="9" fill="' +
        esc(foreground || '#555') + '">' +
        esc(cats[i]) + '</text>');
    });
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
      parts.join('') + '</svg>';
  }

  function pieSvg(cats, vals, w, h) {
    var total = vals.reduce(function (a, b) { return a + Math.max(0, b); }, 0);
    var r = Math.min(w, h) / 2 - 12;
    var cx = r + 12, cy = h / 2;
    var parts = [];
    var angle = -Math.PI / 2;
    if (total > 0) {
      vals.forEach(function (v, i) {
        var frac = Math.max(0, v) / total;
        if (frac <= 0) return;
        if (frac >= 0.999999) {
          parts.push('<circle cx="' + cx + '" cy="' + cy + '" r="' + r +
            '" fill="' + PALETTE[i % PALETTE.length] + '"/>');
          parts.push('<text x="' + cx + '" y="' + (cy + 4) +
            '" text-anchor="middle" font-family="system-ui" font-size="10" fill="#fff">' +
            esc(cats[i]) + '</text>');
          angle += Math.PI * 2;
          return;
        }
        var a2 = angle + frac * Math.PI * 2;
        var x1 = cx + r * Math.cos(angle), y1 = cy + r * Math.sin(angle);
        var x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
        var large = frac > 0.5 ? 1 : 0;
        parts.push('<path d="M ' + cx + ' ' + cy + ' L ' + x1.toFixed(1) + ' ' + y1.toFixed(1) +
          ' A ' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x2.toFixed(1) + ' ' + y2.toFixed(1) + ' Z" fill="' +
          PALETTE[i % PALETTE.length] + '"/>');
        var mid = angle + (a2 - angle) / 2;
        parts.push('<text x="' + (cx + r * 0.62 * Math.cos(mid)).toFixed(1) + '" y="' +
          (cy + r * 0.62 * Math.sin(mid) + 3).toFixed(1) +
          '" text-anchor="middle" font-family="system-ui" font-size="9" fill="#fff">' +
          esc(cats[i]) + '</text>');
        angle = a2;
      });
    }
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
      parts.join('') + '</svg>';
  }

  function legendSvg(series, w, h, foreground) {
    if (!series.length) return emptySvg(w, h, foreground);
    var itemWidth = Math.max(90, Math.floor(w / Math.min(series.length, 3)));
    var columns = Math.max(1, Math.floor(w / itemWidth));
    var parts = [];
    series.forEach(function (entry, i) {
      var col = i % columns, row = Math.floor(i / columns);
      var x = 4 + col * itemWidth, y = 5 + row * 18;
      parts.push('<rect x="' + x + '" y="' + y + '" width="10" height="10" rx="2" fill="' +
        esc(entry.color || PALETTE[i % PALETTE.length]) + '"/>');
      parts.push('<text x="' + (x + 15) + '" y="' + (y + 9) +
        '" font-family="system-ui" font-size="10" fill="' + esc(foreground || '#333') + '">' +
        esc(entry.label) + '</text>');
    });
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
      parts.join('') + '</svg>';
  }

  function svg(rows, cfg) {
    cfg = cfg || {};
    rows = Array.isArray(rows) ? rows : [];
    var type = cfg.type || 'bar';
    var w = cfg.width || 420, h = cfg.height || 300;
    var foreground = cfg.foreground;
    var chart = model(rows, cfg);
    if (!rows.length || !chart.val) return emptySvg(w, h, foreground);
    if (type === 'legend') return legendSvg(chart.series, w, h, foreground);
    var cats = chart.cats, vals = chart.vals;
    if (type === 'pie') return pieSvg(cats, vals, w, h);
    if (type === 'line') return lineSvg(cats, vals, w, h, foreground);
    return barSvg(cats, vals, w, h, foreground);
  }

  global.FXCharts = {
    svg: svg,
    model: model,
    legend: legendSvg,
    pickColumns: pickColumns,
    palette: PALETTE,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = global.FXCharts;
})(typeof window !== 'undefined' ? window : globalThis);
