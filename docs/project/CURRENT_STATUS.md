# Actuele status

Bijgewerkt: 20 oktober 2026.

## Productiestatus

- Productiebranch: `main`; pushes deployen automatisch op Render.
- MiLa is de planner voor trainers en atleten. PAC is een aparte Render-service en repository voor Match Overview en de PR-database.
- Het MiLa-logo wordt als browser- en beginschermicoon aangeboden op iOS en Android.
- De recent aangevraagde atleetaccounts zijn rechtstreeks in productie aangemaakt en aan de bestaande coach-atleetstructuur gekoppeld. Wachtwoorden staan niet in Git of projectdocumentatie.

## Campplanning

- Coach Settings bevat als eerste instelling een opgeslagen aan/uitknop `Planning Camps`, standaard uit.
- Bij inschakeling verschijnt `Details Camps` in de Coach plannings-sectie. Genoemde Camp-whereabouts worden per kampnaam samengevoegd; het overzicht bevat atleten en toegankelijke coaches met ieder hun eigen aankomst- en vertrekdatum. Per deelnemer zijn die datums en in-/uitvluchtgegevens automatisch opgeslagen; datums werken rechtstreeks de Year Planner-range bij. De campdetailtabel sorteert op alle inhoudelijke kolommen, heeft Copy/Paste en een delete-knop per bewerkbare deelnemersregel en markeert coachregels lichtgeel.

## Belangrijk werkend gedrag

- In de AYC-trainingsevaluatie toont `Watch A` dezelfde Type A Polar-uitvoer als Polar Integration voor de geselecteerde atleet en datum. Bestaande opgeslagen horlogeresultaten blijven zichtbaar en kunnen nog worden verwijderd.
- In de AYC-trainingsevaluatie staat naast `Watch A` nu `Watch B`. Model B levert voorlopig dezelfde output via een afzonderlijk analysekanaal en kan daardoor verder worden ontwikkeld zonder Model A direct aan te passen.
- Model B probeert nu herhaalde afstandsblokken te herkennen, inclusief korte herstel-laps en een gecombineerde werk/pauze-lap rond de dominante herhalingsafstand. Bij onvoldoende zekerheid blijft de Model A-uitvoer zichtbaar.
- Model B gebruikt optioneel een taalmodel voor complexere geneste structuren (bijvoorbeeld meerdere afstanden binnen twee herhaalde sets). De vaste afstands- en tijdsberekening blijft leidend; zonder API-sleutel of bij een ongeldige/te onzekere reactie blijft de bestaande rules-based herkenning actief.
- Vanuit een bruikbare Type A-omschrijving kunnen `Use AM` en `Use PM` WU, Main en CD naar het gekozen AYC-slot overnemen; `Continuous run` wordt niet opgeslagen als onderdeel van de trainingstekst.
- Atleten met `Extended edit rights` zien in de AYC altijd AM- en PM-evaluatievelden op zichtbare dagdelen, ook zonder training; toekomstige evaluaties kunnen dan worden opgeslagen voor verdere horloge-integratie.
- Coach Settings bevat een opgeslagen `P(ause)mode`-dropdown met `Static unless "ap"` en `Active unless "pp"`. In de eerste stand telt alleen een expliciete `ap` als Z1-afstand, in de tweede zowel `p` als `ap`; `sp` en `pp` blijven statisch. Dit geldt ook voor AM- en PM-weektotalen in Flex Planner. Bij expliciete herhalingsnotatie is het aantal uit de trainingstekst leidend boven verouderde opgeslagen herhalingsmetadata.

- Polar Type A toont voor iedere handmatige en automatische ronde naast de exacte afstand ook de afstand afgerond op 50 meter en afzonderlijke Zx- en Tx-tempoaanduidingen van de geselecteerde atleet.
- Polar Type A toont per ronde de gemiddelde HR uit de secondegegevens; deze HR is voorlopig alleen zichtbaar en heeft nog geen effect op planning of horlogedata.
- Polar Type A sluit bekende niet-hardlooprecordings, zoals fietslogs, uit met dezelfde sport-ID-regel als Type D.
- Polar Type A genereert bij duidelijke handmatige laps een beschrijving van WU, hoofdsegmenten, gemiddelde herstelduur per segment en eventuele CD.
- Polar Type A herkent ook afwisselende lange tijdsblokken met korte herstelrondes, zodat bijvoorbeeld 10' + 10' + 15' met gemiddeld 90 seconden herstel als hoofdblok wordt beschreven.
- Polar Type A valt bij één lange lap met een kleine GPS-restlap terug op een `Continuous run`-omschrijving met de totale sessieafstand en -duur.
- Polar Type A toont voor hardlooprecordings zonder handmatige laps een General description met afstand, gemiddeld tempo en bijbehorende Z-zone.

- Team Pace gebruikt goed zichtbare middengroene en warme auberginekleurige teambekleding; een teamlogo is nog niet ingesteld.
- Focus Points and Desired Improvements staat onder Planning wanneer de coachschakelaar aanstaat. Trainers kiezen een toegankelijke atleet; eigen trainers en gedelegeerde trainers met editrechten kunnen commentaar in Comment coaches, Plan en Progress per focuspunt opslaan. Commentaar wordt per coach met username-initialen en vaste coachkleur getoond. `Overwrite` staat standaard uit en geldt alleen voor dezelfde focuspunt/kolom-cel; view-only coaches kunnen alleen lezen. Edit-coaches kunnen ook de `.xlsx`-matrix met coachcomments importeren: namen worden vooraf gevalideerd en alleen niet-lege cellen vervangen de eigen comments; comments van anderen en Plan/Progress blijven staan. Prio is per focuspunt gedeeld opgeslagen als —/goud/zilver/brons; de Other 1–3-labels zijn per atleet door iedere bevoegde coach aanpasbaar. Comment Athlete is nog een placeholder.

- `Extended edit rights` geeft een atleet toegang tot toekomstige AYC-trainingen en lege dagdelen. `Can change base planning` staat daar los van en geeft alleen toegang tot de eigen Base Planning.
- Coach Settings bevat `Shared athlete whereabouts in Year Planner`, standaard uit. Daarmee verschijnen read-only whereabouts van ploeggenoten en gerelateerde coaches in de Year Planner; trainingen blijven afgeschermd.
- De tab in Athlete Input heet `Zones. HR, Speed` en gebruikt binnen de tab `Current times`. De trainer kan HR-invoer en snelheidsondersteuning naast de zone-invoer beheren.
- De Flex Planner en AYC herkennen `TM` en andere T-labels alleen als losse tempo-aanduidingen. Tekst zoals `ritme` levert daardoor geen onterechte TM-kilometers meer op.

- Trainers kunnen eigen gegevens bekijken of expliciet als een toegankelijke coach kijken. Die toegang is niet transitief; view-only blijft server-side read-only.
- Atleten zien uitsluitend zichzelf in AYC, settings, races, evaluaties en, waar ingesteld, Year Planner.
- Flex Planner toont de effectieve, gepersonaliseerde planning. Het verwijderen van een flex-override onderdrukt een basistraining correct.
- Coach Settings bevat `See session km`; indien ingeschakeld tonen Flex Planner en DCO Training hetzelfde sessietotaal als AYC, zonder Alternative-kilometers.
- Watch A/B/C-trainingen bewaren de werkelijke meters en seconden uit de horlogeanalyse. Daardoor rekenen AYC, Flex Planner, DCO en weektotalen deze slots niet opnieuw om vanuit geplande zone-snelheden; de zichtbare trainingstekst toont alleen de bestaande min/km-notatie.
- Persoonlijke wijzigingen na de formele einddatum van een bronplanning blijven ook in Flex Planner zichtbaar, net als in AYC.
- Base Planning-koppelingen naar trainerplannen blijven ook bij meerdere geselecteerde atleten zichtbaar in Flex Planner, onafhankelijk van de formele planrange.
- Een expliciete Base Planning-koppeling kan het trainer-slot rechtstreeks laden wanneer de normale Flex-voorlaadlijst het plan mist.
- Flex Planner kiest nu per AM/PM-dagdeel het in Base Planning toegewezen trainerplan. Daarmee kan een leeg slot in een ander, alfabetisch eerder gekoppeld plan (zoals bij Brenn op 13-10 PM) de juiste training niet meer verbergen. Lege, niet-toegewezen oude persoonlijke slots tellen niet als actieve bronplanning.
- Drag/kopieer vanuit een trainerplan bewaart de Flex-override nu in het plan van de actieve coachweergave. Zo wordt een kopie vanuit een gedeeld trainerplan niet alleen in de trainingspopup getoond maar ook in de Flex Planner-cel.
- Trainer Planning kan de ingestelde periode van 1–12 weken als liggend A4 afdrukken. DCO Training kan na de atleetselectie de gekozen dag en AM/PM-slots afdrukken.
- Expliciete atleet-slots worden in Flex Planner als bronplanning herkend, ook zonder oude planlidmaatschap- of groepskoppeling.
- In Flex Planner kan een persoonlijke override met `Reset to plan` worden verwijderd, zodat de onderliggende trainertraining opnieuw zichtbaar wordt.
- AYC gebruikt dezelfde actieve bronplanning als Flex Planner; achtergebleven persoonlijke slots uit oude of niet-toegewezen plannen verbergen de actuele training niet meer.
- In AYC is individuele Base Planning nu net als in Flex leidend boven een gekoppeld groepsplan per AM/PM-dagdeel. `Rest` verbergt de groepstraining; een expliciete persoonlijke override blijft zichtbaar.
- Weekphase-kleuren komen uit Year Planner en verschijnen ook in Flex Planner, AYC en Trainer Planning. Bij meerdere fases krijgt de week een gecombineerde kleur.
- Year Planner ondersteunt één, drie of twaalf maanden, stacked of scrollend. Whereabouts zijn verplaatsbare en schaalbare datumranges met benoemde pills, diagonale overlapweergave, rij-kopiëren en bulktoepassing op de geselecteerde atleten.
- De Year Planner heeft naast de atleetselector een inklapbare coachselector. Iedere toegankelijke coach heeft een eigen whereabouts-rij; view-only coaches blijven strikt alleen-lezen.
- Trainers kunnen in de Year Planner per gekozen Trainer Planning-groep direct onder `All` een eigen `Basis - groepsnaam`-rij selecteren. Basisgegevens van verschillende groepen blijven gescheiden.
- Per atleet zijn Year Planner Training en Whereabouts afzonderlijk zichtbaar te maken. De atleetweergave is alleen-lezen en de legenda volgt de toegestane lagen.
- Base Planning gebruikt handmatig instelbare, aaneengesloten datumblokken. De oude onderliggende Save/Cancel-knoppen zijn verwijderd; wijzigingen blijven op de actieve tab na opslaan.
- Mobiele AYC heeft Open-knoppen, AM/PM-evaluaties, week reports, daily vitals en een popup voor niet-ingevulde evaluaties van de afgelopen zes dagen. De huidige dag en oudere trainingen tellen niet mee. De daily-vitals-popup staat buiten de AYC/team-stackingcontext, slaat mobiel zonder paginareload op en ruimt daarna de Bootstrap-backdrop en modalstatus op, zodat Safari/iOS niet in een onklikbare overlay blijft hangen.
- Mobiele evaluatiecommentaren ondersteunen Nederlandse spraak-naar-tekst. Herkenningsresultaten worden per resultaatindex verwerkt om dubbele of drievoudige tekst te voorkomen.
- Evaluations ondersteunt coachvragenlijsten met gewone en matrixvragen, kopiëren vanuit eigen lijsten en van coaches met editrechten, verwijderen, inklapbare lijsten en ingevulde antwoorden per atleet. Kopiëren laat het origineel en antwoorden intact. `Active` en doelgroep zijn afzonderlijk instelbaar; iedere lijst heeft de keuze alle atleten of geselecteerde losse atleten. Titel, status en doelgroep zijn achteraf bewerkbaar; wijzigingen aan vragen zelf zijn voorlopig uitgesloten om eerder ingediende antwoorden eenduidig te houden. Het aanpassen van de doelgroep wist antwoorden niet, maar uitgesloten atleten kunnen het formulier niet opnieuw openen. De doelgroep wordt ook server-side afgedwongen. De module is per coach aan- en uit te zetten in Coach Settings en geldt dan ook voor diens atleten. Evaluation sharing kan Training-, Week- en Vitals-evaluaties per coach delen met coaches die view- of edit-toegang hebben; standaard staat delen uit.
- Coach Tools in MiLa bevat Track Timer voor 100–1600 m, doeltijdvisualisatie, drie-atletenmodus en tussentijden.
- Parser ondersteunt T1 en T6, progressieve Z/T-ranges met tussenliggende labels, compoundblokken en pauzenotatie `p`/`sp`.
- Polar v3/v4-integratie en reconstructies bestaan. Polar v4-samples worden nu naast laps opgehaald en aan de tijd/afstand-matcher doorgegeven; complexe workoutmatching blijft een actief ontwikkelgebied.

## Recente onderhoudsafspraken

- Nieuwe Mila-chats starten met `AGENTS.md` en `docs/project/START_HERE.md`; `CODEX_CONTEXT.md` is alleen nog een verwijzing.
- Voor eenmalige accountimports bestaan generieke Django-management commands. Passwords en database-URLs horen nooit in Git.

## Bekende aandachtspunten

- Settings is een werkende coachdashboardtegel met onder meer Planning Camps; Stats en Polar houden hun under-development-label.
- Daily Coach Overview Other is beschikbaar met de inklapbare blokken Info Quality en Vitals. Info Quality toont per eigen atleet openstaande AYC-evaluaties van de afgelopen zeven dagen, exclusief vandaag. Vitals toont gemiddelden over de laatste veertien kalenderdagen bij minimaal drie waarden en bevat ook HR zones met Z1–Z5 per atleet; Show NA staat uit en de vitalkeuze houdt Vitals open.
- Stats is bewust eenvoudig en nog in ontwikkeling.
- Polar/watch suggestions, vooral automatische workoutmatching zonder handmatige laps, hebben verdere testgevallen en verfijning nodig.
- E-mail-, WhatsApp- of pushreminders voor openstaande evaluaties zijn nog niet gebouwd; de huidige herinnering is alleen de AYC-popup.

## Afgerond in main, 11–12 oktober 2026

- Polar Integration bevat A/B/C/D: ruwe rondes, samples, tempoverwerking en één overzicht met kilometers per tempozone en HR-zone.
- Type D reproduceert de gecontroleerde voorbeeldtraining: tempo Z1 7,6 km / Z3 5,4 km; HR met de besproken geschatte grenzen 3,8 / 3,9 / 3,6 / 1,7 / 0,0 km. Dit voorbeeld is een rekentest, geen algemeen aanbevolen HR-profiel.
- Overlappende Polar-pauzemarkeringen tijdens aantoonbare beweging verbergen de loopdata niet meer. Regels uit de aangeleverde JSON zijn lokaal gecontroleerd; persoonsgegevens zijn niet als testfixture gecommit.
- Type D heeft eigen opgeslagen HR-grenzen per atleet en migratie `0096_polar_analysis_settings`. AI-toelichting gebruikt de bestaande API-configuratie en heeft een zichtbare terugval als die ontbreekt.
- Polar-knoppen hebben witte tekst op gevulde achtergronden. AYC-, Flex- en Trainer Planning-popups zijn buiten de teambekleding geplaatst zodat invoer, Save en Close boven de backdrop blijven.
- DCO Other heeft werkende Vitals, behoud van het geopende blok en Show NA-filter.
- Laatste applicatiecommit vóór deze documentatieronde: `9198f0c`. Pushes staan op main; de daadwerkelijke Render-deploystatus is bij deze documentatieronde niet apart bevestigd.

## Validatie en resterende beperkingen

- Flex Planner toont een gekopieerde/persoonlijke atleettraining ook wanneer Base Planning voor dat dagdeel `Rest` bevat. De gedeelde trainertraining blijft op zo'n dagdeel verborgen; een expliciete persoonlijke override heeft voorrang.
- De Flex-popup volgt dezelfde bronkeuze als de cel: individuele Base Planning en expliciete Rest gaan vóór een gekoppeld trainerplan; datumblokken volgen de laatste `effective_from`.

- De Flex/Base Planning-reparatie is met tien gerichte regressietests en `manage.py check` gevalideerd. In de bredere `SlotModalSaveTests`-reeks slagen 59 van 60 tests; alleen `test_shared_coach_can_save_vitals_for_accessible_athlete` faalt nog met HTTP 403 in plaats van 204. Dit betreft de aparte vitals-rechtenroute, niet de Flex-weergave.
- De 46 gerichte Polar-tests slaagden, inclusief Type D-berekening, HR-opslag en rechten. Django-check en migratiecontrole slaagden; beide zoneverdelingen zijn tegen de aangeleverde JSON gecontroleerd.
- Witte Polar-knoptekst en Type D zijn op 390/1440 px gecontroleerd. De popupblokkade is met de echte Flex/Trainer-openers gereproduceerd en opgelost voor AM/PM, lege/bestaande invoer en klikbaarheid van Save/Close. Vier gerichte Django-modaltests slaagden.
- C blijft een eerste versie: tempopieken rond stops en hervatten zijn niet altijd betrouwbaar te corrigeren. Type D gebruikt daarom bij voorkeur rondegemiddelden; zonder bruikbare rondes blijft de sampleanalyse conservatief.
- De HR-preset is geschat en moet per atleet beoordeeld worden. Een hoogste gemeten trainingshartslag is niet automatisch HRmax.
- Type D staat los van planning en evaluatie: automatische overname naar AYC is niet gebouwd. AI-uitvoer is een interpretatie, geen vastgestelde uitvoering of medische drempelmeting.
