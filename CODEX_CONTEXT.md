# Mila Codex Context — historisch

> Dit bestand is vervangen door `AGENTS.md` en de thematische documenten in
> `docs/project/`. Het blijft alleen als historische naslag beschikbaar en bevat
> verouderde lokale paden en statusinformatie.

This file is a handover note for continuing Mila development from another Codex task or another machine.

## Project

- Local project folder: `C:\Users\iains\mila_app\mila`
- Django app, branch `main`.
- Render deploys from pushed commits on `main`.
- Use PowerShell and the virtualenv Python: `C:\Users\iains\mila_app\venv\Scripts\python.exe`.
- Usual local check: `C:\Users\iains\mila_app\venv\Scripts\python.exe manage.py check`.
- Run migrations when model fields change: `C:\Users\iains\mila_app\venv\Scripts\python.exe manage.py migrate`.
- Do not commit `Mila4.docx`; it is an untracked program-description document.

## User Preferences

- Work in Dutch unless the user switches language.
- The user often says "naar render" or "gooi naar render"; that means commit and push to `main`.
- Usually implement directly after enough context is clear.
- Keep local changes small and test with `manage.py check` before deploy.
- For UI, preserve the existing Mila style: compact planning screens, pills for training segments and totals, no bulky explanatory text.

## Current Planning Structure

The old coach-console/calendar flow has mostly moved into `Planning`.

Planning contains:

- `Athletes`
- `Trainer Planner`
- `Flex Planner`
- `Races`
- `AYC` / Athlete Year Calendar
- `Daily Coach Overview`
- `Saved Trainings`
- `Standard Strength`

Athletes now have tabs:

- `General`
- `Zone/PRs`
- `Base Planning`
- `WU/CD`
- `Ideal Week`

Athlete users can see their own athlete settings, but some coach-only fields are hidden:

- weeks visible ahead
- AYC choices
- the whole Base Planning tab

## Recent Important Fixes

Latest pushed commit before this file:

- `c356a69 Split compound zone and T loads correctly`

Recent fixes:

- DCO now computes athlete-specific display paces correctly for trainer-planner derived sessions.
- Compound training totals now handle per-part labels correctly. Example:
  - `5*(1000m z3-200m t8) p0 sp3`
  - expected: `5 km Z3`, `1 km Z5`, `1 km T8`.
- Race Calendar uses steeple labels after 10000m:
  - `1000m S`, `1500m S`, `2000m S`, `3000m S`.
- Race target checkbox makes `Race!`; target races are red/white in Flex Planner and AYC.
- Auto WU/CD:
  - athlete setting overrides trainer/group setting;
  - applies only when a core exists;
  - no auto WU/CD for Z1-only sessions;
  - Z2 and harder sessions can get auto WU/CD.
- Standard Strength:
  - lives under Planning;
  - can be selected in Mob/Tech fields;
  - renders as clickable link;
  - text can be added after the selected strength link.

## Daily Coach Overview

DCO selection supports:

- date
- AM / PM / both
- all
- selection
- trains
- planned training
- saved named selections
- one standard saved selection

DCO result screen is separate from the selection screen. It has previous/next day buttons and preserves the current selection. RPE and comments from athlete reports should be visible.

Important implementation detail:

- DCO must clone trainer-planner slots before annotating display paces per athlete.
- Otherwise the same slot object is reused and all athletes can end up with the last athlete's paces.

Relevant file:

- `core/views/coach.py`

## Trainer Planner

Trainer Planner:

- shows multiple weeks, default 4;
- current week is highlighted yellow;
- next/previous moves the first visible week by one week;
- weeks stay 7 days wide, extra weeks stack vertically;
- day/week copy via `c` and paste via `p` works between plans;
- paste mode clears on Escape or when navigating back to the planner dashboard, not when switching between trainer plans.

Training templates from trainer planning flow into Flex Planner and AYC. Flex Planner should allow editing and copying those derived sessions, not show an empty template.

## Flex Planner

Flex Planner:

- current week is highlighted yellow;
- first column week-type color must stay visible over the current-week highlight;
- group selector now uses Trainer Planner references, not old groups;
- derived training display times must be athlete-specific;
- copy/paste and drag-copy must work for both direct Flex sessions and trainer-planner derived sessions.

## AYC

AYC:

- loads immediately after selecting an athlete; no Load button.
- should show the same planned sessions as Flex Planner.
- report popup supports manual adjustment and watch suggestions.
- opening a report should prefill the planned training for that athlete.
- long watch suggestions must not make the popup impossible to save.

## Training Parser Notes

Supported notation includes:

- distance reps: `6*400m t3`
- ranges: `t3>t15`, `z2>z5`
- compound reps: `2*(600m-400m) t15`
- per-part labels: `5*(1000m z3-200m t8)`
- time reps: `3*(1.5'-1.5'-1.5'-5') z4 p30 sp2`
- seconds: `90"`
- minutes: `1.5'`
- pause shorthand:
  - `p15` and higher means seconds;
  - `p14` and lower means minutes;
  - same for `sp`.

For watch-derived totals:

- Z totals use the closest athlete zone.
- T totals are thresholds/minimum speeds:
  - slower than TM gets no T;
  - TM to THM is TM;
  - faster thresholds progress to THM, T10, T5, etc.
- Watch totals should use the displayed rounded pace when classifying, so the totals match what the user sees.

## Polar Integration

Polar v3 OAuth works and is used for:

- exercises
- samples
- physical info
- daily activity

Polar v4 OAuth was added for laps:

- auth URL: `https://auth.polar.com/oauth/authorize`
- token URL: `https://auth.polar.com/oauth/token`
- scope: `training_sessions:read`
- endpoint:
  - `https://www.polaraccesslink.com/v4/data/training-sessions/list`
- query format must use datetimes without timezone suffix:
  - `2026-07-30T00:00:00`

V4 lap data is nested under:

- `trainingSessions[].exercises[].laps.laps`
- `trainingSessions[].exercises[].laps.autoLaps`
- `trainingSessions[].exercises[].pauseTimes`

For the Polar 10x1000 test on `2026-07-30`, V4 returned:

- 1 session
- 22 manual laps
- 15 auto laps

Manual lap pattern:

- warmup lap
- alternating 10 work reps and recoveries
- cooldown lap

If V4 gives 401:

- refresh token once;
- if it still fails, the athlete likely needs to reconnect Polar v4.

## Watch Suggestions

AYC report popup has `Suggest Input`.

It should:

- sync connected watch data for that date;
- show all sessions on that date, ignoring AM/PM for now;
- show no-watch or no-activity messages when relevant;
- allow `Use suggestion`;
- save without requiring RPE/comment if watch input exists;
- set Done to green done automatically if no Done choice was selected.

Current strategy:

- show V4 lap suggestion when available;
- also show V3/sample-based structured suggestion;
- deterministic matching is preferred over AI when possible;
- OpenAI is optional and requires `OPENAI_API_KEY` on Render.

AI note:

- ChatGPT subscription is separate from OpenAI API billing.
- If API quota is missing, Render shows `OpenAI returned HTTP 429`.

## Known Open Ideas

Potential next watch-work:

- Make V4 lap suggestion compact, e.g. detect warmup, work reps, recoveries, cooldown from manual laps.
- Use v4 laps when athlete manually laps intervals.
- Use v3 distance samples when athlete records one continuous session.
- Improve fallback splitting into 100m or planned block distances.
- Consider Strava integration later:
  - OAuth per athlete;
  - `activity:read` / `activity:read_all`;
  - activities, laps, streams;
  - similar UI to Polar.

## Common Git Flow

Before deploy:

```powershell
git status --short
C:\Users\iains\mila_app\venv\Scripts\python.exe manage.py check
git add <files>
git commit -m "<message>"
git push
```

Do not stage `Mila4.docx` unless the user explicitly asks.
