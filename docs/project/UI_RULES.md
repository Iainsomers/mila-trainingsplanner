# UI- en taalafspraken

Laatst inhoudelijk gecontroleerd: 15 augustus 2026.

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
- Toon Week reports onderaan de week als een 2×2-grid met dezelfde vier kleuren als desktop.
- Toon bij Daily vitals een compacte hartknop naast de datum; invoer gebeurt in een schermpassende popup.
- Toon de vier weekgemiddelden compact in het weeksamenvattingsblok en gebruik `NA` totdat minimaal drie waarden beschikbaar zijn.

## Desktop AYC

- Behoud de brede tabel en volledige trainingsinformatie.
- Trainerselectie blijft beschikbaar voor trainers.
- Toon alle trainingsonderdelen, zones en tijden.

## Stats en DCO

- Stats gebruikt voor atleetselectie dezelfde compacte bediening en dezelfde opgeslagen coachselecties als de Daily Coach Overview.
- Stats scheidt selectie en resultaten in twee stappen. De resultatenkoppen zijn aanklikbaar; afstandskolommen sorteren aflopend en de naamkolom alfabetisch.

## Race Calendar

- Houd de lijstweergave compact op één regel: datum, een uitgelijnde naamkolom en bestaande afstanden zijn direct zichtbaar.
- Beperk Add race tot een compacte kaartbreedte en open Race Calendar direct vanuit Races zonder tussenpagina.
- Plaats voor trainers naast Add race eerst een groepsfilter (`All` telt als groep) en daarna een daarvan afhankelijke atleetfilter; laat zowel wedstrijdzichtbaarheid als afstandstellers deze combinatie volgen.
- Geef Add race en de Race filter op desktop dezelfde kaartbreedte.
- Laat de atleetselector in een wedstrijdpopup starten met de bovenliggende kalenderfilter en plaats er een compacte Expand all-schakelaar naast.
- Gebruik in de Race Calendar dezelfde oranje/rode akkoordkleuren als bij wedstrijdpillen; plaats het deelnemersaantal als kleine groene badge rechts in de wedstrijdtegel.
- Toon afstandskeuzes en beheeracties pas nadat de gebruiker een wedstrijd opent.
- Plaats in dezelfde popup een compacte atletenfilter en per afstand de kolommen Trainer, Athlete en Target.
- Gebruik voor onbevestigde wedstrijden een witte pil met oranje of rode omlijning; vul de pil pas wanneer trainer en atleet beiden akkoord zijn.
- Start afstandsbeheer en alle atleten ingeklapt. Toon gekozen afstanden als statuspillen achter de atleetnaam en werk die pillen direct bij wanneer een vinkje verandert.

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
