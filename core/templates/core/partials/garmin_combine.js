/* Compose already analysed recordings without reinterpreting their lap boundaries. */
(function(root) {
  "use strict";
  function combine(entries) {
    if (entries.length < 2 || entries.length > 3) throw new Error("Select two or three activities.");
    entries = entries.slice().sort(function(a, b) { return String(a.session.start).localeCompare(String(b.session.start)); });
    var roles = entries.map(function(entry) { return entry.role; });
    if (roles.indexOf("main") < 0 || new Set(roles).size !== roles.length || roles.some(function(role) { return ["wu", "main", "cd"].indexOf(role) < 0; })) {
      throw new Error("Choose one Main and use each role only once.");
    }
    if (roles.join(",") !== ["wu", "main", "cd"].filter(function(role) { return roles.indexOf(role) >= 0; }).join(",")) {
      throw new Error("Use chronological order: WU, Main, CD.");
    }
    var fields = {wu: "", main: "", cd: ""}, loads = [], distance = 0, seconds = 0;
    entries.forEach(function(entry) {
      var session = entry.session, part = (session.parts || [])[0];
      if (!part || !(part.watch_loads || []).length) throw new Error("Each activity needs usable lap data.");
      if (entry.role === "main" && (!part.training_fields || !part.training_fields.main)) throw new Error("Choose an activity with a generated training description as Main.");
      var meters = Number(session.distance);
      var duration = String(session.duration).split(":").map(Number);
      if (!(meters > 0) || duration.length !== 3 || duration.some(function(n) { return !Number.isFinite(n); })) throw new Error("Activity totals are unavailable.");
      distance += meters;
      seconds += duration[0] * 3600 + duration[1] * 60 + duration[2];
      if (entry.role === "main") {
        Object.assign(fields, part.training_fields);
      }
      (part.watch_loads || []).forEach(function(load) {
        var copy = Object.assign({}, load);
        if (entry.role !== "main") {
          copy.segment = entry.role.toUpperCase();
          copy.combined_outer = true;
        }
        loads.push(copy);
      });
    });
    entries.forEach(function(entry) {
      if (entry.role === "main") return;
      if (fields[entry.role]) throw new Error("Main already contains " + entry.role.toUpperCase() + ". Choose another role or activity.");
      var zones = {};
      entry.session.parts[0].watch_loads.forEach(function(load) {
        var zone = String(load.zone || "");
        if (/^[1-5]$/.test(zone)) zones[zone] = (zones[zone] || 0) + Number(load.meters || 0);
      });
      var dominant = Object.keys(zones).sort(function(a, b) { return zones[b] - zones[a]; })[0];
      fields[entry.role] = (Math.round(Number(entry.session.distance) / 50) * 50) + "m" + (dominant ? " z" + dominant : "");
    });
    var duration = [Math.floor(seconds / 3600), Math.floor(seconds % 3600 / 60), (seconds % 60).toFixed(3)].map(function(n, i) { return String(n).padStart(i === 2 ? 6 : 2, "0"); }).join(":");
    return {name: "Combined training", start: entries[0].session.start, distance: Math.round(distance * 100) / 100,
      duration: duration, parts: [{description_label: "Generated description",
        description: "WU: " + (fields.wu || "none") + " · Main: " + fields.main + " · CD: " + (fields.cd || "none"),
        training_fields: fields, watch_loads: loads}]};
  }
  root.combineGarminActivities = combine;
  if (typeof module !== "undefined") module.exports = combine;
})(typeof window !== "undefined" ? window : globalThis);
