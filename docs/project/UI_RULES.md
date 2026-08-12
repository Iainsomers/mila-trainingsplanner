# UI- en taalafspraken

Laatst inhoudelijk gecontroleerd: 12 augustus 2026.

## Stijl

- Compact, functioneel en rustig; planningsinformatie krijgt voorrang op uitlegtekst.
- Gebruik bestaande Bootstrap-componenten en de huidige MiLa-visuele taal.
- Segmenten, zones, totalen en weektypen mogen als compacte pills worden weergegeven.
- Primaire acties zijn duidelijk; secundaire navigatie gebruikt een outline-stijl.
- Voorkom horizontaal scrollen op mobiel behalve waar een bewust desktopoverzicht wordt gebruikt.

## Terminologie

- Gebruik zichtbaar `Main` en `Main 2`, niet `Core` en `Core 2`.
- Intern mogen `CORE` en `CORE2` blijven bestaan.
- Gebruik binnen één scherm consistente knopnamen. In de mobiele AYC heten zowel training als evaluatie `Open`.
- Bestaande productlabels zijn grotendeels Engels; voeg geen willekeurige mix van Nederlands en Engels toe zonder een bredere vertaalbeslissing.

## Kleuren

- Z1 t/m Z6 volgen de bestaande zonekleuren.
- Huidige week: geel.
- Huidige dag binnen die week: donkerder geel.
- Weektype is een gekleurde pil: Recovery, Aerobe, Specific, Intense of Taper.
- Race is oranje; belangrijke `Race!` is rood met witte tekst waar die markering wordt gebruikt.
- Evaluatie voltooid: groen vinkje.
- Weektypekleur moet zichtbaar blijven naast huidige-weekmarkering.

## Mobiele AYC

- Toon één week tegelijk.
- Houd weeknavigatie, totaal en weektype bovenaan goed zichtbaar.
- Iedere trainingsdag toont AM en/of PM; lege dagen blijven compact.
- Gebruik expliciete `Open`-knoppen; dubbelklikken mag nooit nodig zijn.
- Training- en evaluatiepopups zijn maximaal schermvullend en intern scrollbaar.
- Bestaande waarden moeten direct bij openen zichtbaar zijn.
- Planner, Dashboard en Logout moeten bereikbaar blijven zonder Admin.

## Desktop AYC

- Behoud de brede tabel en volledige trainingsinformatie.
- Trainerselectie blijft beschikbaar voor trainers.
- Toon alle trainingsonderdelen, zones en tijden.

## Formulieren

- Zet vaste scheidingstekens voor tijdformaten visueel vast waar mogelijk.
- Toon invoerformaten bij complexe PR-velden.
- Behoud ingevoerde waarden na validatiefouten.
- Een popup mag niet groter worden dan het viewport en de opslaanknop moet bereikbaar blijven.

## Responsiviteit controleren

Controleer bij relevante UI-wijzigingen minimaal:

- smalle telefoonweergave;
- normale desktopweergave;
- openen, sluiten en opslaan van popups;
- AM en PM afzonderlijk;
- trainer- en atleetrol.
