# Individual Plans: weektotalen

15 november 2026: Individual Plans gebruikt voor de weektotalen dezelfde
`_ayc_slot_loads_for_totals`-berekening als Athlete Diary, eenmaal per zichtbaar
effectief AM-/PM-slot. De browser ontvangt deze loads op de atleetweekrij;
trainingsteksten worden voor deze totalen niet opnieuw geparseerd.

Daarmee blijven gemeten zones, herstelmeters zonder eigen tekstsegment,
loop-/wandeluitsluiting, T-labels en Alternative-minuten gelijk. Not done telt
niet mee; de training blijft zichtbaar. Ook geplande trainingen volgen dezelfde
serverberekening. De sessiekoppen en compacte/mobiele indeling zijn behouden.

Regressie: `core.tests_flex_week_loads`, `core.tests.FlexPlannerAltTotalsTests`
en `node core/tests_flex_progressive_totals.js`; daarnaast `manage.py check`.
Productiegegevens van Sara en de Render-uitrol zijn niet lokaal geverifieerd.
