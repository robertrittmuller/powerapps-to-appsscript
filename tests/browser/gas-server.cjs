// Execute the actual generated Code.gs/DataInit.gs against a Sheets test double.
// The workbook survives browser reloads; this is not a real Google deployment.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const readline = require('node:readline');
const clone = value => JSON.parse(JSON.stringify(value));
let setupComplete = false, mutationRequest = false, lockHeld = false, flushed = false;
let failNextLock = false, failNextFlush = false;
const lockEvents = [];
function checkReadLock() {
  if (mutationRequest && !lockHeld) throw new Error('mutation read occurred outside the script lock');
}
function checkWriteLock() {
  if (!setupComplete) return;
  if (!lockHeld) throw new Error('mutation write occurred outside the script lock');
  if (failNext) {failNext=false; throw new Error('Simulated Sheets write failure');}
}

class Sheet {
  constructor(name) { this.name = name; this.rows = []; }
  clear() { checkWriteLock(); this.rows = []; }
  getLastColumn() { return Math.max(0, ...this.rows.map(row => row.length)); }
  getDataRange() { return this.getRange(1, 1, Math.max(1, this.rows.length), Math.max(1, this.getLastColumn())); }
  getRange(row, col, height = 1, width = 1) {
    const sheet = this;
    return {
      getValues() { checkReadLock(); return Array.from({length: height}, (_, y) =>
        Array.from({length: width}, (_, x) => sheet.rows[row + y - 1]?.[col + x - 1] ?? '')); },
      setValues(values) {
        checkWriteLock();
        if (values.length !== height || values.some(value => value.length !== width)) {
          throw new Error('range dimensions do not match');
        }
        values.forEach((cells, y) => cells.forEach((value, x) => {
          if (value !== null && typeof value === 'object') throw new Error('Sheets cell requires a scalar');
          (sheet.rows[row + y - 1] ||= [])[col + x - 1] = value;
        }));
      },
      setValue(value) { this.setValues([[value]]); },
    };
  }
  appendRow(row) { this.getRange(this.rows.length + 1, 1, 1, row.length).setValues([row]); }
  deleteRow(row) { checkWriteLock(); this.rows.splice(row - 1, 1); }
  setFrozenRows() {}
}

const sheets = new Map([['Sheet1', new Sheet('Sheet1')]]);
const workbook = {
  getSheetByName: name => sheets.get(name),
  insertSheet(name) { const sheet = new Sheet(name); sheets.set(name, sheet); return sheet; },
  getSheets: () => [...sheets.values()],
  deleteSheet: sheet => sheets.delete(sheet.name),
  getId: () => 'test-workbook', getUrl: () => 'https://example.test/workbook',
};
const properties = new Map();
let sequence = 0, failNext = false;
let storageAppId = 'test-script:' + process.argv[2], storageUser = 'business.tester@example.test';
const context = vm.createContext({
  HtmlService: {
    createHtmlOutputFromFile(name) {
      return {getContent: () => fs.readFileSync(path.join(process.argv[2], name), 'utf8')};
    },
    createTemplateFromFile(name) {
      const template = {
        evaluate() {
          context.launchParametersJSON = template.launchParametersJSON;
          context.storageContextJSON = template.storageContextJSON;
          const content = fs.readFileSync(path.join(process.argv[2], name + '.html'), 'utf8')
            .replace(/<\?!=([\s\S]*?)\?>/g, (_match, expression) =>
              vm.runInContext(expression, context, {timeout: 10000}));
          return {getContent: () => content, setTitle() {return this;}, addMetaTag() {return this;}};
        },
      };
      return template;
    },
  },
  PropertiesService: { getScriptProperties: () => ({
    getProperty: key => properties.get(key), setProperty: (key, value) => properties.set(key, value),
  }) },
  SpreadsheetApp: { create: () => workbook, openById: () => workbook,
    flush() {
      if (!lockHeld) throw new Error('flush occurred outside the script lock');
      flushed=true; lockEvents.push('flush');
      if (failNextFlush) {failNextFlush=false; throw new Error('Simulated Sheets flush failure');}
    },
  },
  LockService: {getScriptLock:()=>({
    waitLock(timeout) {
      lockEvents.push('wait:' + timeout);
      if (timeout !== 30000) throw new Error('unexpected script lock timeout');
      if (failNextLock) {failNextLock=false; throw new Error('Simulated script lock timeout');}
      if (lockHeld) throw new Error('script lock was not released');
      lockHeld=true; flushed=false; lockEvents.push('acquired');
    },
    releaseLock() {
      if (!lockHeld || !flushed) throw new Error('script lock release requires acquisition and flush');
      lockHeld=false; lockEvents.push('released');
    },
  })},
  Utilities: { getUuid: () => 'test-record-' + (++sequence) },
  Session: { getActiveUser: () => ({ getEmail: () => storageUser }) },
  ScriptApp: { getScriptId: () => storageAppId },
});
for (const file of ['Code.gs', 'DataInit.gs']) {
  vm.runInContext(fs.readFileSync(path.join(process.argv[2], file), 'utf8'), context, {timeout: 10000});
}
vm.runInContext('setup()', context, {timeout: 10000});
setupComplete = true;
readline.createInterface({input: process.stdin}).on('line', line => {
  try {
    const request = JSON.parse(line);
    if (request.fn === '__failNextMutation') { failNext = true; process.stdout.write('{"result":true}\n'); return; }
    if (request.fn === '__failNextLock') { failNextLock = true; process.stdout.write('{"result":true}\n'); return; }
    if (request.fn === '__failNextFlush') { failNextFlush = true; process.stdout.write('{"result":true}\n'); return; }
    if (request.fn === '__lockState') { process.stdout.write(JSON.stringify({result:{held:lockHeld,events:lockEvents}})+'\n'); return; }
    if (request.fn === '__duplicateSourceRow') {
      // Model a manual spreadsheet edit outside the app's lock discipline.
      const sheet = sheets.get(request.args[0]);
      const row = sheet && sheet.rows[request.args[1]];
      if (!row) throw new Error('unknown source row');
      sheet.rows.push(clone(row)); process.stdout.write('{"result":true}\n'); return;
    }
    if (request.fn === '__setStorageIdentity') {
      [storageAppId, storageUser] = request.args;
      process.stdout.write('{"result":true}\n'); return;
    }
    // Test-only administrative hooks; private Apps Script functions are never RPC endpoints.
    const administrative = {__importPlanner:'importPlanner_', __plannerSnapshot:'plannerDocument_', __setup:'setup'};
    const admin = Object.prototype.hasOwnProperty.call(administrative, request.fn) && administrative[request.fn];
    if (!admin && !['api', 'apiChoices', 'whoami', 'doGet', 'connector'].includes(request.fn)) throw new Error('unknown test endpoint');
    mutationRequest = request.fn === '__importPlanner' || request.fn === 'connector' ||
      (request.fn === 'api' && !['list', 'links', 'relationshipSnapshot'].includes(request.args[1]));
    if (admin) request.fn = admin;
    context.requestJSON = JSON.stringify(request);
    const result = vm.runInContext(
      '(function(){var r=JSON.parse(requestJSON); return globalThis[r.fn].apply(null,r.args);})()',
      context, {timeout: 10000});
    process.stdout.write(JSON.stringify({result: request.fn === 'doGet' ? result.getContent() : result}) + '\n');
  } catch (error) { process.stdout.write(JSON.stringify({error: error.message}) + '\n'); }
  finally {mutationRequest=false;}
});
