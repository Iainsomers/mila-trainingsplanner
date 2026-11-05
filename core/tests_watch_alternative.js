/* Exercise the actual calendar save handler with Alternative-only results. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const template = fs.readFileSync(path.join(__dirname, 'templates/core/athlete_year_calendar.html'), 'utf8');
const source = template.slice(template.indexOf('  function useWatchTraining('),
  template.indexOf('  function hideSuggestInputPlaceholder('));

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
