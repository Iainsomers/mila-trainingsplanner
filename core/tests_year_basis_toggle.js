const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync('core/templates/core/year_planner.html','utf8');
const begin = template.indexOf('  document.querySelectorAll("input[type=');
const end = template.indexOf('  document.querySelector("[data-year-athlete-all]")',begin);
assert.ok(begin > 0 && end > begin);
const input = () => ({checked:true, listeners:{},addEventListener(k,fn){this.listeners[k]=fn;}});
const bases=[input(),input(),input()], athletes=[input(),input()], group=input();
let submissions=0;
vm.runInNewContext(template.slice(begin,end),{form:{submit(){submissions++;}},document:{
  getElementById(id){assert.equal(id,'yearAthleteGroup');return group;},
  querySelectorAll(selector){return selector.includes("name='basis'") ? bases : athletes;}
}});
for(const basis of bases) {
  for(const checked of [false,true,false]) {
    basis.checked=checked;
    const before=submissions;
    basis.listeners.change();
    assert.equal(submissions,before+1,'Basis toggles submit immediately before any group change');
    assert.ok(athletes.every(a=>a.checked),'Basis toggles preserve athlete selection');
  }
}
group.listeners.change();
assert.ok(athletes.every(a=>!a.checked));
const before=submissions;
bases[0].listeners.change();
assert.equal(submissions,before+1,'Group change does not duplicate basis listeners');
console.log('Year Planner basis toggles: immediate on/off, athlete preservation and group change passed.');
