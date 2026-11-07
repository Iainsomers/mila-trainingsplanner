# UI- en taalafspraken

Bijgewerkt: 20 oktober 2026.

## Stijl

- Athlete Settings > General heeft `Automatically import Oura vitals` met uitleg over het lokale controleschema, de bekende apparaattijdzone en de laatste controle. Het vinkje is standaard uit en beschikbaar voor de atleet zelf en bevoegde trainers.

- De klokjespopup heeft achter min/km de kolommen `Avg HR` en `Last 15s HR`, in die volgorde. Ontbrekende gegevens tonen `NA`.

- De AYC-klokjespopup toont achter min/km ook `Last 15s HR`, voor zowel reps als afstandssplits. Ontbrekende metingen worden als `NA` getoond.

- Het AYC-klokje toont bij een duurloop met kilometerlaps de titel `Recorded splits`, met Lap, Distance, Time en min/km. Het laatste korte restant krijgt een eigen regel. Herhaaltrainingen behouden de repweergave.

- Na Use AM/PM staat naast het AYC-klokje een compacte `p/w`-knop. Die opent een kleine popup met `Watch` en `Plan`; de actieve versie is gemarkeerd. Het klokje toont in beide standen de bewaarde Watch-reptijden. De keuzepopup volgt de bestaande trainingsbewerkrechten en staat buiten de team-stackingcontext.

- Flex Planner-rijen groeien mee met de training, met 48 px als minimum. Gebruik rondom de training slechts 2 px verticale padding; reserveer geen lege strook onderaan.
- Compact, functioneel en rustig; planningsinformatie krijgt voorrang op uitlegtekst.
- Gebruik bestaande Bootstrap-componenten en de huidige MiLa-visuele taal.
- Segmenten, zones, totalen en weektypen mogen als compacte pills worden weergegeven.
- Primaire acties zijn duidelijk; secundaire navigatie gebruikt een outline-stijl.
- Voorkom horizontaal scrollen op mobiel behalve waar een bewust desktopoverzicht wordt gebruikt.
- Gebruik het vaste MiLa-logo als browsericoon en als beginschermicoon op iOS en Android.
- Toon in Athlete Input de geselecteerde atleetnaam voor trainers op een vaste plek boven de tabbladen, zodat die bij iedere tab zichtbaar blijft.
- Plaats naast die atleetnaam compacte `<`- en `>`-knoppen om alfabetisch door de atleten van de actieve coachweergave te navigeren. Behoud het huidige tabblad; schakel de knop aan de lijstgrens uit.
- Gebruik in de Race Calendar-popup dezelfde kolombreedtes voor de kop, atleetrij en afstandsrij. De afstandswaarde en de checkboxen moeten op desktop en mobiel exact onder Distance, Trainer, Athlete en Target uitlijnen.
- In New, Plans, Wishes staat `Edit` alleen bij eigen wishes of voor de productbeheerder; andere gebruikers krijgen alleen de beschikbare like-actie.
- Als `See session km` is ingeschakeld, staat het sessietotaal als zwart `T`-getal compact rechtsboven in iedere sessiecel van de AYC, ook mobiel. Als `See session zones` is ingeschakeld, staan daar kleine kleurpillen met alleen de kilometers afgerond op 0,1 km naast; de kleur bepaalt de zone. Het weektotaal gebruikt dezelfde `T`-notatie, zonder `km`-tekst.
- In de linkerbovenhoek van een AM-cel staan één of meerdere kleine dots voor de whereabouts van die dag, ook wanneer er geen training gepland is. De dotkleur volgt de Year Planner-legenda; overlappende whereabouts tonen meerdere dots.
- De coachbrede variant van `See session km` gebruikt dezelfde compacte `T`-notatie zonder `km`-label in Flex Planner en DCO Training. In Flex reserveert de volledige sessiesamenvatting rechtsboven ruimte voor evaluatie-iconen, zodat de zonekilometers er niet onder vallen.
- In Details Camps kan een trainer met voldoende editrechten de kampnaam direct via de titel bewerken; de titel blijft visueel compact en wordt pas na een klik een invoerveld.
- Staff Team Overview opent met een compacte lijst van de toegankelijke atleten en twee duidelijke keuzes: Vitals en Information Quality. De gekozen weergave blijft team-breed.

## Terminologie

- Gebruik zichtbaar `Main` en `Strength`, niet `Core` en `Core 2`.
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

- De geïnstalleerde mobiele app start via de loginroute. Als een bestaande beginscherm-snelkoppeling rechtstreeks de rootpagina opent, brengt `Start op AYC` een ingelogde atleet alsnog naar de eigen AYC; een Dashboard-link binnen de app blijft werken. Trainers en atleten zonder die voorkeur gaan naar het dashboard.
- In de AM/PM-evaluatiepopup staat `Pain` compact naast RPE. Gebruik de opties 🟢 Fit, 🟠 Some issues, pls explain! en 🔴 Serious issue, talk to staff!; de standaardkeuze is Fit. Verberg de keuzelijst wanneer de coachinstelling uitstaat.
- In de AYC-trainingsevaluatie heten de horlogeknoppen `Polar A`, `Polar B` en `Garmin C`. Een compacte, aanklikbare klokindicator rechtsboven in een AM/PM-cel markeert een overgenomen horlogetraining en opent een mobiel-passende popup met de verwerkte Main-reps: afstand, tijd en min/km. Toon de indicator ook als de sessietotalen uitstaan.
- De Garmin C-lapresultaten tonen ook `Last 15s HR`; op smalle schermen moet de tabel horizontaal te scrollen zijn zodat alle kolommen bereikbaar blijven.
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

- Periodisatie bevat ook `Racing` in mediumblauw (`#4a90d9`), donkerder dan Intense. Dit is een bewerkbare trainingsfase; geselecteerde wedstrijden behouden hun eigen racetypekleuren en blokkade.
- Bij het aan-/uitvinken van atleten of coaches blijven de scrollposities van beide selectielijsten en de pagina behouden na de automatische herlaadactie. Een nieuwe groepskeuze begint met de eigen lijstpositie.
- Recovery in de periodisatie gebruikt lichtpaars (`#e4d4f4`) in zowel de kalender als de legenda.
- Toon onder iedere datum in de tabelkop de eerste Engelse weekdagletter: M, T, W, T, F, S, S; hover op de kop toont de volledige Engelse dagnaam en datum.
- Alleen periodisatieblokken hebben links en rechts een compacte sleepgreep om de begin-/einddatum aan te passen. De grepen ondersteunen muis en aanraking, tonen tijdens slepen de nieuwe omvang en stoppen bij wedstrijden. Racecellen krijgen geen sleepgrepen. De bestaande fasekeuze en Whereabouts-bediening blijven beschikbaar.
- De zichtbaarheidsschakelaar naast `Whereabouts` heet `Periodisation/Races`; intern blijft deze laag `training`.
- Wedstrijden staan uitsluitend in de Training-laag van hun atleet, in de Race Type-kleur uit de legenda. De racenaam staat compact vast in de gekleurde cel (met ellipsis bij ruimtegebrek); hover toont de voor die atleet geselecteerde afstand(en). Op wedstrijddagen ontbreken de trainingsfasedropdown en schilder-/plakacties; Whereabouts blijft afzonderlijk bewerkbaar. Meerdere wedstrijden delen de celkleur.
- Plaats de `Race Calendar`-knop naast de legenda; op smalle schermen mag hij naar een volgende regel. Bij de geopende racelijst heet de knop `Back to Yearplanner`. De knop wisselt tussen planner en de geïntegreerde racelijst, zonder de plannerselectie te wissen. Binnen deze racelijst is geen Calendar-keuze beschikbaar.
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

- Add race heeft een Race Type-dropdown met de bestaande zes categorieën; standaard is Race Other geselecteerd. Het type wordt direct bij het aanmaken opgeslagen.
- Add race toont standaard één Date-veld met daaronder de compacte optie `Multiple days`. Inschakelen toont `Until`; dit veld is alleen dan verplicht. Toon bij meerdaagse races start- en einddatum in de lijst/popup, zonder extra velden voor gewone eendaagse races.
- Plaats Group, Athlete en Race Type naast elkaar in het racefilter; op telefoonbreedte staan ze onder elkaar. Race Type heeft All en de bestaande zes categorieën.
- `Delete race` staat linksonder in de wedstrijdpopup; `Close` blijft rechts. Verwijderen is uitgeschakeld zolang Trainer, Athlete of Target bij een atleet is aangevinkt, onafhankelijk van de zichtbare filters. De knop wordt na automatisch opslaan bijgewerkt.
- Het Races-lijstblok is op desktop circa 40% breed, met minimaal 640 px voor leesbare kolommen; op smallere schermen gebruikt het de beschikbare breedte.
- Toon onder Manage distances een compacte Race Type-dropdown. Iedere wedstrijdregel heeft een omlijning van 3 px met links een kleurstrook van 6 px in de Year Planner-legendakleur: Championship rood, Diamond League roze, Gold goud, Zilver zilver, Bronze brons en Other oranje.
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

- De evaluatiepagina met Honoré Hoedts coachkolommen gebruikt op brede schermen maximaal 1800 px: circa 25% voor Questionnaires en 75% voor Filled forms, zodat Plan naast Coach comment past. Op smallere schermen komen deze blokken onder elkaar; tabellen blijven mobiel scrollbaar.
- Bij het ingevulde formulier `Evaluatie seizoen 2025-2026` van Honoré Hoedt staan `Coach comment` en `Plan` als twee compacte tekstkolommen naast iedere antwoordregel, inclusief matrixregels. Sla op bij verlaten van het veld en toon Saving/Saved/foutstatus per formulier. Brede tabellen mogen op mobiel horizontaal scrollen.
- Zet vaste scheidingstekens voor tijdformaten visueel vast waar mogelijk.
- Toon invoerformaten bij complexe PR-velden.
- Behoud ingevoerde waarden na validatiefouten.
- Een popup mag niet groter worden dan het viewport en de opslaanknop moet bereikbaar blijven.
- In Athlete Input heet de zone-tab `Zones. HR, Speed`; binnen die tab staat de sectie `Current times`.
- Focus Points gebruikt een compacte, horizontaal scrollbare matrix op smalle schermen. De focuspuntkolom blijft zichtbaar en Prio is altijd smal. Coachcomments in Comment coaches staan inline en bovenaan uitgelijnd, met initialen uit eerste/laatste username-deel (`Voornaam_Achternaam`) en de volledige tekst in de vaste kleur van die coach. Plan en Progress tonen gewone gedeelde tekst zonder auteur/initialen; een trainer met editrechten overschrijft daar de bestaande tekst. Het kleine plusje staat rechtsboven zonder de commentaarregel omlaag te duwen. De Comment coaches-popup heeft alleen een klein `Overwrite`-vinkje rechtsboven, zonder extra uitlegtekst.
- Focus Points toont Prioriteit compact als —, 🥇, 🥈 of 🥉; klikken opent een klein menu met de vier opties. Er is per atleet maximaal één gouden, zilveren en bronzen medaille; bij een nieuwe keuze schuiven gelijke/lager gerangschikte punten door, waarbij een punt voorbij brons geen medaille meer heeft. De drie Other-namen kunnen met een klein plusje bij de naam per atleet worden aangepast; zonder opgeslagen naam blijven de labels `Other 1`, `Other 2` en `Other 3`.
- In de Year Planner ziet een atleet altijd uitsluitend de eigen atletenrij en eigen whereabouts; geen selectieparameter of coachinstelling mag andere atleten- of coachrijen tonen.
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

- De dynamische trainingspopups in AYC, Flex Planner en Trainer Planning worden onder `document.body` geplaatst, buiten de stacking context van de teambekleding. De AYC-`today`-popup hoort hier ook direct onder `document.body`: de backdrop wordt daar geplaatst en mag de dialoog niet afdekken. Daardoor blijven popups boven de backdrop klikbaar op desktop en mobiel.
- De Oura-importpopup in AYC wordt ook direct onder `document.body` geplaatst. Na opslaan moet eerst de popup/backdrop volledig worden opgeruimd voordat de AYC wordt vernieuwd; dit voorkomt een onklikbare overlay op mobiel.

## Polar-knoppen

Polar Integration en de Type A/B/C/D-dataweergave gebruiken witte knoptekst op gevulde primaire/secundaire knoppen. Teamkleur 2 overschrijft deze tekstkleur niet.

## Meeting requests

- In Athlete Settings staat `Request meeting`; na aanvraag verandert dit in de datumstatus met een compacte X-annuleerknop.
- DCO Other toont een compacte statusknop bij Info Quality: groen 0–2 dagen, oranje 3–5 dagen en rood vanaf 6 dagen.
- Nieuwe aanvragen tonen de hoofdcoach een Bootstrap-popup met de naam van de atleet; OK markeert de getoonde aanvragen als gezien.

## Polar en DCO Other

- Type C toont ruw/verwerkt min/km, werkelijk venster, status en reden naast elkaar; op smalle schermen staan meetregels als compacte vakken met eigen labels.
- Type D toont tempo-km en HR-km in één compacte tabel, inclusief Unclassified en totaal. HR-invoer heeft vier bovengrenzen en zichtbare Estimated/Remember-keuzes. Bij wisselen van atleet worden diens grenzen opnieuw geladen.
- De optionele AI-toelichting staat los van de vaste tabel. Een niet-beschikbare AI blokkeert het kilometeroverzicht niet. Original Polar JSON staat ingeklapt.
- DCO Other behoudt Vitals als geopende sectie bij vitalkeuze. Show NA is standaard uit en blijft behouden bij wisselen; zonder vinkje worden alleen gemiddelden met minimaal drie bruikbare waarden getoond.
- DCO Other toont naast de vier gemiddelden een `HR zones`-knop met een compacte tabel: atleten verticaal, Z1–Z5 horizontaal. Niet-aansluitende, zelf ingevoerde grenzen krijgen rode tekst; `Show NA` werkt ook voor deze tabel.

In de Year Planner scheidt een 2px grijze lijn de opeenvolgende atleet-/coachrijen. Het raster en de scheiding tussen Periodisation/Races en Whereabouts binnen één atleet blijven dun.

Information Quality toont `Last active in MiLa` als datum en tijd. De compacte pill is groen bij vandaag, oranje bij gisteren en rood bij oudere kalenderdagen, volgens Europe/Amsterdam. Zonder registratie staat NA zonder kleur. De bestaande responsive tabel blijft behouden.

Information Quality reserveert 28% voor de atleetnaam en verdeelt de vier informatiekolommen gelijkmatig (elk 18%). Koppen, pills en NA zijn per informatiekolom gecentreerd. Op mobiel blijft de tabel horizontaal bereikbaar via de bestaande scrollcontainer.

De AYC controleert voor de atleet na een uur zonder interactie opnieuw op openstaande evaluaties, ook bij terugkeer uit de achtergrond. De popup gebruikt verse gegevens zonder paginareload; een geopende evaluatiepopup wordt niet onderbroken.

Race Calendar-lijst gebruikt op brede schermen drie gelijkmatig gevulde kolommen, chronologisch eerst omlaag en dan naar rechts. Extra wedstrijden komen eerst links (22 wordt 8/7/7). Onder 1200px staan de kolommen onder elkaar in dezelfde volgorde. De periodekeuze bevat ook seizoen (1 oktober t/m 30 september).

Race Calendar-popup: Athlete, Attend, Distance, Trainer, Athlete, Target gebruiken gedeelde gridbreedtes op desktop en mobiel. Attend staat eenmaal op de eerste afstandsrij (ook bruikbaar zonder afstanden); Distance-kop en afstandswaarden zijn gecentreerd op dezelfde kolom.

Race Calendar toont tussen wedstrijdnaam en afstanden het aantal Attend-selecties zonder geselecteerde afstand als hetzelfde groene bolletje als de afstandsaantallen. Nul wordt verborgen. De telling volgt de actieve groep-/atleetfilter en wijzigt direct na opslaan van selecties.

Add race: naam en begindatum krijgen elk een halve rij; Add staat op de volgende rij naast Race Type en Multiple days. Hierdoor blijft de volledige begindatum leesbaar. Op mobiel stapelen de velden en knop.

Year Planner toont aaneengesloten dagen van dezelfde wedstrijd als één doorlopende pil met één naam per zichtbare kalenderstrook. Bij een maand-/strookgrens begint een nieuwe pil; de dagelijkse raceblokkade en afstand-hover blijven bestaan.

De wisselknop Race Calendar / Back to Yearplanner staat gecentreerd naast de legenda, heeft in beide standen dezelfde breedte (196px), donker MiLa-blauw (#17324d), gele semibold tekst en een richtingspijl. Op mobiel mag hij onder de legenda afbreken en is hij minimaal 44px hoog.

Year Planner-wisselknop gebruikt gele tekst (#f2c200) op donkerblauw, ook bij hover. Daarnaast staat een gelijkvormige Details Camps-knop voor gebruikers die campdetails mogen zien. De trainerplanning heeft geen losse Races-tegel meer; Details Camps blijft staan. De eigen Races-ingang voor atleten blijft beschikbaar.

De atleetweergave van Race Calendar toont dezelfde groene deelnamebolletjes bij de eigen geselecteerde afstanden en eigen Attend zonder afstand (waarde 1). Ook deze bolletjes verversen na opslaan. Deelname van andere atleten telt daar niet mee en wordt niet getoond.

## Information Quality — ALL-rij

De eerste tabelrij heet ALL en toont de gemiddelde Evaluated- en Vitals-percentages met dezelfde kleurpillen als de atleetrijen. Last active en Meeting request blijven in deze rij leeg.

Garmin C toont bij bruikbare activiteiten een Combine-vinkje en compacte WU/Main/CD-keuze. De bovenste Combine-knop werkt bij twee of drie selecties en toont rolproblemen bij de knop. De gecombineerde preview staat bovenaan; wijzigen van een selectie/rol verwijdert de oude preview. Bediening en beschrijvingsknoppen lopen op smalle schermen door naar de volgende regel; laptabellen blijven horizontaal scrollbaar.

Garmin Combine blijft zichtbaar bij bruikbare lapdata zonder herkende trainingsstructuur. Zo’n activiteit biedt WU en CD, met Main uitgeschakeld; standaard wordt WU gekozen.

Garmin D staat naast Garmin C in de evaluatiepopup en gebruikt dezelfde compacte/mobile bediening. De D-tabel toont Pace Zx naast HR Zx (kolom 7, de effectieve zone) en End HR. Een korte toelichting benoemt de grens 400m of 50s en fallback bij ontbrekende HR/limieten. Opgeslagen D-resultaten tonen Garmin D bij het klokje en ondersteunen dezelfde p/w-wissel en combineren.

Garmin C en D tonen bij gemeten WU/CD alleen het gemiddelde tempo in min/km: totale gemeten duur gedeeld door totale gemeten afstand. Deel-/laptijden en temporanges verschijnen daar niet meer achter. De Main-repweergave en klokdetails blijven behouden.

Bij Garmin C én D tonen Main-blokken op tijd (minuten/seconden) achter de training uitsluitend het gemeten tempo of temporange in min/km. Main-blokken op afstand tonen zowel reptijd(en) als tempo. WU/CD behouden hun ene gemiddelde tempo. De klokdetails veranderen niet.

De vier losse dagelijkse-vitaltabs zijn samengevoegd tot Daily vitals; HR zones blijft apart. De compacte tabel heeft Athlete plus vier vitalkolommen met gemiddelde (low–high). Ranges staan gedempt tussen haakjes. De bestaande table-responsive-container houdt het overzicht op mobiel horizontaal scrollbaar. Show NA blijft bij tabwisselen behouden.

Camp details: Comments staat direct na Accommodation, als compact tekstvak van één regel dat verticaal vergroot kan worden. De kolom is sorteerbaar en blijft onderdeel van de horizontaal scrollbare deelnemerstabel op mobiel.

Bij dubbelzinnige lange Garmin-intervalgroepen staan twee compacte knoppen Distance en Time boven de gegenereerde beschrijving, met de actieve keuze gevuld. Wisselen past de preview en de Use AM/PM-inhoud aan en verwijdert een eerder gecombineerde preview, zodat geen verouderde keuze wordt opgeslagen. De knoppen lopen op mobiel naar een volgende regel door.

Details Camps heeft vooraan een smalle #-telkolom. De telling volgt uitsluitend de zichtbare rijvolgorde, begint bij 1 en loopt door over atleten en coaches. Na sorteren wordt opnieuw genummerd; dit zijn geen opgeslagen persoonsnummers.


Garmin C/D tonen End HR in de rondetabel en klokpopup; de klok legt uit: laatste 10% van de gemeten repduur, minimaal 15s, Avg HR onder 15s. Avg HR blijft een aparte kolom. Polar behoudt Last 15s HR. De bestaande compacte, scrollbare tabellen blijven behouden.


Stats-weekbalken tonen Z1 onderaan gevolgd door Z2–Z6 in de AYC-zonekleuren. Een dunne rand houdt het lichte Z1 zichtbaar; de compacte legenda kan afbreken en de grafiek blijft op mobiel horizontaal scrollbaar. Hover toont zonekilometers en het weektotaal.


DCO Training gebruikt dezelfde gedeelde pillenkleuring als Flex Planner. Progressieve zones (zoals z2>z3), meerdere zones binnen samengestelde reps en T-bereiken krijgen dezelfde diagonale, gelijk verdeelde kleurvlakken. Gewone éénzonepillen behouden hun bestaande achtergrond. Dit geldt voor AM/PM, mobiel en de printweergave.


Trainingsfoto’s: compacte Add photos-knop naast de Strength-kop, maximaal vijf in totaal, thumbnails van 64px onder het Strength-tekstveld. De browser biedt foto maken/kiezen waar ondersteund. Iedere bestaande thumbnail heeft bij bewerken een Remove-vinkje; wijzigingen worden met Save opgeslagen. Klikken opent de grote foto met browserzoom. Dezelfde thumbnails staan bij Strength (of bij het oorspronkelijke Mob/Tech-segment voor bestaande foto’s) in de trainingsweergaven en DCO; ze stoppen doorklikken op de achterliggende trainingscel. Bestandsfouten verschijnen bij het veld.


Alternative-weektotalen in AYC en de live Flex-telling behouden halve minuten bij progressieve zones, met maximaal één decimaal en zonder overbodige .0. De bestaande meerzonekleuren blijven van toepassing.

Injury/Issue Overview gebruikt een compacte tabel met naam en 5–25 ronde groen/geel/rood-indicatoren (schuifje, standaard 5), oudste links en nieuwste rechts. Grijs betekent ontbrekende data. De legenda en navigatie mogen op mobiel ombreken; de tabel heeft geen desktop-minimumbreedte. Elke indicator heeft een datum-/AM-PM-/statuslabel voor toegankelijkheid en hover.


Injury/Issue-indicatoren zijn toetsenbordbedienbare knoppen wanneer een evaluatie bestaat. Ze openen een alleen-lezen popup met statuskleur/-teken, evaluatietekst en RPE. Meer indicatoren lopen op mobiel naar een volgende regel door; de modal staat buiten de pagina-container en kan verticaal scrollen. De schuif toont het actuele aantal naast het label en in de tabelkop.

Injury/Issue Overview heeft naast de statusreeks een Comments coaches-cel met de auteursteksten in hun vaste trainerkleur en een + rechts. De + opent de eigen commentaartekst; er is geen overschrijven van andere auteurs. Op smalle schermen staan naam, bolletjes en commentaar onder elkaar. See training wisselt van evaluatiepopup naar een afzonderlijke scrollbare trainingspopup met terugknop; beide popups staan buiten de pagina-container.

Strength (CORE2) is een vrij tekstveld zonder zoneplicht en zonder parse-feedback. Het gedeelde formulier toont alle segmenten onder elkaar; de volgorde is per training instelbaar, ook mobiel. De trainingsweergave volgt de opgeslagen segmentvolgorde; zonder aangepaste volgorde geldt WU, Mob/Tech, Strength, Sprint, Main, Alternative, CD. Strength-tekst heeft geen hardloopzonekleur, richttempo of automatisch voorvoegsel in de trainingsweergave. Het formulierveld blijft Strength heten.

Trainingbuilder: één kolom op desktop en mobiel. Naast elke segmentkop staan ↑/↓ en een sleepgreep; de pijltjes aan de boven-/ondergrens zijn uitgeschakeld. Read-only-velden hebben geen verplaatsknoppen. De modal kan verticaal scrollen en de Save-bediening blijft mobiel onderaan beschikbaar. Ook de trainingscellen tonen elk segment op een eigen compacte regel in de gekozen volgorde.


De hoofdknoppen Save/Cancel (en Delete/Reset waar beschikbaar) staan in een vaste footer buiten het scrollbare veldgedeelte, op desktop én mobiel. Save/Load standard staat daaronder helemaal onderaan de modal. Alle knoppen blijven deel van hetzelfde formulier, zodat HTMX en AYC dezelfde opgeslagen velden blijven gebruiken.

Trainer Planner gebruikt voor meerzonekleuren dezelfde gedeelde routine als Flex Planner en DCO. Een bereik toont alle tussenliggende zones met gelijke kleurstroken: Z2>Z4 geeft Z2, Z3 en Z4; een dalend bereik houdt de omgekeerde volgorde. Dit geldt ook na HTMX-verversingen en bij afdrukken. Eén zone houdt zijn gewone kleur.

Garmin D: HR Zx toont de HR-zone van de End HR van de betreffende tabelregel. Geen getoonde HR-zone mag uit Pace Zx of alleen uit een geslaagde trainingsherkenning worden afgeleid; ontbrekende HR/grenzen tonen NA. Dit geldt voor handmatige en automatische laps.


Championships in Trainer Planner (5 november 2026): alle RaceEvent-records met race_type=championship van de planeigenaar verschijnen als extra rode pill in de juiste dagkop van elk trainerplan. Alleen evenementnaam; geen deelnemers, afstanden of deelnamefilter. Meerdaagse evenementen gelden inclusief einddatum en worden op de zichtbare weken begrensd. Meerdere evenementen leveren aparte pills; titels worden geescaped, breken af in smalle kolommen en blijven in Print weeks zichtbaar. Geen trainingsslots, kopieerdata of kilometers toegevoegd. Toegang volgt het bestaande plan-/coachbereik, ook gedeelde view-only coach. Vijf gerichte championship-/kleurtests en manage.py check geslaagd; geen migratie. Visuele desktop-/mobiele controle nog niet uitgevoerd.


Evaluatie per dagdeel (5 november 2026): desktop AM-/PM-previewhelften en mobiele AM-/PM-knoppen openen uitsluitend hun eigen evaluatie. Popup toont datum/dagdeel en actuele weergegeven training (alle tekstsegmenten in weergavevolgorde, veilig als tekst); Watch/Plan-keuze blijft gevolgd. Alleen zichtbare dagdeel wordt gevalideerd/opgeslagen; bestaand status/RPE/pain/commentaar en Watch-resultaat van het andere dagdeel blijven ongemoeid. Herinnering Evaluate opent de bijbehorende slot_index. Compacte flex-popup met scrollbaar middendeel, vaste ombrekende knoppen, 16px mobiele invoervelden, max92dvh en toetsenbordbediening desktop. 9 gerichte tests inclusief werkelijk uitgevoerde JS-open-/savehandlers, behoud PM bij AM-opslag, bestaande evaluatie-/pain-/herinnerings-/mobieltests en manage.py check slagen. Synthetische gerenderde popup visueel gecontroleerd in Chromium op 390x844 en 1440x900; mobiel 390px documentbreedte en dialoog volledig binnen viewport. Geen migratie; productiecontrole nog niet uitgevoerd.


Garmin C/D toont direct na het gemeten verzoek de laps en bestaande trainingskeuzes. Een compacte regel meldt de lopende AI-analyse. Bij reeds begonnen interactie vervangt AI de resultaten pas na Show analysis. Een oudere reactie mag een later geopende C/D-popup niet overschrijven. De melding/knop gebruikt bestaande compacte Bootstrap-stijl, zonder vaste breedte.


6 november — ALT-resultaten hebben Use AM, Use PM, Add AM en Add PM in dezelfde compacte, ombrekende actieregel. Gewone hardloopresultaten behouden uitsluitend Use AM/PM.


Information Quality heeft een compacte Show NA-schuifschakelaar boven de tabel, standaard uit, met GET-parameter show_na=1 voor ingeschakelde weergave. Geen vaste breedte; bestaande tabel blijft op mobiel horizontaal schuifbaar.


Hardware acces is de exacte coachtegelnaam. Het hardwareoverzicht gebruikt dezelfde MiLa-kaarten, één kolom op mobiel, twee vanaf md en drie vanaf lg, met Dashboard-terugknop. Atleetdashboard ongewijzigd.


6 november — Evaluations-tegel verplaatst van Dashboard naar Planning > Views, voor coaches en atleten. De instelling evaluations_enabled van de actieve coach/eigen coach en coach-tools-only-beperking blijven van kracht. Bestaande evaluatiepagina, rechten en inhoud ongewijzigd. Tegel gebruikt responsieve Planning-kolommen. Gerichte evaluatieflow en modulezichtbaarheid voor coach/atleet plus manage.py check gecontroleerd.


Under Dev staat als schuif onder Modules in Coach Settings. Op dashboard vervangt deze optionele tegel Stats en Hardware acces; het submenu gebruikt dezelfde responsieve MiLa-kaarten. Hardware acces verwijst terug naar Under Dev.


Planning > More groepeert Coach tools, Under Dev, Settings en New, Plans, Wishes als bestaande compacte planningkaarten, één kolom op mobiel/twee vanaf md/vier vanaf lg. Alleen New, Plans, Wishes geldt ook voor atleten. Under Dev verwijst terug naar Planning.


Planning bevat View as coach boven de tegelsecties, met bestaande view-only-waarschuwing. De kiezer blijft maximaal360px breed en past op mobiel. Onderliggende templates hebben geen directe Dashboard-/root-terugknoppen meer.


Atleten: Garmin connection behoudt alle bestaande toestemmingsvelden/acties maar staat onder Planning; Garmin uploads staat ernaast/eronder in responsieve kaartgrid. De coachhardwaregroep blijft ongewijzigd.


6 november — hoofdpagina /planning/ heet nu Mila Planner (paginakop en browsertitel). Evaluations heeft een Back-knop naar deze hoofdpagina. Bestaande terugknoppen naar planning_overview met label Planner/Planning/Back to Planning heten consequent Back; links naar specifieke planners en annuleerknoppen blijven ongewijzigd. Gerichte titel-/evaluatienavigatie-/module-/coachselectietests en manage.py check geslaagd.


Atleten: More bevat Hardware naast New, Plans, Wishes in responsieve grid. Hardware opent een eigen overzicht met Back en bestaande Garmin-inhoud. Planning-tegellabels voor coach Athletes en atleet Athlete settings zijn beide Athlete info. Ontbrekende Back-knoppen toegevoegd aan coachtools, wishes en settings.


Gebruik Athlete Diary, General Plans en Individual planner in tegels/paginakoppen/toelichting. De bestaande start-op-AYC-instelling heet Start on Diary en legt uit dat deze naar het dagboek start in plaats van Mila Planner.


Tegeltitels gebruiken voortaan een hoofdletter aan het begin van elk woord, inclusief And/Under/Development. Bijvoorbeeld Athlete Info, Coach Tools, Garmin Uploads (Under Development). Productnamen en acroniemen blijven intact; vrije gebruikersinhoud wordt niet gewijzigd. Officiële labels: Individual Plans, Improvements, Camps.


Mila Planner gebruikt uniforme col-md-6 col-lg-4 tegels: drie naast elkaar op desktop, twee op middelgrote schermen, één op mobiel. Gewone tegels hebben minimumhoogte116px; More-tegels80px met compacte padding/tekst. Mobiel groeit hoogte bij lange inhoud. Standard Trainings is een compacte More-tegel met twee bestaande standaardonderdelen in submenu.


6 november — More toont op desktop vier compacte tegels per rij (col-lg-3); overige categorieën behouden drie (col-lg-4). Middelgrote schermen twee en mobiel één. Gerichte grid-/navigatietest en manage.py check geslaagd.


6 november — More staat op laptop/desktop in één automatische rasterrij, ongeacht vier/vijf zichtbare tegels. Vanaf992px minder padding/witruimte, hoofdtegels80px en More64px; bij schermhoogte<=760px respectievelijk64/56px. Mobiel behoudt bestaande stapeling en automatische inhoudshoogte. Geen overflow verbergen of pagina-afkapping.


6 november — coachtegels volgen expliciet rechts-naar-links per rij. Coach Plannings: Athlete Info, General Plans, Individual Plans, Year Planner, Improvements, Camps, Evaluations. Views: Athlete Diary, Staff Team Overview, Daily Coach Overview Training. More: New/Plans/Wishes, Settings, Coach Tools, Under Dev, Standard Trainings. Flex row-reverse op meerkolomsrijen; More-grid rechts-naar-links met links-naar-rechts tekst. Mobiel volgt de opgegeven lijst van boven naar beneden. Atleten houden eigen categorie-indeling.


6 november — atleten Views volgt rechts-naar-links per rij de volgorde Athlete Diary, Year Planner, Athlete Info, Camps, Improvements, Evaluations. Mobiel dezelfde volgorde van boven naar beneden. Losse Races-tegel verwijderd; races blijven via Year Planner bereikbaar. Bestaande instellingen bepalen welke tegels zichtbaar zijn.


6 november — correctie leesrichting voor BEIDE rollen: alle opgegeven tegelvolgordes gelden van links naar rechts, eerst rij1 dan rij2. Omgekeerde flex-/gridrichting verwijderd; categorieën, lijsten en zichtbaarheid ongewijzigd. More blijft één rij op laptop/desktop. Tien gerichte tests en manage.py check geslaagd.


6 november — hoofdpagina: ondertitels van alle tegels verwijderd voor coach/atleet; alleen titels en bestaande iconen blijven. Desktoptegels verhoogd80→96px, More64→76px; compacte laptopvariant64→76px en More56→64px. Indeling, volgorde, rechten en bestemmingen behouden. Tien gerichte navigatie-/volgordetests en manage.py check geslaagd; geen visuele browsercontrole.


More gebruikt native details/summary (muis, touch en toetsenbord), met pijltje en klein rood telbolletje rechtsboven naast de titel. Standaard ingeklapt. Uitgeklapt blijft laptop/desktop één automatische tegelrij; mobiel bestaande stapeling. Badge met toegankelijk numeriek label en ruimte voor meer cijfers.


6 november — tegelnamen hoofdpagina vergroot naar uniforme1.6rem (ook More en compacte laptopvariant). Alle tegels centreren inhoud verticaal; lange titels mogen omlopen. More/compacte tegels minimaal80px om twee tekstregels te passen. Bestaande iconen/volgorde behouden. Elf gerichte tests en manage.py check geslaagd; geen visuele browsercontrole.


6 november — Evaluations-tegel heeft een ☑-icoon in dezelfde planning-card-icon-cirkel als de andere hoofdtegels, voor coach en atleet. Decoratief icoon is aria-hidden.


6 november — dezelfde rode New-teller staat zowel naast More als rechtsboven op de New, Plans, Wishes-tegel. Bij atleten staat die tegel nu ook als eerste links, vóór Hardware. Teller blijft gebaseerd op New-items afgelopen14 dagen. Elf gerichte tests en manage.py check geslaagd.


6 november — Django Admin-tegel verplaatst van oud dashboard naar More op Mila Planner. Alleen zichtbaar voor het ingelogde coach-adminaccount (bestaande productbeheerdercontrole), onafhankelijk van actieve coachselectie. Bestaande Django-adminrechten behouden. Twaalf gerichte tests en manage.py check geslaagd.


Mobiele Diary-weekkaart heeft ALT-zonepillen naast de hardloopzones, met expliciete eenheid min en bestaande zonekleuren. Alleen niet-nul totalen worden getoond; de regel kan omlopen.


Login: desktop centraal formulier max480px met invoervelden/Login-knop minimaal52px hoog en18px tekst. Mobiel tot768px vrijwel volle breedte,76px hoge velden/knop en24px tekst, ruime labels/tussenruimte. Login heeft viewport=device-width zodat mobiel niet verkleind wordt. Labels gekoppeld aan velden, autocomplete behouden.


Sessiekop Athlete Diary: zwart A-label met daarachter minuten in bestaande session-zone-z1/z2/z3-kleurpillen, zonder extra zoneletters. Tooltip vermeldt Alternative, zone en min. Sessiekop mag omlopen op smalle cellen; loopkm blijven afzonderlijk.


Year Planner: onder All in de atleetselector staat Basis - All wanneer Group=All, of Basis - groepsnaam bij een General Plan. Aan-/uitvinken ververst direct zonder aanvullende atleetselectie. Schema blijft zichtbaar met alleen Basis geselecteerd.


Bij Group=All staan Basis - All en de beschikbare programmagroepen als aparte selectievakjes in Athletes. Basis-selectie wordt direct verstuurd en behouden bij periode-/jaarnavigatie; checkbox All blijft uitsluitend atleten selecteren.


Garmin C/D (6 november 2026): Suggest-invoer en knop staan links van Use AM/PM, binnen dezelfde ombrekende actieregel. Invoer 16px en maximaal160px breed; bediening via klik of Enter. Wacht-/foutmelding bij de activiteit, bestaande preview blijft beschikbaar bij afwijzing. Alleen coaches zien technische AI-status/afwijsredenen; atleten krijgen een korte melding wanneer de suggestie niet bevestigd kan worden.


6 november - Hardware acces: Polar Integration, Garmin uploads en Garmin Connected Athletes hebben bovenaan Back naar het coachhardwareoverzicht. Garmin uploads voor atleten gaat terug naar hun eigen Planning > Hardware. Kopregels kunnen omlopen op mobiel. 23 GarminConnection-tests en manage.py check geslaagd; aanvullende gerichte teruglinkcontrole voor alle drie coachpagina's toegevoegd.


Garmin-preview: wanneer analyse klaar is maar gebruikersinteractie automatisch vervangen verhindert, tonen ook de afzonderlijke activiteitstatussen Analysis ready met Show analysis. Bij een laadfout blijft geen oude pending-melding staan. Invoer en keuzes blijven behouden tot expliciet Show analysis wordt gekozen.


6 november - Year Planner basisvinkjes: change-handlers stonden per ongeluk binnen de change-handler van Group. Nu worden Basis-All en afzonderlijke programmagroepen direct bij paginaladen gekoppeld: aan/uit verstuurt meteen de selectie, zonder eerst Group te wijzigen. Atleetselectie blijft intact; groepswissel voegt geen dubbele handlers toe. JS-regressie voert werkelijke handlers uit voor herhaald aan/uit en groepswissel.


Garmin C/D: oude Suggest-invoer vervangen door Chat-knop met uitklapbaar gesprek per activiteit. Meerregelige invoer16px, gesprek met begrensde scrollhoogte; tekst wordt veilig als tekst getoond. Coach houdt diagnostische afwijsdetails; atleet krijgt alleen kort resultaat. Gevalideerd voorstel wordt expliciet als zodanig benoemd en blijft een preview tot Use AM/PM.


Year Planner: compacte bedieningsbalk en kleinere navigatieknoppen; drie aparte selectiepanelen in native details/summary. Selection standaard dicht bij bestaande selectie, open zonder rijen; toestand per gebruiker in sessionStorage. Legend standaard dicht en toont alleen ingeschakelde/toegestane onderdelen. Kwartalen hebben maandkoppen en wekelijkse labels zoals05 Nov, jaarweergave maandlabels, maandweergave dagnummer+weekdag; geen verticaal afgebroken datums. Daglijnen zacht, weekgrenzen duidelijker, maandgrenzen het sterkst. Vaste linkernaamkolom en tweerijige sticky kop; bij smal scherm horizontaal scrollen. Kalenderhoogte gebruikt resterende viewport; mobiel natuurlijke paginahoogte. Viewportmeta toegevoegd voor echt mobiele layout.


6 november — selectie-uitlijning gecorrigeerd: Group boven alle drie kolommen; Basis/Athletes/Coaches hebben gelijke koppen, bovenrand en180px lijsten op desktop. Checkboxen en meerregelige labels gebruiken flex-uitlijning; mobiel natuurlijke hoogte met max180px. Selection-openstand wordt nu server-side gerenderd via selection_open en sessievoorkeur, niet achteraf uit sessionStorage hersteld. Dit voorkomt zichtbaar dicht-/openklappen na een checkboxselectie; formulier en periode-links sturen de actuele stand mee.


6 november — Year Planner Race Calendar lichtblauw #EFF6FF met tekst/rand #245A91; Camps lichtgroen #EFF8F1 met tekst/rand #28663D. Donkerdere hover en passende focusrand. Beide knoppen auto-breedte, compact38px hoog met6px afronding, passend bij Back. Tekstkleur blijft leesbaar bij teambranding. Gerichte YearPlanner-tests en manage.py check geslaagd.


Sleep length toont kleur afzonderlijk op low/high in de bestaande range, met contrasterende tekst en datumtooltip. Dit werkt in dezelfde compacte, horizontaal scrollbare vitalstabel op mobiel.


7 november — Extremumkleuren gelden voor alle vier Daily vitals. Sleep length, Sleep quality en HRV: laagste rood, hoogste groen. Morning HR: laagste groen, hoogste rood. Vandaag donker, één/twee dagen terug licht; oudere/volledig gelijke waarden neutraal, meest recente datum bij gedeeld extremum. Daggrens 08:00 en minimum drie waarden blijven gelden. Alleen range-eindpunten gekleurd, met datumtooltip; gemiddelden/NA en rechten ongewijzigd.
