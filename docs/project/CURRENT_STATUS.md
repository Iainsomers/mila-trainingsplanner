# Actuele status

Bijgewerkt: 7 oktober 2026.

## Productiestatus

- Productiebranch: `main`; pushes deployen automatisch op Render.
- MiLa is de planner voor trainers en atleten. PAC is een aparte Render-service en repository voor Match Overview en de PR-database.
- Het MiLa-logo wordt als browser- en beginschermicoon aangeboden op iOS en Android.
- De recent aangevraagde atleetaccounts zijn rechtstreeks in productie aangemaakt en aan de bestaande coach-atleetstructuur gekoppeld. Wachtwoorden staan niet in Git of projectdocumentatie.

## Actieve vervolgstap

- Coach Settings bevat als eerste instelling een opgeslagen aan/uitknop `Planning Camps`, standaard uit.
- Bij inschakeling verschijnt `Details Camps` in de Coach plannings-sectie. Genoemde Camp-whereabouts worden per kampnaam samengevoegd; het overzicht bevat atleten en toegankelijke coaches met ieder hun eigen aankomst- en vertrekdatum. Per deelnemer zijn die datums en in-/uitvluchtgegevens automatisch opgeslagen; datums werken rechtstreeks de Year Planner-range bij. De campdetailtabel sorteert op alle inhoudelijke kolommen, heeft Copy/Paste en een delete-knop per bewerkbare deelnemersregel en markeert coachregels lichtgeel.

## Belangrijk werkend gedrag

- `Extended edit rights` geeft een atleet toegang tot toekomstige AYC-trainingen en lege dagdelen. `Can change base planning` staat daar los van en geeft alleen toegang tot de eigen Base Planning.
- Coach Settings bevat `Shared athlete whereabouts in Year Planner`, standaard uit. Daarmee verschijnen read-only whereabouts van ploeggenoten en gerelateerde coaches in de Year Planner; trainingen blijven afgeschermd.
- De tab in Athlete Input heet `Zones. HR, Speed` en gebruikt binnen de tab `Current times`. De trainer kan HR-invoer en snelheidsondersteuning naast de zone-invoer beheren.
- De Flex Planner en AYC herkennen `TM` en andere T-labels alleen als losse tempo-aanduidingen. Tekst zoals `ritme` levert daardoor geen onterechte TM-kilometers meer op.

- Trainers kunnen eigen gegevens bekijken of expliciet als een toegankelijke coach kijken. Die toegang is niet transitief; view-only blijft server-side read-only.
- Atleten zien uitsluitend zichzelf in AYC, settings, races, evaluaties en, waar ingesteld, Year Planner.
- Flex Planner toont de effectieve, gepersonaliseerde planning. Het verwijderen van een flex-override onderdrukt een basistraining correct.
- Weekphase-kleuren komen uit Year Planner en verschijnen ook in Flex Planner, AYC en Trainer Planning. Bij meerdere fases krijgt de week een gecombineerde kleur.
- Year Planner ondersteunt één, drie of twaalf maanden, stacked of scrollend. Whereabouts zijn verplaatsbare en schaalbare datumranges met benoemde pills, diagonale overlapweergave, rij-kopiëren en bulktoepassing op de geselecteerde atleten.
- De Year Planner heeft naast de atleetselector een inklapbare coachselector. Iedere toegankelijke coach heeft een eigen whereabouts-rij; view-only coaches blijven strikt alleen-lezen.
- Trainers kunnen in de Year Planner per gekozen Trainer Planning-groep direct onder `All` een eigen `Basis - groepsnaam`-rij selecteren. Basisgegevens van verschillende groepen blijven gescheiden.
- Per atleet zijn Year Planner Training en Whereabouts afzonderlijk zichtbaar te maken. De atleetweergave is alleen-lezen en de legenda volgt de toegestane lagen.
- Base Planning gebruikt handmatig instelbare, aaneengesloten datumblokken. De oude onderliggende Save/Cancel-knoppen zijn verwijderd; wijzigingen blijven op de actieve tab na opslaan.
- Mobiele AYC heeft Open-knoppen, AM/PM-evaluaties, week reports, daily vitals en een popup voor niet-ingevulde evaluaties van de afgelopen zes dagen. De huidige dag en oudere trainingen tellen niet mee.
- Mobiele evaluatiecommentaren ondersteunen Nederlandse spraak-naar-tekst. Herkenningsresultaten worden per resultaatindex verwerkt om dubbele of drievoudige tekst te voorkomen.
- Evaluations ondersteunt actieve coachvragenlijsten, gewone en matrixvragen, kopiëren vanuit bestaande lijsten, verwijderen, inklapbare lijsten en ingevulde antwoorden per atleet. De module is per coach aan- en uit te zetten in Coach Settings en geldt dan ook voor diens atleten. Evaluation sharing kan Training-, Week- en Vitals-evaluaties per coach delen met coaches die view- of edit-toegang hebben; standaard staat delen uit.
- Coach Tools in MiLa bevat Track Timer voor 100–1600 m, doeltijdvisualisatie, drie-atletenmodus en tussentijden.
- Parser ondersteunt T1 en T6, progressieve Z/T-ranges met tussenliggende labels, compoundblokken en pauzenotatie `p`/`sp`.
- Polar v3/v4-integratie en reconstructies bestaan. Polar v4-samples worden nu naast laps opgehaald en aan de tijd/afstand-matcher doorgegeven; complexe workoutmatching blijft een actief ontwikkelgebied.

## Recente onderhoudsafspraken

- Nieuwe Mila-chats starten met `AGENTS.md` en `docs/project/START_HERE.md`; `CODEX_CONTEXT.md` is alleen nog een verwijzing.
- Voor eenmalige accountimports bestaan generieke Django-management commands. Passwords en database-URLs horen nooit in Git.

## Bekende aandachtspunten

- Settings bevat bestaande technische voorkeuren, maar de dashboardtegel wordt nog als `under development` gepresenteerd. `Planning Camps` wordt de eerste expliciet aangevraagde coachinstelling.
- Daily Coach Overview Other is beschikbaar met de inklapbare blokken Info Quality en Vitals. Info Quality toont per eigen atleet openstaande AYC-evaluaties van de afgelopen zeven dagen, exclusief vandaag; Vitals is nog leeg.
- Stats is bewust eenvoudig en nog in ontwikkeling.
- Polar/watch suggestions, vooral automatische workoutmatching zonder handmatige laps, hebben verdere testgevallen en verfijning nodig.
- E-mail-, WhatsApp- of pushreminders voor openstaande evaluaties zijn nog niet gebouwd; de huidige herinnering is alleen de AYC-popup.


### Polar raw data (2026-10-11)
Polar Integration links to a read-only v4 data inspector. Type A shows recorded totals and separate manual/automatic laps with millisecond durations. Type B shows cumulative DISTANCE and HEART_RATE samples at a configurable 1–3600 second interval; unmatched timestamps and missing values are NA, without interpolation or speed estimates. One selected local calendar day is fetched server-side with Bearer authentication and one token refresh on 401. Original JSON is available for inspection. No training matching or import is performed. Athlete selection excludes unrelated Polar-user connections. Display is capped at 24 recording hours; original JSON is retained.

Polar raw-data requests start with the known working seconds-only date format and retry alternate formats on Polar date parsing errors. HTTP errors include the Polar error detail; reconnect advice is restricted to 401/403.

Polar raw data includes min/km: Type A uses each individual lap duration/distance; Type B uses the selected interval and the cumulative distance difference between consecutive displayed rows. Pace is rounded to whole seconds per km. Missing, zero or negative distance increments and the initial sample show NA. Missing samples break the segment; no interpolation is applied.


### Polar Type C (2026-10-11)
Read-only processed pace alongside unchanged raw values. Native distance increments are time-weighted over a centered 15-second window clipped to valid stretches. Manual lap boundaries, missing/negative distance, explicit Polar pauses and possible stops split stretches. A possible stop requires <=0.5 m/s for >=5 seconds. Isolated high/low bursts <=5 seconds require >=5 seconds of stable running on both sides before replacing speed with the neighboring median; flags and reasons remain visible. These provisional thresholds can confuse very short sprints with measurement errors. Pause clock mapping is checked against stop-start and sample duration; omitted paused seconds produce boundaries, uncertain clocks show a warning. No zones or workout mutations. Actual window duration is displayed, with a compact mobile layout.
