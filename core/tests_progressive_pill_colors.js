const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const pills = [
  "7*(400m-300m) z2>z3 p=100m wandel sp1 (1:38/1:14-->1:28/1:06)",
  "3*800m z3>z2", "3*(400m z2 + 300m z4)", "800m z1", "3*800m TM>THM"
].map(textContent => ({textContent, style:{}}));
const context = {document:{querySelectorAll:()=>pills}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('core/templates/core/partials/progressive_pill_colors.js.html', 'utf8'), context);
vm.runInContext('applyFlexProgressivePillColors()', context);
assert.equal(pills[0].style.background, 'linear-gradient(30deg, #f7c6d0 0.000%, #f7c6d0 50.000%, #f06f5f 50.000%, #f06f5f 100.000%)');
assert.ok(pills[1].style.background.indexOf('#f06f5f') < pills[1].style.background.indexOf('#f7c6d0'));
assert.ok(pills[2].style.background.includes('#f7c6d0'));
assert.ok(pills[2].style.background.includes('#bfe7bf'));
assert.equal(pills[3].style.background, undefined);
assert.equal(pills[4].style.background, pills[0].style.background);
console.log('Progressive pill colours: 5 scenarios passed');
