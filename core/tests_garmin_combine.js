const assert = require('node:assert/strict');
const combine = require('./templates/core/partials/garmin_combine.js');
function session(start, distance, duration, main) {
  return {start, distance, duration, parts: [{training_fields: {wu: '', main, cd: ''},
    watch_loads: [{segment: 'CORE', meters: distance, seconds: 20, zone: '2', average_hr: 155, average_hr_last_15: 160}]}]};
}
const wu = session('2026-11-01T09:35:00+01:00', 2723.63, '00:13:33.000', '2700m z2');
const main = session('2026-11-01T10:09:00+01:00', 5683.13, '00:34:52.000', '2*(5*100m z4>z5) p45//3750m z2');
const cd = session('2026-11-01T10:45:00+01:00', 2052.38, '00:10:39.000', '2050m z1');
const original = JSON.stringify([wu, main, cd]);
const entries = [{session: cd, role: 'cd'}, {session: wu, role: 'wu'}, {session: main, role: 'main'}];
const result = combine(entries);
assert.equal(result.distance, 10459.14);
assert.equal(result.duration, '00:59:04.000'); // Excludes gaps between recordings.
assert.deepEqual(result.parts[0].training_fields, {wu: '2700m z2', main: main.parts[0].training_fields.main, cd: '2050m z2'});
assert.deepEqual(result.parts[0].watch_loads.map(l => l.segment), ['WU', 'CORE', 'CD']);
assert.equal(result.parts[0].watch_loads[1].average_hr_last_15, 160);
assert.equal(result.parts[0].watch_loads[0].combined_outer, true);
assert.equal(JSON.stringify([wu, main, cd]), original);
assert.equal(combine(entries.slice(0, 1).concat(entries.slice(2))).parts[0].training_fields.wu, '');
assert.throws(() => combine(entries.slice(0, 1)));
assert.throws(() => combine(entries.concat(entries[0])));
assert.throws(() => combine([{session: wu, role: 'main'}, {session: main, role: 'main'}]));
assert.throws(() => combine([{session: wu, role: 'cd'}, {session: main, role: 'main'}]));
const embeddedCd = structuredClone(main);
embeddedCd.parts[0].training_fields.cd = '1000m';
assert.throws(() => combine([{session: embeddedCd, role: 'main'}, {session: cd, role: 'cd'}]));
assert.throws(() => combine([{session: {...wu, parts: []}, role: 'wu'}, {session: main, role: 'main'}]));
console.log('Garmin composition checks passed.');

// Warmup/cooldown need measured laps, not successful Main recognition.
const unrecognised = session('2026-11-01T09:35:00+01:00', 1479.89, '00:06:31.000', '');
const shortWarmup = combine([{session: unrecognised, role: 'wu'}, {session: main, role: 'main'}]);
assert.equal(shortWarmup.parts[0].training_fields.wu, '1500m z2');
assert.equal(shortWarmup.parts[0].training_fields.main, main.parts[0].training_fields.main);
const unknownCd = structuredClone(unrecognised);
unknownCd.start = '2026-11-01T10:45:00+01:00';
assert.equal(combine([{session: main, role: 'main'}, {session: unknownCd, role: 'cd'}]).parts[0].training_fields.cd, '1500m z2');
assert.throws(() => combine([{session: wu, role: 'wu'}, {session: unrecognised, role: 'main'}]));
