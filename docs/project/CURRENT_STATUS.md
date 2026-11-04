# Actuele status

## Laatste overdracht — 4 november 2026

- `e81f743` staat op main: het C/D-klokoverzicht verwerkt alle minutenblokken na Use AM/PM, ook als oudere opslag meerdere blokken met ` - ` in één CORE-record bevat. Casus atleet 29, 3 november: 2×8′ + 4×4′ moet zes klokregels tonen met 482, 481, 253, 240, 241 en 242 gemeten seconden.
- Getest via echte import/opslag en bestaande gecombineerde records voor C/D; 75 gerichte tests slagen, daarna ook de extra parserregressie (7 tests) en manage.py check. Geen migratie nodig. De volledige suite is niet uitgevoerd.
- Open: eigenaar ververst na Render-deploy en controleert de zes klokregels visueel. Deployvoltooiing is niet geverifieerd. Opnieuw importeren is voor deze fix niet nodig.
- Zie START_HERE.md voor de compacte overdracht en relevante bestanden; DATA_RULES.md beschrijft de parserregel.

## Privacyverklaring

- Een openbare Engelstalige privacyverklaring staat op `/privacy/` en is bereikbaar vanaf de loginpagina. De tekst omvat MiLa-verwerking, Oura en Garmin, de afzonderlijke optionele Garmin-AI-toestemming, OpenAI als verwerker en intrekking via dashboard of Athlete settings. Bijgewerkt op 31 oktober 2026; automatische Garmin-import wordt niet als bestaande functie voorgesteld. Controleer de verklaring opnieuw wanneer dataverwerking, providers of bewaartermijnen veranderen.
- De bijbehorende Engelstalige Terms of Service staat openbaar op `/terms/` en is eveneens gelinkt vanaf de loginpagina.
- Op het atleten-dashboard staat een `Hardware settings`-blok voor de optionele Oura OAuth-verbinding, alleen zichtbaar als de coach per atleet `Allow Oura connection` inschakelt. De Oura-testpagina is een tijdelijke preview; coaches kunnen die openen voor eigen aangesloten atleten. In de AYC kan de atleet met `Use Oura data` maximaal veertien dagen bekijken, individuele dagen verwijderen en de overige waarden met `Use all` opslaan. Alleen lege velden voor slaapuren, slaapkwaliteit (Oura-score / 10), Morning HR (laagste slaap-HR, afgerond op bpm) en HRV worden gevuld. Readiness is een verborgen voorwaarde. Uitschakelen verwijdert de opgeslagen Oura-koppeling. De productieconfiguratie gebruikt `OURA_CLIENT_ID` en `OURA_CLIENT_SECRET`; callback: `https://mila-trainingsplanner.onrender.com/integrations/oura/callback/`.
- Polar-toegang is per atleet standaard uit. De coachschakelaar `Allow Polar access` bepaalt of de atleet Polar-functies ziet en Polar-data-endpoints kan gebruiken; coachtoegang blijft werken.

Bijgewerkt: 4 november 2026.

## Productiestatus

- Productiebranch: `main`; pushes deployen automatisch op Render.
- MiLa is de planner voor trainers en atleten. PAC is een aparte Render-service en repository voor Match Overview en de PR-database.
- Het MiLa-logo wordt als browser- en beginschermicoon aangeboden op iOS en Android.
- De recent aangevraagde atleetaccounts zijn rechtstreeks in productie aangemaakt en aan de bestaande coach-atleetstructuur gekoppeld. Wachtwoorden staan niet in Git of projectdocumentatie.

## Campplanning

- Coach Settings bevat als eerste instelling een opgeslagen aan/uitknop `Planning Camps`, standaard uit.
- Bij inschakeling verschijnt `Details Camps` in de Coach plannings-sectie. Genoemde Camp-whereabouts worden per kampnaam samengevoegd; het overzicht bevat atleten en toegankelijke coaches met ieder hun eigen aankomst- en vertrekdatum. Per deelnemer zijn die datums en in-/uitvluchtgegevens automatisch opgeslagen; datums werken rechtstreeks de Year Planner-range bij. De campdetailtabel sorteert op alle inhoudelijke kolommen, heeft Copy/Paste en een delete-knop per bewerkbare deelnemersregel en markeert coachregels lichtgeel.

## Belangrijk werkend gedrag

- Garmin FIT uploads zijn beschikbaar voor coaches en geselecteerde atleten waarbij `Allow Garmin FIT uploads` is aangezet. FIT- en Garmin-zipuploads worden per atleet opgeslagen. Garmin C in de AYC leest de opgeslagen laps voor de geselecteerde atleet en hergebruikt Polar B's lapherkenning en optionele AI-structuurherkenning. Garmin C corrigeert Main-volgorde, ontbrekende herhalingen en zonebereiken aan de hand van chronologische Garmin-laps en voorkomt dubbeltelling wanneer een Main-Z1-lap ook expliciet als CD is herkend. Aangrenzende AI-segmenten met dezelfde afstand kunnen ook in een Main met andere afstanden tot één reeks worden samengevoegd wanneer het aantal werk-laps dit bevestigt; halve laps worden rechtstreeks op de ruwe afstand en volgorde samengevoegd, inclusief langere setpauzes en onafhankelijk van de tempozoneclassificatie. Dit wijzigt geen km-totalen. Opgeslagen lapsegmenten volgen de WU/Main/CD-velden. Alleen een expliciete Use AM/PM-keuze wijzigt de planning.

- In de AYC-trainingsevaluatie tonen `Polar A`, `Polar B` en `Garmin C` de resultaten van het geselecteerde model. Bestaande opgeslagen horlogeresultaten blijven zichtbaar en kunnen nog worden verwijderd. Garmin C gebruikt per atleet de lokaal opgeslagen Garmin FIT-laps van de gekozen datum; de Polar B-matcher/AI wordt hergebruikt en Garmin-bestanden van andere atleten zijn niet zichtbaar via de endpoint.
- Garmin C toont bij laps de gemiddelde hartslag en het gemiddelde van de FIT-record-hartslagmetingen in de laatste 15 seconden. De FIT-reader decodeert hartslagveld 3 en reconstrueert ontbrekende tijdstempels van gecomprimeerde records. Ontbreekt de meetreeks in een venster, dan toont de laatste-15-secondenwaarde `NA` in plaats van het lapgemiddelde; alleen de gewone gemiddelde HR kan daarop terugvallen. Laps zonder expliciete starttijd worden aan de activiteitstart en voorafgaande lapduren gekoppeld.
- De aanklikbare klokindicator bovenin een AYC-AM/PM-cel markeert overgenomen Polar A-, Polar B- of Garmin C-trainingen en toont per verwerkte Main-rep de nette geplande afstand, tijd en min/km. De gemeten afstand wordt apart bewaard en blijft de basis voor tempo; de ruwe laps en km-totalen veranderen niet.
- Model B probeert nu herhaalde afstandsblokken te herkennen, inclusief korte herstel-laps en een gecombineerde werk/pauze-lap rond de dominante herhalingsafstand. Een kort herhalingsfragment dat door een lange pauze van vergelijkbare werkblokken is afgesplitst wordt niet meer weggegooid; bij onvoldoende zekerheid blijft de Model A-uitvoer zichtbaar.
- Model B accepteert een taalmodelvoorstel alleen wanneer de voorgestelde afstanden aantoonbaar voorkomen én alle herhaalde actieve laps voor de herkende afstand zijn meegenomen; anders gebruikt het de rules-based herkenning.
- Ontbrekende tempo’s in een geldig Model B-taalmodelvoorstel worden server-side opnieuw berekend uit de gemeten laps, zodat Main-blokken altijd hun gemiddelde min/km tonen.
- Model B gebruikt optioneel een taalmodel voor complexere geneste structuren (bijvoorbeeld meerdere afstanden binnen twee herhaalde sets). Afstanden uit de AI-reactie worden server-side op 50 meter afgerond en identieke segmentreeksen worden gecomprimeerd tot sets. De vaste afstands- en tijdsberekening blijft leidend; WU en CD worden deterministisch aangevuld, ook wanneer na het laatste hoofdblok nog andere werkafstanden staan of de CD over meerdere laatste Z1-laps is verdeeld. Zonder API-sleutel of bij een ongeldige/te onzekere reactie blijft de bestaande rules-based herkenning actief.
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
- Focus Points and Desired Improvements staat onder Planning wanneer de coachschakelaar aanstaat. Trainers kiezen een toegankelijke atleet; eigen trainers en gedelegeerde trainers met editrechten kunnen commentaar in Comment coaches, Plan en Progress per focuspunt opslaan. Commentaar wordt per coach met username-initialen en vaste coachkleur getoond. `Overwrite` staat standaard uit en geldt alleen voor dezelfde focuspunt/kolom-cel; view-only coaches kunnen alleen lezen. Edit-coaches kunnen ook de `.xlsx`-matrix met coachcomments importeren: namen worden vooraf gevalideerd en alleen niet-lege cellen vervangen de eigen comments; comments van anderen en Plan/Progress blijven staan. Prio is per focuspunt gedeeld opgeslagen als —/goud/zilver/brons; de Other 1–3-labels zijn per atleet door iedere bevoegde coach aanpasbaar. Met de Athlete setting `See desired improvement points` krijgt een atleet een beperkte eigen weergave met alleen focuspunten, prioriteit en Comments athletes; die athlete-comments zijn in het coachoverzicht zichtbaar.

- `Extended edit rights` geeft een atleet toegang tot toekomstige AYC-trainingen en lege dagdelen. `Can change base planning` staat daar los van en geeft alleen toegang tot de eigen Base Planning.
- Atleten zien in de Year Planner uitsluitend hun eigen atletenrij en whereabouts; coachrijen zijn alleen zichtbaar in de coachweergave.
- Athlete settings bevat naast `See session km` nu `See session zones`. De AYC kan per sessie een zwart `T`-getal en kleurpillen met alleen kilometers op 0,1 km tonen; de weektotalen gebruiken dezelfde `T`-notatie zonder `km`-label.
- De tab in Athlete Input heet `Zones. HR, Speed` en gebruikt binnen de tab `Current times`. De trainer kan HR-invoer en snelheidsondersteuning naast de zone-invoer beheren.
- De Flex Planner en AYC herkennen `TM` en andere T-labels alleen als losse tempo-aanduidingen. Tekst zoals `ritme` levert daardoor geen onterechte TM-kilometers meer op.

- Trainers kunnen eigen gegevens bekijken of expliciet als een toegankelijke coach kijken. Die toegang is niet transitief; view-only blijft server-side read-only.
- Atleten zien uitsluitend zichzelf in AYC, settings, races, evaluaties en, waar ingesteld, Year Planner.
- Flex Planner toont de effectieve, gepersonaliseerde planning. Het verwijderen van een flex-override onderdrukt een basistraining correct.
- Coach Settings bevat `See session km`; indien ingeschakeld tonen Flex Planner en DCO Training hetzelfde sessietotaal als AYC, met `T`-notatie zonder `km` en zonder Alternative-kilometers.
- Polar A/B- en Garmin C-trainingen bewaren de werkelijke meters en seconden uit de horlogeanalyse. Daardoor rekenen AYC, Flex Planner, DCO en weektotalen deze slots niet opnieuw om vanuit geplande zone-snelheden; de zichtbare trainingstekst toont alleen de bestaande min/km-notatie.
- Een gewone handmatige AYC-bewerking van een eerder met Polar A/B of Garmin C opgeslagen training wist de oude werkelijke lapbelasting en maakt de persoonlijke override weer een geplande training. Zo volgen km-totalen na het wijzigen van WU/Main/CD weer de ingevoerde tekst.
- Bij zo'n AYC-bewerking wordt ook een bestaand Watch-slot in het Flex Planner-plan gebruikt wanneer de kalendercel nog naar het onderliggende bronplan verwijst. Daarmee komen de gewijzigde tekst en het opnieuw berekende km-totaal niet meer in een los, onzichtbaar slot terecht.
- Ook oudere gedeelde Watch-bronslots worden bij een AYC-bewerking niet meer als actuele totalen gebruikt: er wordt dan een persoonlijke geplande override aangemaakt, zodat een extra WU/CD/Main-afstand niet tegen de oude Watch-afstand wordt verrekend.
- Bij het bewerken van een Polar A/B- of Garmin C-training vraagt een wijziging van Main eerst om bevestiging: `Are you sure? This might give an incorrect km count!`; WU, CD, Sprint en Alternative blijven zonder deze waarschuwing bewerkbaar.
- Bij zo'n wijziging van alleen WU, CD, Sprint of Alternative blijven de gemeten Main-laps en hun werkelijke tijden behouden. De aangepaste niet-Main-onderdelen worden opnieuw uit hun tekst berekend; alleen de gemeten Main-laps blijven leidend voor het horlogetotaal.
- De weergegeven werkelijke Watch-segmenten tonen repduur én min/km. Korte herstel-laps die door de horlogeanalyse in dezelfde CORE-reeks zijn geplaatst worden uit die weergave gehouden; ze blijven wel beschikbaar voor de afstandsberekening.
- Bij meerdere korte Main-reeksen in dezelfde CORE-groep worden de werkelijke tijd- en tempo-indicaties per pill gefilterd op herhalingsafstand en zone, en begrensd op het geplande aantal herhalingen. Daardoor vervuilen herstel-laps de indicatie niet en tellen 200 m- en 150 m-reeksen niet bij elkaar op. Dit verandert de km-totalen niet.
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
- De whereabouts-dots in AYC en Flex Planner zijn beperkt tot ranges die aan die specifieke atleet zijn gekoppeld; coach- en basisplanranges lekken niet naar alle geselecteerde atleten.
- De Year Planner heeft naast de atleetselector een inklapbare coachselector. Iedere toegankelijke coach heeft een eigen whereabouts-rij; view-only coaches blijven strikt alleen-lezen.
- Trainers kunnen in de Year Planner per gekozen Trainer Planning-groep direct onder `All` een eigen `Basis - groepsnaam`-rij selecteren. Basisgegevens van verschillende groepen blijven gescheiden.
- Per atleet zijn Year Planner Training en Whereabouts afzonderlijk zichtbaar te maken. De atleetweergave is alleen-lezen en de legenda volgt de toegestane lagen.
- Base Planning gebruikt handmatig instelbare, aaneengesloten datumblokken. De oude onderliggende Save/Cancel-knoppen zijn verwijderd; wijzigingen blijven op de actieve tab na opslaan.
- Mobiele AYC heeft Open-knoppen, AM/PM-evaluaties, week reports, daily vitals en een popup voor niet-ingevulde evaluaties van de afgelopen zes dagen. De huidige dag en oudere trainingen tellen niet mee. De daily-vitals-popup staat buiten de AYC/team-stackingcontext, slaat mobiel zonder paginareload op en ruimt daarna de Bootstrap-backdrop en modalstatus op, zodat Safari/iOS niet in een onklikbare overlay blijft hangen.
- Mobiele evaluatiecommentaren ondersteunen Nederlandse spraak-naar-tekst. Herkenningsresultaten worden per resultaatindex verwerkt om dubbele of drievoudige tekst te voorkomen.
- Evaluations ondersteunt coachvragenlijsten met gewone en matrixvragen, kopiëren vanuit eigen lijsten en van coaches met editrechten, verwijderen, inklapbare lijsten en ingevulde antwoorden per atleet. Kopiëren laat het origineel en antwoorden intact. `Active` en doelgroep zijn afzonderlijk instelbaar; iedere lijst heeft de keuze alle atleten of geselecteerde losse atleten. Titel, status en doelgroep zijn achteraf bewerkbaar; wijzigingen aan vragen zelf zijn voorlopig uitgesloten om eerder ingediende antwoorden eenduidig te houden. Het aanpassen van de doelgroep wist antwoorden niet, maar uitgesloten atleten kunnen het formulier niet opnieuw openen. De doelgroep wordt ook server-side afgedwongen. De module is per coach aan- en uit te zetten in Coach Settings en geldt dan ook voor diens atleten. Evaluation sharing kan Training-, Week- en Vitals-evaluaties per coach delen met coaches die view- of edit-toegang hebben. Zolang delen niet expliciet wordt aangezet, blijft de bestaande zichtbaarheid voor coaches met toegang behouden; na inschakelen bepaalt de matrix de zichtbaarheid per type.
- Coach Tools in MiLa bevat Track Timer voor 100–1600 m, doeltijdvisualisatie, drie-atletenmodus en tussentijden.
- Parser ondersteunt T1 en T6, progressieve Z/T-ranges met tussenliggende labels, compoundblokken en pauzenotatie `p`/`sp`.
- De Main-parser splitst ook een koppelteken tussen zelfstandige afstandsblokken (zoals `3x2000m ... - 2x1000m ...`), maar laat koppeltekens binnen samengestelde blokken tussen haakjes intact.
- Polar v3/v4-integratie en reconstructies bestaan. Polar v4-samples worden nu naast laps opgehaald en aan de tijd/afstand-matcher doorgegeven; complexe workoutmatching blijft een actief ontwikkelgebied.

## Recente onderhoudsafspraken

- Nieuwe Mila-chats starten met `AGENTS.md` en `docs/project/START_HERE.md`; `CODEX_CONTEXT.md` is alleen nog een verwijzing.
- Voor eenmalige accountimports bestaan generieke Django-management commands. Passwords en database-URLs horen nooit in Git.

## Bekende aandachtspunten

- Settings is een werkende coachdashboardtegel met onder meer Planning Camps; Stats en Polar houden hun under-development-label.
- Staff Team Overview vervangt Daily Coach Overview Other. De startpagina toont de toegankelijke atleten en de keuzes Vitals en Information Quality; elk opent het bestaande overzicht voor alle toegankelijke atleten. Info Quality toont per atleet het percentage geëvalueerde trainingen in de laatste tien kalenderdagen inclusief vandaag. De AM-sessie van vandaag telt vanaf 12:00 lokale tijd mee en de PM-sessie vanaf 21:00. Hover op het percentage toont de aantallen open en geëvalueerd; zonder trainingen staat er `NA`. Percentages zijn rood onder 60%, oranje vanaf 60%, lichtgroen vanaf 80% en donkergroen vanaf 95%; 0% is zwart met rode tekst. Vitals toont gemiddelden over de laatste veertien kalenderdagen bij minimaal drie waarden en bevat ook HR zones met Z1–Z5 per atleet; Show NA staat uit.
- In `View as coach` gebruikt Info Quality ook de Flex Planner-overrides van die actieve coach. Als trainingsevaluaties voor de trainer niet zichtbaar zijn of voor de atleet uitstaan, toont de kolom geen evaluatiegegevens zodat sessies en evaluatiestatus niet onbedoeld worden onthuld.
- Stats is bewust eenvoudig en nog in ontwikkeling.
- Polar/watch suggestions, vooral automatische workoutmatching zonder handmatige laps, hebben verdere testgevallen en verfijning nodig.
- E-mail-, WhatsApp- of pushreminders voor openstaande evaluaties zijn nog niet gebouwd; de huidige herinnering is alleen de AYC-popup.

## Laatste overdracht — 29 oktober 2026

- Ingevulde formulieren `Evaluatie seizoen 2025-2026` van Honoré Hoedt hebben Coach comment/Plan per antwoordregel: coaches kunnen bewerken, de betreffende atleet kan deze bij de eigen antwoorden lezen. Migratie `0129_evaluationresponse_coach_feedback` voegt aparte lege JSON-opslag toe zonder bestaande antwoorden te wijzigen. De productievragenlijst staat niet in de lokale database; de functie wordt begrensd op genormaliseerde coachnaam en formuliertitel. Zes gerichte evaluatietests slagen, inclusief behoud van antwoorden/indieningsdatum en edit-/view-onlyrechten. De bredere TrackTimerTests-run bevat twee niet-gerelateerde bestaande dashboardlabelasserties die falen.

- Race Calendar bewaart bij Save distances en overige popupterugkeren het gekozen kalenderjaar. Bij Indoor 2026/27 sprong een bewerking van een wedstrijd in januari 2027 eerder naar Indoor 2027/28 doordat het wedstrijdjaar als terugkeerjaar werd gebruikt.

- Aanvullende dropdownreparatie: de select zelf start ook geen schilderactie meer. Een open native optiemenu kan mouseenter/mouseup naar onderliggende kalendercellen sturen; die leidden met de achtergebleven schilderstatus alsnog tot opslaan en dichtklappen. Randgrepen blijven de manier om periodisatieblokken te verlengen/verkorten.

- Het openen van de periodisatiedropdown veroorzaakt geen opslagactie meer. Een gebubbelde mousedown markeerde het startvak onterecht als gewijzigd; de nieuwe opslagblokkade sloot daardoor het keuzemenu voordat een fase gekozen kon worden. Opslaan gebeurt nu na een echte keuze of schilderactie.

- Gedeeltelijk opgeslagen jaarrijen in Year Planner zijn hersteld: de eerdere stroom verstuurde honderden parallelle dagverzoeken. Periodisatie gebruikt nu een atomair batchendpoint met bulkdatabasebewerkingen. Rij-plakken verandert de weergave pas na bevestiging; tijdens opslaan wordt nieuwe bediening tijdelijk geblokkeerd. Wedstrijddagen en rechten blijven beschermd.

- Een periodisatiedag naar `—` wijzigen verwijdert nu ook direct de kleur en sleepgrepen van een leeg blok. Een lege dropdownwaarde viel eerder onterecht terug op de oude fasekleur; de lege keuze blijft nu leidend.

- Meerdaagse races gebruiken de optionele inclusieve einddatum uit migratie `0127_raceevent_end_date`. Add race toont standaard één datum; `Multiple days` opent `Until`. Race Calendar en Year Planner ondersteunen overlap met de zichtbare periode en blokkeren periodisatie op iedere geselecteerde wedstrijddag. Neem migratie 0127 mee bij de Render-deploy.

- Race Calendar heeft Race Type met omlijningen volgens de Year Planner-legenda. Migratie `0126_raceevent_race_type` geeft alle bestaande races Race Other en moet bij de Render-deploy worden uitgevoerd. De dropdown onder Manage distances slaat automatisch op; atleten kunnen het gedeelde type alleen lezen.

- De HTTP 500 in Flex Planner is lokaal gereproduceerd en hersteld: het weekclipboard leest nu de al geordende segmenten van virtuele weergaveslots via `all()`. Een paginatest met gevulde AM- en PM-trainingen controleert dat de pagina opent en de weekinhoud bevat. De dynamische rijhoogte met minimum 48 px blijft behouden. De live Render-status na de rollback is nog niet bevestigd.
- Validatie van deze reparatie: alle 104 tests in `FlexPlannerAltTotalsTests` en `SlotModalSaveTests` slagen, evenals `manage.py check`.

- Flex Planner week kopiëren/plakken is afgerond in commit `fcb0b49`. De acties `c` en `p` staan per atleet/week; kopiëren gebruikt de zichtbare week, plakken blijft binnen dezelfde atleet en laat racecellen ongemoeid. Cel- en rijhoogtes groeien mee met de trainingsinhoud.
- De wijziging is lokaal gecontroleerd met `manage.py check`, template-compilatie en 12 gerichte Flex Planner-tests.
- De actuele Render-status moet na de door de eigenaar gemelde HTTP 500/rollback apart worden gecontroleerd. Een Render-dashboard-rollback kan autodeploy uitschakelen; bevestig daarom eerst de live deploy voordat nieuwe wijzigingen worden gepusht.

## Afgerond in main, 11–12 oktober 2026

- Polar Integration bevat A/B/C/D: ruwe rondes, samples, tempoverwerking en één overzicht met kilometers per tempozone en HR-zone.
- Type D reproduceert de gecontroleerde voorbeeldtraining: tempo Z1 7,6 km / Z3 5,4 km; HR met de besproken geschatte grenzen 3,8 / 3,9 / 3,6 / 1,7 / 0,0 km. Dit voorbeeld is een rekentest, geen algemeen aanbevolen HR-profiel.
- Overlappende Polar-pauzemarkeringen tijdens aantoonbare beweging verbergen de loopdata niet meer. Regels uit de aangeleverde JSON zijn lokaal gecontroleerd; persoonsgegevens zijn niet als testfixture gecommit.
- Type D heeft eigen opgeslagen HR-grenzen per atleet en migratie `0096_polar_analysis_settings`. AI-toelichting gebruikt de bestaande API-configuratie en heeft een zichtbare terugval als die ontbreekt.
- Polar-knoppen hebben witte tekst op gevulde achtergronden. AYC-, Flex- en Trainer Planning-popups staan buiten de teambekleding; ook de AYC-`today`-popup wordt direct onder `document.body` geplaatst zodat de Bootstrap-backdrop de dialoog niet afdekt.
- DCO Other heeft werkende Vitals, behoud van het geopende blok en Show NA-filter.
- Laatste applicatiecommit vóór deze documentatieronde: `fcb0b49`. De documentatie-overdracht wordt op `main` bijgewerkt; de daadwerkelijke Render-deploystatus moet na een eventuele rollback nog worden bevestigd.

## Validatie en resterende beperkingen

- AYC-popupbewerkingen slaan nu op in hetzelfde actieve Flex Planner-plan waaruit de popup leest; een regressietest controleert dat de wijziging na opslaan zichtbaar is in zowel AYC als Flex Planner voor atleet en coach.

- Meeting requests zijn toegevoegd aan Athlete Settings en DCO Other Info Quality. Nieuwe aanvragen melden zich via een hoofdcoach-popup; de status/leeftijd blijft zichtbaar tot de atleet annuleert.

- Flex Planner toont een gekopieerde/persoonlijke atleettraining ook wanneer Base Planning voor dat dagdeel `Rest` bevat. De gedeelde trainertraining blijft op zo'n dagdeel verborgen; een expliciete persoonlijke override heeft voorrang.
- De Flex-popup volgt dezelfde bronkeuze als de cel: individuele Base Planning en expliciete Rest gaan vóór een gekoppeld trainerplan; datumblokken volgen de laatste `effective_from`.
- De AYC-trainingspopup laat een individueel Base Planning-slot niet meer overschrijven door een gedeeld Flex-basisslot. Een bestaande persoonlijke Flex-override blijft zichtbaar en bewerkbaar.

- De Flex/Base Planning-reparatie is met tien gerichte regressietests en `manage.py check` gevalideerd. In de bredere `SlotModalSaveTests`-reeks slagen 59 van 60 tests; alleen `test_shared_coach_can_save_vitals_for_accessible_athlete` faalt nog met HTTP 403 in plaats van 204. Dit betreft de aparte vitals-rechtenroute, niet de Flex-weergave.
- De 46 gerichte Polar-tests slaagden, inclusief Type D-berekening, HR-opslag en rechten. Django-check en migratiecontrole slaagden; beide zoneverdelingen zijn tegen de aangeleverde JSON gecontroleerd.
- Witte Polar-knoptekst en Type D zijn op 390/1440 px gecontroleerd. De popupblokkade is met de echte Flex/Trainer-openers gereproduceerd en opgelost voor AM/PM, lege/bestaande invoer en klikbaarheid van Save/Close. Vier gerichte Django-modaltests slaagden.
- C blijft een eerste versie: tempopieken rond stops en hervatten zijn niet altijd betrouwbaar te corrigeren. Type D gebruikt daarom bij voorkeur rondegemiddelden; zonder bruikbare rondes blijft de sampleanalyse conservatief.
- De HR-preset is geschat en moet per atleet beoordeeld worden. Een hoogste gemeten trainingshartslag is niet automatisch HRmax.
- Type D staat los van planning en evaluatie: automatische overname naar AYC is niet gebouwd. AI-uitvoer is een interpretatie, geen vastgestelde uitvoering of medische drempelmeting.

## Garmin — 31 oktober 2026

Trainer-only `Allow Garmin Connection`, de eigen dashboardtegel, OAuth2 PKCE, optionele AI-toestemming en `Withdraw AI permission` zijn toegevoegd. Intrekken blokkeert Garmin-AI en ontkoppelt; trainer uitschakelen doet hetzelfde. Garmin C valt zonder toestemming terug op vaste herkenning. De privacyverklaring beschrijft deze concrete werking. Render heeft de Garmin-appsleutels nodig voordat echt verbinden beschikbaar is. Activity Summary Push-ontvangst is nu geïmplementeerd; externe activering en een echte Garmin-push moeten nog worden bevestigd.

Validatie Garmin: 28 gerichte Garmin/Oura-tests geslaagd; `manage.py check`, migratiecontrole en lokale migratie geslaagd. De uitgebreidere `core.tests_polar_raw`-controle heeft vier bestaande fouten door SimpleNamespace-gebruikers in de toegangscontrole; alle vier zijn ook met de ongewijzigde HEAD-versie van polar_raw.py gereproduceerd. Overige Polar-raw-tests slagen.

## Garmin-ontvangst — 31 oktober 2026

De minimale Push-ontvanger, stabiele user-ID-koppeling en gecombineerde lijst (datum/afstand) zijn gebouwd. Migratie 0131 is vereist. De privé-URL staat voor beheerders op Garmin Connections onder Garmin receiving setup. De huidige API Tools-pagina was niet toegankelijk via computerbediening; de gebruiker moet de URL daar voor Activity Summaries/Push invullen en een activiteit synchroniseren. De automatische stroom is pas end-to-end bevestigd na die echte levering; synthetische tests bewaken nu identiteit, toegangsrechten, ongeldige batches, herhalingen en ontkoppeling.

Garmin C ziet vanaf migratie 0132 ook ontvangen activiteiten. Automatische Activities-ontvangst is op 31 oktober met een echte testactiviteit bevestigd door de eigenaar. Voor C-lapherkenning moet de eigenaar nu ook `ACTIVITY – Activity Details` inschakelen met dezelfde URL; dit deel is met synthetische push-/C-integratietests gecontroleerd en wacht nog op echte detailaanlevering.

Last active in MiLa is toegevoegd als kolom in Information Quality. Migratie 0133 voegt een leeg tijdstempelveld toe; AthleteLastActiveMiddleware registreert vanaf de uitrol interactief atleetgebruik. Er is geen historische backfill.

Migratie 0134 voegt RaceAttendance toe zonder bestaande RaceEntry-selecties te wijzigen. Attend verschijnt zonder afstand in Year Planner, AYC en Flex. AYC toont nu ook rechtstreeks gekoppelde afstandselecties onafhankelijk van het gekozen bronplan.

1 november: eigenaar toont echte Garmin POST met HTTP 400 terwijl summaries binnenkomen. De specifieke afwijsreden is nog onbekend. Afgewezen pushes loggen voortaan validatiefase, ondersteund berichttype, bytegrootte en uitsluitend bekende veldtypen/aanwezigheid en sample-/lapaantallen; geen inhoud, user-ID, token of ontvangst-URL. Een nieuwe ActivityDetail-resend na deploy is nodig voor de concrete diagnose.

Garmin-detailbatchfout gereproduceerd met door eigenaar aangeleverde Data Viewer-uitvoer: eerste activiteit mist distanceInMeters, waarna de ontvanger ook de overige geldige activiteiten afwees. Ontbrekende afstand wordt nu als ontvangen details zonder afstand/lapanalyse bewaard; de overige activiteiten worden verwerkt. Bestaande summary-afstanden worden niet gewist. De aangeleverde persoonsgegevens zijn niet in tests of Git opgenomen.

Diagnose tweede Garmin-training: de aangeleverde activiteit met 27 lapmarkeringen wordt lokaal verwerkt tot 26 bruikbare rondes, maar live ontbrak nog de detailsontvangst. Ontvanger logt nu na commit per activiteit een gehashte activity_ref, summary_stored/details_stored/ignored en rondeaantallen. Eigen Garmin-logger op INFO maakt ook succesvolle afleveringen zichtbaar in Render; geen ruwe data of IDs. Root cause van de ontbrekende live-aflevering is nog niet vastgesteld.
# Garmin-diagnostiek — 1 november 2026

Avg HR is toegevoegd vóór Last 15s HR in de klokjespopup. De gemiddelde HR wordt bij nieuwe overnames bewaard in loads/reps/splits en Watch-versie. Tests controleren afzonderlijke HR-gemiddelden, tijdweging bij het 3750m-blok en onbekend blijven bij ontbrekende dekking. De eigenaar doet de visuele controle.

HR-correctie samengevoegd Main-blok: het 3750m-blok na de korte series neemt nu de laatste-15-seconden-HR van zijn laatste bronlap over. De korte 12s-rep behield al correct haar samplegemiddelde; het ontbrekende veld zat bij het samengestelde lange blok. Tests bewaken beide waarden en houden ontbrekende HR onbekend.

Last 15s HR is toegevoegd aan de AYC-klokjespopup voor reps en afstandssplits. Nieuwe Use AM/PM-overnames bewaren de bestaande sampleberekening in loads, afgeleide details en Watch-momentopname. Regressietests bewaken bronberekening, ontbrekende meetdekking, de korte laatste split en behoud bij Watch/Plan-wisselen. Eerdere overnames zonder opgeslagen HR moeten eenmaal opnieuw worden overgenomen om die kolom te vullen; resenden is niet vereist. Visuele controle door de eigenaar.

De duurloopregel is uitgebreid naar 500m-splits. Een anoniem numeriek voorbeeld met tien gelijkmatige 500m-laps plus 22 m wordt één blok; de klokjespopup behoudt alle elf splits. Een terugkerend snel/langzaam-patroon blijft uitgesloten van de duurloopregel. Visuele controle door de eigenaar.

De klokjespopup van een duurloop toont nu kilometerlaps en het laatste korte restant in plaats van alleen één totaalregel. Het kalenderblok en gemeten totalen blijven gelijk. Regressietests bewaken 27 kilometerlaps plus 300 m, behoud van de trage stopkilometers en omrekening van GPS-afwijkingen naar kilometertijd. De eigenaar doet de visuele controle.

Duurloopherkenning: gelijke kilometerlaps met enkele losse vertragingen worden als doorlopend blok voorgesteld; herhaalde timerpauzes, duidelijke herstelpatronen en FIT-intensity bewaken intervalgevallen. Timer-/bewegings-/kloktellers uit nieuwe ActivityDetails worden per lap bewaard en doorgegeven aan de herkenning en AI. Ontbrekende informatie blijft onbekend. FIT-lap_trigger en intensity zijn apart gemapt. De synthetische duurloop van 27,3 km met twee trage kilometers verschijnt als één blok, ook na overname met opgetelde duur. Geen migratie nodig. De bredere Polar-raw-suite heeft nog de vier eerder gedocumenteerde SimpleNamespace-toegangsfouten; de overige 24 tests slagen.

Reptijdcorrectie na Use AM/PM: herhaalde reps tonen tijd omgerekend naar de herkende afstand (bijvoorbeeld 12 s / 62,95 m wordt 19,06 s / 100 m). Ruwe laps en loadtotalen blijven ongewijzigd; gemeten seconden blijven apart in de afgeleide repgegevens bewaard. Het doorlopende blok houdt zijn opgetelde gemeten duur. Ook bestaande Watch-trainingen en het klokje bij een actieve Plan-versie worden uit de bewaarde ruwe Watch-data berekend. 23 gerichte tests en manage.py check slagen.

Watch/Plan-keuze: `p/w` staat nu naast het klokje en opent een aparte keuzepopup. De actieve trainingsversie bepaalt de kalender en totalen; de opgeslagen Watch-onderdelen, loads en reptijden blijven behouden bij kiezen van Plan. Het klokje blijft ook bij Plan beschikbaar. Migratie 0136 voegt de Watch-momentopname toe; bestaande Watch-slots met een planmomentopname worden bij de eerste wissel opgevangen. Twaalf gerichte tests slagen, waaronder herhaald beide kanten op wisselen voor AM en PM en behoud van klokresultaten. Django-check en migratiecontrole slagen. Visuele controle doet de eigenaar.

Use AM/PM bewaart vanaf migratie 0135 het oorspronkelijke plan in een aparte momentopname. De klokjespopup kan dat via `p` herstellen met de bestaande trainingbewerkrechten. AM/PM, herhaalde overnames, lege slots, atleetisolatie en coachrechten zijn getest. De 100 gerichte slot-/Watch-tests en vijf aanvullende snapshottests slagen, evenals manage.py check. Visuele controle wordt op verzoek door de eigenaar uitgevoerd. Eerder overschreven plannen kunnen niet automatisch uit deze nieuwe opslag worden teruggehaald.

Reptijden na Use AM/PM: de korte series en het doorlopende blok krijgen nu hun eigen gemeten laps. Het doorlopende blok toont de opgetelde bloktijd in plaats van de tijd-/temporange van alle Main- en herstellaps. De repdetailweergave wordt bij bestaande opgeslagen Watch-trainingen bij het lezen vernieuwd. Gerichte tests bewaken beide opnamevormen, uitsluiting van herstel/CD en behoud van ruwe loads.

Aanvulling korte series: de beschrijving toont nu ook de zone/het zonebereik van de 100m-werk-laps, afzonderlijk van herstel en het doorlopende blok. Gerichte regressietests bewaken gemengde werkzones, één bekende zone en ontbrekende zonegegevens.

De eigenaar heeft succesvolle detailontvangst en Garmin C-weergave bevestigd voor de drie gemelde activiteiten, inclusief 26 bruikbare laps van de hoofdtraining. Het oorspronkelijke afleverprobleem is voor deze activiteiten hersteld; welke herhaalpoging ze afleverde is niet vastgesteld. Vervolgwijziging: korte werk/herstelseries plus een doorlopend blok en eventueel CD worden structureel herkend vóór de AI/oudere dominante-afstandregels. Anonieme numerieke regressievoorbeelden bewaken beide opnamevormen en behoud van gemeten laps/loadtotalen. De bredere Polar-raw-suite houdt de vier reeds gedocumenteerde SimpleNamespace-fouten in de toegangscontrole; de overige 24 tests slagen.

Het coachoverzicht toont nu ontvangst en detailontvangst per activiteit plus bruikbare laps; FIT-uploads zijn afzonderlijk gelabeld. Dit maakt ontbrekende detailaflevering te onderscheiden van ontvangen details zonder bruikbare laps. De oorzaak van de ontbrekende details van de gemelde hoofdtraining is hiermee nog niet vastgesteld; deze wijziging verandert de ontvangst/opslag niet.

## Information Quality — gemiddelde

ALL-rij toegevoegd boven de atleten, als ongewogen gemiddelde van de getoonde percentages per kolom, afgerond op hele procenten. NA/afgeschermde waarden worden overgeslagen; nul telt mee. Twee gerichte paginatests en manage.py check slagen. Visuele controle door de eigenaar.

## Automatische Oura-import — 1 november 2026

Gebouwd met opt-in in Athlete Settings, automatische opslag van de eigen apparaattijdzone en een Render-achtergrondcontrole. Het lokale schema is 06:30–08:00 iedere tien minuten en daarbuiten ieder heel uur. Readiness moet numeriek geldig zijn; uitsluitend lege vitalsvelden worden gevuld met de bestaande importregels. De schrijver is gedeeld met de handmatige import en vergrendelt de atleet om gelijktijdige writes te serialiseren. Databaseclaims voorkomen dubbele automatische pulls; toestemming, koppeling en opt-in worden vóór schrijven opnieuw gecontroleerd. De tijdzone-update en achtergrondimport veranderen Last active niet. Migratie 0137 lokaal uitgevoerd; Django-check en migratiecontrole slagen. Oura- en schematests slagen. De achtergrondthread start bij Render-WSGI; continue uitvoering vereist een niet-slapende webservice. Live automatische import moet na deploy en opt-in nog worden bevestigd. De eigenaar doet de visuele controle.

Garmin C ondersteunt nu samenvoegen van twee of drie afzonderlijke opnames via expliciete WU/Main/CD-rollen, met een nieuwe preview en de bestaande Use AM/PM- en Watch/Plan-opslag. Gerichte combinatie-, Main-rep-, Garmin C- en Watch/Plan-tests plus manage.py check zijn uitgevoerd. De eigenaar controleert de interface visueel.

Garmin Combine: het benodigde script wordt onafhankelijk van de Oura-import geladen. Een echte AYC-paginatest zonder Oura bewaakt dat de functie beschikbaar blijft.

Render-timeout bij het openen van Garmin C op 1 november: traceback wachtte tijdens URL-initialisatie op de modulelock van requests, terwijl Oura kort na de WSGI-start achtergrondimports uitvoert. WSGI initialiseert nu de URL/view-modules vóór het starten van de poller; een afzonderlijk Python-proces test de koude importvolgorde. Sara’s drie aangeleverde activiteiten zijn lokaal daarnaast zonder externe AI-aanroep verwerkt (3/26/3 laps).

Garmin Combine wordt nu in hetzelfde paginascript als de Garmin-bediening opgenomen, zonder afzonderlijke static-aanvraag. De AYC-regressietest voert de daadwerkelijk gerenderde functie uit in JavaScript; alleen een aanwezige script-URL gold eerder ten onrechte als voldoende controle.

Garmin C: live diagnose van de opname met 39 laps toonde dat meerdere oorspronkelijke 500m-groepen pas na de half-lapcontrole tot 24×500m werden samengevoegd. Die uitkomst wordt nu opnieuw tegen de gemeten work/work/recovery-structuur gecontroleerd, zodat 12×1000m ontstaat. Het klokje verwerkt de halve laps samen inclusief tijd en HR. Regressie gebruikt de daadwerkelijk aangetroffen meerblokbeschrijving; ook een misleidende herstel-lap tussen de helften wordt getest.

Garmin C: lang blok vóór korte reps kan niet langer stil verdwijnen uit een uitsluitend korte-repbeschrijving. Afwijkende WU/CD-classificatie kon bovendien tekstuele WU/CD dubbel bovenop de gemeten lapafstand laten tellen; de AYC-totalen sluiten nu de gemeten grenslaps aan, ook voor oudere opgeslagen Watch-loads. Regressies controleren behoud van het lange blok, ongewijzigde zones en exact eenmaal tellen van alle gemeten meters.

Gemengde Garmin-opname met 29 laps: een reeks kilometer-aanlooplaps maskeerde de volgende korte versnellingen en afwisselende 200/150m-reps. Nieuwe relatieve work/recovery-herkenning bewaart alle elf korte werk-laps, aanloop en uitloop. Regressies bewaken de screenshotreeks, uitsluiting van doorlopend lopen, geen externe AI bij sterke structuur en geen verwarring tussen gelijk lange werk-/herstel-laps in het klokje.

Korte gemengde Garmin-trainingen zijn compacter: afstandsgroepen vervangen losse segmenten per rep, met behoud van de klokvolgorde. Josefine-regressie bewaakt 2400m + 4×50m + 6×200m + 6×150m en 1850m CD, inclusief de laatste snelle rep vóór CD. Djamell behoudt zijn gemeten vijf 200m- en vier 150m-reps en twee versnellingen; de afzonderlijke lange stop blijft buiten de werkreps.

Watch-terugwandelen telt niet langer als Z1/hardloopafstand: gemeten laptempo strikt trager dan 10:00/km wordt uitgesloten van AYC-sessie/week- en gedeelde trainingsstatistieken. Bestaande Watch-overname hoeft niet opnieuw geïmporteerd. Stats-cacheversie vernieuwd. Regressies bewaken de exacte grens, andere zones, ongewijzigde ruwe data en nul kilometers zonder planterugval wanneer alle laps wandelen zijn.

Wojtek-regressie: losse opname met twaalf werk/herstelparen wordt 5×200m + 7×150m, inclusief 174.91m als 150m. De uitbreiding is beperkt tot complete afwisselende Main-opnames zonder aanloop; Josefine- en Djamell-regressies blijven slagen.

Nathan-regressie: vijf ongeveer acht minuten durende werkblokken, ieder opgesplitst in 1000+1000+rest met circa 90s herstel, worden als 5×8′ beschreven. Klokreps voegen de drie werklaps samen. Regressies bewaken 480/483/477/482/483s, exacte gemeten sessiemeters onafhankelijk van gewijzigde zonesnelheden en afwijzen van ongelijke tijdsblokken of ontbrekend herstel. Eerdere korte-repherkenning blijft getest.

Nathan-uitloop met twee kilometerlaps en een restlap van 155m viel onder de oude minimumgrens van drie volledige autolaps. Herkenning accepteert nu twee volledige autolaps plus restant; nominale beschrijving 2150m Z1, drie splits en 2162.83m gemeten blijven behouden. Expliciete herstel-/pauzefeiten worden nog steeds gecontroleerd.

Garmin-opname van circa 1480m met twee laps was onterecht niet combineerbaar doordat de UI ook voor WU/CD een Main-beschrijving vereiste. WU/CD vereisen nu uitsluitend gemeten laps en bruikbare totalen; de gegenereerde Main-eis geldt alleen voor de Main-rol. Combinatietests dekken onbekende structuur als WU/CD en weigering als Main.

Garmin D toegevoegd als afzonderlijk model met dezelfde C-structuur en gemeten kilometers, maar HR-zonecontrole vanaf 400m of 50s. Nathan-regressie maakt 5×8′ Z2 van de C-zone Z2>Z3 op basis van de eind-HR per volledig blok. Grenswaarden, ontbrekende data, korte reps, meetafstand, toegang en Watch/Plan-rondegang zijn getest. Migratie 0138 voegt watch_d als bronkeuze toe.

WU/CD-weergave in Garmin C én D vereenvoudigd tot één afstandgewogen gemiddeld tempo; geen deel-tijdranges of deel-temporanges meer in de kalenderpillen. Dit geldt direct voor bestaande overnames. De blijvende afspraak dat algemene Garmin-wijzigingen beide modellen volgen staat in AGENTS.md.

Garmin C/D-weergave afgestemd op trainingsbasis: tijdsblokken tonen alleen tempo, afstandsblokken reptijd plus tempo. Dit werkt bij bestaande opgeslagen Watch-trainingen door de pagina opnieuw te laden. Regressies testen minuten, seconden en afstandsreps in beide modellen.

Staff Team Overview bundelt Sleep length, Sleep quality, Morning HR en HRV in één Daily vitals-tab met gemiddelde en low–high-range per cel. HR zones, veertiendaags venster, drie-metingenvoorwaarde en privacyfilters blijven behouden. Tests dekken alle vier kolommen, ranges, oude links, Show NA, nulwaarden en uitsluiting van een oude uitschieter.

Camp details heeft Comments na Accommodation, met automatische opslag en bestaande deelnemerrechten en Copy/Paste. Migratie 0139 voegt camp_comments toe aan de whereabout. Gerichte coach-/atleetopslagtests en toegangsregressie slagen.

Kane-regressie: lange herstelpauze liet de oorspronkelijke herkenning na twee werkblokken stoppen en verborg een derde circa 3000m-lap en twee 1000m-laps. Prefixafkapping is geblokkeerd. Voor deze complete herhaalde werk/herstelreeks verschijnen nu Distance (3×3000m + 2×1000m) en Time (3×10′ + 2×3′), beide met alle meetgegevens en C/D-zoneverwerking. Tests bewaken beide previews, vijf klokreps en identieke meetkilometers.

Camp details heeft een doorlopende rijtelling voor alle deelnemers, inclusief coaches. De nummers worden na iedere sortering opnieuw vanaf 1 bepaald; geen model- of identiteitswijziging.


Garmin C/D End HR is aangepast naar laatste 10% van de gemeten repduur (minimaal 15s, onder 15s Avg HR). Volledige samengestelde reps tellen als één tijdvenster. Gerichte regressies dekken venstergrenzen, meerdere laps, korte reps, ontbrekende oudere samples en D-zonecontrole; Polar-weergave blijft ongewijzigd.


Stats-atleetgrafiek toont nu gestapelde weekafstanden per zone met Z1 onderaan, zonekleuren, legenda en tooltips. Regressie bewaakt gemeten Watch-kilometers, uitgesloten wandelen, zonevolgorde en gelijke som van stapelhoogtes en totaal.


Year Planner: groeps-Basis-periodisering kan weer worden uitgerekt/ingekort en in batches opgeslagen. De lockqueries sorteren expliciet op datum, zodat de nullable atleetnaam uit de standaardmodelsortering geen outer join veroorzaakt die PostgreSQL bij SELECT FOR UPDATE weigert. Regressie controleert Basis-opslag, verlengen, inkorten, gescheiden atleetdata en SQL zonder nullable atleetjoin.


DCO-meerzonepillen: de Flex-kleurroutine is verplaatst naar een gedeelde templatepartial en wordt nu ook in DCO toegepast. Regressies bewaken Robins z2>z3-voorbeeld, omgekeerde ranges, samengestelde zones, T-ranges en éénzonepillen.


Mob/Tech-foto’s toegevoegd in de trainingspopup, met uploadpreview, verwijderen bij Save en privé thumbnails/groot openen. Opslag en verkleinen via Pillow/database; migratie 0140 vereist. Tests dekken upload, invalid files, aantallimiet, toegangsrechten, AYC-persoonlijke kopie, toekomstige bewerkgrens, foto zonder tekst, dagkopie en behoud bij tekstwijziging.


Mob/Tech-fotolinks zijn nu gekoppeld aan de stabiele TrainingSlot-id. AYC maakt segmenten bij opslaan opnieuw aan; oude segmentlinks konden daardoor 404 geven. Persoonlijke foto’s volgen coachtoegang tot de atleet, ook bij een persoonlijk plan met een andere eigenaar. Tests dekken herhaald opslaan met dezelfde foto-URL, thumbnails en deze toegangsgrens.


Garmin C/D missen geen 300m-reps meer bij volledige afwisselende 400/300m-opnames met herstel. Een aparte middelgrote-repregel houdt beide afstandsgroepen en hun nominale lapkoppeling vast; de bestaande korte-rep- en lange-intervalregels blijven behouden. 55 gerichte structuur-, D- en pushtests slagen, inclusief twaalf klokreps in bronvolgorde en negatieve patrooncontroles.


De exacte 5480m/32:32-regressie bevat zes 400m-reps, zeven 300m-reps, een gesplitst herstel voor de laatste rep en geen eindherstel. De middelgrote-repregel gebruikt 1.4 als relatieve snelheidsgrens (de gemeten hersteljogs vielen net onder 1.5). Alle dertien werkreps blijven in C/D-klokvolgorde staan; er wordt geen ontbrekende 400m-rep bij verzonnen.


Klokfix voor gemengde Garmin-reps: de twee Z4-laps binnen 7×300m Z3>Z5 werden ten onrechte overgeslagen doordat alleen bereikseindpunten werden gematcht. Volledige zonebereiken en expliciete nominale repidentiteit zijn hersteld voor C/D; bestaande Watch-trainingen profiteren bij herladen zonder opnieuw importeren.


AI-herkenning uitgebreid met gevalideerde bronlapgroepen voor Garmin C/D. De 18-lap-regressie ondersteunt 2×8′ + 4×4′ ondanks een eerste rep over drie laps, een 4:13-rep en een lange voorafgaande stop. Distance/Time, samengestelde End HR en gemeten totalen zijn getest met gemockte AI-output; de echte modelrespons is niet op productie aangeroepen. Gerichte regressies: 72 tests, manage.py check en migratiecontrole slagen; geen migratie nodig.


Alternative Z2>Z3 telde volledig als de eerste zone. De actieve tijd wordt nu gelijk verdeeld over alle bereikzones in serverstats/AYC én Flex-browserberekening. Tests dekken het 20′ Z1 // 15×3′ Z2>Z3 // 10′ Z1-voorbeeld, losse segmenten, drie zones, dalende ranges en uitsluiting van loopkilometers.


De 18-laptraining kreeg nog geen minutenkeuze omdat de eerdere uitbreiding van een geldig AI-antwoord afhing. Nu leidt lokale herkenning dezelfde gevalideerde lapgroepen af, waarna de volledige Garmin C- én D-endpointtest zonder AI-toestemming aantoonbaar Distance/Time teruggeeft met 2×8′ Z2 + 4×4′ Z2, WU 2000m en CD 1100m. De eerste rep blijft uit drie laps bestaan; alle bronmeters en seconden blijven identiek.

Garmin C/D: één reeks N×T minuten krijgt nu ook een Time-optie, onafhankelijk van wisselende werkafstanden. Screenshotregressie bewaakt zeven gemeten reps (242, 241, 243, 242, 242, 245, 243s), WU/CD en behoud van alle bronmetingen in C en D. D bewaart de repmetadata per alternatief. Algemene voorbeelden 3×2, 5×6 en 9×10 minuten en negatieve patrooncontroles zijn gedekt. 36 gerichte tests en manage.py check slagen. Geen layoutwijziging; visuele desktop-/mobielcontrole en Render-deploy nog niet geverifieerd.

Garmin C/D, 33-lap gemengde opname: korte-repherkenning stopte na vijf versnellingen en verborg langere Main-series en CD. Herkenning bewaart nu zes versnellingen (laatste heeft 16s overgang), circa 900m tussenlap, 3×800m, 5×500m en circa 1000m CD. Regressie dekt vaste herkenning zonder externe AI, alle vijftien gemeten klokblokken in C/D, ongewijzigde bronmeters en afwijzen van een onvolledige afwijkende serie. 70 gerichte tests en manage.py check slagen. Geen layoutwijziging; visuele mobiele/desktopcontrole en Render-deploy nog niet bevestigd.

Alternative accepteert `+` naast `//` voor losse blokken. Voorbeeld 25'z1 + 3*10' z2 + 25'z1 elliptical levert 50 minuten Z1 en 30 minuten Z2. Opslag voor AM/PM, bestaande gecombineerde teksten, base-slots, stats/AYC en Flex-browserberekening zijn gecontroleerd; haakjes en zonebereiken blijven intact. 20 gerichte Alternative/Flex-tests, 12 Main/Watch-regressies en manage.py check slagen. De echte Flex-JavaScriptfuncties geven voor plus, dubbele slash en gemengde separators dezelfde 80 minuten. Geen layoutwijziging; visuele desktop-/mobielcontrole en Render-deploy niet geverifieerd.

Staff Team Overview: Injury/Issue Overview-tab toegevoegd met vijf statusbolletjes per toegankelijke atleet voor de laatste vijf ingevulde evaluaties (datum/AM-PM, nieuwste rechts). Groen Fit, geel Some issue, rood Serious issue; onbekend/ontbrekend grijs. Trainingsevaluatieprivacy en training_reports_enabled blijven leidend. Vier gerichte regressies en 37 bestaande PlanningOverview-tests slagen; manage.py check slaagt. Geen migratie nodig. Compacte tabel zonder desktop-minimumbreedte; visuele mobiel-/desktopcontrole en Render-deploy nog niet geverifieerd.

Injury/Issue Overview uitgebreid: schuifje 5–25 evaluaties, standaard 5, direct zonder pagina-herladen. Klik op een bestaande evaluatie opent een alleen-lezen popup met naam, datum/AM-PM, issue-status, oorspronkelijke effective_status met teken/label, RPE en evaluatiecommentaar. Ontbrekende evaluaties zijn neutraal en niet aanklikbaar; afgeschermde data komt niet in de popup-attributen. Zeven gerichte tests, 37 bestaande PlanningOverview-tests en manage.py check slagen; de JavaScriptbediening voor 5/13/25 en drie statussen is apart uitgevoerd. Mobiele wrapping en scrollbare popup ingericht; visuele desktop-/mobielcontrole en Render-deploy nog niet geverifieerd. Geen migratie nodig.

Injury/Issue Overview: See training toegevoegd met juiste AM/PM-keuze, persoonlijke/Flex-/Watch-override, expliciete lege override en base-/rustplanning. Comments coaches krijgt een +, eigen commentaar per auteur en dezelfde initialen/trainerkleur als Desired Improvements. Migratie 0141 lokaal uitgevoerd; Render moet deze via de bestaande migratiestap toepassen. 14 gerichte tests en 37 PlanningOverview-regressies slagen, plus manage.py check en migratiecontrole. De JavaScriptbediening voor See training/terug/eigen-commentaar is apart uitgevoerd. Visuele desktop-/mobielcontrole kon niet worden afgerond doordat de browser de lokale testpagina niet bereikte; Render-deploy nog niet geverifieerd. Geen lokale database of testpreviewbestanden committen.

Strength (voorheen Main 2) is overal vrij tekstveld: gedeelde Trainer/AYC/Flex-modal, baseplanning, standaarden en trainingsdetails. Het interne type CORE2 blijft behouden; migratie 0142 past alleen het zichtbare keuzelabel aan en is lokaal uitgevoerd. Zelfstandige Strength-training is toegestaan. Bestaande teksten blijven behouden en worden na alle Main-blokken weergegeven, inclusief mobiel en compacte core-only-weergave. Strength is uitgesloten van loopafstand/looptijd/zones; stats-cacheversie v21. Nieuwe invoer wist oude numerieke parsevelden; meerregelige standaarden blijven intact. Gerichte formulier-/opslag-/weergave-/stats- en rechtenregressies slagen, evenals manage.py check en migratiecontrole. Volledige core-suite en visuele desktop-/mobielcontrole niet uitgevoerd; Render-deploy nog niet geverifieerd.

Trainingsvolgorde: één kolom met standaard WU-Mob/Tech-Strength-Sprint-Main-Alternative-CD. Sleepgreep en ↑/↓ verplaatsen de velden per training; opgeslagen TrainingSlot.segment_order en display-klonen volgen dit in Trainer Planner, AYC, Flex en trainingsdetails. Trainingscellen tonen losse regels. Meerdere Main-blokken blijven onderling in bronvolgorde. Volgorde reist mee met dag-/weekkopieën, standaarden en Watch/Plan-versies; alleen verplaatsen behoudt gemeten Main-loads. Migratie 0143 lokaal uitgevoerd; Render moet deze via de bestaande migratiestap toepassen. 65 verschillende gerichte regressies slagen (segmentvolgorde, Strength, Watch/Plan, Injury-overzicht, Flex-totalen, mobiele AM/PM-prefill en rechten), plus manage.py check en migratiecontrole. De werkelijke formulier-JavaScript is apart uitgevoerd voor pijltjes, drag/drop, verborgen velden en read-only. Geen visuele desktop-/mobielcontrole of Render-deploybevestiging; volledige core-suite niet uitgevoerd.

Strength-weergave: het automatisch toegevoegde voorvoegsel `Strength:` is verwijderd uit het vrije Strength-segment in Trainer Planner, AYC en Flex, inclusief de oudere AYC-variant. Alleen de ingevoerde tekst wordt getoond; de veldnaam Strength blijft behouden. Negen gerichte Strength-tests en manage.py check slagen. Geen migratie nodig; visuele productiecontrole nog niet uitgevoerd.

Trainingspopup compacter en beter bedienbaar: Add photos staat naast Strength; nieuwe uploads gebruiken CORE2 en verschijnen daar ook in de training. Bestaande Mob/Tech-foto’s blijven ongewijzigd, inclusief oude uploadcompatibiliteit en privélinks. Maximaal vijf foto’s gezamenlijk; Strength met uitsluitend foto’s is geldig. De hoofdknoppen staan buiten het scrollbare velddeel in een vaste footer; Save/Load standard staat eronder helemaal onderaan. AYC stuurt Strength-uploads en verwijderingen apart mee. 48 verschillende gerichte regressies slagen (foto’s, Strength, segmentvolgorde, Watch/Plan, mobiele AM/PM en gedeelde rechten), plus manage.py check en migratiecontrole. Geen migratie nodig. Visuele desktop-/mobielcontrole en Render-deploy nog niet geverifieerd.

Trainer Planner-meerzonekleuren: de verouderde aparte routine toonde alleen de twee bereikseindpunten. Trainer gebruikt nu dezelfde gedeelde partial als Flex/DCO, zodat 12*400m Z2>Z4 drie gelijke stroken krijgt (Z2/Z3/Z4). Regressie voert de echt gerenderde JavaScript uit en controleert drie zones, dalende ranges, twee/één zone, samengestelde zones en T-ranges. Vier gerichte trainer-/printtests en manage.py check slagen. Geen migratie nodig; visuele productie-/mobielcontrole en Render-deploy nog niet bevestigd.

Garmin D HR Zx: de kolom toonde eerder de door de trainingsherkenning gecorrigeerde tempozone, waardoor niet-gematchte laps met End HR 178 op Z1 konden blijven. Elke manual/auto-regel krijgt nu een eigen HR-zone uit de getoonde hr_tail en atleetgrenzen, onafhankelijk van de herkenning en correctiedrempel. NA zonder tempo-terugval bij ontbrekende HR/grenzen. Regressies dekken de zes HR-waarden 171/173/174/175/178/178, ontbrekende gegevens, korte/onherkende regels en de daadwerkelijk uitgevoerde tabelrenderer. 39 gerichte Garmin-/Watch-tests en manage.py check slagen. Geen migratie; trainingsbeschrijving/loadcorrectie blijft ongewijzigd. Visuele productiecontrole en Render-deploy niet geverifieerd.

Aanvullende Garmin C/D-herkenning voor de 15-lap all-Z1-tempo-opname: duidelijke HR-werk/herstelstructuur geeft 6×1000m (bronlaps 1/4/6/8/10/12), mediane tussenpauze p356 en 1400m nominale CD. De 12:13-kilometer blijft herstel, niet werk. C houdt tempozones; D maakt de werkreps Z3 met de bestaande End-HR-controle. Nieuwe regel staat na gevalideerde lapstructuren, vereist complete HR, gelijke lange afstanden/vergelijkbare tijden en duidelijk HR-/snelheidscontrast, en laat afwijzingen ongewijzigd terugvallen. 87 gerichte tests slagen, inclusief echte C/D-preview zonder AI, zes klokreps, behoud van bronmetingen en negatieve duurloop-/onzekere-HR-/afstands-/herstelgevallen; na extra plausibiliteitsgrenzen slagen ook de drie directe regressies opnieuw. manage.py check slaagt. Geen migratie nodig. Volledige core-suite, visuele productiecontrole en Render-deploy niet geverifieerd.


## AI-afstandsgroepen (4 november 2026)

De bestaande AI-lapindeling ondersteunt nu ook target_meters naast target_seconds (per groep precies een doeltype). AI kiest de bronlaps en nominale afstand; de server valideert volledige, unieke dekking, chronologie, herstel en maximaal 8% afstandsafwijking. Geen nieuwe patroonherkenningsregel toegevoegd. Afstandsgroepen behouden alle gemeten meters/seconden en krijgen geen verzonnen Time-alternatief. Geldt voor Garmin C en D binnen bestaande AI-toestemming; bestaande vaste herkenningen blijven als voorrang/fallback bestaan. Regressie met gemockt AI-antwoord: 2000m WU, lange stop, 17x500m inclusief 531.92m-uitbijter en laatste werkrep; alle 17 kloktijden behouden. 88 gerichte tests en manage.py check geslaagd. Echte AI-service, Render-deploy en visuele productiecontrole nog niet bevestigd.


Garmin AI-diagnose (4 november 2026): C/D vraagt nu uitsluitend lap_structure/confidence in plaats van ook de oude segmenten/sets-optie. De oudere Polar-aanroep blijft compatibel. Per activiteit verschijnt een compacte status: toegepast, toestemming ontbreekt, serversleutel ontbreekt, servicefout, onbruikbaar/afgewezen antwoord of vaste herkenning zonder AI. Geen ruwe foutantwoorden of sleutels naar de browser. Productiecasus 17x500m nog niet bevestigd: lokale omgeving heeft geen serversleutel/atleet59; productiereden vereist de nieuwe status na deploy. 106 gerichte tests slagen, plus manage.py check. Bredere Polar Raw-tests hebben vier bestaande rechtenmockfouten (SimpleNamespace als user-id); de overige herkenningsasserties slagen na behoud legacycompatibiliteit.


Garmin herstellen na intrekken (4 november 2026): dashboard behoudt een hersteltegel bij garmin_ai_withdrawn_at, ook als de coachschakelaar inmiddels uit staat. In dat geval alleen uitleg om de coach Allow Garmin Connection te laten inschakelen; endpointrechten blijven ongewijzigd. Een bestaande verbinding zonder geldige AI-toestemming toont opnieuw het toestemmings-/OAuth-formulier. Intrekken verwijdert lokale tokens, remote ontkoppeling blijft best effort; nooit automatisch toestemming herstellen. Tests: 19 Garmin Connection-regressies en manage.py check slagen. Geen migratie; visuele mobiele/productiecontrole nog niet uitgevoerd.


Garmin timertijd (4 november 2026): C/D gebruikt geldige lap.timer_time voor getoonde duur, tempo en looploads; zonder positieve geldige timertijd blijft elapsed_time de fallback. splitTimeMillis en elapsedDurationMillis blijven de oorspronkelijke verstreken tijdlijn bevatten; HR-samples worden niet verschoven of afgekapt door de kortere looptijd. Loads bewaren elapsed_seconds zodat samengestelde End-HR-controle de bestaande bronklok blijft gebruiken. FIT-sessies gebruiken total_timer_time; Activity Details bewaren total_timer_s uit timerDurationInSeconds of summary.durationInSeconds. Bij precies één complete lap mag het gemeten activiteitstotaal als laptimertijd dienen; bij meerdere laps wordt geen pauze over laps verdeeld. Eerdere opgeslagen Activity Details zonder total_timer_s gebruiken ontvangen summary.duration_s bij preview, zonder databasewijziging. Regressie voor nieuwe en bestaande pushdetails in C en D: 17336m, 4676s verstreken, 4503s timer geeft 01:15:03 en 4:20/km, terwijl HR na timerseconde 4503 behouden blijft. 90 gerichte tests en manage.py check geslaagd; productie-/mobiele visuele controle niet uitgevoerd. Opnieuw openen herberekent previews; al via Use AM/PM opgeslagen trainingen moeten opnieuw worden toegepast voor de nieuwe looptijd.


FIT AI-toestemming (4 november 2026): uploadscherm bevat voor atleten een optioneel, standaard uitgeschakeld vakje met Save AI permission, apart van bestand uploaden. Geldt voor bestaande/toekomstige eigen FIT-bestanden inclusief Coros, zonder Garmin OAuth. Coach ziet alleen status/uitleg en kan nooit toestemming namens een atleet opslaan; endpoint controleert eigen atleet en uploadrecht. Migratie 0144 voegt fit_ai_consent_at, fit_ai_withdrawn_at en fit_ai_consent_version toe. Intrekken verwijdert geen bestanden en raakt Garmin-koppeling/toestemming niet. C/D kiest toestemming per activiteitbron: GarminActivity gebruikt FIT-toestemming, ontvangen Garmin-details blijven de bestaande Garmin-toestemming gebruiken. Geen AI zonder geldige toestemming of bij ingetrokken uploadrecht. Privacytekst bijgewerkt. 60 gerichte Garmin-/Watch-tests en manage.py check geslaagd; visuele desktop-/mobiele controle en productie-uitrol nog niet bevestigd.


Download originele FIT-upload (4 november 2026): Saved Garmin activities op het uploadscherm heeft Download original. GET-route garmin_upload_download retourneert ongewijzigde raw_file met veilige attachment-bestandsnaam, private/no-store en nosniff; oorspronkelijke ZIP blijft ZIP. Zelfde uploadrecht/toegankelijke atleet vereist; eigen atleet of bevoegde coach, geen Coach Tools-only of vreemde atleet, 404 zonder bronbestand. 21 gerichte tests en manage.py check slagen. Geen migratie. Kilometerafwijking Daan blijft open en vereist brononderzoek; deze wijziging maakt het bronbestand downloadbaar. Visuele desktop-/mobiele controle nog niet uitgevoerd.


FIT-uploadscherm: atleetkeuze navigeert direct naar ?athlete=id zodat opgeslagen activiteiten en Download original zichtbaar worden zonder verplicht nieuw bestand. Gerichte download-/paginatest en manage.py check slagen.


HR-zonecontrole bij gedeeltelijke/overlappende instellingen (4 november 2026): hr_zone beoordeelt elke meting tegen alle bruikbare expliciete bereiken. Precies een match geeft een zone; overlappende waarde (bijvoorbeeld 178 bij 169-178 en 178-184) blijft NA, zonder alle andere waarden uit te schakelen. Ontbrekende/ongeldige zone blokkeert geen eenduidige match elders. Een bovengrens zonder ondergrens na een ontbrekende zone blijft onbekend; er worden geen grenzen geschat. Ongewijzigde drempels voor D-trainingscorrectie en bronmeters/tijden. Regressie met opgegeven grenzen 151 / 152-168 / 169-178 / 178-184 / 188 dekt losse lapkolom en grenswaarden. 54 gerichte tests en manage.py check slagen; productie-/mobiele visuele controle nog niet uitgevoerd.


AI-setgrenzen en pauzes (4 november 2026): lap_structure.groups accepteert optionele set_start_laps met de eerste werk-lap per set. De AI kiest de setindeling; geen nieuwe lokale herkenningsregel. Validator vereist bestaande oplopende rep-starts, gelijk aantal reps per set, minstens twee reps per set en gemeten setpauzes minstens 1.5 maal de mediane gewone pauze. P en SP worden uit bronpauzes berekend, niet uit AI-getallen; alle laps blijven uniek/volledig toegewezen en meetmeters/tijden onveranderd. Langzame aanloop-overgang mag recovery zijn voor de eerste rep, maar geen lopende lap >=2m/s. Klok-/D-matcher bindt geneste AI-setlabels aan alle oorspronkelijke repidentiteiten. Regressie met 20x400m en AI-setstarts [4,24] produceert 2x(10x400 m Z2 p60) sp318, behoudt alle twintig klokreps in C/D en wijst verzonnen/ongelijke setstarts af. 93 gerichte tests slagen; AI-service/visuele productiecontrole nog niet bevestigd.


AI-herstel na afgewezen lapindeling (4 november 2026): validator levert optioneel een vaste servergeschreven afwijsreden per controlefase. Garmin C/D vraagt bij een ongeldig lapvoorstel maximaal eenmaal een nieuw volledig AI-voorstel met oorspronkelijke anonieme lapfeiten plus die feedback (extra verzoek maximaal 15s; bestaande toestemming blijft vereist). Tweede voorstel doorloopt identieke controles; bij falen blijft gemeten fallback met zichtbare afwijsreden. Geen ruwe servicefouten/modelpayloads of tokens in browserfeedback. Regressies dekken herstel van langzame overgang in warmup, een tweede afwijzing, exact twee verzoeken, behouden meetwaarden en succesvolle setindeling. 94 gerichte tests en manage.py check slagen. De productie-afwijsreden voor Daans opname is nog niet bevestigd; eerdere gemockte AI-test bewijst geen echte service-uitkomst.


AI-opdracht en confidence verduidelijkt (4 november 2026): strict Garmin C/D gebruikt een zelfstandige lap-only opdracht en systeembericht, zonder tegenstrijdige legacy segments/sets-instructies of oude schema-beperkingen. Opdracht benoemt gemeten werk/herstel/setgrenzen, langzame overgangslaps en grenzen van de bestaande validator. Geen andere confidencegrens: geldige numerieke score vereist 0.75-1.00. Afwijzing noemt nu exacte score of ontbrekend/ongeldig getal; bools/NaN/strings worden niet als score geaccepteerd. Legacy Polar-pad ongewijzigd. 95 gerichte tests en manage.py check slagen; echte AI-score/uitkomst voor productieopname nog niet geverifieerd.


AI-voorstel ter beoordeling (4 november 2026): automatische acceptatie blijft confidence >=0.75 vereisen. Een AI-voorstel met geldige score 0.50-0.75 kan na volledige identieke lap-/meetvalidatie als aparte keuze AI proposal — review worden aangeboden. Fallback blijft standaard geselecteerd; alleen expliciet kiezen vervangt fields/loads voor Use AM/PM. Ongeldige/ontbrekende laps blijven afgewezen. Zelfgerapporteerde modelscore is geen gemeten juistheidspercentage. Toestemming en maximaal een AI-herstelpoging ongewijzigd; C/D behandelen voorstel dezelfde wijze inclusief HR-correctie en klokmetadata. Regressies bewaken .70 zonder automatische acceptatie, afwijzing van verzonnen laps, optionele C/D-preview en ongewijzigde standaardvelden. 97 gerichte tests en manage.py check slagen. Echte productie-indeling en visuele controle nog niet bevestigd.


AI-reviewdiagnose: lage confidence maskeerde de eerste inhoudelijke meetfout omdat confidence eerder wordt gecontroleerd. Ook bij onvoldoende automatische confidence wordt nu de review-meetcontrole uitgevoerd; unieke afwijsredenen gaan samen naar de ene AI-herstelpoging en browsermelding. Ongeldige repindeling wordt nooit toegestaan door lagere reviewgrens. 13 gerichte AI-tests en manage.py check slagen.


Gerichte AI-repcorrectie (4 november 2026): de ene herstelpoging krijgt nu het oorspronkelijke numerieke AI-voorstel als assistant-context plus validatiefout. Alleen bekende structuurvelden/numerieke waarden worden teruggestuurd, geen willekeurige modeltekst. Repfouten zijn opgesplitst naar concrete lap-ID-volgorde, gemeten meters versus doelmeters, seconden versus tijdtarget, en langzame herstel-lap in werkrep. Lap-only opdracht verduidelijkt dat elke reps-entry precies een herhaling is en geen volledige set. 46 gerichte tests slagen; daarna 14 AI-tests met nieuwe herstelcontext-/foutdetailregressies en manage.py check slagen. Productievoorstel nog niet beschikbaar; geen bevestiging van de specifieke lapfout op productie.


Wandelen in AI-WU/CD (4 november 2026): een door AI aan warmup/cooldown toegewezen lap die volgens de bestaande >10:00/km-regel wandelen is, wordt binnen het gevalideerde voorstel behouden als niet-werkherstel. Geen nieuwe rep-/setherkenning; AI blijft de bronreps/setgrenzen kiezen. Wandelmeters verdwijnen uit boundary-tekst, blijven in bronloads en worden volgens bestaand beleid uitgesloten van loopkilometers. Voorkomt dat wandelende overgangslaps een verder geldig AI-voorstel geheel blokkeren en de fallback zonder pauzes terugbrengen. Regressie met verkeerd gegroepeerde bronlaps 2/3 en 43 geeft WU 3800m, CD 1450m, 2x(10x400m) p60 sp318 en bewaart alle assignments. 98 gerichte tests en manage.py check slagen; echte AI-productieuitkomst niet bevestigd.


AI-brondekking bij ontbrekende wandel-laps (4 november 2026): niet door AI toegewezen bronlaps worden uitsluitend wanneer ze onder de bestaande >10:00/km-wandelregel vallen als niet-werkherstel behouden. Geen lopende lap, rep of set wordt geraden. Ontbrekende lopende bronlaps blijven afwijzing, met exacte lap-ID-lijst voor de AI-herstelpoging en popup; te weinig werkreps krijgt een afzonderlijke melding met werkelijk aantal. Regressie laat AI stop/overgang/slotwandelen en wandelende setpauze overslaan en bewaart alsnog dezelfde volledige metingen/velden; weglaten van lopende WU wordt afgewezen. 98 gerichte tests en manage.py check slagen. Productie-AI-antwoord en resultaat nog niet bevestigd.


Trainingsstructuur-model opgewaardeerd (4 november 2026): Garmin C/D en FIT-AI gebruiken in strict_lap_structure nu standaard gpt-5.4-mini met reasoning_effort=low, zonder temperature. Dedicated WATCH_STRUCTURE_MODEL kan een expliciet compatibel reasoning-model instellen; bestaande globale OPENAI_MODEL blijft uitsluitend het legacy Polar-pad bepalen. Daardoor houdt een oude OPENAI_MODEL=gpt-4o-mini de nieuwe structuurherkenning niet tegen. Dezelfde parameters gelden voor de ene herstelpoging. Popup toont AI model: plus de werkelijk gekozen modelnaam, uitsluitend na AI-aanroep. Aanvankelijk overwogen zwaarste model is op verzoek van eigenaar niet gekozen; middenweg GPT-5.4 mini. Officiële API-bronnen: https://developers.openai.com/api/docs/models/gpt-5.4-mini en https://developers.openai.com/api/docs/guides/latest-model (reasoning-parameters). Lokale modelresolver tweemaal niet bereikbaar; keuze geverifieerd via opgehaalde officiële modelpagina. 99 gerichte tests en manage.py check slagen; verzoekparameters en modeloverride inclusief herstel getest met gemockte API. Geen lokale API-sleutel, dus geen echte modelaanroep of productie-kwaliteit/latentie bevestigd. Geen migratie nodig.


Activiteiten zonder afstand (4 november 2026): Garmin Activity Details missing_distance behoudt nu ook geldige hartslagsamples en beperkte summaryvelden activityType, average/maxHeartRateInBeatsPerMinute en activeKilocalories. C/D-summarykaart toont sport, aangeleverde gemiddelde/max-HR, actieve kcal en ontvangen HR-sampleaantal. Alleen indien Garmin geen HR-samenvatting levert, afzonderlijk benoemde samplegemiddelde/max; geen afstanden, pace of looploads geschat en geen AI-aanroep voor deze kaart. GPS/overige raw data blijven uitgesloten. Oude missing_distance-ontvangsten bevatten deze velden niet: nieuwe/resend Activity Details vereist; originele FIT-upload kan brongegevens ter inspectie leveren. 34 gerichte tests en manage.py check slagen; visuele desktop-/mobiel-/productiecontrole niet uitgevoerd.
