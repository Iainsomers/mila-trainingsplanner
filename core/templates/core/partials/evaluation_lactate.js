  const lactateDialog = document.getElementById("evaluationLactate");
  const lactateBody = document.getElementById("evaluationLactateRows");
  const lactateStatus = document.getElementById("evaluationLactateStatus");
  const lactateAdd = document.getElementById("evaluationLactateAdd");
  const lactateSave = document.getElementById("evaluationLactateSave");
  const lactateFields = {lactate: 12, rpe: 12, comment: 500, length: 12, speed: 20, hr: 6, end_hr: 6};
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

  function lactateWatchValues(watch) {
    const paceSeconds = Math.round(Number(watch?.pace_seconds_per_km));
    return {
      length: Number(watch?.distance_m) > 0 ? String(Math.round(watch.distance_m)) : "",
      speed: paceSeconds > 0 ? Math.floor(paceSeconds / 60) + ":" + String(paceSeconds % 60).padStart(2, "0") : "",
      hr: Number(watch?.average_hr) > 0 ? String(Math.round(watch.average_hr)) : "",
      end_hr: Number(watch?.hr_tail) > 0 ? String(Math.round(watch.hr_tail)) : ""
    };
  }

  function addLactateRow(rep, saved, watchReps) {
    const row = lactateBody.insertRow();
    const repCell = row.insertCell();
    let number;
    if (!canWriteLactate) {
      repCell.textContent = rep;
      row.dataset.rep = rep;
    } else {
      number = document.createElement("input");
      number.type = "number";
      number.min = "1";
      number.max = "200";
      number.value = rep;
      number.placeholder = "#";
      number.className = "form-control form-control-sm";
      number.setAttribute("aria-label", "Rep number");
      repCell.append(number);
    }
    const watchFields = {};
    const measured = lactateWatchValues(watchReps[Number(rep) - 1]);
    for (const [field, limit] of Object.entries(lactateFields)) {
      const cell = row.insertCell();
      const manual = Object.hasOwn(measured, field);
      const value = saved[field] || "";
      if (!canWriteLactate) {
        cell.textContent = measured[field] || value || (manual ? "m" : "—");
        continue;
      }
      const input = document.createElement("input");
      input.className = "form-control form-control-sm";
      input.dataset.lactateField = field;
      input.setAttribute("aria-label", field + ", rep " + rep);
      input.maxLength = limit;
      input.value = value;
      if (["lactate", "rpe", "length", "hr", "end_hr"].includes(field)) input.inputMode = "decimal";
      if (manual) {
        input.placeholder = "m";
        input.title = "Manual entry";
        const reading = document.createElement("span");
        cell.append(reading);
        watchFields[field] = {input, reading};
      }
      cell.append(input);
    }
    if (number) {
      function updateWatchFields() {
        const readings = lactateWatchValues(watchReps[Number(number.value) - 1]);
        for (const [field, {input, reading}] of Object.entries(watchFields)) {
          reading.textContent = readings[field];
          reading.hidden = !readings[field];
          input.hidden = Boolean(readings[field]);
        }
      }
      number.addEventListener("input", updateWatchFields);
      updateWatchFields();
    }
  }

  function renderLactateRows(saved, measured) {
    lactateBody.replaceChildren();
    saved.forEach(row => addLactateRow(row.rep, row, measured));
    if (canWriteLactate && saved.length < 200) addLactateRow("", {}, measured);
    lactateAdd.hidden = !canWriteLactate || lactateBody.rows.length >= 200;
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
    if (lactateBody.rows.length >= 200) return;
    addLactateRow("", {}, lactateSession.measured);
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
    })).filter(({rep, ...values}) => rep || Object.values(values).some(Boolean));
    lactateSave.disabled = true;
    lactateStatus.textContent = "Saving…";
    try {
      const saved = await lactateRequest("save", session, rows);
      const values = JSON.stringify(Object.fromEntries(saved.filter(row => row.lactate).map(row => [row.rep, row.lactate])));
      document.querySelectorAll('.slotbox[data-date="' + session.day + '"][data-slot-index="' + session.slot + '"]')
        .forEach(box => { box.dataset.lactateValues = values; });
      if (lactateSession === session && session.opening === opening && lactateDialog.open) lactateDialog.close();
    } catch (error) {
      if (lactateSession === session && session.opening === opening) lactateStatus.textContent = error.message;
    } finally {
      lactateSave.disabled = false;
    }
  });
