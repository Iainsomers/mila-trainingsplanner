from datetime import date
from pathlib import Path
import json
import re
import shutil
import subprocess
from unittest import skipUnless
from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import Athlete, AthleteWeekReport, TrainingPlan, PlanMembership, TrainingSlot, AthleteDayCheck, EvaluationReaction, YearPlannerEntry


class EvaluationSessionTests(TestCase):
    def setUp(self):
        self.coach=get_user_model().objects.create_user(username='eval-coach',is_staff=True)
        self.plan=TrainingPlan.objects.create(owner=self.coach,name='Evaluation plan')
        self.athlete=Athlete.objects.create(owner=self.coach,name='Evaluation Runner',birth_year=2000,gender='X')
        PlanMembership.objects.create(plan=self.plan,athlete=self.athlete)
        self.day=date(2026,10,29)
        self.client.force_login(self.coach)
        for index,text in ((1,'AM easy 5000m Z1'),(2,'PM 6*400m Z3')):
            slot=TrainingSlot.objects.create(plan=self.plan,athlete=self.athlete,date=self.day,slot_index=index)
            slot.segments.create(type='CORE',text=text,order=3)
        self.url=f'/athlete/year/?start=2026-10-26&athlete={self.athlete.pk}'

    def test_mobile_week_phase_colour_is_on_header_and_mixed_week_has_label(self):
        for day, phase in ((date(2026, 10, 26), "aerobe"), (self.day, "specific"),
                           (date(2026, 11, 2), "aerobe")):
            YearPlannerEntry.objects.create(owner=self.coach, athlete=self.athlete, date=day, training_type=phase)
        response = self.client.get(self.url)
        self.assertEqual(response.context["week_rows"][0]["week_phase_label"], "Mixed")
        self.assertEqual(response.context["week_rows"][1]["week_phase_label"], "Aerobe")
        self.assertContains(response, 'class="ayc-mobile-summary-head d-flex justify-content-between align-items-center gap-2" style="background: linear-gradient')
        self.assertContains(response, 'class="ayc-mobile-summary-body"')
        self.assertNotContains(response, 'class="ayc-mobile-summary phase-')

    def test_page_contains_current_training_and_daypart_targets_on_desktop_and_mobile(self):
        TrainingSlot.objects.get(plan=self.plan, athlete=self.athlete, date=self.day, slot_index=1).segments.create(
            type="WU", text="Warmup-only label", order=0,
        )
        TrainingSlot.objects.get(plan=self.plan, athlete=self.athlete, date=self.day, slot_index=1).segments.create(
            type="ALT", text="Elliptical 15' Z1", zone="1", duration_s=900, order=4,
        )
        TrainingSlot.objects.get(plan=self.plan, athlete=self.athlete, date=self.day, slot_index=2).segments.filter(
            type="CORE",
        ).update(zone="3", reps=6, distance_m=400, norm_distance_m=2400, parse_ok=True)
        response=self.client.get(self.url)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'data-t1-training="Warmup-only label')
        texts=re.findall(r'data-t2-training="([^"]+)"',response.content.decode())
        self.assertTrue(any('PM 6' in text and '400m' in text for text in texts),texts)
        self.assertContains(response,'data-evaluation-slot="1" role="button"')
        self.assertContains(response,'data-evaluation-slot="2" role="button"')
        self.assertContains(response,'data-evaluation-slot="1"')
        self.assertContains(response,'class="evaluation-actions"')
        self.assertContains(response, ">Polar A</button>")
        self.assertContains(response, ">Polar B</button>")
        self.assertContains(response, ">Garmin E</button>")
        self.assertNotContains(response, 'id="suggestInputBtnC"')
        self.assertNotContains(response, 'id="suggestInputBtnD"')
        self.assertContains(response,'max-height:92dvh')
        self.assertContains(response, 'id="aycMobileDayView"')
        self.assertContains(response, 'id="aycMobileWeekView"')
        self.assertContains(response, 'data-overview-day="2026-10-29"')
        day = next(day for week in response.context["week_rows"] for day in week["mobile_days"] if day["day"] == self.day)
        am, pm = day["summary_slots"]
        self.assertEqual(am["zones"], [])
        self.assertEqual(pm["zones"], [{"zone": "3", "km": "2.4"}])
        self.assertEqual(pm["km"], "2.4 km")
        self.assertContains(response, '<span class="total-pill total-z3">Z3 2.4 km</span>', html=True)
        self.assertContains(response, "<span class='total-pill total-z1'>A Z1 15'</span>", html=True)

    @skipUnless(shutil.which("node"), "Node required for mobile Diary navigation")
    def test_mobile_week_overview_opens_day_and_keeps_selected_week(self):
        source = Path("core/templates/core/athlete_year_calendar.html").read_text(encoding="utf-8")
        start = source.index('    document.addEventListener("DOMContentLoaded", function () {\n      var weeks')
        source = source[start:source.index("</script>", start)].replace("{{ today|date:'Y-m-d' }}", "2026-11-26")
        script = """
const assert = require("node:assert/strict");
function element(dataset = {}) {
    const classes = new Set();
    return {dataset, disabled: false, classList: {
        toggle: (name, on) => on ? classes.add(name) : classes.delete(name),
        contains: name => classes.has(name),
    }, setAttribute() {}, focus() {}, addEventListener(name, action) { this[name] = action; }};
}
function week(weekStart, weekEnd, day) {
    const box = element({weekStart, weekEnd});
    box.cards = [element({day: weekStart}), element({day})];
    box.overview = [element({overviewDay: weekStart}), element({overviewDay: day})];
    const tabs = [element({dayTarget: weekStart}), element({dayTarget: day})];
    box.querySelectorAll = selector => selector === ".ayc-mobile-day" ? box.cards
        : selector === ".ayc-mobile-day-tab" ? tabs : box.overview;
    return box;
}
const first = week("2026-11-16", "2026-11-22", "2026-11-19");
const current = week("2026-11-23", "2026-11-29", "2026-11-26");
const diary = element(), controls = {};
let requestedUrl;
const window = {scrollTo() {}, location: {search: "", href: "https://example.org/athlete/year/?athlete=42",
    assign(url) { requestedUrl = new URL(url); }
}};
const document = {querySelectorAll: () => [first, current], querySelector: () => diary,
    getElementById: id => controls[id] ??= element(),
    addEventListener: (_, action) => action()};
""" + source + """
assert.ok(current.classList.contains("is-active"));
assert.ok(current.cards[1].classList.contains("is-active-day"));
controls.aycMobilePrev.click();
controls.aycMobileWeekView.click();
assert.ok(diary.classList.contains("is-week-view"));
first.overview[1].click();
assert.ok(first.cards[1].classList.contains("is-active-day"));
assert.ok(!diary.classList.contains("is-week-view"));
controls.aycMobileWeekView.click();
assert.ok(first.classList.contains("is-active"));
assert.ok(first.overview[1].classList.contains("is-selected"));
controls.aycMobilePrev.click();
assert.equal(requestedUrl.searchParams.get("start"), "2026-11-09");
assert.equal(requestedUrl.searchParams.get("mobile_week"), "2026-11-09");
assert.equal(requestedUrl.searchParams.get("mobile_view"), "week");
assert.equal(requestedUrl.searchParams.get("athlete"), "42");
"""
        result = subprocess.run(["node", "-"], input=script, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_posting_one_daypart_leaves_other_evaluation_unchanged(self):
        other=AthleteDayCheck.objects.create(athlete=self.athlete,date=self.day,slot_index=2,
            updated_by=self.coach,status='done_as_planned',rpe=7,pain='some_pain',comment='PM original comment')
        response=self.client.post(self.url,dict(date=self.day.isoformat(),slot_index='1',report_submit='1',
            check_status='adjusted_ok',rpe='4',pain='no_pain',report_comment='AM evaluation only'))
        self.assertIn(response.status_code,(200,204,302))
        other.refresh_from_db()
        self.assertEqual((other.rpe,other.pain,other.comment),(7,'some_pain','PM original comment'))
        self.assertEqual(AthleteDayCheck.objects.get(athlete=self.athlete,date=self.day,slot_index=1).comment,'AM evaluation only')

    def test_lactate_rows_are_saved_per_daypart_and_visible_to_the_athlete(self):
        self.assertContains(self.client.get(self.url), 'data-lactate-open aria-haspopup="dialog"', count=2)
        payload = {"date": self.day.isoformat(), "slot_index": 2}
        rows = [{"rep": 10, "lactate": "2,5", "rpe": "5", "comment": "After set", "length": "400",
                 "speed": "3:20", "hr": "170", "end_hr": "178"}]
        result = self.client.post(self.url, {**payload, "evaluation_lactate": "save", "rows": json.dumps(rows)})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["rows"], rows)
        self.assertContains(self.client.get(self.url),
                            'data-lactate-values="{&quot;10&quot;:{&quot;lactate&quot;:&quot;2,5&quot;,&quot;rpe&quot;:&quot;5&quot;}}"')
        self.assertFalse(AthleteDayCheck.objects.filter(athlete=self.athlete).exists())
        runner = get_user_model().objects.create_user(username="Evaluation_Runner")
        self.client.force_login(runner)
        self.assertEqual(self.client.post(self.url, {**payload, "evaluation_lactate": "list"}).json()["rows"], rows)
        self.assertEqual(self.client.post(self.url, {**payload, "slot_index": 1,
                                                   "evaluation_lactate": "list"}).json()["rows"], [])
        invalid = self.client.post(self.url, {**payload, "evaluation_lactate": "save",
                                             "rows": json.dumps([{"rep": 10, "rpe": "11"}])})
        self.assertEqual(invalid.status_code, 400)

    @skipUnless(shutil.which("node"), "Node required for clock popup checks")
    def test_clock_popup_only_shows_columns_with_rep_measurements(self):
        source = Path("core/templates/core/athlete_year_calendar.html").read_text(encoding="utf-8")
        source = source[source.index("  function showStoredWatchMainReps("):source.index("  function formatWatchDuration(")]
        script = """
const assert = require("node:assert/strict");
const nodes = {};
function node() {
    return {children: [], style: {}, focus() {}, replaceChildren() { this.children = []; },
        appendChild(child) { this.children.push(child); }};
}
const document = {createElement: node, getElementById: id => nodes[id] ??= node()};
const formatWatchDuration = () => "", formatWatchPace = () => "";
""" + source + """
function show(values) {
    showStoredWatchMainReps({
        closest: () => ({dataset: {lactateValues: JSON.stringify(values)}}),
        getAttribute: key => key === "data-watch-model" ? "Garmin E" : '[{"rep":10}]'
    });
    const [, table] = nodes.watchMainRepsBody.children;
    return table.children.map(section => section.children[0].children.map(cell => cell.textContent));
}
assert.equal(show({})[0].length, 6);
assert.equal(show({20: {rpe: "8"}})[0].length, 6);
assert.deepEqual(show({10: {rpe: "0"}}).map(row => row.slice(6)), [["RPE"], ["0"]]);
assert.deepEqual(show({10: {lactate: "2.5", rpe: "6"}}).map(row => row.slice(6)), [["Lac", "RPE"], ["2.5", "6"]]);
"""
        result = subprocess.run(["node", "-"], input=script, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @skipUnless(shutil.which("node"), "Node required for lactate row checks")
    def test_lactate_row_uses_watch_values_and_marks_missing_values_manual(self):
        source = Path("core/templates/core/partials/evaluation_lactate.js").read_text(encoding="utf-8")
        source = re.sub(r"const canWriteLactate = .*?;", "const canWriteLactate = true;", source)
        source = source[:source.index('  document.querySelectorAll("[data-lactate-open]")')]
        script = """
const assert = require("node:assert/strict");
const body = {rows: [], replaceChildren() { this.rows = []; }, insertRow() {
    const row = {dataset: {}, cells: [], insertCell() {
        const cell = {children: [], append(child) { this.children.push(child); }};
        this.cells.push(cell);
        return cell;
    }};
    this.rows.push(row);
    return row;
}};
const document = {getElementById: () => body, createElement: () => ({
    dataset: {}, setAttribute() {}, addEventListener(name, callback) { this[name] = callback; }
})};
""" + source + """
const watch = Array.from({length: 20}, (_, index) => ({
    distance_m: 400, pace_seconds_per_km: 192 + index, average_hr: 164 + index, hr_tail: 170 + index
}));
renderLactateRows([{rep: 10, lactate: "2,5"}], watch);
assert.equal(body.rows.length, 2);
assert.equal(body.rows[0].cells[1].children[0].value, "2,5");
const row = body.rows[1];
const rep = row.cells[0].children[0];
assert.equal(rep.value, "");
assert.deepEqual(row.cells.slice(4).map(cell => cell.children[1].placeholder), ["m", "m", "m", "m"]);
rep.value = "10";
rep.input();
assert.deepEqual(row.cells.slice(4).map(cell => cell.children[0].textContent), ["400", "3:21", "173", "179"]);
assert.ok(row.cells.slice(4).every(cell => cell.children[1].hidden));
rep.value = "21";
rep.input();
assert.ok(row.cells.slice(4).every(cell => !cell.children[1].hidden));
"""
        result = subprocess.run(["node", "-"], input=script, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_coach_reply_is_visible_and_acknowledged_only_by_the_athlete(self):
        User = get_user_model()
        self.coach.first_name = "Iain"
        self.coach.last_name = "van Somers"
        self.coach.save()
        runner = User.objects.create_user(username="Evaluation_Runner")
        check = AthleteDayCheck.objects.create(
            athlete=self.athlete, date=self.day, slot_index=2, updated_by=runner, comment="Original comment",
        )
        payload = {"date": self.day.isoformat(), "slot_index": 2, "reaction_text": "<Good work>"}
        self.assertContains(self.client.get(self.url), 'data-react="reportT2"')
        result = self.client.post(self.url, {**payload, "evaluation_reaction": "create"})
        self.assertEqual(result.json()["reactions"], [{"initials": "IS", "text": "<Good work>"}])
        reply = EvaluationReaction.objects.get()
        self.coach.username = "iains"
        self.coach.last_name = ""
        self.coach.save()
        self.assertEqual(EvaluationReaction.author_initials(self.coach), "IS")
        reply.initials = "I"
        reply.save(update_fields=["initials"])
        check.refresh_from_db()
        self.assertEqual(check.comment, "Original comment")

        self.client.force_login(runner)
        page = self.client.get(self.url)
        self.assertNotContains(page, 'data-react="reportT2"')
        self.assertContains(page, 'id="evaluationReactionNotice"')
        self.assertContains(page, '&lt;Good work&gt;')
        self.assertContains(page, '<strong>IS:</strong>')
        self.assertContains(page, 'min(540px, calc(100% - 2rem))')
        self.assertEqual(self.client.post(self.url, {**payload, "evaluation_reaction": "create"}).status_code, 403)
        self.assertEqual(self.client.post(self.url, {
            "evaluation_reaction": "read", "reaction_id": reply.pk,
        }).status_code, 200)
        self.assertNotContains(self.client.get(self.url), 'id="evaluationReactionNotice"')
        self.assertEqual(self.client.post(self.url, {**payload, "evaluation_reaction": "list"}).json(),
                         {"reactions": [{"initials": "IS", "text": "<Good work>"}]})

    def test_coach_can_reply_before_the_athlete_evaluates(self):
        AthleteDayCheck.objects.create(
            athlete=self.athlete, date=self.day, slot_index=2, updated_by=self.coach,
            watch_activity_id="watch-import",
        )
        for slot in (1, 2):
            response = self.client.post(self.url, {
                "evaluation_reaction": "create", "date": self.day.isoformat(),
                "slot_index": slot, "reaction_text": f"Please evaluate session {slot}.",
            })
            self.assertEqual(response.status_code, 200)
            evaluation = AthleteDayCheck.objects.get(athlete=self.athlete, date=self.day, slot_index=slot)
            self.assertFalse(evaluation.has_evaluation)
            self.assertEqual(evaluation.watch_activity_id, "watch-import" if slot == 2 else "")

        runner = get_user_model().objects.create_user(username="Evaluation_Runner")
        self.client.force_login(runner)
        page = self.client.get(self.url)
        self.assertContains(page, 'id="evaluationReactionNotice"')
        self.assertContains(page, "Please evaluate session 1.")
        self.assertContains(page, "Please evaluate session 2.")
        response = self.client.post(self.url, {
            "report_submit": "1", "date": self.day.isoformat(), "slot_index": 1,
            "check_status": AthleteDayCheck.STATUS_DONE_AS_PLANNED, "pain": AthleteDayCheck.PAIN_NONE,
        })
        self.assertEqual(response.status_code, 200)
        reply = EvaluationReaction.objects.select_related("evaluation").get(evaluation__slot_index=1)
        self.assertTrue(reply.evaluation.has_evaluation)

    def test_week_report_trainer_comment_notifies_only_for_changes(self):
        self.athlete.week_report_enabled = True
        self.athlete.save(update_fields=["week_report_enabled"])
        runner = get_user_model().objects.create_user(username="Evaluation_Runner")
        payload = {"date": "2026-10-26", "week_start": "2026-10-26", "week_report_submit": "1"}

        def save(field, value):
            response = self.client.post(self.url, {**payload, "field": field, "value": value},
                                        headers={"X-Requested-With": "XMLHttpRequest"})
            self.assertEqual(response.status_code, 200)
            return response.json()

        self.assertEqual(save("match_report", "Report"), {"has_content": True})
        week = AthleteWeekReport.objects.get(athlete=self.athlete)
        self.assertIsNone(week.trainer_comment_notice)
        self.assertEqual(save("comm_trainer", "First comment"), {"has_content": True})
        week.refresh_from_db()
        first_notice = week.trainer_comment_notice
        self.assertIsNotNone(first_notice)
        save("comm_trainer", "First comment")
        week.refresh_from_db()
        self.assertEqual(week.trainer_comment_notice, first_notice)
        self.assertNotContains(self.client.get(self.url), 'id="weekReportNotice"')
        save("comm_trainer", "Updated comment")
        week.refresh_from_db()
        self.assertNotEqual(week.trainer_comment_notice, first_notice)

        self.client.force_login(runner)
        page = self.client.get(self.url)
        self.assertContains(page, 'id="weekReportNotice"')
        self.assertContains(page, 'week-report-indicator-trainer has-content')
        self.assertContains(page, 'week-report-indicator-match has-content')
        self.assertContains(page, 'Updated comment')
        self.assertEqual(self.client.post(self.url, {"week_report_notice_read": first_notice}).status_code, 200)
        self.assertContains(self.client.get(self.url), 'id="weekReportNotice"')
        self.assertEqual(self.client.post(self.url, {"week_report_notice_read": week.trainer_comment_notice}).status_code, 200)
        self.assertNotContains(self.client.get(self.url), 'id="weekReportNotice"')

    @skipUnless(shutil.which('node'),'Node required for actual browser handler regression')
    def test_actual_js_opens_and_saves_only_clicked_session(self):
        source=Path('core/templates/core/athlete_year_calendar.html').read_text(encoding='utf-8')
        start=source.index('  document.querySelectorAll(".comment-display").forEach(function(el){')
        opening=source[start:source.index('  function showPendingEvaluations()',start)]
        start=source.index('  document.getElementById("commentOkBtn").addEventListener("click", function(){')
        saving=source[start:source.index('})();',start)]
        script=r"""const assert=require('assert');
const els={};
const document={getElementById:(id)=>els[id]||(els[id]={value:'',textContent:'',style:{},addEventListener:function(k,fn){this[k]=fn}}),querySelectorAll:()=>[el]};
let activeDate='',evaluationPainEnabled=true,savedWatch=[],requests=[],visible={};
const values={'data-date':'2026-10-29','data-t1-enabled':'1','data-t2-enabled':'1',
 'data-t1-training':'AM training','data-t2-training':'PM <script>training</script>',
 'data-t1-watch-id':'am-watch','data-t2-watch-id':'pm-watch',
 'data-t1-comment':'AM comment','data-t2-comment':'PM comment'};
const el={getAttribute:(k)=>values[k]||'',addEventListener:(k,fn)=>{el[k]=fn}};
function setSectionVisible(k,v){visible[k]=v;}
function enabled(k){return visible[k];}
function updateReportGrid(){}
function setVal(id,v){document.getElementById(id).value=v||'';}
function val(id){return document.getElementById(id).value;}
function setNotDoneRpe(){}
function setSavedWatchResult(id,summary){savedWatch=[id,summary];}
function loadEvaluationReactions(){}
function setLactateSession(){}
function validate(){}
function stopVoiceComment(){}
function post(...args){requests.push(args);return Promise.resolve();}
const window={location:{reload:()=>{}}};
"""+opening+saving+r"""
(async()=>{
 for(const slot of ['1','2']){
  requests=[];
  el.click({preventDefault(){},stopImmediatePropagation(){},target:{closest:()=>({getAttribute:()=>slot})}});
  assert.equal(visible.reportT1,slot==='1');assert.equal(visible.reportT2,slot==='2');
  assert.equal(els.reportTraining.textContent,values['data-t'+slot+'-training']);
  assert.equal(savedWatch[0],slot==='1'?'am-watch':'pm-watch');
  els.commentOkBtn.click.call(els.commentOkBtn);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.length,1);assert.equal(requests[0][0],Number(slot));
 }
})();
"""
        result=subprocess.run([shutil.which('node'),'-'],input=script,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
