# Start Here

Bijgewerkt: 5 november 2026.

## Project in één minuut

MiLa Training Planner is een Django 5.2-app voor trainers en atleten. Trainers maken trainer-, base- en flexplanning; atleten zien hun eigen AYC, wedstrijden, evaluaties en waar toegestaan hun Year Planner. Productie draait op Render vanaf GitHub-branch `main`.

- Repository: `C:\Users\iains\mila-trainingsplanner`
- Lokale Python: `C:\Users\iains\mila-trainingsplanner\.venv\Scripts\python.exe`
- Basale controle: `& '.\\.venv\\Scripts\\python.exe' manage.py check`
- Interface en communicatie: Engels in de app, Nederlands met de projecteigenaar.
- Voltooide wijzigingen worden normaal direct gecommit en naar `main` gepusht, tenzij de gebruiker expliciet lokaal werk vraagt.

## Handoff voor een nieuwe chat — 5 november 2026

- Laatste codecommit: `42c8470` (`Teach AI to group autolaps while retaining jogging recovery threshold`), gepusht naar `main`. Daarvoor: `bec1d8a` (niet-hardloopactiviteiten naar Alternative), `a8447c2` (Use AM/PM beschermt andere velden), `0a651fc` (evaluatie per dagdeel). Render-rollout en de echte AI-productieuitkomst zijn niet onafhankelijk bevestigd.
- Actuele casus: AYC-atleet 70, 5 november, vier blokken van drie kilometer-autolaps met telkens ~450m/~120s jogherstel. Gewenste hoofdindeling is `4×3000 m ... p119`; bronreps zijn laps `[1,2,3]`, `[5,6,7]`, `[9,10,11]`, `[13,14,15]`. Laps 4/8/12 zijn herstel; lap 16 is een korte slotrest. Gemeten reptijden: 593/586/592/589s. Exacte synthetische regressie: `split_distance_example()` in `core/tests_watch_ai_structure.py`.
- Expliciete wens eigenaar: laat de **AI** deze autolaps tot langere reps groeperen; voeg hiervoor geen lokale patroonherkenning toe. Opdracht bevat voorbeelden voor 3000m/2000m en een duurloop als tegenvoorbeeld. AI bepaalt de groepering; code controleert meetgegevens en leidt de getoonde getallen af.
- Behoud een controledrempel: beide complete werkreps naast een herstelblok moeten minimaal **20% sneller** zijn dan dat herstel (`work_speed / recovery_speed >= 1.2`, voorheen 1.4). Herstel blijft 30–600s en maximaal 600m; alle laps uniek/volledig/chronologisch toegewezen. De oude 1.4-grens wees ook het correcte gereconstrueerde testvoorstel voor deze casus af. Bestaande lokale herkenningsregels zijn niet aangepast.
- AI-model blijft standaard `gpt-5.4-mini`, `reasoning_effort=low`; `WATCH_STRUCTURE_MODEL` kan dit expliciet overschrijven. Geen modelverhoging gedaan. Bestaande toestemmingscontroles en maximaal één herstelverzoek blijven vereist. Confidence >=0.75 voor automatisch gebruiken; 0.50 <= score <0.75 alleen als te beoordelen AI-keuze na volledige meetcontrole. Verhoog confidence niet kunstmatig en verlaag deze grens niet om een voorbeeld te laten slagen.
- Laatste validatie: **111 gerichte tests** voor AI-structuur, bestaande herkenning, alternatieven, Garmin C/D en Watch/Plan plus `manage.py check` geslaagd. De C/D-endpointtest met gemockte AI-response bevestigt vier klokreps, intacte zestien bronlaps, geen nieuwe lokale 4x3000-herkenning zonder toestemming, en review-only bij confidence 0.68. Dit bevestigt verwerking van het modelantwoord, niet dat de live AI het na deploy daadwerkelijk zo indeelt. Geen nieuwe migratie; volledige core-suite niet uitgevoerd.
- Niet-hardloopactiviteiten (`bec1d8a`): C/D genereert bijvoorbeeld `Elliptical 90' Z2` of `Pilates 46' Z1` uit bekende sport, afgeronde hele minuten en gemiddelde HR +10 gekoppeld aan eigen HR-grenzen. Geen AI of loopafstandschatting. Geen verzonnen zone bij ontbrekende HR/grenzen. `Use AM/PM` schrijft uitsluitend ALT (`watch_fields=alternative`), behoudt alle andere velden, bronstatus, looploads en foto's. ALT-minuten tellen ook naast gemeten looploads mee. Oude ontvangsten zonder sport/HR vragen nieuwe Activity Details. 98 gerichte tests plus beide JS-tests/check slaagden; echte renderer met synthetische data visueel gecontroleerd op 390/1440 px.
- Gewone hardloopimport (`a8447c2`): Use AM/PM voor horloge A/B/C/D vervangt alleen WU/Main/Alternative/CD; Mob/Tech, Sprint en Strength plus foto's blijven behouden, ook uit gedeelde/Base Planning-bronnen. Lege ontvangen WU/ALT/CD wissen deze vervangbare velden. Segmentvolgorde en volledige Watch/Plan-snapshots blijven behouden.
- Evaluatie (`0a651fc`): AM opent alleen AM, PM alleen PM, met de actuele training erboven; de andere evaluatie blijft ongemoeid. Mobiele en desktop-popup eerder op 390/1440 px gecontroleerd. Gebruikerslabel is **Strength**, intern CORE2; de latere expliciete gebruikerswens gaat voor de verouderde Main 2-benaming in oudere instructies.
- Voorgaande klokfix `e81f743` blijft relevant: alle Main-minutenblokken na `+`/` - ` worden verwerkt, ook in oudere gecombineerde CORE-records. Casus 2×8′ + 4×4′ houdt zes klokregels 482/481/253/240/241/242s; daarvoor is opnieuw importeren niet nodig. Z1-doorloopfix `4610387` behoudt de laatste gedeeltelijke lap als deel van één rustig loopblok.
- Algemene Garmin-wijzigingen gelden voor C én D. D gebruikt End HR (laatste 10% van de volledige gemeten repduur, minimaal 15s; bij reps <15s Avg HR) vanaf 400m óf 50s voor trainingszonecorrectie. HR Zx classificeert elke eigen lap-HR. Gemeten meters/seconden blijven leidend; wandelen trager dan 10:00/km telt niet als loopafstand.
- Kernbestanden: `core/views/polar_raw.py`, `core/watch_ai_structure.py`, `core/views/coach.py`, `core/garmin_d.py`, `core/watch_processing.py`, `core/watch_alternative.py`, `core/views/slots.py`. Tests: `core/tests_watch_ai_structure.py`, `core/tests_garmin_c_push.py`, `core/tests_watch_plan.py`; zie DATA_RULES/FEATURES/CURRENT_STATUS voor details.
- Open vervolg: controleer eerst dat Render `42c8470` bevat; ververs AYC en open Garmin C/D opnieuw voor de actuele casus. Inspecteer AI-status, gekozen afstandsindeling, p119 en vier klokreps. Bij score <0.75 hoort hoogstens een geldige AI-reviewkeuze te verschijnen. Als het nog faalt, onderzoek de concrete nieuwe afwijsreden; claim geen live fix op basis van alleen mocks en voeg geen casusspecifieke lokale herkenning toe.
- Ongevolgde Word-handleidingen, Office-lockbestanden, `_manual_v2_render/` en `output/` zijn ongerelateerd en bewust niet gecommit. Geen databases, geheimen of privé-Garmin-payloads meestagen.

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
