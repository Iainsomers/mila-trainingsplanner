const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync('core/templates/core/athlete_year_calendar.html','utf8');
const source = template.slice(template.indexOf('  function renderTypeAResults('),template.indexOf('  function useWatchTraining('));
function element(tag) { return {tag, style:{}, children:[], listeners:{}, isConnected:true,
  setAttribute(){}, focus(){}, appendChild(n){this.children.push(n);},
  addEventListener(k,fn){this.listeners[k]=fn;}}; }
const flatten = n => [n,...n.children.flatMap(flatten)];
async function check(model, coach, success) {
  let requested, requestOptions;
  const current={start:'2026-11-05T17:33:32+01:00', parts:[{description:'Old result',training_fields:{main:'15x500m'},
    ai_structure_status:'rejected_structure',ai_structure_reason:'Private coach diagnostic',ai_structure_model:'model'}]};
  const replacement={...current,parts:[{description:'2x8x500m',training_fields:{main:'2x8x500m'},watch_loads:[{seconds:101}]}]};
  const parent=element('div');
  const context={document:{createElement:element,createTextNode:t=>({...element('text'),textContent:t})},
    watchChats:{},URLSearchParams,getCookie(){return "csrf";},renderTypeALaps(){},activeAthlete:89,activeDate:'2026-11-05',watchPreviewSequence:1,
    fetch:async (url, options)=>{requested=url;requestOptions=options; return {json:async()=>success ? {ok:true,results:[replacement]} : {ok:false,message:'No matching structure could be confirmed.'}};}};
  vm.createContext(context); vm.runInContext(source.replace('{{ is_coach_user|yesno:"true,false" }}',String(coach)),context);
  context.renderTypeAResults(parent,[current],'',model);
  const nodes=flatten(parent), buttons=nodes.filter(n=>n.tag==='button');
  assert.deepEqual(buttons.map(n=>n.textContent),['Send','Chat','Use AM','Use PM']);
  assert.equal(nodes.some(n=>(n.textContent||'').includes('Private coach diagnostic')),coach);
  const input=nodes.find(n=>n.tag==='textarea'); input.value='2x(8x500m)';
  buttons[0].listeners.click();
  assert.equal(buttons[0].disabled,true);
  await new Promise(resolve=>setImmediate(resolve));
  const url=new URL(requested,'https://example.org');
  assert.equal(requestOptions.method,'POST');
  assert.equal(JSON.parse(new URLSearchParams(requestOptions.body).get('chat')).at(-1).content,'2x(8x500m)');
  assert.equal(url.searchParams.get('suggestion_session'),current.start);
  assert.ok(url.pathname.includes('type-'+model.toLowerCase()));
  if(success) {
    assert.equal(current.parts[0].training_fields.main,'15x500m','Original result is not mutated');
    assert.ok(flatten(parent).some(n=>(n.textContent||'').includes('2x8x500m')),'Matched preview is rendered');
  }
  else assert.ok(flatten(parent).some(n=>(n.textContent||'').includes('No matching structure could be confirmed.')));
}
(async()=>{for(const model of ['C','D']) for(const coach of [true,false]) for(const success of [true,false]) await check(model,coach,success);
console.log('Garmin suggestions: C/D request, preview, rejection and coach diagnostics passed.');})().catch(e=>{console.error(e);process.exitCode=1;});
