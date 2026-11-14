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

// Week totals consume the server's Diary loads, including unrendered recovery.
let rendered = '';
const row = {getAttribute: () => JSON.stringify([
  {zone: '3', meters: 980, seconds: 240, t_key: 'THM'},
  {zone: '4', meters: 1020, seconds: 230},
  {zone: '1', meters: 300, seconds: 120},
  {kind: 'alt', zone: '2', seconds: 600},
])};
const totalCell = {closest: () => row, set innerHTML(value) {rendered = value;}};
context.document = {querySelectorAll: () => [totalCell]};
context.flexZoneSpeedsForRow = () => ({'1': 3, '2': 3.5, '3': 4, '4': 4.5});
for (const name of ['flexKm', 'flexMinutes', 'flexPct', 'flexPill', 'updateFlexTotalsFromVisibleRows']) {
  vm.runInContext(extractFunction(template, name), context);
}
context.updateFlexTotalsFromVisibleRows();
assert.match(rendered, /Total: 2[.,]3 km/);
assert.match(rendered, /Z1 0[.,]3/);
assert.match(rendered, /Z3 1[.,]0/);
assert.match(rendered, /Z4 1[.,]0/);
assert.match(rendered, /THM 1[.,]0/);
assert.match(rendered, /ALT Z2/);
row.getAttribute = () => '[]';
context.updateFlexTotalsFromVisibleRows();
assert.match(rendered, /Total: 0[.,]0 km/);
console.log('Flex Diary week loads: passed');
