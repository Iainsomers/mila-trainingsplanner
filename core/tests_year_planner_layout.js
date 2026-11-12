const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('core/templates/core/year_planner.html','utf8');
const start = html.indexOf('  const selectionDisclosure =');
const end = html.indexOf('  let rowClipboard =',start);
const source = html.slice(start,end);
function check(width,initiallyOpen) {
  const events={}, formEvents={}, windowEvents={};
  let isOpen=initiallyOpen,assignments=0;
  const disclosure={get open(){return isOpen;},set open(value){assignments++;isOpen=value;},addEventListener(name,fn){events[name]=fn;}};
  const input={value:initiallyOpen?'1':'0'};
  const link={href:'https://mila.test/planning/year/?year=2026&athletes=7'};
  const wrap={style:{},getBoundingClientRect(){return {top:150};}};
  const context={URL,document:{getElementById(id){return id==='yearSelection'?disclosure:input;},querySelector(selector){return selector==='.year-table-wrap'?wrap:null;},querySelectorAll(selector){return selector==='.year-control-bar a[href]'?[link]:[];}},
    form:{addEventListener(name,fn){formEvents[name]=fn;}},requestAnimationFrame(fn){fn();},
    window:{innerWidth:width,innerHeight:800,addEventListener(name,fn){windowEvents[name]=fn;}}};
  vm.createContext(context);vm.runInContext(source,context);
  assert.equal(assignments,0,'Startup must preserve server-rendered open state without a collapse/expand flash');
  assert.equal(input.value,initiallyOpen?'1':'0');
  assert.equal(wrap.style.maxHeight,width<=768?'none':'634px');
  disclosure.open=!initiallyOpen;events.toggle();formEvents.change();
  const expected=initiallyOpen?'0':'1';
  assert.equal(input.value,expected);
  assert.equal(new URL(link.href).searchParams.get('selection_open'),expected);
  assert.equal(new URL(link.href).searchParams.get('athletes'),'7');
  context.window.innerWidth=390;windowEvents.resize();
  assert.equal(wrap.style.maxHeight,'none');
}
for(const width of [390,1366])for(const opened of [false,true])check(width,opened);
console.log('Year Planner selection stays stable on load and follows form/navigation state; responsive height checks passed.');
