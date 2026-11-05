const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('core/templates/core/athlete_year_calendar.html', 'utf8');
const start = source.indexOf('  var watchPreviewSequence = 0;');
const end = source.indexOf('  function renderTypeALaps', start);
function element() {
  return {style:{}, isConnected:true, listeners:{}, children:[],
    focus(){}, appendChild(child){this.children.push(child);}, prepend(child){this.notice=child;},
    addEventListener(event, fn){this.listeners[event]=fn;},
    removeEventListener(event, fn){if(this.listeners[event]===fn) delete this.listeners[event];}};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
async function scenario(touched) {
  const body=element(), elements={suggestInputPlaceholderBody:body};
  const pending={ok:true,results:[{parts:[{ai_structure_status:'pending'}]}]};
  const analyzed={ok:true,results:[{parts:[{ai_structure_status:'applied'}]}]};
  let finish;
  const calls=[], renders=[];
  const context={activeAthlete:70, activeDate:'2026-11-05',
    document:{getElementById(id){return elements[id] ||= element();},createElement:element},
    fetch(url){calls.push(url);return calls.length===1 ? Promise.resolve({json:()=>Promise.resolve(pending)}) :
      new Promise(resolve=>{finish=()=>resolve({json:()=>Promise.resolve(analyzed)});});},
    renderTypeAResults(parent, results){renders.push(results);}};
  vm.createContext(context);
  vm.runInContext(source.slice(start,end),context);
  context.showWatchModel('C');
  await tick();
  assert(calls[0].endsWith('&preview=measured'));
  assert.equal(calls.length,2);
  assert.equal(renders.length,1,'Measured result appears while AI is still pending');
  if(touched) body.listeners.pointerdown();
  finish(); await tick();
  if(touched) {
    assert.equal(renders.length,1,'AI cannot overwrite an active selection');
    const button=body.notice.children[0];
    assert.equal(button.textContent,'Show analysis');
    button.listeners.click();
  }
  assert.equal(renders.length,2);
  assert.equal(renders[1][0].parts[0].ai_structure_status,'applied');
}
(async()=>{await scenario(false);await scenario(true);console.log('Garmin measured-first preview checks passed.');})().catch(error=>{console.error(error);process.exitCode=1;});
