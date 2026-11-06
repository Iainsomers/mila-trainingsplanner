/* Exercise the actual calendar save handler with Alternative-only results. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const template = fs.readFileSync(path.join(__dirname, 'templates/core/athlete_year_calendar.html'), 'utf8');
const source = template.slice(template.indexOf('  function useWatchTraining('),
  template.indexOf('  function hideSuggestInputPlaceholder('));

// Render the actual action row: only Alternative has Add, and it wraps on narrow screens.
function checkButtons() {
  const renderSource = template.slice(template.indexOf('  function renderTypeAResults('),
    template.indexOf('  function useWatchTraining('));
  function element(tag) { return {tag, style:{}, children: [], listeners: {}, setAttribute(){},
    appendChild(child) { this.children.push(child); },
    addEventListener(event, callback) { this.listeners[event] = callback; }}; }
  const invoked = [];
  const render = new Function('document','renderTypeALaps','useWatchTraining','aycCoachUser',
    renderSource + '\nreturn renderTypeAResults;')({createElement:element},()=>{},(...args)=>invoked.push(args), false);
  for (const model of ['C','D']) {
    for (const fields of [{alt:"Pilates 46' Z1"},{main:'4x400m Z3'}]) {
      const parent=element('div');
      render(parent,[{parts:[{description:'Training',training_fields:fields}]}],'',model);
      const flatten = node => [node,...node.children.flatMap(flatten)];
      const nodes=flatten(parent);
      const buttons=nodes.filter(node=>node.tag==='button');
      assert.deepEqual(buttons.map(button=>button.textContent),fields.alt ?
        ['Use AM','Use PM','Add AM','Add PM'] : ['Suggest','Use AM','Use PM']);
      const actionRow=nodes.find(node=>node.children.includes(buttons[0]));
      assert.ok(actionRow.className.includes('flex-wrap'));
      for (const button of buttons.filter(b=>b.textContent !== 'Suggest')) button.listeners.click({preventDefault(){}});
      if(fields.alt) {
        assert.equal(invoked.at(-1)[5],true);
        assert.equal(invoked.at(-2)[5],true);
        assert.equal(invoked.at(-3)[5],undefined);
      }
    }
  }
}
checkButtons();

async function check() {
  for (const model of ['C', 'D']) {
    for (const slot of [1, 2]) {
      let saved;
      let reloaded = false;
      const save = new Function('activeDate', 'activeAthlete', 'getCookie', 'fetch', 'window',
        source + '\nreturn useWatchTraining;')('2026-11-05', '42', () => 'csrf',
        async (url, request) => { saved = {url, data: request.body}; return {ok: true}; },
        {location: {reload() { reloaded = true; }}, alert(message) { throw Error(message); }});
      save({alt: "Elliptical 90' Z2"}, [], slot, {textContent: 'Use', disabled: false}, model);
      await new Promise(resolve => setImmediate(resolve));
      assert.equal(saved.data.get('watch_fields'), 'alternative_replace');
      for (const field of ['wu_text', 'core_text', 'cd_text']) assert.equal(saved.data.get(field), '');
      save({alt: "Elliptical 90' Z2"}, [], slot, {textContent:'Add'}, model, true);
      await new Promise(resolve => setImmediate(resolve));
      assert.equal(saved.data.get('watch_fields'), 'alternative');
      assert.equal(saved.data.get('alt_text'), "Elliptical 90' Z2");
      assert.equal(saved.data.get('watch_origin'), 'watch_' + model.toLowerCase());
      assert.ok(saved.url.includes('/05/' + slot + '/'));
      assert.equal(saved.data.get('core2_text'), null);
      assert.equal(saved.data.get('mob_text'), null);
      assert.equal(saved.data.get('sprint_text'), null);
      assert.equal(reloaded, true);
      save({main: '4*400m Z3', wu: '1500m Z1', cd: '800m Z1'}, [], slot,
        {textContent: 'Use', disabled: false}, model);
      await new Promise(resolve => setImmediate(resolve));
      assert.equal(saved.data.get('watch_fields'), null);
      assert.equal(saved.data.get('core_text'), '4*400m Z3');
    }
  }
  console.log('Watch Alternative save handler: C/D, AM/PM and running imports passed.');
}
check().catch(error => { console.error(error); process.exitCode = 1; });
