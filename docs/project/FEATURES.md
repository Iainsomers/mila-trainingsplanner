# Functionele onderdelen

Laatst inhoudelijk gecontroleerd: 15 augustus 2026.

## Dashboard en Planning

Het coachdashboard toont Planning bovenaan. Admin, Stats, Polar en Settings (under development) staan onderaan. De Settings-tegel doet voorlopig niets.

Atleten gebruiken Planning voor drie onderdelen: Athlete Year Planning, Athlete settings en Races.

## Trainer Planning

- Meerdere weken, standaard vier.
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

- Trainer beheert wedstrijden en afstanden.
- Atleet kiest maximaal drie afstanden per wedstrijd.
- Een wedstrijd kan als doelwedstrijd worden gemarkeerd.
- `Race` is een gewone wedstrijd; `Race!` is een belangrijke doelwedstrijd.

## Athlete settings

Tabs voor atleten: General, Zone/PR's, Base Planning, Ideal week en WU settings. Base Planning is voor atleten alleen-lezen. `Fill missing PB's` kan ontbrekende prestaties afleiden uit beschikbare PR's.

## Daily Coach Overview

Selectie op datum, AM/PM, alle atleten, selectie, trains, geplande training en opgeslagen selecties. De resultaatpagina behoudt de selectie en toont atleet-specifieke tempo's, RPE en opmerkingen.

## Stats

Trainer-only, nog in ontwikkeling. Toont per atleet de totale kilometers van deze en vorige week.

## Polar

Ondersteunt OAuth en synchronisatie van relevante trainings-, activiteits- en lapgegevens. Watch suggestions kunnen evaluatie-invoer voorstellen. De atleet controleert een voorstel altijd vóór gebruik.
