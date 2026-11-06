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


Garmin C/D AI-latentie (5 november 2026): automatisch goedgekeurde AI-indelingen worden 24 uur gecachet per atleet en exacte opdracht (inclusief meetwaarden, zones en model). C en D delen dit voorstel; actuele toestemming blijft voor ieder gebruik vereist. De standaard Django-cache is proceslokaal: andere workers/herstarts kunnen opnieuw AI vragen. Afwijzingen, reviews en servicefouten worden niet gecachet. Strict AI-verzoeken wachten maximaal 12s per eerste netwerkpoging en 6s voor één herstelpoging (voorheen 25+15); meerdere activiteiten kunnen nog steeds optellen. De popup onderscheidt confidence- of meetafwijzing, zonder twee confidencegrenzen achter elkaar. Screenshotcasus confidence 0,42 bewijst geen meetfout; stabiele live 4×3000-herkenning blijft onbevestigd. Geen lokale patroonherkenning of confidenceverhoging toegevoegd.


Actueel vervolg 5 november: C/D-browser vraagt eerst preview=measured (zonder AI) en daarna de volledige analyse. Gebruiker kan de meetgegevens al gebruiken; na interactie wordt een nieuw resultaat alleen via Show analysis geladen. Exacte zone-/lap-/rolfeedback vervangt de algemene grenszonefout en staat ook in de AI-opdracht. De live 4×3000-indeling blijft onbevestigd; controleer nieuwe concrete afwijsreden indien nodig. Validatie: 109 gerichte Django-tests, check en drie JS-tests slagen; zie CURRENT_STATUS.


Actuele 4×3000-status: screenshot bevestigt toegepaste AI-groepering. Aanvullende correctie bepaalt C-zones uit volledige gemeten reps in plaats van de afzonderlijke autolaps. D behoudt End HR-correctie; zonder bruikbare HR blijft de volledige-reptempozone staan. 111 gerichte tests en check geslaagd.


Nieuwste casus: 3×8 circa300m met p28-30s en setpauzes175/180s. Correct AI-voorstel wordt nu toegelaten met korte-afstandsherstelminimum15s en afstandsmarge max(30m,8%); bestaande 20%-snelheidscontrole blijft. Zie DATA_RULES/CURRENT_STATUS voor voorwaarden. Prompt verduidelijkt afstandtarget bij ~55s-reps en één groep voor gelijke sets. 112 gerichte tests/check slagen; live herkenning nog te controleren.


Nieuwste afspraak: groepszonelabel C/D telt uitsluitend zones met >=10% van de volledige reps. Eén Z5 van 24 valt buiten het label, individuele zones en meetloads blijven intact. D telt na eigen HR-correctie, met volledige-reptempo als fallback. Screenshot bevestigt live 3×8×300-herkenning; deze nieuwe samenvattingsregel is lokaal getest (114 tests + check).


6 november: vooraf analyseren en blijvend opslaan van AI-resultaten is uitgesteld. Nieuwe Alternative-acties: Use AM/PM wist WU/Main/CD en vult ALT; alleen ALT-resultaten krijgen Add AM/PM voor uitsluitend ALT vervangen. Mob/Tech/Sprint/Strength blijven behouden. 50 gerichte tests, JS-renderer-/opslagtest en check geslaagd; zie DATA_RULES.


6 november — Information Quality: Evaluated NA betekent Vitals NA. Nieuwe Show NA-schuif staat standaard uit en verbergt Evaluated-NA-atleten; 0% blijft zichtbaar. ALL sluit NA uit. Zie FEATURES/UI_RULES.


6 november — coachdashboard: Polar/Garmin uploads/Garmin onder Hardware acces, bestaande links en zichtbaarheid behouden. Hardwareoverzicht via dashboard?section=hardware alleen voor coaches. 22 gerichte tests/check geslaagd.


6 november — Trainer Planning opent standaard met 12 zichtbare weken (voorheen 4). De bestaande weekkeuze en navigatie blijven behouden; ongeldige weekinvoer valt terug op 12. Gerichte standaard-/expliciete-/ongeldige-weektest en manage.py check geslaagd.


6 november — Evaluations-tegel verplaatst van Dashboard naar Planning > Views, voor coaches en atleten. De instelling evaluations_enabled van de actieve coach/eigen coach en coach-tools-only-beperking blijven van kracht. Bestaande evaluatiepagina, rechten en inhoud ongewijzigd. Tegel gebruikt responsieve Planning-kolommen. Gerichte evaluatieflow en modulezichtbaarheid voor coach/atleet plus manage.py check gecontroleerd.


6 november — Stats en Hardware acces staan nu onder optionele Under Dev-coachtegel. Coach Settings > Modules > Under Dev standaard uit, opgeslagen per actieve coach. Migratie 0145 vereist bij deploy. 24 gerichte tests/check/migratiecheck geslaagd.


6 november — reguliere coachtegels Coach tools/Settings/Under Dev en New, Plans, Wishes staan nu onder Planning > More. Atleten zien hier alleen New, Plans, Wishes; coachmodulezichtbaarheid blijft intact. Speciale coach-tools-only-account behoudt directe tooltoegang.


6 november — actieve coach wordt nu gekozen bovenaan Planning. Dashboardkeuze is weg; Dashboard-terugknoppen op onderliggende pagina’s verwijderd. Planning-POST behoudt bestaande selectie-/toegangsregels. 27 gerichte tests en check geslaagd.


6 november — Garmin connection en Garmin uploads voor atleten verhuisd van Dashboard naar Planning. Dezelfde toestemmingen en acties; Garmin-statusredirects wijzen nu naar Planning. Coachhardwaregroep ongewijzigd.


6 november — hoofdpagina /planning/ heet nu Mila Planner (paginakop en browsertitel). Evaluations heeft een Back-knop naar deze hoofdpagina. Bestaande terugknoppen naar planning_overview met label Planner/Planning/Back to Planning heten consequent Back; links naar specifieke planners en annuleerknoppen blijven ongewijzigd. Gerichte titel-/evaluatienavigatie-/module-/coachselectietests en manage.py check geslaagd.


6 november — atleten hebben Hardware onder More naast New/Plans/Wishes; Garmin-tiles en statusmeldingen staan in /planning/?section=hardware. Coach/atleettegels heten Athlete info. Coachtools/NewPlansWishes/Settings hebben Back. 30 gerichte tests + check geslaagd.


6 november — nieuwe UI-namen Athlete Diary / General Plans / Individual planner. Default na login en rootlaunch is Mila Planner. Start on Diary (bestaande boolean start_on_ayc) behoudt uitzondering voor atleet. Under Dev/Hardware-rootsecties blijven werken; interne Flex Planner-plannamen en routes zijn bewust niet hernoemd.


6 november — gebruik UI-namen Individual Plans, Improvements en Camps. Alle statische tegeltitels hebben elk woord met beginhoofdletter. Bestaande routes/datamodellen blijven intact. 30 gerichte tests/check geslaagd.


6 november — Standard Trainings onder More bundelt Saved Trainings/Standard Strength. Mila Planner behoudt categorieën en toont desktop drie even brede tegels; More is lager/compacter. Acht gerichte tests/check geslaagd.


6 november — More toont laptop/desktop alle zichtbare tegels in één rij via automatisch grid. Tegelhoogtes en witruimte op laptop verlaagd; extra compacte variant bij viewporthoogte<=760px. Acht gerichte tests/check slagen; browserpreview kon localhost niet bereiken.


6 november — coachtegels bewust rechts-naar-links volgens eigenaarsopdracht. Evaluations staat voor coaches in Coach Plannings; Views bestaat uit Diary/Staff Team Overview/DCO. More heeft nieuwe volgorde; zie UI_RULES. Negen gerichte tests/check geslaagd.


6 november — atletenvolgorde Views: Athlete Diary/Year Planner/Athlete Info/Camps/Improvements/Evaluations, rechts-naar-links per rij. Races-tegel verwijderd (via Year Planner). Tien gerichte tests/check geslaagd.


6 november — correctie leesrichting voor BEIDE rollen: alle opgegeven tegelvolgordes gelden van links naar rechts, eerst rij1 dan rij2. Omgekeerde flex-/gridrichting verwijderd; categorieën, lijsten en zichtbaarheid ongewijzigd. More blijft één rij op laptop/desktop. Tien gerichte tests en manage.py check geslaagd.


6 november — hoofdpagina: ondertitels van alle tegels verwijderd voor coach/atleet; alleen titels en bestaande iconen blijven. Desktoptegels verhoogd80→96px, More64→76px; compacte laptopvariant64→76px en More56→64px. Indeling, volgorde, rechten en bestemmingen behouden. Tien gerichte navigatie-/volgordetests en manage.py check geslaagd; geen visuele browsercontrole.


6 november — More is standaard ingeklapt en opent via de categorietitel. Rood bolletje toont aantal New-items afgelopen14 dagen, gelijk aan New/Plans/Wishes. Elf gerichte tests/check geslaagd.


6 november — tegelnamen hoofdpagina vergroot naar uniforme1.6rem (ook More en compacte laptopvariant). Alle tegels centreren inhoud verticaal; lange titels mogen omlopen. More/compacte tegels minimaal80px om twee tekstregels te passen. Bestaande iconen/volgorde behouden. Elf gerichte tests en manage.py check geslaagd; geen visuele browsercontrole.


6 november — Athlete Diary mobiel toont ALT-weekminuten per Z1/Z2/Z3 bij de loopzones, met min-eenheid. Bestaande berekening/uitsluiting niet-uitgevoerd blijft intact; gerichte test/check geslaagd.


6 november — loginformulier nu52px desktop en76px mobiel, mobiele tekst24px en bijna volle breedte. Viewportinstelling voorkomt verkleinde mobiele desktopweergave. Tien gerichte logintests/check geslaagd.


6 november — Diary-sessiekoppen tonen nu A + Alternative-minuten per zonekleur, naast loopkm. See session zones bepaalt zichtbaarheid; loop- en weektotalen ongewijzigd. Twintig gerichte tests/check geslaagd.


6 november — Year Planner Basis - All toegevoegd bij Group=All. Basis-checkbox verstuurt nu direct; geen atleet nodig. Interne plansoort year_basis bewaart All-schema apart van groepen/coaches. Migratie0146 vereist. 28 YearPlanner- en2 TrainerPlanningList-tests/check geslaagd; zie DATA_RULES.


6 november — Year Planner Group=All kan meerdere Basis-schema’s tonen, inclusief eigen MID/LONG-General Plans naast Basis - All. Herhaalde basis_plans-parameters behouden selectie bij navigatie. Rechten en scheiding van data intact; geen extra migratie.
