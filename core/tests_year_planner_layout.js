const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('core/templates/core/year_planner.html','utf8');
const start = html.indexOf('  const selectionDisclosure =');
const end = html.indexOf('  let rowClipboard =',start);
const source = html.slice(start,end).replace(/{{ request.user.pk }}/g,'test');
function check(width,saved,blocked=false) {
  const events={}, formEvents={}, windowEvents={}, storage=new Map(saved===null?[]:[['mila:year-selection-open:test',saved]]);
  const disclosure={open:true,addEventListener(name,fn){events[name]=fn;}};
  const wrap={style:{},getBoundingClientRect(){return {top:150};}};
  const context={document:{getElementById(){return disclosure;},querySelector(selector){return selector==='.year-table-wrap'?wrap:null;}},
    form:{addEventListener(name,fn){formEvents[name]=fn;}},requestAnimationFrame(fn){fn();},
    window:{innerWidth:width,innerHeight:800,addEventListener(name,fn){windowEvents[name]=fn;}},
    sessionStorage:{getItem(key){if(blocked)throw Error('blocked');return storage.get(key)??null;},setItem(key,value){if(blocked)throw Error('blocked');storage.set(key,value);}}};
  vm.createContext(context);vm.runInContext(source,context);
  assert.equal(disclosure.open,blocked||saved===null?true:saved==='1');
  assert.equal(wrap.style.maxHeight,width<=768?'none':'634px');
  disclosure.open=false;events.toggle();formEvents.change();
  if(!blocked)assert.equal(storage.get('mila:year-selection-open:test'),'0');
  context.window.innerWidth=390;windowEvents.resize();
  assert.equal(wrap.style.maxHeight,'none');
}
for(const width of [390,1366])for(const saved of [null,'0','1'])check(width,saved);
check(1366,null,true);
console.log('Year Planner selection persistence and responsive height checks passed.');
