// Parse proposals as data. Never evaluate model-generated JavaScript here.
const fs = require('node:fs');
const acorn = require('acorn');

function check({js, behavior}) {
  if (typeof js !== 'string' || !js.trim()) throw new Error('proposal must be nonempty JavaScript text');
  const source = behavior ? `async function proposal() {\n${js}\n}` : `(\n${js}\n)`;
  const program = acorn.parse(source, {ecmaVersion: 2022});
  if (program.body.length !== 1) throw new Error('proposal escapes its formula boundary');
  const root = program.body[0];
  if (behavior ? root.type !== 'FunctionDeclaration' || root.id.name !== 'proposal'
      : root.type !== 'ExpressionStatement') throw new Error('value formula must be one expression');
  const FX = require('../static/fx-stdlib.js');
  global.document = {getElementById: () => null, addEventListener: () => {}};
  require('../static/gas-runtime.js');
  const forbidden = new Set(['constructor', '__proto__', 'prototype']);
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (!behavior && (node.type === 'AssignmentExpression' || node.type === 'UpdateExpression'
        || node.type === 'AwaitExpression' || (node.type === 'UnaryExpression' && node.operator === 'delete'))) {
      throw new Error('value formula contains a mutation or asynchronous operation');
    }
    if (node.type === 'MemberExpression') {
      const property = node.computed ? node.property.type === 'Literal' ? node.property.value : null : node.property.name;
      if (forbidden.has(property)) throw new Error('prototype access is outside the formula contract');
      if (node.object.type === 'Identifier' && node.object.name === 'FX') {
        if (property === null || !Object.prototype.hasOwnProperty.call(FX, property)) {
          throw new Error('unknown FX helper: ' + String(property));
        }
      }
      if (node.object.type === 'Identifier' && node.object.name === 'FXRuntime') {
        if (property === null || !Object.prototype.hasOwnProperty.call(FXRuntime, property)) {
          throw new Error('unknown FXRuntime helper: ' + String(property));
        }
      }
    }
    if (node.type === 'Identifier' && ['eval', 'Function', 'require', 'process', 'globalThis', 'fetch',
        'XMLHttpRequest', 'WebSocket'].includes(node.name)) {
      throw new Error('unsupported formula capability: ' + node.name);
    }
    if (node.type === 'ImportExpression' || node.type === 'ThisExpression') {
      throw new Error('unsupported formula syntax: ' + node.type);
    }
    for (const [key, child] of Object.entries(node)) {
      if (key === 'start' || key === 'end') continue;
      if (Array.isArray(child)) child.forEach(visit);
      else if (child && typeof child === 'object') visit(child);
    }
  }
  visit(root);
  return {ok: true};
}

try {
  process.stdout.write(JSON.stringify(check(JSON.parse(fs.readFileSync(0, 'utf8')))));
} catch (error) {
  process.stdout.write(JSON.stringify({ok: false, error: error.message}));
}
