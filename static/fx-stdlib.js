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
  // A Symbol survives object copies (gallery AllItems) without becoming a
  // source field or leaking into JSON/Sheets. Plain records never coerce.
  var primaryOutputProperty = Symbol('Power Fx primary output');
  var choiceCode = Symbol('Power Fx exported choice');
  function choiceScalar(value) {
    return value && typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, choiceCode)
      ? value[choiceCode] : value;
  }
  function controlReference(record, property) {
    if (property) Object.defineProperty(record, primaryOutputProperty, {value:property, enumerable:true});
    return record;
  }
  function primaryOutput(value) {
    var property = value && typeof value === 'object' && value[primaryOutputProperty];
    if (!property) return value;
    if (!Object.prototype.hasOwnProperty.call(value, property))
      throw new Error('Unsupported control primary output: ' + property);
    return FX.field(value, property);
  }
  function isNumericError(v) {
    return typeof v === 'number' && !Number.isFinite(v);
  }
  function toNum(v) {
    return isBlank(v) ? 0 : numberValue(v);
  }
  function finiteNumber(value) {
    if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('Numeric result is not finite');
    return value;
  }
  function scalar(value) {
    if (value !== null && typeof value === 'object' && !(value instanceof Date))
      throw new Error('This function requires a scalar; table/record overload is not implemented');
    return finiteNumber(value);
  }
  function numberValue(value, language) {
    scalar(value);
    if (isBlank(value)) return null;
    if (value instanceof Date) return finiteNumber(value.getTime());
    if (typeof value === 'number') return finiteNumber(value);
    if (typeof value === 'boolean') return value ? 1 : 0;
    if (typeof value !== 'string') throw new Error('Value requires numeric text');
    var locale = language || (global.navigator && global.navigator.language) || 'en-US';
    var tag = new Intl.Locale(locale).maximize();
    if (!Intl.NumberFormat.supportedLocalesOf([locale]).length) throw new Error('Unsupported numeric language: ' + locale);
    var parts = new Intl.NumberFormat(locale).formatToParts(12345.6);
    var decimal = parts.find(function (p) { return p.type === 'decimal'; }).value;
    var group = parts.find(function (p) { return p.type === 'group'; });
    var text = value.trim(), percent = /%$/.test(text);
    if (percent) text = text.slice(0, -1).trim();
    // Currency must belong to the requested culture; never strip arbitrary text.
    var currencies = {US:'USD',GB:'GBP',ES:'EUR',FR:'EUR',DE:'EUR',IT:'EUR',PT:'EUR',NL:'EUR',IE:'EUR',
      CA:'CAD',AU:'AUD',NZ:'NZD',IN:'INR',JP:'JPY',CN:'CNY',BR:'BRL',MX:'MXN',CH:'CHF'};
    var currency = currencies[tag.region];
    if (currency) {
      var symbol = new Intl.NumberFormat(locale, {style:'currency',currency:currency}).formatToParts(1)
        .find(function (p) { return p.type === 'currency'; }).value;
      if (text.includes(symbol)) {
        if (percent) throw new Error('Value cannot mix currency and percentage');
        if (text.startsWith(symbol)) text = text.slice(symbol.length).trim();
        else if (text.endsWith(symbol)) text = text.slice(0, -symbol.length).trim();
        else throw new Error('Invalid currency position');
      }
    }
    if (group) text = text.split(group.value).join('');
    if (decimal !== '.') {
      if (text.includes('.')) throw new Error('Invalid numeric separator');
      text = text.replace(decimal, '.');
    }
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text))
      throw new Error('Value cannot convert text to a number');
    return finiteNumber(Number(text) / (percent ? 100 : 1));
  }
  function toDate(v) {
    // Power Fx replaces blank date arithmetic operands with its civil epoch.
    // Undefined initial state must behave like Blank(), not Invalid Date.
    if (isBlank(v)) return new Date(1899, 11, 30);
    if (v instanceof Date) return v;
    return new Date(v);
  }
  function startOfDay(d) {
    var x = new Date(d);
    x.setHours(0, 0, 0, 0);
    return x;
  }
  function arithmeticNumber(value) {
    if (value == null || value === '') return 0;
    if (!['number', 'string', 'boolean'].includes(typeof value)) throw new Error('Arithmetic requires a number or date');
    var number = Number(value);
    if (!Number.isFinite(number)) throw new Error('Arithmetic requires a finite number');
    return number;
  }
  function civilStamp(date) {
    if (!Number.isFinite(date.getTime())) throw new Error('Invalid date arithmetic operand');
    var civil = new Date(0);
    civil.setUTCFullYear(date.getFullYear(), date.getMonth(), date.getDate());
    civil.setUTCHours(date.getHours(), date.getMinutes(), date.getSeconds(), date.getMilliseconds());
    return civil.getTime();
  }
  function dateFromCivil(stamp) {
    function local(value) {
      var civil = new Date(value), result = new Date(0);
      result.setFullYear(civil.getUTCFullYear(), civil.getUTCMonth(), civil.getUTCDate());
      result.setHours(civil.getUTCHours(), civil.getUTCMinutes(), civil.getUTCSeconds(), civil.getUTCMilliseconds());
      return result;
    }
    if (!Number.isFinite(new Date(stamp).getTime())) throw new Error('Date arithmetic is out of range');
    var result = local(stamp), normalized = civilStamp(result);
    // Power Fx moves a nonexistent civil time to the start of the first
    // valid interval. JS otherwise preserves its minutes inside the DST gap.
    if (normalized > stamp) {
      var low = stamp, high = normalized;
      while (high-low > 1) {
        var mid = Math.floor((low+high)/2);
        if (civilStamp(local(mid)) === mid) high = mid; else low = mid;
      }
      result = local(high);
    }
    return result;
  }
  function addDateDays(date, days) {
    return dateFromCivil(civilStamp(date) + arithmeticNumber(days)*86400000);
  }
  // Typed keys avoid collisions between values such as 1/"1", delimiter
  // characters in text, and records whose properties arrived in a new order.
  function valueKey(value, ignoreCase) {
    if (value == null) return ['blank'];
    if (value instanceof Date) return ['date', value.getTime()];
    if (Array.isArray(value)) return ['table', value.map(function (v) { return valueKey(v, ignoreCase); })];
    if (typeof value === 'object') return ['record', Object.keys(value).sort().map(function (key) {
      return [key, valueKey(value[key], ignoreCase)];
    })];
    return [typeof value, ignoreCase && typeof value === 'string' ? value.toLowerCase() : value];
  }

  function localeTag(language) {
    return language || (global.navigator && global.navigator.language) || 'en-US';
  }
  function dayPeriod(hour, language) {
    return new Intl.DateTimeFormat(localeTag(language), {hour: 'numeric', hour12: true})
      .formatToParts(new Date(2020, 0, 1, hour)).find(function (part) { return part.type === 'dayPeriod'; }).value;
  }
  function clockValue(h, m, s, ms) {
    return new Date(1970, 0, 1, h, m, s, ms);
  }
  function timeValue(value, language) {
    if (isBlank(value)) return null;
    if (value instanceof Date) {
      if (!isFinite(value.getTime())) throw new Error('Invalid TimeValue');
      return clockValue(value.getHours(), value.getMinutes(), value.getSeconds(), value.getMilliseconds());
    }
    var text = String(value).trim().replace(/[\u200e\u200f]/g, '');
    // UTC/offset timestamps from external records display in the user's zone.
    if (/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:?\d{2})$/i.test(text)) {
      var instant = new Date(text);
      if (!isFinite(instant.getTime())) throw new Error('Invalid TimeValue timestamp');
      return timeValue(instant, language);
    }
    var lang = localeTag(language);
    var number = new Intl.NumberFormat(lang, {useGrouping: false});
    for (var n = 0; n < 10; n++) text = text.split(number.format(n)).join(String(n));
    var separator = new Intl.DateTimeFormat(lang, {hour: '2-digit', minute: '2-digit', hourCycle: 'h23'})
      .formatToParts(new Date(2020, 0, 1, 13, 24)).find(function (part) { return part.type === 'literal'; }).value;
    if (separator !== ':') text = text.split(separator).join(':');
    var match = /(?:^|[^0-9])(\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d{1,3}))?)?(?![\d:.,])/.exec(text);
    if (!match) throw new Error('TimeValue requires valid clock text');
    var hours = Number(match[1]), minutes = Number(match[2]), seconds = Number(match[3] || 0);
    var milliseconds = Number((match[4] || '').padEnd(3, '0') || 0);
    var remainder = text;
    var period = null;
    ['AM', 'PM', dayPeriod(1, lang), dayPeriod(13, lang)].forEach(function (marker, i) {
      var escaped = marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      if (new RegExp('(?:^|[^a-z])' + escaped + '(?:$|[^a-z])', 'i').test(remainder)) period = i % 2;
    });
    if (minutes > 59 || seconds > 59 || hours > (period === null ? 23 : 12) || (period !== null && hours < 1))
      throw new Error('TimeValue component is out of range');
    if (period !== null) hours = hours % 12 + period * 12;
    return clockValue(hours, minutes, seconds, milliseconds);
  }

  function dateText(value, format, language) {
    if (isBlank(value)) return '';
    var date = new Date(toDate(value).getTime());
    if (!isFinite(date.getTime())) throw new Error('Invalid date for Text');
    var lang = localeTag(language), f = format || 'ShortDateTime';
    if (f === 'UTC') return date.toISOString();
    var enumMatch = /^(Long|Short)(DateTime|Date|Time)(24)?$/.exec(f);
    if (enumMatch) {
      var long = enumMatch[1] === 'Long', kind = enumMatch[2], twentyFour = !!enumMatch[3], pieces = [];
      if (kind.indexOf('Date') >= 0) {
        var dates = {year: 'numeric', month: long ? 'long' : 'numeric', day: 'numeric'};
        if (long) dates.weekday = 'long';
        pieces.push(new Intl.DateTimeFormat(lang, dates).format(date));
      }
      if (kind.indexOf('Time') >= 0) {
        var times = {hour: 'numeric', minute: '2-digit'};
        if (twentyFour) times.hourCycle = 'h23'; else times.hour12 = true;
        if (long) times.second = '2-digit';
        pieces.push(new Intl.DateTimeFormat(lang, times).format(date));
      }
      return pieces.join(' ').replace(/[\u202f\u00a0]/g, ' ');
    }
    var tokens = f.match(/"[^"]*"|AM\/PM|a\/p|yyyy|yy|mmmm|mmm|mm|m|dddd|ddd|dd|d|hh|h|ss|s|fff|ff|f|./gi) || [];
    var fraction = tokens.find(function (token) { return /^f{1,3}$/i.test(token); });
    if (fraction && fraction.length < 3) {
      var precision = Math.pow(10, 3 - fraction.length);
      date.setMilliseconds(Math.round(date.getMilliseconds() / precision) * precision);
    }
    var twelve = tokens.some(function (token) { return /^(am\/pm|a\/p)$/i.test(token); });
    function padded(value, length) { return String(value).padStart(length, '0'); }
    function named(options) { return new Intl.DateTimeFormat(lang, options).format(date); }
    return tokens.map(function (token, index) {
      var lower = token.toLowerCase();
      if (token[0] === '"') return token.slice(1, -1);
      if (lower === 'yyyy') return padded(date.getFullYear(), 4);
      if (lower === 'yy') return padded(date.getFullYear() % 100, 2);
      if (lower === 'mmmm' || lower === 'mmm') return named({month: lower === 'mmmm' ? 'long' : 'short'});
      if (lower === 'dddd' || lower === 'ddd') return named({weekday: lower === 'dddd' ? 'long' : 'short'});
      if (lower === 'd' || lower === 'dd') return padded(date.getDate(), lower.length);
      if (lower === 'h' || lower === 'hh') return padded(twelve ? date.getHours() % 12 || 12 : date.getHours(), lower.length);
      if (lower === 's' || lower === 'ss') return padded(date.getSeconds(), lower.length);
      if (lower === 'm' || lower === 'mm') {
        var before = tokens.slice(0, index).reverse().find(function (part) { return /^[a-z]+$/i.test(part); }) || '';
        var after = tokens.slice(index + 1).find(function (part) { return /^[a-z]+$/i.test(part); }) || '';
        var minute = /^h{1,2}$/i.test(before) || /^s{1,2}$/i.test(after);
        return padded(minute ? date.getMinutes() : date.getMonth() + 1, lower.length);
      }
      if (/^f{1,3}$/.test(lower)) return padded(date.getMilliseconds(), 3).slice(0, lower.length);
      if (lower === 'am/pm') return dayPeriod(date.getHours(), lang);
      if (lower === 'a/p') return date.getHours() < 12 ? 'a' : 'p';
      return token;
    }).join('');
  }

  function regexFor(pattern, options, complete, all) {
    var opts = String(options || '').split('|').filter(Boolean);
    var allowed = ['BeginsWith', 'Complete', 'Contains', 'EndsWith', 'IgnoreCase', 'Multiline', 'NumberedSubMatches'];
    if (opts.some(function (option) { return allowed.indexOf(option) < 0; })) throw new Error('Unsupported canvas match option');
    var boundaries = opts.filter(function (option) { return ['BeginsWith', 'Complete', 'Contains', 'EndsWith'].indexOf(option) >= 0; });
    if (boundaries.length > 1) throw new Error('Conflicting canvas match boundaries');
    var boundary = boundaries[0] || (complete ? 'Complete' : 'Contains');
    var expression = '(?:' + String(pattern) + ')';
    if (boundary === 'Complete' || boundary === 'BeginsWith') expression = '^' + expression;
    if (boundary === 'Complete' || boundary === 'EndsWith') expression += '$';
    return new RegExp(expression, (all ? 'g' : '') + (opts.indexOf('IgnoreCase') >= 0 ? 'i' : '') + (opts.indexOf('Multiline') >= 0 ? 'm' : ''));
  }
  function captureName(name) {
    var out = '', upper = false;
    for (var i = 0; i < name.length; i++) {
      var ch = name[i], nextUpper = /[A-Z]/.test(ch);
      if (nextUpper && i > 0 && !upper) out += '_';
      out += ch.toLowerCase(); upper = nextUpper;
    }
    return out.replace(/^_+|_+$/g, '');
  }
  function matchRecord(match) {
    if (!match) return null;
    var record = {full_match: match[0], start_match: match.index + 1,
      sub_matches: match.slice(1).map(function (value) { return {value: value == null ? null : value}; })};
    Object.keys(match.groups || {}).forEach(function (name) { record[captureName(name)] = match.groups[name] == null ? null : match.groups[name]; });
    return record;
  }

  var FX = {
    // The overloaded + / - operators use calendar days for dates. Raw JS
    // concatenates Date + number and subtracts epoch milliseconds instead.
    add: function (a, b) {
      if (a instanceof Date && b instanceof Date) throw new Error('Adding two dates requires a typed Time adapter');
      if (a instanceof Date) return addDateDays(a, b);
      if (b instanceof Date) return addDateDays(b, a);
      return arithmeticNumber(a) + arithmeticNumber(b);
    },
    subtract: function (a, b) {
      if (a instanceof Date && b instanceof Date) return (civilStamp(a)-civilStamp(b))/86400000;
      if (a instanceof Date) return addDateDays(a, -arithmeticNumber(b));
      if (b instanceof Date) throw new Error('Cannot subtract a date from a number');
      return arithmeticNumber(a) - arithmeticNumber(b);
    },
    // --- predicates / equality -------------------------------------------
    eq: function (a, b) {
      a = choiceScalar(a); b = choiceScalar(b);
      return a instanceof Date && b instanceof Date ? a.getTime() === b.getTime() : a == b;
    },
    neq: function (a, b) { return !FX.eq(a, b); },
    concatStr: function (a, b) {
      return (a == null ? '' : String(a)) + (b == null ? '' : String(b));
    },
    // Used only by the ledgered static-SVG text interpolation repair.
    xmlText: function (value) {
      return (value == null ? '' : String(value)).replace(/[&<>"']/g, function (char) {
        return {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&apos;'}[char];
      });
    },
    // Power Fx treats a field read from Blank()/a missing record as Blank.
    // Raw JavaScript member access throws instead, so emitted nullable reads
    // route through this helper.
    field: function (record, key) {
      if (record == null) return null;
      if (Array.isArray(record)) return record.map(function (row) {
        var projected = {};
        projected[key] = FX.field(row, key);
        return projected;
      });
      if (key === 'value' && typeof record !== 'object') return record;
      if (!Object.prototype.hasOwnProperty.call(Object(record), key) && global.FXRuntime && global.FXRuntime.relationshipField) {
        var related = global.FXRuntime.relationshipField(record, key);
        if (related) return related.value;
      }
      return record[key] === undefined ? null : record[key];
    },
    // Inner record fields shadow outer fields, including explicit Blank values.
    // Only an absent field falls through to the outer scope or app state.
    scopeValue: function (scopes, key, fallback) {
      for (var i = 0; i < scopes.length; i++) {
        var record = scopes[i];
        if (record != null && Object.prototype.hasOwnProperty.call(record, key)) return record[key];
        if (record != null && global.FXRuntime && global.FXRuntime.relationshipField) {
          var related = global.FXRuntime.relationshipField(record, key);
          if (related) return related.value;
        }
        if (key === 'value' && record != null && typeof record !== 'object') return record;
      }
      return fallback();
    },
    contains: function (needle, haystack, exact) {
      if (Array.isArray(haystack)) {
        var key = JSON.stringify(valueKey(needle, !exact));
        return haystack.some(function (row) {
          // A scalar is compared with the sole field of a single-column
          // table. A record is compared with the complete row.
          if ((needle == null || typeof needle !== 'object') && row && typeof row === 'object') {
            var names = Object.keys(row);
            if (names.length === 1) row = row[names[0]];
          }
          return JSON.stringify(valueKey(row, !exact)) === key;
        });
      }
      var text = String(haystack == null ? '' : haystack), part = String(needle == null ? '' : needle);
      return (exact ? text : text.toLowerCase()).indexOf(exact ? part : part.toLowerCase()) >= 0;
    },
    isBlank: isBlank,
    controlReference: controlReference,
    primaryOutput: primaryOutput,
    isError: function (value) {
      try {
        var result = typeof value === 'function' ? value() : value;
        return result && typeof result.then === 'function'
          ? result.then(isNumericError, function () { return true; }) : isNumericError(result);
      } catch (error) { return true; }
    },
    isBlankOrError: function (v) {
      function check(value) { return isBlank(value) || isNumericError(value); }
      try {
        var value = typeof v === 'function' ? v() : v;
        return value && typeof value.then === 'function' ? value.then(check, function () { return true; }) : check(value);
      } catch (error) { return true; }
    },
    isMatch: function (text, pattern, options) { return regexFor(pattern, options, true, false).test(String(text == null ? '' : text)); },
    match: function (text, pattern, options) { return matchRecord(regexFor(pattern, options, false, false).exec(String(text == null ? '' : text))); },
    matchAll: function (text, pattern, options) {
      var regex = regexFor(pattern, options, false, true), out = [], match, input = String(text == null ? '' : text);
      while ((match = regex.exec(input)) !== null) {
        out.push(matchRecord(match));
        if (match[0] === '') regex.lastIndex += 1;
      }
      return out;
    },
    find: function (needle, haystack, start) {
      var position = start == null ? 1 : Number(start);
      if (!isFinite(position) || position < 1) throw new Error('Find starting position must be positive');
      var index = String(haystack == null ? '' : haystack).indexOf(String(needle == null ? '' : needle), Math.floor(position) - 1);
      return index < 0 ? null : index + 1;
    },
    isEmpty: function (t) { return rows(t).length === 0; },
    isNumeric: function (v) { return !isNaN(parseFloat(v)) && isFinite(v); },
    coalesce: function (list) {
      for (var i = 0; i < list.length; i++) if (!isBlank(list[i])) return list[i];
      return null;
    },
    ifError: function (tryFn, catchFn) {
      try {
        var result = tryFn();
        return result && typeof result.then === 'function' ? result.then(finiteNumber).catch(catchFn) : finiteNumber(result);
      } catch (e) { return catchFn(e); }
    },
    withRow: function (record, fn) { return fn(Object.assign({}, record)); },
    unsupported: function (name) {
      throw new Error('Power Fx function not supported in converted app: ' + name +
        ' (see conversion-report.md)');
    },

    // --- tables ------------------------------------------------------------
    filter: function (t, pred) { return rows(t).filter(pred); },
    userId: function (users, email, key, emailField) {
      if (!email) throw new Error('Dataverse current-user view requires an identified Google session');
      var matches = rows(users).filter(function (row) {
        return String(FX.field(row, emailField) || '').toLowerCase() === String(email).toLowerCase();
      });
      if (matches.length !== 1 || !FX.field(matches[0], key))
        throw new Error('Dataverse current-user view requires one migrated user record matching the Google account email');
      return String(FX.field(matches[0], key)).toLowerCase();
    },
    applyView: function (table, query, userId, dateContext) {
      if (!query || query.error) throw new Error(query && query.error || 'Dataverse view definition is missing');
      var blank = function (value) { return value === null || value === undefined || value === ''; };
      // One clock reading and timezone per query, shared by every condition.
      // Compare civil dates rather than subtracting 24-hour durations: local
      // days across a DST transition can be 23 or 25 hours long.
      var relativeContext;
      var instant = function (value) {
        if (Object.prototype.toString.call(value) !== '[object Date]') {
          var match = typeof value === 'string' && /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,7})?(Z|[+-](\d{2}):(\d{2}))$/i.exec(value);
          if (!match) throw new Error('Relative Dataverse view date requires an ISO timestamp with an explicit timezone');
          var calendar = new Date(0);
          calendar.setUTCFullYear(+match[1], +match[2] - 1, +match[3]);
          if (calendar.getUTCFullYear() !== +match[1] || calendar.getUTCMonth() !== +match[2] - 1 ||
              calendar.getUTCDate() !== +match[3] || +match[4] > 23 || +match[5] > 59 || +match[6] > 59 ||
              (match[8] && (+match[8] > 23 || +match[9] > 59)))
            throw new Error('Invalid date in relative Dataverse view');
        }
        var result = new Date(value).getTime();
        if (!Number.isFinite(result)) throw new Error('Invalid date in relative Dataverse view');
        return result;
      };
      var relative = function () {
        if (relativeContext) return relativeContext;
        var context = dateContext || {};
        var now = context.now === undefined ? Date.now() : typeof context.now === 'number' ? context.now : instant(context.now);
        if (!Number.isFinite(now) || !Number.isFinite(new Date(now).getTime()))
          throw new Error('Invalid relative Dataverse view clock');
        var zone = context.timeZone === undefined ? new Intl.DateTimeFormat().resolvedOptions().timeZone : context.timeZone;
        if (typeof zone !== 'string' || !zone) throw new Error('Relative Dataverse view timezone is missing');
        var formatter = new Intl.DateTimeFormat('en-US-u-ca-gregory-nu-latn', {
          timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit'
        });
        var day = function (value) {
          var parts = {};
          formatter.formatToParts(new Date(value)).forEach(function (part) { parts[part.type] = part.value; });
          var date = new Date(0);
          date.setUTCFullYear(+parts.year, +parts.month - 1, +parts.day);
          return date.getTime() / 86400000;
        };
        relativeContext = {now: now, today: day(now), day: day};
        return relativeContext;
      };
      var typed = function (value, type) {
        if (blank(value)) return null;
        if (type === 'date') {
          var date = new Date(value).getTime();
          if (!Number.isFinite(date)) throw new Error('Invalid date in Dataverse view');
          return date;
        }
        if (type === 'number' || type === 'choice') {
          var number = Number(value);
          if (!Number.isFinite(number)) throw new Error('Invalid number in Dataverse view');
          return number;
        }
        if (type === 'bool') {
          if (typeof value !== 'boolean') throw new Error('Invalid boolean in Dataverse view');
          return value;
        }
        if (type === 'text') return String(value).toLowerCase();
        throw new Error('Unsupported Dataverse view field type: ' + type);
      };
      var predicate = function (condition) {
        if (!condition) throw new Error('Dataverse view filter is missing');
        var op = condition.op;
        if (op === 'and' || op === 'or') {
          var children = condition.args.map(predicate);
          return function (row) { return op === 'and'
            ? children.every(function (fn) { return fn(row); })
            : children.some(function (fn) { return fn(row); }); };
        }
        if (op === 'eq-userid' || op === 'ne-userid') {
          if (!userId) throw new Error('Dataverse current-user view identity is missing');
          return function (row) {
            var reference = FX.field(row, condition.field);
            var id = reference && typeof reference === 'object'
              ? FX.field(reference, query.identity.key) || reference.id : reference;
            if (blank(id)) return false;
            return op === 'eq-userid' ? String(id).toLowerCase() === userId : String(id).toLowerCase() !== userId;
          };
        }
        if (['last-seven-days','last-x-days','today','yesterday','tomorrow'].indexOf(op) >= 0) {
          if (condition.type !== 'date' || condition.dateBehavior !== 'UserLocal')
            throw new Error('Relative Dataverse view requires exported UserLocal date behavior');
          if (!Array.isArray(condition.values) || condition.values.length !== (op === 'last-x-days' ? 1 : 0))
            throw new Error('Wrong number of relative Dataverse view values');
          var count = op === 'last-seven-days' ? 7 : condition.values[0];
          if (op === 'last-x-days' && (!Number.isInteger(count) || count < 1 || count > 2147483647))
            throw new Error('last-x-days requires a positive 32-bit integer');
          var clock = relative();
          var targetDay = clock.today + (op === 'yesterday' ? -1 : op === 'tomorrow' ? 1 : 0);
          return function (row) {
            var value = FX.field(row, condition.field);
            if (blank(value)) return false;
            var time = instant(value), rowDay = clock.day(time);
            return op === 'last-seven-days' || op === 'last-x-days'
              ? rowDay >= clock.today - count && time < clock.now : rowDay === targetDay;
          };
        }
        if (['eq','ne','gt','ge','lt','le','in','not-in','null','not-null'].indexOf(op) < 0)
          throw new Error('Unsupported Dataverse view operator: ' + op);
        var values = condition.values.map(function (value) { return typed(value, condition.type); });
        return function (row) {
          var value = typed(FX.field(row, condition.field), condition.type);
          if (op === 'null') return value === null;
          if (op === 'not-null') return value !== null;
          // Dataverse/SQL null comparisons do not turn missing values into 0
          // or include them in a not-equal filter.
          if (value === null) return false;
          if (op === 'eq') return value === values[0];
          if (op === 'ne') return value !== values[0];
          if (op === 'gt') return value > values[0];
          if (op === 'ge') return value >= values[0];
          if (op === 'lt') return value < values[0];
          if (op === 'le') return value <= values[0];
          return op === 'in' ? values.indexOf(value) >= 0 : values.indexOf(value) < 0;
        };
      };
      var result = rows(table).filter(predicate(query.filter));
      return result.sort(function (a, b) {
        for (var i = 0; i < query.order.length; i++) {
          var order = query.order[i], av = typed(FX.field(a, order.field), order.type), bv = typed(FX.field(b, order.field), order.type);
          if (av === bv) continue;
          var comparison = av === null ? -1 : bv === null ? 1 : av < bv ? -1 : 1;
          return order.descending ? -comparison : comparison;
        }
        return 0;
      });
    },
    forAll: function (t, fn) { return rows(t).map(fn); },
    lookUp: function (t, pred, projection) {
      for (var i = 0; i < rows(t).length; i++) if (pred(rows(t)[i])) {
        return projection ? projection(rows(t)[i]) : rows(t)[i];
      }
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
      if (/^(?:SortOrder\.)?Descending$/i.test(String(order))) s.reverse();
      return s;
    },
    sortByColumns: function (t, cols, orders) {
      var c = asArray(cols), o = asArray(orders);
      return rows(t).slice().sort(function (a, b) {
        for (var i = 0; i < c.length; i++) {
          var k = c[i], av = a[k], bv = b[k];
          var descending = /^(?:SortOrder\.)?Descending$/i.test(String(o[i]));
          if (av < bv) return descending ? 1 : -1;
          if (av > bv) return descending ? -1 : 1;
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
      var table = rows(args[0]).map(function (r) {
        // Preserve record aliases/control getters while adding columns; scalar
        // table entries introduce the single Value field, never string indices.
        return r !== null && typeof r === 'object'
          ? Object.defineProperties({}, Object.getOwnPropertyDescriptors(r)) : {value:r};
      });
      for (var i = 1; i + 1 < args.length; i += 2) {
        var name = args[i], fn = args[i + 1];
        table.forEach(function (r) { r[name] = fn(r); });
      }
      return table;
    },
    groupBy: function (t, columns, groupColumn) {
      if (!columns.length || new Set(columns).size !== columns.length || columns.indexOf(groupColumn) >= 0)
        throw new Error('GroupBy requires distinct grouping columns and a separate group column');
      var groups = new Map(), result = [];
      rows(t).forEach(function (row) {
        var key = JSON.stringify(columns.map(function (column) { return valueKey(FX.field(row, column), false); }));
        var group = groups.get(key);
        if (!group) {
          group = {};
          columns.forEach(function (column) { group[column] = FX.field(row, column); });
          group[groupColumn] = [];
          groups.set(key, group);
          result.push(group);
        }
        var remaining = Object.assign({}, row);
        columns.forEach(function (column) { delete remaining[column]; });
        group[groupColumn].push(remaining);
      });
      return result;
    },
    ungroup: function (t, groupColumn) {
      var result = [];
      rows(t).forEach(function (group) {
        // Scalar single-column tables use bare values internally. Nested
        // ForAll therefore produces an array of tables in the Value column.
        if (Array.isArray(group) && groupColumn === 'value') {
          result = result.concat(group);
          return;
        }
        var outer = Object.assign({}, group);
        delete outer[groupColumn];
        rows(FX.field(group, groupColumn)).forEach(function (row) {
          result.push(Object.assign({}, outer, row));
        });
      });
      return result;
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
    scalar: scalar,
    tableArg: function (value) {
      if (isBlank(value)) return [];
      if (!Array.isArray(value)) throw new Error('This mapping requires a table; scalar/record overload is not implemented');
      return value;
    },
    value: numberValue,
    multiply: function (a, b) { return finiteNumber(arithmeticNumber(a) * arithmeticNumber(b)); },
    divide: function (a, b) {
      var denominator = arithmeticNumber(b);
      if (denominator === 0) throw new Error('Division by zero');
      return finiteNumber(arithmeticNumber(a) / denominator);
    },
    mod: function (a, b) { return ((toNum(a) % toNum(b)) + toNum(b)) % toNum(b); },
    round: function (v, places) {
      var p = Math.pow(10, places == null ? 0 : toNum(places));
      var n = toNum(v); return finiteNumber(Math.sign(n) * Math.round(Math.abs(n) * p) / p);
    },
    roundUp: function (v, places) {
      var p = Math.pow(10, places == null ? 0 : toNum(places));
      var n = toNum(v); return finiteNumber(Math.sign(n) * Math.ceil(Math.abs(n) * p) / p);
    },
    roundDown: function (v, places) {
      var p = Math.pow(10, places == null ? 0 : toNum(places));
      return finiteNumber(Math.trunc(toNum(v) * p) / p);
    },

    // --- text --------------------------------------------------------------
    trim: function (s) { return String(s == null ? '' : s).replace(/\s+/g, ' ').trim(); },
    right: function (s, n) {
      var str = String(s == null ? '' : s);
      var k = toNum(n);
      if (k < 0) throw new Error('Right count cannot be negative');
      return k <= 0 ? '' : str.slice(Math.max(0, str.length - k));
    },
    proper: function (s) {
      return String(s == null ? '' : s).replace(/\w\S*/g, function (w) {
        return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
      });
    },
    substitute: function (s, old, rep, instance) {
      var text = String(s == null ? '' : s), needle = String(old == null ? '' : old), replacement = String(rep == null ? '' : rep);
      if (instance != null && (!Number.isInteger(instance) || instance < 1)) throw new Error('Substitute instance must be a positive integer');
      if (!needle) return text;
      if (instance == null) return text.split(needle).join(replacement);
      var from = 0, at = -1;
      for (var i = 0; i < instance; i++) {
        at = text.indexOf(needle, from);
        if (at < 0) return text;
        from = at + needle.length;
      }
      return text.slice(0, at) + replacement + text.slice(from);
    },
    replace: function (s, start, count, rep) {
      var str = String(s == null ? '' : s);
      return str.slice(0, toNum(start) - 1) + String(rep) + str.slice(toNum(start) - 1 + toNum(count));
    },
    text: function (v, fmt, language) {
      var str = String(v == null ? '' : v);
      if (!fmt) return v instanceof Date ? dateText(v, null, language) : str;
      var f = String(fmt).replace(/\[\$-[^\]]+\]/g, '');
      if (/0\.00/.test(f)) return toNum(v).toFixed((f.split('.')[1] || '00').length);
      if (v instanceof Date || /[ymdhs]|^(Long|Short)|^UTC$/i.test(f)) return dateText(v, f, language);
      if (/^#,#/.test(f)) return toNum(v).toLocaleString();
      return str;
    },
    globalChoices: function (options) {
      if (!Array.isArray(options)) throw new Error('Global Choices requires exported options');
      return options.map(function (option) {
        if (!option || !Number.isInteger(option.value) || typeof option.name !== 'string')
          throw new Error('Invalid exported global choice');
        var code = option.value, label = option.name;
        var value = {};
        Object.defineProperty(value, choiceCode, {value:code});
        Object.defineProperties(value, {
          toString: {value:function () { return label; }},
          valueOf: {value:function () { return code; }},
          toJSON: {value:function () { return code; }}
        });
        return {value:Object.freeze(value), name:label};
      });
    },
    choiceScalar: function (value) { return choiceScalar(value); },
    choiceDescriptor: function (value) {
      return choiceScalar(value) === value ? null : {name:String(value), value:choiceScalar(value)};
    },
    guid: function () {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = (Math.random() * 16) | 0;
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
      });
    },

    // --- colors / encoding --------------------------------------------------
    rgba: function (r, g, b, a) {
      var channel = function (n) {
        return Math.max(0, Math.min(255, Math.round(toNum(n))));
      };
      var alpha = a === undefined || a === null ? 1 : Math.max(0, Math.min(1, toNum(a)));
      return 'rgba(' + channel(r) + ',' + channel(g) + ',' + channel(b) + ',' + alpha + ')';
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
      return String(text == null ? '' : text).split(String(separator == null ? '' : separator)).map(function (value) {
        var record = {value:value};
        // Older exports call this column Result. Keep it an alias rather than
        // a second enumerable column, so scalar membership/projection works.
        Object.defineProperty(record, 'result', {configurable:true, get:function () { return this.value; }});
        return record;
      });
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
    concurrent: async function (fns) {
      if (!Array.isArray(fns) || fns.length < 2 || fns.some(function (fn) { return typeof fn !== 'function'; }))
        throw new Error('Concurrent requires at least two deferred formulas');
      // Catch synchronous throws independently and start every branch before
      // awaiting any result. allSettled retains source argument order.
      var results = await Promise.allSettled(fns.map(function (fn) { return Promise.resolve().then(fn); }));
      var failed = results.find(function (result) { return result.status === 'rejected'; });
      if (failed) throw failed.reason;
      return true;
    },

    // --- dates ---------------------------------------------------------------
    today: function () { return startOfDay(new Date()); },
    now: function () { return new Date(); },
    year: function (d) { return toDate(d).getFullYear(); },
    month: function (d) { return toDate(d).getMonth() + 1; },
    day: function (d) { return toDate(d).getDate(); },
    hour: function (d) { return toDate(d).getHours(); },
    minute: function (d) { return toDate(d).getMinutes(); },
    weekday: function (d, start) {
      var codes = {Sunday:1,Monday:2,MondayZero:3,Tuesday:12,Wednesday:13,Thursday:14,Friday:15,Saturday:16};
      var code = start == null ? 1 : (codes[start] || start);
      var first = {1:0,2:1,3:1,11:1,12:2,13:3,14:4,15:5,16:6,17:0}[code];
      if (first === undefined) throw new Error('Unsupported Weekday start');
      return (toDate(d).getDay() - first + 7) % 7 + (code === 3 ? 0 : 1);
    },
    dateAdd: function (d, n, unit) {
      var x = new Date(toDate(d).getTime()), k = toNum(n);
      switch (String(unit || 'days').toLowerCase()) {
        case 'milliseconds': return new Date(x.getTime() + k);
        case 'seconds': return new Date(x.getTime() + k * 1000);
        case 'minutes': return new Date(x.getTime() + k * 60000);
        case 'hours': return new Date(x.getTime() + k * 3600000);
        case 'days':
          return addDateDays(x, k);
        case 'months': case 'quarters': case 'years': {
          var scale = {months:1,quarters:3,years:12}[String(unit).toLowerCase()];
          var day = x.getDate();
          x.setDate(1); x.setMonth(x.getMonth() + Math.trunc(k) * scale);
          var last = new Date(x.getFullYear(), x.getMonth() + 1, 0).getDate();
          x.setDate(Math.min(day, last)); return x;
        }
        default: throw new Error('Unsupported DateAdd unit');
      }
    },
    dateDiff: function (a, b, unit) {
      var start = toDate(a), end = toDate(b), startStamp = civilStamp(start);
      var endStamp = civilStamp(end) + (end.getTimezoneOffset() - start.getTimezoneOffset()) * 60000;
      function boundaries(size) { return Math.floor(endStamp / size) - Math.floor(startStamp / size); }
      switch (String(unit || 'days').toLowerCase()) {
        case 'milliseconds': return boundaries(1);
        case 'seconds': return boundaries(1000);
        case 'minutes': return boundaries(60000);
        case 'hours': return boundaries(3600000);
        case 'days': return boundaries(86400000);
        case 'months': return (toDate(b).getFullYear() - toDate(a).getFullYear()) * 12 +
          (toDate(b).getMonth() - toDate(a).getMonth());
        case 'quarters': return FX.dateDiff(a, b, 'years') * 4 + Math.floor(end.getMonth()/3) - Math.floor(start.getMonth()/3);
        case 'years': return toDate(b).getFullYear() - toDate(a).getFullYear();
        default: throw new Error('Unsupported DateDiff unit');
      }
    },
    date: function (y, m, d) { return new Date(toNum(y), toNum(m) - 1, toNum(d)); },
    time: function (h, m, s) {
      return clockValue(toNum(h), toNum(m), toNum(s || 0), 0);
    },
    timeValue: timeValue,
  };

  function flattenArgs(args) {
    var out = [];
    for (var i = 0; i < args.length; i++) {
      if (Array.isArray(args[i])) out = out.concat(args[i]);
      else out.push(args[i]);
    }
    return out;
  }

  // --- collections (client-side state arrays, like Power Apps collections) ---
  // Collections live in the generated app's `state` object under their exact
  // Power Fx name; every helper takes that state object explicitly so the
  // functions stay testable outside the runtime.

  function shallowEq(a, b) {
    if (a === b) return true;
    if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return a == b;
    var ka = Object.keys(a), kb = Object.keys(b);
    if (ka.length !== kb.length) return false;
    for (var i = 0; i < ka.length; i++) {
      if (a[ka[i]] !== b[ka[i]] && !(a[ka[i]] == null && b[ka[i]] == null)) return false;
    }
    return true;
  }

  /** Power Apps Patch/Remove matching: every field of `base` equals the row's. */
  function matchesBase(row, base) {
    if (!row || !base || typeof base !== 'object') return false;
    var keys = Object.keys(base);
    for (var i = 0; i < keys.length; i++) {
      if (!(row[keys[i]] == base[keys[i]])) return false;
    }
    return true;
  }

  function asRecords(args) {
    var out = [];
    var flat = flattenArgs(args);
    for (var i = 0; i < flat.length; i++) {
      if (flat[i] == null) continue;
      if (Array.isArray(flat[i])) { out = out.concat(flat[i]); continue; }
      out.push(flat[i]);
    }
    return out;
  }

  var collectionContracts = new WeakMap();
  function attachCollectionAliases(st, name, record) {
    var contract = (collectionContracts.get(st) || {})[name];
    if (!contract) return record;
    Object.keys(contract.aliases).forEach(function (alias) {
      var canonical = contract.aliases[alias];
      if (alias === canonical || !Object.prototype.hasOwnProperty.call(record, canonical)) return;
      Object.defineProperty(record, alias, {enumerable:false, configurable:true,
        get:function () { return record[canonical]; }, set:function (value) { record[canonical] = value; }});
    });
    return record;
  }
  function normalizeCollectionRecord(st, name, record) {
    var contracts = collectionContracts.get(st) || {}, contract = contracts[name];
    if (!contract) return record;
    if (contract.error) throw new Error(contract.error);
    if (!record || typeof record !== 'object' || Array.isArray(record))
      throw new Error('Typed collection requires a record: ' + name);
    var aliases = contract.aliases, result = {};
    Object.keys(record).forEach(function (key) {
      var canonical = Object.prototype.hasOwnProperty.call(aliases, key) ? aliases[key] : key;
      if (Object.prototype.hasOwnProperty.call(result, canonical) && JSON.stringify(result[canonical]) !== JSON.stringify(record[key]))
        throw new Error('Conflicting collection field aliases: ' + name + '.' + canonical);
      Object.defineProperty(result, canonical, {value:record[key], writable:true, enumerable:true, configurable:true});
    });
    return attachCollectionAliases(st, name, result);
  }
  function prepareCollectionRecords(st, name, records) {
    return records.map(function (record) { return normalizeCollectionRecord(st, name, record); });
  }
  var FXCollections = {
    configureContracts: function (st, contracts) { collectionContracts.set(st, contracts); },
    prepare: prepareCollectionRecords,
    updateIf: function (st, name, pairs) {
      var table = st[name] = st[name] || [];
      // Evaluate conditions/changes against original rows and validate aliases
      // before mutating, retaining row identity and skipped branch laziness.
      var updates = table.map(function (record) {
        for (var i = 0; i < pairs.length; i++) {
          var matched = pairs[i].condition(record);
          if (matched && typeof matched.then === 'function') throw new Error('UpdateIf condition must be synchronous');
          if (matched) {
            var changes = pairs[i].changes(record);
            if (!changes || typeof changes !== 'object' || Array.isArray(changes) || typeof changes.then === 'function')
              throw new Error('UpdateIf changes must be a synchronous record');
            return normalizeCollectionRecord(st, name, changes);
          }
        }
        return null;
      });
      updates.forEach(function (changes, index) {
        if (changes !== null) {
          Object.assign(table[index], changes);
          attachCollectionAliases(st, name, table[index]);
        }
      });
      return table;
    },
    /** Collect(coll, records...) — append records/tables to state[name]. */
    collect: function (st, name) {
      var recs = prepareCollectionRecords(st, name, asRecords(Array.prototype.slice.call(arguments, 2)));
      var arr = st[name] = st[name] || [];
      for (var i = 0; i < recs.length; i++) arr.push(recs[i]);
      return arr;
    },
    /** ClearCollect(coll, records...) — reset then append. */
    clearCollect: function (st, name) {
      var recs = prepareCollectionRecords(st, name, asRecords(Array.prototype.slice.call(arguments, 2)));
      st[name] = recs;
      return recs;
    },
    /** Clear(coll) — remove all rows. */
    clearCollection: function (st, name) {
      st[name] = [];
      return st[name];
    },
    /** RemoveIf(coll, predicate) — drop rows where pred(item) is truthy. */
    removeItems: function (st, name, predFn) {
      var arr = st[name] = st[name] || [];
      st[name] = arr.filter(function (x) { return !predFn(x); });
      return st[name];
    },
    /** Remove(coll, record) — drop the first row matching by identity, then by value. */
    dropRecord: function (st, name, rec) {
      var arr = st[name] = st[name] || [];
      for (var i = 0; i < arr.length; i++) {
        if (arr[i] === rec) { arr.splice(i, 1); return arr; }
      }
      rec = normalizeCollectionRecord(st, name, rec);
      for (var j = 0; j < arr.length; j++) {
        if (matchesBase(arr[j], rec)) { arr.splice(j, 1); return arr; }
      }
      return arr;
    },
    /** Patch(coll, base, changes) — merge into the matching row; no base = append. */
    patchCollection: function (st, name, base, changes) {
      changes = normalizeCollectionRecord(st, name, changes || {});
      var arr = st[name] = st[name] || [];
      if (base && typeof base === 'object') {
        var target = null;
        for (var i = 0; i < arr.length; i++) { if (arr[i] === base) { target = arr[i]; break; } }
        if (!target) {
          var normalizedBase = normalizeCollectionRecord(st, name, base);
          for (var j = 0; j < arr.length; j++) { if (matchesBase(arr[j], normalizedBase)) { target = arr[j]; break; } }
        }
        if (target) { Object.assign(target, changes || {}); return attachCollectionAliases(st, name, target); }
        var rec = normalizeCollectionRecord(st, name, Object.assign({}, normalizeCollectionRecord(st, name, base), changes || {}));
        arr.push(rec);
        return rec;
      }
      var rec2 = normalizeCollectionRecord(st, name, Object.assign({}, changes || {}));
      arr.push(rec2);
      return rec2;
    },
    /** Refresh(coll) — no-op read for local collections; returns the rows. */
    refreshCollection: function (st, name) {
      return st[name] = st[name] || [];
    },
  };

  global.FX = FX;
  global.FXCollections = FXCollections;
  FX.collections = FXCollections;  // convenient namespaced access
  if (typeof module !== 'undefined' && module.exports) module.exports = FX;
})(typeof window !== 'undefined' ? window : globalThis);
