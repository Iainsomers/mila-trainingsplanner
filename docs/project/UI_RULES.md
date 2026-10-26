# UI- en taalafspraken

Bijgewerkt: 20 oktober 2026.

## Stijl

- Compact, functioneel en rustig; planningsinformatie krijgt voorrang op uitlegtekst.
- Gebruik bestaande Bootstrap-componenten en de huidige MiLa-visuele taal.
- Segmenten, zones, totalen en weektypen mogen als compacte pills worden weergegeven.
- Primaire acties zijn duidelijk; secundaire navigatie gebruikt een outline-stijl.
- Voorkom horizontaal scrollen op mobiel behalve waar een bewust desktopoverzicht wordt gebruikt.
- Gebruik het vaste MiLa-logo als browsericoon en als beginschermicoon op iOS en Android.
- Toon in Athlete Input de geselecteerde atleetnaam voor trainers op een vaste plek boven de tabbladen, zodat die bij iedere tab zichtbaar blijft.
- Plaats naast die atleetnaam compacte `<`- en `>`-knoppen om alfabetisch door de atleten van de actieve coachweergave te navigeren. Behoud het huidige tabblad; schakel de knop aan de lijstgrens uit.
- In New, Plans, Wishes staat `Edit` alleen bij eigen wishes of voor de productbeheerder; andere gebruikers krijgen alleen de beschikbare like-actie.
- Als `See session km` is ingeschakeld, staat het sessietotaal als zwart `T`-getal compact rechtsboven in iedere sessiecel van de AYC, ook mobiel. Als `See session zones` is ingeschakeld, staan daar kleine kleurpillen met alleen de kilometers afgerond op 0,1 km naast; de kleur bepaalt de zone. Het weektotaal gebruikt dezelfde `T`-notatie, zonder `km`-tekst.
- In de linkerbovenhoek van een AM-cel staan één of meerdere kleine dots voor de whereabouts van die dag, ook wanneer er geen training gepland is. De dotkleur volgt de Year Planner-legenda; overlappende whereabouts tonen meerdere dots.
- De coachbrede variant van `See session km` gebruikt dezelfde compacte `T`-notatie zonder `km`-label in Flex Planner en DCO Training. In Flex schuift het label op wanneer rechtsboven ook een rapporticoon staat.

## Terminologie

- Gebruik zichtbaar `Main` en `Main 2`, niet `Core` en `Core 2`.
- Intern mogen `CORE` en `CORE2` blijven bestaan.
- Gebruik binnen één scherm consistente knopnamen. In de mobiele AYC heten zowel training als evaluatie `Open`.
- Bestaande productlabels zijn grotendeels Engels; voeg geen willekeurige mix van Nederlands en Engels toe zonder een bredere vertaalbeslissing.
- Coach Settings > Planning toont de compacte dropdown `P(ause)mode` met `Static unless "ap"` en `Active unless "pp"`.

## Kleuren

- Team Pace gebruikt middengroen (`#2E7D5B`) als kleur 1 en warm aubergine (`#8A4F7D`) als kleur 2. Er is nog geen apart teamlogo.
- Z1 t/m Z6 volgen de bestaande zonekleuren.
- Als één herhaalblok in Flex Planner meerdere zones bevat, krijgt de trainingspil een compacte verdeling van de bijbehorende zonekleuren; de trainings- en weektotalen blijven onafhankelijk hiervan berekend.
- Huidige week: geel.
- Huidige dag binnen die week: donkerder geel.
- Weektype is een gekleurde pil: Recovery, Aerobe, Specific, Intense of Taper.
- Race is oranje; belangrijke `Race!` is rood met witte tekst waar die markering wordt gebruikt.
- Year Planner whereabouts gebruiken vaste onderscheidende kleuren: Camp groen, Travel lichtgroen, Test paars, Championship rood, Diamond L roze, Race Gold goud, Race Silver zilver, Race Bronze brons, Race Other oranje, Expermeetings blauw, Medical geel en Brinec oranje.
- Evaluatie voltooid: groen vinkje.
- Weektypekleur moet zichtbaar blijven naast huidige-weekmarkering.

## Mobiele AYC

- `Watch A` in de trainingsevaluatie toont Type A Polar-resultaten in een schermpassende, intern scrollbare popup met een duidelijke sluitknop.
- Een bruikbare Type A-omschrijving toont de acties `Use AM` en `Use PM` rechts naast de omschrijving; op smalle schermen mogen deze knoppen onder de tekst afbreken.
- Toon één week tegelijk.
- Houd weeknavigatie, totaal en weektype bovenaan goed zichtbaar.
- Iedere trainingsdag toont AM en/of PM; lege dagen blijven compact.
- Gebruik expliciete `Open`-knoppen; dubbelklikken mag nooit nodig zijn.
- Bij `Extended edit rights` blijven de AM- en PM-evaluatievelden zichtbaar en openbaar op lege dagdelen; op toekomstige dagen mag de evaluatieknop niet disabled zijn.
- Training- en evaluatiepopups zijn maximaal schermvullend en intern scrollbaar.
- Toon de microfoonknop alleen op mobiel bij het Comment-label. Tijdens opname heeft de knop een duidelijke actieve toestand; één opname mag herkenningstekst nooit verdubbelen.
- De popup voor openstaande evaluaties toont uitsluitend trainingen van de afgelopen zes kalenderdagen, nooit de huidige dag.
- Bestaande waarden moeten direct bij openen zichtbaar zijn.
- Planner, Dashboard en Logout moeten bereikbaar blijven zonder Admin.
- Toon Week reports onderaan de week als een 2×2-grid met dezelfde vier kleuren als desktop.
- Toon bij Daily vitals een compacte hartknop naast de datum; invoer gebeurt in een schermpassende popup. Plaats deze popup buiten de AYC/team-stackingcontext zodat de Bootstrap-backdrop nooit boven het formulier komt. Na opslaan sluit de popup volledig, inclusief backdrop en `modal-open`-status, zonder een paginareload tijdens de mobiele Bootstrap-transitie.
- Toon de vier weekgemiddelden compact in het weeksamenvattingsblok en gebruik `NA` totdat minimaal drie waarden beschikbaar zijn.

## Desktop AYC

- Behoud de brede tabel en volledige trainingsinformatie.
- Trainerselectie blijft beschikbaar voor trainers.
- Toon alle trainingsonderdelen, zones en tijden.
- Maak toekomstige AYC-trainingen voor atleten visueel niet-bewerkbaar; de coach behoudt de bewerkactie.

## Trainer Planner

- Toon bij een gevulde trainingscel rechtsboven een compacte rode `×` om die specifieke AM- of PM-training direct te verwijderen, gelijk aan de Flex Planner.
- Print de ingestelde 1–12 weken als liggend A4. Verberg navigatie, instellingen, kopieer- en verwijderacties op papier; houd trainingskleuren waar mogelijk aan.
- DCO Training krijgt de Print-knop pas na de atleetselectie en drukt alleen de gekozen atleten, datum en AM/PM-weergave af.

## Year Planner

- Stacked layout is standaard; één, drie of twaalf maanden bepalen de breedte van een stuk.
- Toon na keuze van een Trainer Planning-groep de aparte `Basis - groepsnaam`-planningsrij direct onder `All`; deze keuze is alleen voor trainers zichtbaar. Toon bij de algemene groepskeuze `All` geen gedeelde Basis.
- Houd atleetnamen klein en rijen stabiel van hoogte. Gebruik geen lege placeholder-strepen.
- Whereabouts zijn doorlopende, benoemde ranges. Overlap wordt visueel als diagonale kleurverdeling getoond; de belangrijkste zichtbare naam blijft leesbaar.
- Toon alleen rij-kopieeracties voor de actieve laag: Training of Whereabouts. Plakken werkt alleen binnen het zichtbare periodeblok.
- De atleetweergave is alleen-lezen en toont alleen de legenda van toegestane lagen.

## Stats en DCO

- Stats gebruikt voor atleetselectie dezelfde compacte bediening en dezelfde opgeslagen coachselecties als de Daily Coach Overview.
- Stats scheidt selectie en resultaten in twee stappen. De resultatenkoppen zijn aanklikbaar; afstandskolommen sorteren aflopend en de naamkolom alfabetisch.
- Atleetnamen in Stats zijn aanklikbaar. De detailpagina accepteert een vrij in te vullen heel aantal maanden en toont die periode als een responsieve kilometerstaafgrafiek, met 6 maanden als standaard. Compacte terug- en vooruitpijlen verschuiven steeds één volledige gekozen periode; vooruit is bij de huidige periode uitgeschakeld. Gemiddelde, hoogste en laagste week staan compact onder de grafiek; de pagina vermeldt dat de huidige week nog onvolledig kan zijn.

## Race Calendar

- Houd de lijstweergave compact op één regel: datum, een uitgelijnde naamkolom en bestaande afstanden zijn direct zichtbaar.
- Beperk Add race tot een compacte kaartbreedte en open Race Calendar direct vanuit Races zonder tussenpagina.
- Plaats voor trainers naast Add race eerst een groepsfilter (`All` telt als groep) en daarna een daarvan afhankelijke atleetfilter; laat zowel wedstrijdzichtbaarheid als afstandstellers deze combinatie volgen.
- Geef Add race en de Race filter op desktop dezelfde kaartbreedte.
- Laat de hoofdfilter `Show all races` uitschakelen zodra de groep of atleet wordt gewijzigd. Laat de popupfilter alleen `All`, groepen en `Participating athletes` aanbieden; geen individuele atleten. De popup start standaard op `Participating athletes`. Plaats er een compacte Expand all-schakelaar naast, standaard aan.
- Gebruik in de Race Calendar dezelfde oranje/rode akkoordkleuren als bij wedstrijdpillen; plaats het deelnemersaantal als kleine groene badge rechts in de wedstrijdtegel.
- Toon afstandskeuzes en beheeracties pas nadat de gebruiker een wedstrijd opent.
- Splits de atleet-/afstandskolom in aparte kolommen, zodat naam en afstand direct naast elkaar staan. Houd de rijen compact; de selectiekolommen zijn Trainer, Athlete en Target.
- Gebruik voor onbevestigde wedstrijden een witte pil met oranje of rode omlijning; vul de pil pas wanneer trainer en atleet beiden akkoord zijn.
- Start afstandsbeheer ingeklapt en de atleten uitgeklapt. Toon gekozen afstanden als statuspillen achter de atleetnaam en werk die pillen direct bij wanneer een vinkje verandert.

## Formulieren

- Zet vaste scheidingstekens voor tijdformaten visueel vast waar mogelijk.
- Toon invoerformaten bij complexe PR-velden.
- Behoud ingevoerde waarden na validatiefouten.
- Een popup mag niet groter worden dan het viewport en de opslaanknop moet bereikbaar blijven.
- In Athlete Input heet de zone-tab `Zones. HR, Speed`; binnen die tab staat de sectie `Current times`.
- Focus Points gebruikt een compacte, horizontaal scrollbare matrix op smalle schermen. De focuspuntkolom blijft zichtbaar en Prio is altijd smal. Coachcomments in Comment coaches staan inline en bovenaan uitgelijnd, met initialen uit eerste/laatste username-deel (`Voornaam_Achternaam`) en de volledige tekst in de vaste kleur van die coach. Plan en Progress tonen gewone gedeelde tekst zonder auteur/initialen; een trainer met editrechten overschrijft daar de bestaande tekst. Het kleine plusje staat rechtsboven zonder de commentaarregel omlaag te duwen. De Comment coaches-popup heeft alleen een klein `Overwrite`-vinkje rechtsboven, zonder extra uitlegtekst.
- Focus Points toont Prioriteit compact als —, 🥇, 🥈 of 🥉; klikken opent een klein menu met de vier opties. Er is per atleet maximaal één gouden, zilveren en bronzen medaille; bij een nieuwe keuze schuiven gelijke/lager gerangschikte punten door, waarbij een punt voorbij brons geen medaille meer heeft. De drie Other-namen kunnen met een klein plusje bij de naam per atleet worden aangepast; zonder opgeslagen naam blijven de labels `Other 1`, `Other 2` en `Other 3`.
- In de Year Planner ziet een atleet altijd alleen de eigen atletenrij; geen selectieparameter of coachinstelling mag andere atletenrijen tonen. Gedeelde coach-whereabouts kunnen read-only als aparte coachrij worden getoond.
- Met `See desired improvement points` ziet een atleet standaard alleen Focus point en de eigen kolom `Comments athletes`; coachcommentaren blijven verborgen. De coach kan boven de kolom `Plan` per atleet de schuif `Show to athlete` gebruiken; alleen wanneer die aanstaat worden Prio, Plan en Progress aan de atleet getoond. Plan/Progress tonen geen coachinitialen of auteursinformatie. Coaches zien de ingevulde athlete-comments in het volledige overzicht.
- Focus Points biedt trainers met editrechten naast de atleetselector een compacte `.xlsx`-import voor `Comment coaches`; op smalle schermen mag deze onder de selector staan. Gebruik een eigen grid voor deze controls zodat de desktopuitlijning niet afhankelijk is van Bootstrap-formrastergedrag. Toon vóór import een expliciete bevestigingscheckbox en maak duidelijk dat alleen niet-lege cellen de eigen bestaande comments voor atleten in het bestand vervangen; lege cellen en comments van andere trainers blijven behouden. Plan/Progress verandert niet.

## Responsiviteit controleren

Controleer bij relevante UI-wijzigingen minimaal:

- smalle telefoonweergave;
- normale desktopweergave;
- openen, sluiten en opslaan van popups;
- AM en PM afzonderlijk;
- trainer- en atleetrol.

## Trainingspopups en teambekleding

- De dynamische trainingspopups in AYC, Flex Planner en Trainer Planning worden onder `document.body` geplaatst, buiten de stacking context van de teambekleding. Daardoor blijven zij boven de Bootstrap-backdrop klikbaar op desktop en mobiel.

## Polar-knoppen

Polar Integration en de Type A/B/C/D-dataweergave gebruiken witte knoptekst op gevulde primaire/secundaire knoppen. Teamkleur 2 overschrijft deze tekstkleur niet.

## Polar en DCO Other

- Type C toont ruw/verwerkt min/km, werkelijk venster, status en reden naast elkaar; op smalle schermen staan meetregels als compacte vakken met eigen labels.
- Type D toont tempo-km en HR-km in één compacte tabel, inclusief Unclassified en totaal. HR-invoer heeft vier bovengrenzen en zichtbare Estimated/Remember-keuzes. Bij wisselen van atleet worden diens grenzen opnieuw geladen.
- De optionele AI-toelichting staat los van de vaste tabel. Een niet-beschikbare AI blokkeert het kilometeroverzicht niet. Original Polar JSON staat ingeklapt.
- DCO Other behoudt Vitals als geopende sectie bij vitalkeuze. Show NA is standaard uit en blijft behouden bij wisselen; zonder vinkje worden alleen gemiddelden met minimaal drie bruikbare waarden getoond.
- DCO Other toont naast de vier gemiddelden een `HR zones`-knop met een compacte tabel: atleten verticaal, Z1–Z5 horizontaal. Niet-aansluitende, zelf ingevoerde grenzen krijgen rode tekst; `Show NA` werkt ook voor deze tabel.
