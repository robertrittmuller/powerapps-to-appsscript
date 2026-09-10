const test = require('node:test');
const assert = require('node:assert/strict');
const FX = require('../../static/fx-stdlib.js');

test('TimeValue ignores dates, preserves milliseconds, and compares as a time value', () => {
  assert.equal(FX.text(FX.timeValue('10/11/2014 1:50:24.765 PM', 'en-US'), 'hh:mm:ss.fff AM/PM', 'en-US'), '01:50:24.765 PM');
  assert.equal(FX.eq(FX.timeValue('1:15 PM'), FX.time(13, 15, 0)), true);
  assert.equal(FX.neq(FX.timeValue('1:15 PM'), FX.time(13, 16, 0)), true);
  assert.equal(FX.timeValue('4:59:59.999 PM') < FX.timeValue('5:00:00.000 PM'), true);
  assert.equal(FX.timeValue('12:00 AM').getHours(), 0);
  assert.equal(FX.timeValue('12:00 PM').getHours(), 12);
  assert.equal(FX.timeValue('午後1:15', 'ja-JP').getHours(), 13);
  assert.equal(FX.timeValue('13.15', 'fi-FI').getMinutes(), 15);
  assert.equal(FX.timeValue(null), null);
  for (const value of ['25:00', '12:60', '10:01:60', '0:10 PM', '13:10 AM', 'bad', '09:00:00.1234']) {
    assert.throws(() => FX.timeValue(value), /TimeValue/, value);
  }
  const instant = new Date('2026-09-09T13:15:22.345Z');
  assert.equal(FX.timeValue(instant.toISOString()).getHours(), instant.getHours());
  assert.equal(FX.timeValue(instant.toISOString()).getMilliseconds(), 345);
});

test('Text formats hours vs months, localized output, named formats and rounding', () => {
  const date = new Date(2026, 8, 9, 13, 5, 2, 765);
  assert.equal(FX.text(date, '[$-en-US]hh:mm AM/PM', 'en-US'), '01:05 PM');
  assert.equal(FX.text(date, 'yyyy-mm-dd hh:mm:ss', 'en-US'), '2026-09-09 13:05:02');
  assert.equal(FX.text(date, '[$-en-US]dd mmm', 'en-US'), '09 Sep');
  assert.equal(FX.text(date, '[$-en-US]dd mmm', 'fr-FR'), '09 sept.');
  assert.equal(FX.text(date, 'LongTime24', 'en-US'), '13:05:02');
  assert.equal(FX.text(date, 'ShortTime', 'en-US'), '1:05 PM');
  assert.equal(FX.text(date, 'UTC'), date.toISOString());
  assert.equal(FX.timeValue(FX.text(date)).getHours(), 13);
  assert.equal(FX.text(null, 'dd mmm'), '');
  assert.equal(FX.text(date, 'ss.ff'), '02.77');
  assert.equal(date.getMilliseconds(), 765);
});

test('canvas matching implements default boundaries, flags, capture records and zero-length progress', () => {
  assert.equal(FX.isMatch('Hello world', 'Hello world'), true);
  assert.equal(FX.isMatch('Hello world!', 'Hello world'), false);
  assert.equal(FX.isMatch('Hello world', 'hello', 'Contains|IgnoreCase|'), true);
  assert.equal(FX.isMatch('line one\nline two', '^line two$', 'Contains|Multiline|'), true);
  assert.deepEqual(FX.match('id=42', 'id=(?<ItemId>\\d+)'), {full_match:'id=42', start_match:1, sub_matches:[{value:'42'}], item_id:'42'});
  assert.equal(FX.match('no digits', '\\d+'), null);
  assert.deepEqual(FX.matchAll('a1 b22', '\\d+').map(r => [r.full_match, r.start_match]), [['1',2], ['22',5]]);
  assert.equal(FX.matchAll('x', '(?=x)|$').length, 2);
  assert.equal(FX.matchAll('https://contoso.sharepoint.com/sites/Team', '\\/').length, 4);
  assert.throws(() => FX.isMatch('a', '['));
  assert.throws(() => FX.isMatch('a', 'a', 'unsupported'), /option/);
});

test('Find and deferred IsBlankOrError preserve validation failure semantics', async () => {
  assert.equal(FX.find('World', 'Hello World'), 7);
  assert.equal(FX.find('World', 'Hello World, Hello World', 10), 20);
  assert.equal(FX.find('Mars', 'Hello World'), null);
  assert.equal(FX.find('world', 'Hello World'), null);
  assert.equal(FX.isBlankOrError(() => FX.right('abc', -1)), true);
  assert.equal(FX.isBlankOrError(() => 0), false);
  assert.equal(FX.isBlankOrError(() => false), false);
  assert.equal(await FX.isBlankOrError(async () => {throw new Error('save failed');}), true);
  assert.equal(await FX.isBlankOrError(async () => 'saved'), false);
});
