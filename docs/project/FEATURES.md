# Functionele onderdelen

Laatst inhoudelijk gecontroleerd: 15 augustus 2026.

## Dashboard en Planning

Het coachdashboard toont Planning bovenaan. Admin, Stats, Polar en Settings (under development) staan onderaan. De Settings-tegel doet voorlopig niets.

Atleten gebruiken Planning voor drie onderdelen: Athlete Year Planning, Athlete settings en Races.

## Trainer Planning

- Meerdere weken, standaard vier.
- De lijst met trainerplannen toont de eigenaar/coach compact in een eigen, links uitgelijnde middelste kolom.
- Weken blijven zeven dagen breed en extra weken stapelen verticaal.
- Huidige week wordt geel gemarkeerd.
- Vorige/volgende verschuift één week.
- Dag- en weekkopiëren werkt tussen trainerplannen.
- Trainingsonderdelen worden uiteindelijk in Flex Planner en AYC gebruikt.

## Flex Planner

- Toont de effectieve planning per geselecteerde atleet.
- Ondersteunt persoonlijke wijzigingen, kopiëren en drag-copy.
- Toont alle trainingsonderdelen en atleet-specifieke richttijden/tempo's.
- Behoudt de weektypekleur naast de markering van de huidige week.

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
- Planner, Dashboard en Logout blijven bereikbaar.
- Bij ingeschakelde Week reports staan onder iedere mobiele week vier gekleurde rapportvakken, gelijk aan desktop.
- Bij ingeschakelde Daily vitals staat naast iedere datum een hartknop die een mobiele invoerpopup opent.
- Weekgemiddelden voor slaapuren, slaapkwaliteit, ochtendhartslag en HRV staan compact in het weekoverzicht zodra voldoende waarden beschikbaar zijn.

## Trainingen

Ondersteunde onderdelen zijn WU, Mob/Tech, Sprint, Main, Main 2, Alternative en CD. Standaard krachtprogramma's kunnen vanuit Mob/Tech worden geopend. Afstanden tonen waar mogelijk richttijden; tijdsblokken tonen richttempo in min/km.

## Evaluaties

Per training kan de atleet vastleggen:

- status: Done, More/too fast, Adjusted, Less/slower of Not done;
- RPE van 0 tot 10;
- commentaar;
- voorgestelde invoer uit horlogedata;
- afzonderlijke AM/PM-evaluaties wanneer er twee trainingen zijn.

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

Tabs voor atleten: General, Zone/PR's, Base Planning, Ideal week en WU settings. Base Planning is voor atleten alleen-lezen. `Fill missing PB's` kan ontbrekende prestaties afleiden uit beschikbare PR's.

## Daily Coach Overview

Selectie op datum, AM/PM, alle atleten, selectie, trains, geplande training en opgeslagen selecties. De resultaatpagina behoudt de selectie en toont atleet-specifieke tempo's, RPE en opmerkingen.

## Stats

Trainer-only, nog in ontwikkeling. Toont per atleet de totale kilometers van deze en vorige week.

## Polar

Ondersteunt OAuth en synchronisatie van relevante trainings-, activiteits- en lapgegevens. Watch suggestions kunnen evaluatie-invoer voorstellen. De atleet controleert een voorstel altijd vóór gebruik.

Wanneer horlogedata duidelijk niet aansluit op de geplande training begint de interpretatie met een rood kruis. Via `Suggest alternative plan` kan vervolgens een alternatief trainingsconcept uit de horlogedata worden gereconstrueerd. Dit concept vervangt de oude interpretatie in beeld, toont een betrouwbaarheidsschatting en vervangt de oorspronkelijke planning nooit automatisch. Naast handmatige laps kan een herhalend fartlekpatroon uit aanhoudende tempowisselingen worden herkend; automatische kilometersplits worden niet ten onrechte als trainingsblokken gepresenteerd.

Meerdere sporten op dezelfde dag blijven als losse activiteiten zichtbaar, maar worden niet samengevoegd in de interpretatie. Technische watch-details staan standaard ingeklapt.
