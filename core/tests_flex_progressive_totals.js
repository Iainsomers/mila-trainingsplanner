const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function extractFunction(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} not found`);
  const braceStart = source.indexOf('{', start);
  let depth = 0;
  for (let index = braceStart; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') depth -= 1;
    if (depth === 0) return source.slice(start, index + 1);
  }
  throw new Error(`${name} is incomplete`);
}

const template = fs.readFileSync('core/templates/core/flex_planner.html', 'utf8');
const progressive = fs.readFileSync('core/templates/core/partials/progressive_pill_colors.js.html', 'utf8');
const context = {};
vm.createContext(context);
vm.runInContext(progressive, context);
vm.runInContext(extractFunction(template, 'flexMetersFromValue'), context);
vm.runInContext(extractFunction(template, 'flexCompoundLoads'), context);

const loads = JSON.parse(JSON.stringify(
  context.flexCompoundLoads('2*(300m z2-200m z3>z4)', '2')
));
assert.deepEqual(loads, [
  {zone: '2', meters: 600, tKey: '', race: false},
  {zone: '3', meters: 200, tKey: '', race: false},
  {zone: '4', meters: 200, tKey: '', race: false},
]);
assert.equal(loads.reduce((total, load) => total + load.meters, 0), 1000);
console.log('Flex compound progressive totals: passed');
