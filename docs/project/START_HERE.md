# Start Here

Bijgewerkt: 4 november 2026.

## Project in één minuut

MiLa Training Planner is een Django 5.2-app voor trainers en atleten. Trainers maken trainer-, base- en flexplanning; atleten zien hun eigen AYC, wedstrijden, evaluaties en waar toegestaan hun Year Planner. Productie draait op Render vanaf GitHub-branch `main`.

- Repository: `C:\Users\iains\mila-trainingsplanner`
- Lokale Python: `C:\Users\iains\mila-trainingsplanner\.venv\Scripts\python.exe`
- Basale controle: `& '.\\.venv\\Scripts\\python.exe' manage.py check`
- Interface en communicatie: Engels in de app, Nederlands met de projecteigenaar.
- Voltooide wijzigingen worden normaal direct gecommit en naar `main` gepusht, tenzij de gebruiker expliciet lokaal werk vraagt.

## Handoff voor een nieuwe chat — 4 november 2026

- Laatste codefix: `e81f743` (`Keep all timed Main blocks in Watch clock results`), gepusht naar `main`. Render-deploy en visuele productiecontrole zijn nog niet bevestigd; de eigenaar controleert visueel.
- Actuele casus: atleet 29, Garmin-activiteit `24955086351`, 3 november 2026. Main is `2×8′ Z2 p91 + 4×4′ Z2 p61`, WU 2000m en CD 1100m. De beschrijving was correct, maar het klokje toonde alleen de twee 8-minutenreps.
- Oorzaak: `normalize_watch_main_text` zet `+` om naar ` - `; `split_main_segments` splitste dat alleen voor afstandsblokken. Minutenblokken worden nu ook gesplitst. `processed_main_reps` verwerkt bovendien bestaande gecombineerde CORE-records, zodat opnieuw Use AM/PM voor deze fix niet nodig is; na deploy de pagina verversen.
- Regressie na echte Use AM/PM-opslag voor C én D: alle zes gemeten reptijden blijven `[482, 481, 253, 240, 241, 242]` seconden. Ook oudere gecombineerde records zijn gedekt. Geneste sets, zonebereiken en temporanges blijven intact. 75 gerichte tests slaagden; daarna slaagden 7 tests met de extra parserregressie en `manage.py check`. Volledige core-suite en visuele mobiele controle zijn niet uitgevoerd.
- Voorgaande herkenningsfix `d30d058`: lokale, gevalideerde herkenning geeft Distance/Time voor deze gemengde training zonder afhankelijk te zijn van een AI-respons. De eerste 8-minutenrep bestaat uit bronlaps 4–6; de tweede uit lap 8; vier korte reps uit laps 10, 12, 14 en 16. De lange stop in lap 3 mag geen werkrep worden.
- Kernbestanden: `core/training_text.py`, `core/watch_processing.py`, `core/watch_ai_structure.py`, `core/garmin_d.py`, `core/views/coach.py`. Tests: `core/tests_watch_plan.py`, `core/tests_watch_ai_structure.py`, `core/tests_watch_structure.py`, `core/tests_garmin_d.py`, `core/tests_garmin_c_push.py`, `core/tests_watch_alternatives.py`.
- Algemene Garmin-wijzigingen standaard in C én D. D gebruikt End HR (laatste 10% van de volledige gemeten repduur, minimaal 15s; onder 15s Avg HR) om vanaf 400m óf 50s tempozones te corrigeren. Gemeten meters/seconden blijven leidend voor totalen; wandelen trager dan 10:00/km telt niet mee als loopafstand.
- Ongevolgde Word-handleidingen, Office-lockbestanden, `_manual_v2_render/` en `output/` zijn ongerelateerd en bewust niet gecommit. Geen databases of privé-Garmin-payloads meestagen.

## Leesvolgorde voor nieuw werk

1. Lees `AGENTS.md`.
2. Lees dit bestand en de relevante documenten in deze map.
3. Controleer altijd de actuele code: documentatie beschrijft intentie, code en tests zijn leidend.
4. Behoud ongerelateerde, lokale bestanden. In deze werkmap horen `Mila4.docx` en `atletiek_fetch_list.txt` niet in commits.

## Huidige productvorm

- Planning: Athletes, Trainer planning, Flex Planner, Races, Year Planner, AYC/DCO en opgeslagen standaarden.
- Year Planner is de bron voor weekphase-kleuren in Flex Planner, AYC en Trainer Planning.
- Atleten zien de Year Planner alleen wanneer de trainer dat afzonderlijk toestaat voor Training en/of Whereabouts.
- Mobiele AYC heeft evaluatiepopups, een openstaande-evaluaties-prompt en spraak-naar-tekst voor commentaar.
- Evaluations is een apart vragenlijstonderdeel voor trainers en atleten.
- Coach Tools in MiLa bevat alleen Track Timer. Match Overview en PR-database horen bij het aparte PAC-project.
- Athlete settings bevat `Extended edit rights` voor toekomstige AYC-trainingen en lege dagdelen. `Can change base planning` is een afzonderlijk recht waarmee een atleet de eigen Base Planning mag aanpassen.

## Polar-analyse en recente fixes

- Polar Integration biedt Type A (totalen/rondes), B (ruwe samples), C (verwerkt tempo) en D (één overzicht met km per tempozone en hartslagzone).
- Type D rekent vaste totalen uit code; AI geeft alleen een optionele toelichting. HR-grenzen worden per atleet apart opgeslagen met een Estimated-vlag. Zie `FEATURES.md` en `DATA_RULES.md` voor methoden en onzekerheden.
- Polar-pauzemarkeringen worden tegen afstandssamples gecontroleerd; tegenstrijdige markeringen mogen loopgegevens niet verbergen.
- Trainingspopups in AYC, Flex Planner en Trainer Planning staan buiten de stacking context van de teambekleding en blijven boven de backdrop klikbaar.
- DCO Other toont dagelijkse vitals-gemiddelden. `Show NA` staat standaard uit; de keuze en het geopende Vitals-blok blijven behouden bij wisselen van vital.
- Migratie `0096_polar_analysis_settings` hoort bij Type D. Nieuwe deploys moeten deze meenemen via de bestaande Render-migratiestap.

## Nieuwe campbasis

- Coach Settings bevat een per coach opgeslagen `Planning Camps`-schakelaar, standaard uit.
- Bij inschakeling verschijnt Details Camps in de Coach plannings-sectie. Genoemde Camp-whereabouts met dezelfde kampnaam worden als een kamp herkend, ook wanneer deelnemers verschillende datums hebben. Het overzicht bevat atleten en toegankelijke coaches; de brede detailpagina laat individuele aankomst-/vertrekdatums en in-/uitvluchtgegevens automatisch opslaan. Aangepaste datums worden direct in dezelfde Year Planner-range opgeslagen. Deelnemersregels kunnen worden gekopieerd en geplakt; coachregels zijn lichtgeel.
- Atleten zien uitsluitend hun eigen Year Planner-rij en eigen whereabouts. Coaches zijn alleen zichtbaar als rijen in de coachweergave.

## Belangrijke grenzen

- Controleer trainer-/atleetrechten server-side; verborgen knoppen zijn niet voldoende.
- Gedeelde coachtoegang is niet transitief. View-only mag nooit schrijven.
- Accounts en wachtwoorden: nooit credentials, API-sleutels, database-URL's of tijdelijke accountlijsten committen. De herbruikbare opdracht `create_athlete_accounts` accepteert credentials alleen tijdens uitvoering.
- Tempoherkenning gebruikt alleen losse labels; vrije tekst zoals `ritme` mag nooit als `TM` worden geteld.
- Werk mobiele AYC altijd mee na bij zichtbare AYC-wijzigingen.

## Handige commando's

```powershell
& 'C:\Users\iains\mila-trainingsplanner\.venv\Scripts\python.exe' manage.py check
& 'C:\Users\iains\mila-trainingsplanner\.venv\Scripts\python.exe' manage.py test core
```

Bij modelwijzigingen: maak migraties, voer ze lokaal uit en laat Render daarna migreren via de bestaande deploystap. Zie `DEVELOPMENT.md` voor de volledige werkwijze.
