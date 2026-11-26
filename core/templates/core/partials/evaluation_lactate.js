  const lactateDialog = document.getElementById("evaluationLactate");
  const lactateBody = document.getElementById("evaluationLactateRows");
  const lactateStatus = document.getElementById("evaluationLactateStatus");
  const lactateAdd = document.getElementById("evaluationLactateAdd");
  const lactateSave = document.getElementById("evaluationLactateSave");
  const lactateFields = {lactate: 12, rpe: 12, comment: 500, length: 12, speed: 20, hr: 6};
  const canWriteLactate = {% if is_coach_user %}{{ coach_can_edit_training|yesno:"true,false" }}{% else %}true{% endif %};
  let lactateSession;

  function setLactateSession(day, slot, measured) {
    lactateSession = {day, slot, measured: JSON.parse(measured || "[]").slice(0, 200)};
  }

  async function lactateRequest(action, session, rows) {
    const body = new URLSearchParams({
      evaluation_lactate: action, date: session.day, slot_index: session.slot,
      athlete: "{{ selected_athlete_id }}"
    });
    if (rows) body.set("rows", JSON.stringify(rows));
    const response = await fetch("{% url 'athlete_year_calendar' %}", {
      method: "POST", body, credentials: "same-origin", headers: {"X-CSRFToken": getCookie("csrftoken")}
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || !Array.isArray(result.rows)) throw new Error(result.error || "Lactate log is unavailable. Try again.");
    return result.rows;
  }

  function addLactateRow(rep, saved, watch) {
    const row = lactateBody.insertRow();
    const paceSeconds = Math.round(Number(watch?.pace_seconds_per_km));
    const measured = {
      length: Number(watch?.distance_m) > 0 ? String(Math.round(watch.distance_m)) : "",
      speed: paceSeconds > 0 ? Math.floor(paceSeconds / 60) + ":" + String(paceSeconds % 60).padStart(2, "0") : "",
      hr: Number(watch?.average_hr) > 0 ? String(Math.round(watch.average_hr)) : ""
    };
    const repCell = row.insertCell();
    if (watch || !canWriteLactate) {
      repCell.textContent = rep;
      row.dataset.rep = rep;
    } else {
      const number = document.createElement("input");
      number.type = "number";
      number.min = "1";
      number.max = "200";
      number.value = rep;
      number.className = "form-control form-control-sm";
      number.setAttribute("aria-label", "Rep number");
      repCell.append(number);
    }
    for (const [field, limit] of Object.entries(lactateFields)) {
      const cell = row.insertCell();
      if (measured[field]) {
        cell.textContent = measured[field];
        continue;
      }
      const manual = Object.hasOwn(measured, field);
      const value = saved[field] || "";
      if (!canWriteLactate) {
        cell.textContent = value || (manual ? "m" : "—");
        continue;
      }
      const input = document.createElement("input");
      input.className = "form-control form-control-sm";
      input.dataset.lactateField = field;
      input.setAttribute("aria-label", field + ", rep " + rep);
      input.maxLength = limit;
      input.value = value;
      if (["lactate", "rpe", "length", "hr"].includes(field)) input.inputMode = "decimal";
      if (manual) {
        input.placeholder = "m";
        input.title = "Manual entry";
      }
      cell.append(input);
    }
  }

  function renderLactateRows(saved, measured) {
    const rows = new Map(saved.map(row => [row.rep, row]));
    const watchRows = new Map(measured.map((row, index) => [index + 1, row]));
    const numbers = [...new Set([...rows.keys(), ...watchRows.keys()])].sort((a, b) => a - b);
    if (!numbers.length) numbers.push(1);
    lactateBody.replaceChildren();
    numbers.forEach(rep => addLactateRow(rep, rows.get(rep) || {}, watchRows.get(rep)));
    lactateAdd.hidden = !canWriteLactate || numbers.length >= 200;
    lactateSave.hidden = !canWriteLactate;
  }

  document.querySelectorAll("[data-lactate-open]").forEach(button => {
    button.addEventListener("click", async () => {
      const session = lactateSession;
      if (!session) return;
      lactateBody.replaceChildren();
      lactateSave.hidden = lactateAdd.hidden = true;
      lactateStatus.textContent = "Loading…";
      const opening = {};
      session.opening = opening;
      lactateDialog.showModal();
      try {
        const rows = await lactateRequest("list", session);
        if (lactateSession !== session || session.opening !== opening || !lactateDialog.open) return;
        renderLactateRows(rows, session.measured);
        lactateStatus.textContent = "";
      } catch (error) {
        if (session.opening === opening) lactateStatus.textContent = error.message;
      }
    });
  });
  lactateAdd.addEventListener("click", () => {
    const taken = new Set(Array.from(lactateBody.rows, row => Number(row.dataset.rep || row.cells[0].firstElementChild.value)));
    let rep = 1;
    while (taken.has(rep)) rep++;
    if (rep > 200 || lactateBody.rows.length >= 200) return;
    addLactateRow(rep, {}, null);
    lactateBody.lastElementChild.querySelector("input").focus();
    lactateAdd.hidden = lactateBody.rows.length >= 200;
  });
  lactateSave.addEventListener("click", async () => {
    const session = lactateSession;
    const opening = session.opening;
    const rows = Array.from(lactateBody.rows, row => ({
      rep: Number(row.dataset.rep || row.cells[0].firstElementChild.value),
      ...Object.fromEntries(Array.from(row.querySelectorAll("[data-lactate-field]"),
        input => [input.dataset.lactateField, input.value.trim()]))
    }));
    lactateSave.disabled = true;
    lactateStatus.textContent = "Saving…";
    try {
      await lactateRequest("save", session, rows);
      if (lactateSession === session && session.opening === opening && lactateDialog.open) lactateDialog.close();
    } catch (error) {
      if (lactateSession === session && session.opening === opening) lactateStatus.textContent = error.message;
    } finally {
      lactateSave.disabled = false;
    }
  });
