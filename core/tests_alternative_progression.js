const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ctx = {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('core/templates/core/partials/alternative_loads.js.html','utf8'),ctx);
const durations = {"20'z1":1200,"15*3' z2>z3":2700,"10'z1 p1":600,"9' z3>z1":540,"3x 8' z4":1440,"3'":180};
const loads = ctx.flexAlternativeLoads("20'z1 // 15*3' z2>z3 // 10'z1 p1",'1',1200,p=>durations[p] || 0);
assert.deepEqual(JSON.parse(JSON.stringify(loads)).map(l=>[l.zone,l.seconds]),[['1',1200],['2',1350],['3',1350],['1',600]]);
assert.ok(loads.every(l=>l.kind==='alt' && !l.meters));
assert.deepEqual(JSON.parse(JSON.stringify(ctx.flexAlternativeLoads("9' z3>z1",'3',540,p=>durations[p] || 0))).map(l=>[l.zone,l.seconds]),[['3',180],['2',180],['1',180]]);
assert.deepEqual(JSON.parse(JSON.stringify(ctx.flexAlternativeLoads("3x 8' z4",'1',0,p=>durations[p] || 0))).map(l=>[l.zone,l.seconds]),[['4',1440]]);
for (const symbol of ['*', 'x', '×']) {
  const prefixed = ctx.flexAlternativeLoads(`Elliptical 16${symbol}3' p45 Z2>Z3`,'2',180,p=>durations[p] || 0);
  assert.deepEqual(JSON.parse(JSON.stringify(prefixed)).map(l=>[l.zone,l.seconds]),[['2',1440],['3',1440]]);
}
console.log('Alternative progression: combined, downward and high zones passed');
