# Functionele onderdelen

Laatst inhoudelijk gecontroleerd: 28 september 2026.

## Dashboard en Planning

Het coachdashboard toont Planning bovenaan. Onder `Coach dashboard` staat voor trainers met gedeelde toegang een `View as coach`-keuze. Standaard kijkt een trainer als zichzelf; na selectie van een andere toegestane coach tonen plannings- en beheerschermen alleen de gegevens van die coach. De dropdown toont of die toegang view-only of edit is; bij view-only worden schrijfacties server-side geblokkeerd. Admin, Stats, Polar en Settings (under development) staan onderaan. De Settings-tegel doet voorlopig niets.

Planning is voor coaches gegroepeerd in Coach plannings, Views en Standards. Coach plannings bevat Athletes, Trainer planning, Flex Planner, Races en Year Planner. Views bevat Athlete Year Calendar en Daily Coach Overview Training; de toekomstige Daily Coach Overview Vitals-tab is bewust nog niet aanklikbaar. Standards bevat Saved Trainings en Standard Strength. Atleten gebruiken Planning voor Athlete Year Calendar, Athlete settings, Races en, wanneer toegestaan, Year Planner.

Het dashboard bevat daarnaast Coach Tools. MiLa bevat daar alleen de Track Timer; Match Overview en de PR-database zijn verplaatst naar het aparte PAC-project. De timer toont een getekende atletiekbaan met 100m-punten, een afstandskeuze van 100m tot 1600m, een optionele doeltijd en een single/multiple-modus voor één of drie atleten. In multiple staan drie gekleurde atleetknoppen en een zwarte knop voor alle drie. De start/finishknop kan naar een van de vier meetpunten worden gesleept, waarna de andere meetpunten meedraaien. Bij afstanden boven 400m moeten 400m-doorkomsten worden vastgelegd voordat de eindtijd kan worden gestopt. De resultaten tonen tussentijd, tempo per 100 m, min/km en eventueel afwijking van de doeltijd; een lijn op de baan visualiseert het doeltempo.

Het dashboard bevat ook Evaluations. Trainers maken vragenlijsten, kunnen een eerdere lijst als basis kopiëren en zien ingevulde formulieren per vragenlijst en daarna per atleet. Een formulier kan gewone open vragen en matrixvragen combineren. Een matrix heeft een eigen header, vrij instelbare rijvragen en vrij instelbare kolomkoppen, bijvoorbeeld jaartallen. Trainers kunnen een volledige vragenlijst inclusief de bijbehorende antwoorden verwijderen. Actieve vragenlijsten zijn voor alle eigen atleten beschikbaar; atleten zien alleen beschikbare lijsten en hun eigen ingevulde antwoord.

Ingelogde pagina's publiceren het MiLa-logo als favicon, Apple touch icon en PWA-icoon. Een snelkoppeling die vanaf een telefoon op het beginscherm wordt gezet, gebruikt daardoor standaard het MiLa-logo.

## Trainer Planning

- Meerdere weken, standaard vier.
- De lijst met trainerplannen toont de eigenaar/coach compact in een eigen, links uitgelijnde middelste kolom.
- Weken blijven zeven dagen breed en extra weken stapelen verticaal.
- Huidige week wordt geel gemarkeerd.
- Vorige/volgende verschuift één week.
- Dag- en weekkopiëren werkt tussen trainerplannen.
- `Copy weeks` kopieert 1–12 aaneengesloten weken naar hetzelfde of een ander trainerplan, met keuze tussen overschrijven en alleen lege slots vullen.
- Een gevulde AM- of PM-training kan rechtstreeks uit de Trainer Planner worden verwijderd met de compacte `×` in de cel.
- Trainingsonderdelen worden uiteindelijk in Flex Planner en AYC gebruikt.

## Year Planner

- Overzicht onder Planning voor training phases en whereabouts over een flexibele periode. Trainers beheren eigen atleten; atleten kunnen uitsluitend hun eigen, door de trainer toegestane lagen lezen.
- De periode gebruikt current/next month, outdoor, indoor, full year en een seizoensperiode zoals 2026/2027.
- Trainers kunnen Training, Whereabouts of beide lagen tonen.
- De weergave kan worden geschaald naar ongeveer 1, 3 of 12 maanden per schermbreedte en kan horizontaal scrollend of in schermbrede stukken onder elkaar worden getoond; stacked is de standaardweergave.
- Meerdere atleten kunnen tegelijk worden getoond, maar er worden standaard geen atleten voorgeselecteerd. De atletenlijst kan op `All` of op een Trainer Planning-verwijzing worden gefilterd. `All` selecteert alle zichtbare atleten. Na keuze van een specifieke Trainer Planning-groep kan de trainer direct onder `All` de aparte `Basis - groepsnaam`-planningsrij kiezen. Iedere groep heeft eigen Basis-data; bij de algemene groepskeuze `All` is er bewust geen gedeelde Basis. Historische algemene Basis-data wordt niet automatisch naar alle groepen vermenigvuldigd. Atleten zonder ingeschakelde Year Planner-laag zijn rood gemarkeerd in de selector.
- Training phases gebruiken dezelfde keuzes als de Flex Planner: Recovery, Aerobe, Specific, Intense en Taper.
- Whereabouts-keuzes zijn Camp, Travel, Test, Championship, Diamond L, Race Gold, Race Silver, Race Bronze, Race Other, Expermeetings, Medical en Brinec, elk met een vaste kleur. Ze worden als echte datumranges opgeslagen, zodat een kamp of reis als één doorlopende pil met gecentreerde naam verschijnt, kan worden verkleind/verlengd en naar een andere atleet kan worden gesleept. Overlappende whereabouts, zoals een testdag binnen een kamp, blijven naast elkaar bestaan en delen de dagcel diagonaal.
- Trainingcellen slaan direct op. Gekozen trainingswaarden kunnen over een datumrange worden gesleept. Hele atletrijen kunnen per zichtbare periode met `c`/`p` worden gekopieerd voor Training en afzonderlijk voor Whereabouts. Een nieuwe of bewerkte whereabout kan in één keer op alle geselecteerde atleten worden toegepast.
- Per atleet bepaalt de trainer in Athlete settings > General afzonderlijk of de Training-calendar en/of Whereabouts-calendar in de Year Planner zichtbaar zijn. De legenda volgt die zichtbaarheid.

## Flex Planner

- Toont de effectieve planning per geselecteerde atleet.
- Ondersteunt persoonlijke wijzigingen, kopiëren en drag-copy.
- Toont alle trainingsonderdelen en atleet-specifieke richttijden/tempo's.
- Haalt weekphase-kleuren uit de Year Planner. Meerdere fases in één week worden diagonaal gecombineerd; de oude weektype-dropdown bestaat niet meer.

## Athlete Year Calendar (AYC)

- Trainer kan tussen atleten schakelen; atleet ziet alleen zichzelf.
- Desktop toont een brede jaartabel; mobiel toont één week tegelijk.
- Op mobiel opent de huidige week automatisch en navigeert men met pijlen.
- De huidige week is geel en de huidige dag donkerder geel.
- Weektype staat als gekleurde pil.
- `Total` en de zoneverdeling tonen het berekende weektotaal.
- AM en PM worden afzonderlijk getoond.
- Training en Evaluation hebben beide een zichtbare knop `Open`.
- Trainingen openen in een op mobiel beeldvullende popup, maar niet groter dan het scherm.
- Bestaande AM- én PM-trainingen worden vooraf ingevuld in de popup.
- Een groen vinkje toont dat alle evaluaties van die dag zijn voltooid.
- Bij een atleet verschijnt voor niet-geëvalueerde trainingen van gisteren tot maximaal zes dagen geleden automatisch een popup. De huidige dag en oudere trainingen worden genegeerd.
- Op mobiele AYC kan een atleet bij Comment op de microfoon drukken om Nederlands commentaar in te spreken. Nogmaals drukken stopt de opname; tussenresultaten mogen bestaande woorden niet dupliceren.
- Planner, zones/times, Dashboard en Logout blijven bereikbaar.
- Bij ingeschakelde Week reports staan onder iedere mobiele week vier gekleurde rapportvakken, gelijk aan desktop.
- Bij ingeschakelde Daily vitals staat naast iedere datum een hartknop die een mobiele invoerpopup opent.
- Weekgemiddelden voor slaapuren, slaapkwaliteit, ochtendhartslag en HRV staan compact in het weekoverzicht zodra voldoende waarden beschikbaar zijn.

## Trainingen

Ondersteunde onderdelen zijn WU, Mob/Tech, Sprint, Main, Main 2, Alternative en CD. Standaard krachtprogramma's kunnen vanuit Mob/Tech worden geopend. Afstanden tonen waar mogelijk richttijden; tijdsblokken tonen richttempo in min/km. Progressive ranges zoals `z2>z4` en `t5>t15` nemen de tussenliggende Z/T-stappen mee in de kleurverdeling en kilometertelling. Alternative-tijdsblokken in Z1, Z2 en Z3 worden in de weektotalen afzonderlijk als ALT-minuten getoond en tellen niet mee als loopkilometers. Net als bij Main scheidt `//` meerdere Alternative-blokken.

## Evaluaties

Per training kan de atleet vastleggen:

- status: Done, More/too fast, Adjusted, Less/slower of Not done;
- RPE van 0 tot 10;
- commentaar;
- voorgestelde invoer uit horlogedata;
- afzonderlijke AM/PM-evaluaties wanneer er twee trainingen zijn.

Naast trainingsevaluaties bestaat Evaluations voor losse coachvragenlijsten. Trainers publiceren actieve vragenlijsten voor hun atleten. Trainers kunnen de vragen en antwoorden alleen lezen; atleten kunnen alleen hun eigen antwoorden invullen en later terugzien.

## Rapportages

Optioneel per atleet:

- Training reports;
- Week report met atleetcommentaar, trainerreactie, wedstrijdverslag en blessures;
- Daily vitals: slaapuren, slaapkwaliteit, ochtendhartslag en HRV.

Weekgemiddelden verschijnen bij minimaal drie bruikbare dagwaarden en staan mobiel compact onder het weektotaal.

## Wedstrijden

- Trainer beheert wedstrijden en afstanden; trainer en atleet beheren hun selecties vanuit dezelfde Race Calendar-popup.
- De lijstweergave van de Race Calendar toont per wedstrijd datum, naam en reeds gekozen afstanden; afstandsbeheer verschijnt pas na het openen van de wedstrijd.
- De lijst toont boven iedere gekozen afstand een groene teller met het aantal deelnemende atleten; bij nul deelnemers wordt geen teller getoond.
- Trainers kiezen eerst `All` of een Trainer Planning-groep en daarna `All` of één atleet binnen die groep. De keuze `Show all races` bepaalt of wedstrijden zonder deelnemers uit die selectie zichtbaar blijven; afstandstellers volgen dezelfde selectie.
- Atleet kiest maximaal drie afstanden per wedstrijd.
- Een wedstrijd kan als doelwedstrijd worden gemarkeerd.
- De popup kan voor trainers alle atleten, een Trainer Planning-groep of alleen reeds deelnemende atleten tonen; een atleet ziet alleen zichzelf. Achter ingeklapte atleetnamen staan geen afstandspillen.
- Atleten openen de Race Calendar standaard in de compacte lijstweergave, met de afstanden als pillen achter de wedstrijdnaam.
- De Races-tegel voor atleten opent de geïntegreerde Race Calendar en niet meer de oude Race Selector. Alleen gekozen afstanden verschijnen in de compacte lijst, met de kleur van de akkoordstatus.
- In een geopende wedstrijd ziet een atleet de eigen selectiehokjes meteen; trainers blijven atleetregels eerst openklappen.
- Bij atleten werken de afstandspillen in de lijst direct bij wanneer een selectiehokje verandert, ook vóór het opslaan.
- Athlete- en Target-vinkjes worden voor atleten direct op de achtergrond opgeslagen; daarom heeft hun wedstrijdpopup geen aparte Save selections-knop.
- Ook Coach- en Target-vinkjes van trainers worden direct op de achtergrond opgeslagen; de wedstrijdpopup heeft voor geen van beide rollen nog een Save selections-knop.
- Atleten kunnen in zowel List als Calendar view een wedstrijd toevoegen aan de kalender van hun trainer en daar nieuwe afstanden aan toevoegen. Bestaande afstanden of de wedstrijd verwijderen blijft trainer-only.
- Een trainerspopup neemt de bovenaan gekozen groep of atleet als beginfilter over. De popupselector kan daarna naar alle atleten, een andere groep, één atleet of deelnemende atleten schakelen.
- Met de schakelaar `Expand all` opent of sluit de trainer alle momenteel zichtbare atleetregels tegelijk.
- De kalenderweergave kleurt wedstrijden volgens de zwaarste akkoordstatus binnen de gekozen atleet/groep: licht zonder deelname, oranje/rood omlijnd bij een enkel akkoord en oranje/rood gevuld bij dubbel akkoord. Alleen trainers zien een groene badge met het aantal deelnemers boven nul.
- Trainer-, atleet- en doelwedstrijdvinkjes hebben afzonderlijke rechten. Bestaande selecties worden als wederzijds bevestigd gemigreerd.
- Een nog niet wederzijds bevestigde wedstrijd is wit met oranje rand, of met rode rand als Target aanstaat. Na trainer- én atleetakkoord wordt de pil gevuld oranje of rood.

## Athlete settings

Tabs voor atleten: General, Zone/PR's, Base Planning en Ideal week. WU/CD-instellingen staan op General; de oude WU settings-tab bestaat niet meer. Base Planning is voor atleten alleen-lezen. `Fill missing PB's` kan ontbrekende prestaties afleiden uit beschikbare PR's. De atletenlijst is sorteerbaar op naam en leeftijd, in beide richtingen.

## Daily Coach Overview Training

Selectie op datum, AM/PM, alle atleten, selectie, trains, geplande training en opgeslagen selecties. De resultaatpagina behoudt de selectie en toont atleet-specifieke tempo's, RPE en opmerkingen.

## Stats

Trainer-only, nog in ontwikkeling. De hoofdpagina toont eerst uitsluitend de atleetselector; na `OK` verschijnt het kilometeroverzicht voor die selectie, met een knop terug naar Selection. Het overzicht toont per atleet de totale kilometers van deze en vorige week. De drie kolommen zijn sorteerbaar: naam alfabetisch en beide weekafstanden van hoog naar laag. De atleetnaam opent een staafgrafiek met de effectieve totale kilometers per trainingsweek. De trainer vult daar vrij het gewenste aantal maanden in; standaard staat de periode op 6 maanden. Kleine pijlen verschuiven precies één gekozen periode terug of vooruit, waarbij vooruit stopt bij de huidige periode. Onder de grafiek staan het weekgemiddelde en de hoogste en laagste week van de gekozen periode. De atleetselector gebruikt dezelfde standen, opgeslagen selecties, standaardselectie en `Trains`-lijst als de Daily Coach Overview. `Planned training` beperkt Stats tot atleten met geplande loopkilometers in een van de twee getoonde weken.

## Polar

Ondersteunt OAuth en synchronisatie van relevante trainings-, activiteits- en lapgegevens. Watch suggestions kunnen evaluatie-invoer voorstellen. De atleet controleert een voorstel altijd vóór gebruik.

Wanneer horlogedata duidelijk niet aansluit op de geplande training begint de interpretatie met een rood kruis. Via `Suggest alternative plan` kan vervolgens een alternatief trainingsconcept uit de horlogedata worden gereconstrueerd. Dit concept vervangt de oude interpretatie in beeld, toont een betrouwbaarheidsschatting en vervangt de oorspronkelijke planning nooit automatisch. Naast handmatige laps kan een herhalend fartlekpatroon uit aanhoudende tempowisselingen worden herkend; automatische kilometersplits worden niet ten onrechte als trainingsblokken gepresenteerd.

Meerdere sporten op dezelfde dag blijven als losse activiteiten zichtbaar, maar worden niet samengevoegd in de interpretatie. Technische watch-details staan standaard ingeklapt.

## COROS

De voorbereidende partnerinfrastructuur bestaat uit een publieke statuscheck en een workout-pushendpoint volgens sectie 5.3 van de COROS API Reference. Pushes worden alleen geaccepteerd met de door COROS verstrekte `client`- en `secret`-headers, dubbele payloads leveren opnieuw succes op zonder dubbele opslag. OAuth-koppeling en verwerking naar atleettrainingen worden pas toegevoegd nadat COROS API-credentials heeft verstrekt.

De vier voor de aanvraag vereiste MiLa-logo's staan in `core/static/core/brand/coros/`.
