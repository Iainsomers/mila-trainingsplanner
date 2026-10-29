# Functionele onderdelen

- Race filter biedt naast Group en Athlete ook Race Type met All en de zes racetypes. Het typefilter combineert met de overige filters en blijft behouden bij periode-/jaarnavigatie en opslaan; Show all races toont uitsluitend races van het gekozen type.

- De groene deelnemeraantallen per afstand in de Race Calendar-lijst worden direct na succesvol automatisch opslaan bijgewerkt, inclusief het verschijnen bij de eerste selectie en verdwijnen bij de laatste uitschrijving. Ze volgen de actieve groeps-/atleetfilter; meerdere vinkjes voor dezelfde atleet/afstand tellen één keer.

- Een race kan alleen verwijderd worden als er geen atleet meer aan gekoppeld is via Trainer-, Athlete- of Target-selectie. Deze controle geldt voor alle atleten, los van filters, en wordt server-side afgedwongen. De Delete race-knop staat linksonder en wordt na opslaan van selecties direct bijgewerkt.

- Geselecteerde Race Calendar-wedstrijden (Trainer, Athlete of Target aangevinkt) verschijnen per atleet op de Training-laag van Year Planner in hun Race Type-kleur, nooit als Whereabouts. Meerdere afstanden van dezelfde wedstrijd tellen als één markering; bij meerdere wedstrijden op één dag delen de kleuren de cel. De wedstrijdnaam staat vast in de cel; hover toont de voor die atleet geselecteerde afstand(en). Wedstrijddagen hebben geen fasekeuze en zijn ook server-side tegen fasewijzigingen beschermd. Bestaande fases blijven onder de wedstrijd bewaard en verschijnen weer na uitvinken. Terugkeren vanuit Race Calendar ververst de planner met behoud van de URL-selectie.

- Races hebben een opgeslagen Race Type: Championship, Race Other, Diamond League, Race Gold, Race Zilver of Race Bronze. Bestaande en nieuwe races beginnen als Race Other. Coaches wijzigen dit direct onder Manage distances; de keuze slaat automatisch op en de lijstomlijning volgt direct de Year Planner-legendakleur. Atleten kunnen het gedeelde racetype alleen lezen.

- Year Planner heeft naast de legenda een `Race Calendar`-knop die de bestaande werkende racelijst binnen de pagina opent. Dezelfde knop keert terug naar de ongewijzigde planner met behoud van de selectie. De geïntegreerde weergave biedt alleen de lijst, inclusief perioden, filters, toevoegen, afstanden en wedstrijdkeuzes; de losse Race Calendar behoudt List/Calendar. Bestaande coach-/atleetrechten blijven gelden.

## Privacyverklaring

- De openbare Engelstalige privacyverklaring is beschikbaar via `/privacy/` en gelinkt vanaf de loginpagina. De tekst beschrijft de gegevenscategorieën, doeleinden, coach-/atleetzichtbaarheid, bewaartermijnen, beveiligingsmaatregelen, minderjarigen en externe diensten (Render, Oura en jsDelivr).
- De Oura-koppeling ondersteunt OAuth-autorisatie; automatische data-import is nog niet beschikbaar. Oura-data wordt volgens de gepubliceerde verklaring alleen na autorisatie verwerkt; eerder gesynchroniseerde gegevens blijven staan tot accountverwijdering of een verwijderverzoek.
- De Engelstalige Terms of Service is openbaar beschikbaar via `/terms/`, met links naar de privacyverklaring. Beide documenten zijn bereikbaar vanaf de loginpagina.
- Atleten hebben alleen wanneer hun coach `Allow Oura connection` inschakelt een apart dashboardblok `Hardware settings` met de optionele Oura OAuth-koppeling. De verbinding is per eigen atleetaccount, vraagt expliciete wellness-toestemming en een bevestiging van volwassenheid/ouderlijke toestemming, vraagt alleen `daily` en `heartrate`, en kan vanuit hetzelfde blok worden losgekoppeld. Uitschakelen door de coach trekt de token in (waar mogelijk) en verwijdert de lokaal opgeslagen koppeling. Automatische import naar Daily Vitals is nog niet actief.
- De coach kan per atleet `Allow Polar access` inschakelen; standaard staat dit uit. Alleen met toestemming ziet de atleet de Polar-tegel en Polar A/B-knoppen in de AYC. Polar-pagina's en data-endpoints controleren dezelfde toestemming; coachgebruik blijft beschikbaar.

Bijgewerkt: 29 oktober 2026.

## Dashboard en Planning

In New, Plans, Wishes kan de maker een eigen actieve wish bewerken. De productbeheerder (`admin`) kan iedere actieve wish bewerken. Andere gebruikers hebben geen Edit-knop en wijzigingen worden ook server-side geweigerd.

In Athlete Input staat boven de tabs voor trainers steeds de naam van de geselecteerde atleet. De aanduiding blijft zichtbaar wanneer tussen tabs wordt gewisseld; in de eigen Athlete settings van een atleet wordt deze niet getoond. Naast de naam kunnen trainers alfabetisch naar de vorige of volgende atleet binnen de actieve coachweergave gaan; het huidige tabblad blijft behouden.

Het coachdashboard toont Planning bovenaan. Onder `Coach dashboard` staat voor trainers met gedeelde toegang een `View as coach`-keuze. Standaard kijkt een trainer als zichzelf; na selectie van een andere toegestane coach tonen plannings- en beheerschermen alleen de gegevens van die coach. De dropdown toont of die toegang view-only of edit is; bij view-only worden schrijfacties server-side geblokkeerd. Settings is een werkende dashboardtegel voor coachinstellingen, waaronder Planning Camps. Stats en Polar houden hun under-development-aanduiding.

Planning is voor coaches gegroepeerd in Coach plannings, Views en Standards. Coach plannings bevat Athletes, Trainer planning, Flex Planner, Races en Year Planner. Na inschakeling van `Planning Camps` in de eigen Settings verschijnt hier ook Details Camps. Views bevat Athlete Year Calendar, Daily Coach Overview Training en Staff Team Overview. Staff Team Overview opent met de lijst toegankelijke atleten en keuzes Vitals en Information Quality. Beide keuzes tonen het bestaande overzicht voor alle toegankelijke atleten. Information Quality toont per atleet in de actieve coachweergave het percentage geëvalueerde AYC-trainingen over de laatste tien kalenderdagen inclusief vandaag. Vandaag telt vanaf 12:00 voor AM en vanaf 21:00 voor PM. Hover over het percentage toont het aantal open en geëvalueerde trainingen; zonder trainingen staat er `NA`. Het toont daarnaast het percentage ingevulde waarden van de vier dagelijkse vitals (sleep hours, sleep quality, morning HR en HRV) over dezelfde tien kalenderdagen; hover toont het aantal ingevulde waarden van de 40 mogelijke waarden. De vitalscore wordt verborgen als de coach de vitals niet mag inzien. Beide percentages gebruiken dezelfde kleurgrenzen: rood onder 60%, oranje vanaf 60%, lichtgroen vanaf 80%, donkergroen vanaf 95%; 0% is zwart met rode tekst. De Flex Planner-overrides worden uit diezelfde actieve coachweergave gelezen. Wanneer trainingsevaluaties door de coach niet mogen worden ingezien of voor de atleet zijn uitgeschakeld, toont Information Quality geen evaluatiegegevens. Vitals toont per atleet het gemiddelde van de gekozen vital over de laatste veertien kalenderdagen, inclusief vandaag, bij minimaal drie bruikbare dagwaarden. Zie het Vitals-filter hieronder. Standards bevat Saved Trainings en Standard Strength. Atleten gebruiken Planning voor Athlete Year Calendar, Athlete settings, Races en, wanneer toegestaan, Year Planner.

Het dashboard bevat daarnaast Coach Tools. MiLa bevat daar alleen de Track Timer; Match Overview en de PR-database zijn verplaatst naar het aparte PAC-project. De timer toont een getekende atletiekbaan met 100m-punten, een afstandskeuze van 100m tot 1600m, een optionele doeltijd en een single/multiple-modus voor één of drie atleten. In multiple staan drie gekleurde atleetknoppen en een zwarte knop voor alle drie. De start/finishknop kan naar een van de vier meetpunten worden gesleept, waarna de andere meetpunten meedraaien. Bij afstanden boven 400m moeten 400m-doorkomsten worden vastgelegd voordat de eindtijd kan worden gestopt. De resultaten tonen tussentijd, tempo per 100 m, min/km en eventueel afwijking van de doeltijd; een lijn op de baan visualiseert het doeltempo.

Iedere ingelogde trainer en atleet kan via `Change password` het eigen wachtwoord wijzigen. Het huidige wachtwoord is vereist; nieuwe wachtwoorden hebben minimaal 8 tekens, met een hoofdletter, kleine letter, cijfer en speciaal teken. Een vergeten-wachtwoord-flow is niet ingebouwd.

In Athlete settings > General kan een atleet `Start op AYC` inschakelen. Deze persoonlijke instelling staat standaard uit; na inloggen opent de atleet dan de eigen Athlete Year Calendar in plaats van het dashboard. Een rechtstreekse start op de rootpagina doet dit ook voor reeds ingelogde atleten, inclusief bestaande mobiele beginscherm-snelkoppelingen; een Dashboard-link binnen de app blijft werken. De coach kan de instelling ook per atleet beheren. Een expliciete loginbestemming (`next`) blijft leidend; trainers blijven na inloggen op het dashboard.

Het dashboard bevat ook Evaluations. In Coach Settings kan een coach deze module voor zichzelf en al zijn atleten aan- of uitzetten; standaard staat de module aan. Trainers maken vragenlijsten, kunnen een eerdere lijst als basis kopiëren en zien ingevulde formulieren per vragenlijst en daarna per atleet. Coaches kunnen als kopieerbron hun eigen vragenlijsten gebruiken en die van coaches aan wie ze editrechten hebben; kopiëren neemt vragen en matrixstructuur over, nooit ingevulde antwoorden, en laat het origineel intact. Bij elke vragenlijst kiest de maker expliciet `All athletes` of `Selected athletes`; bij de tweede optie is minimaal één eigen atleet vereist. Deze keuze staat los van `Active`: alleen actieve vragenlijsten kunnen worden ingevuld. De doelgroep wordt zowel in de lijst als bij het openen en opslaan gecontroleerd. Na aanmaak kunnen trainers titel, actieve status en doelgroep aanpassen. De vragenstructuur wordt nog niet achteraf aangepast; zo blijven bestaande antwoorden ondubbelzinnig bij hun oorspronkelijke vraag. Het wijzigen van de doelgroep verwijdert geen bestaande antwoorden: een atleet die uit de doelgroep wordt gehaald, kan het formulier niet meer openen, maar de trainer behoudt het eerder ingediende antwoord. Een formulier kan gewone open vragen en matrixvragen combineren. Een matrix heeft een eigen header, vrij instelbare rijvragen en vrij instelbare kolomkoppen, bijvoorbeeld jaartallen. Trainers kunnen een volledige vragenlijst inclusief de bijbehorende antwoorden verwijderen. Atleten zien alleen actieve vragenlijsten waarvoor ze zijn geselecteerd en zien uitsluitend hun eigen ingevulde antwoord. Met Evaluation sharing kan de eigenaarcoach per coach en per type (Training, Week, Vitals) bepalen welke evaluaties een coach met view- of edit-toegang mag zien.

Ingelogde pagina's publiceren het MiLa-logo als favicon, Apple touch icon en PWA-icoon. Een snelkoppeling die vanaf een telefoon op het beginscherm wordt gezet, gebruikt daardoor standaard het MiLa-logo.

### Focus Points and Desired Improvements

Wanneer de bestaande `Focus Points and Desired Improvements`-schakelaar in Coach Settings aanstaat, verschijnt de pagina voor coaches onder Planning. De trainer kiest bovenaan een toegankelijke atleet. De focuspuntenmatrix heeft de kolommen Comment coaches, Prio, Plan, Progress en Comments athletes. Bevoegde coaches beheren Comment coaches afzonderlijk per trainer; Plan en Progress zijn gedeelde velden die iedere bevoegde trainer kan overschrijven. Prio blijft compact en smal; aanklikken opent de keuzes —/goud/zilver/brons. Per atleet kan iedere medaille maar één keer voorkomen: bij het kiezen schuiven gelijke of lagere prioriteiten één positie omlaag en brons valt af; kiezen voor — verwijdert de prioriteit en vult de vrijgekomen volgorde op. De drie Other-namen zijn per atleet aanpasbaar; een lege aangepaste naam toont weer Other 1/2/3. Met de coach-only Athlete setting `See desired improvement points` krijgt een atleet een eigen, beperkte weergave met focuspunten en de invulbare kolom Comments athletes; coachcommentaren worden daar nooit getoond. Prio, Plan en Progress zijn alleen zichtbaar als de coach `Show to athlete` heeft ingeschakeld. Comments athletes blijven in het coachoverzicht zichtbaar.

Een trainer met eigen beheer of gedeelde editrechten kan per focuspunt een eigen commentaar opslaan in Comment coaches. Deze opmerkingen blijven afzonderlijk per coach opgeslagen, worden achter elkaar in de cel getoond en zijn inclusief initialen (eerste en laatste username-deel, gescheiden door `_`) volledig gekleurd in een stabiele, aan die coach gekoppelde kleur. De standaardoptie `Overwrite` staat uit en staat compact rechtsboven in de commentaarpopup; dan blijven opmerkingen van andere coaches staan. Met de optie aan worden alle comments van andere coaches voor dat focuspunt verwijderd voordat het commentaar van de huidige trainer wordt opgeslagen. Een leeg eigen commentaar verwijdert alleen dat commentaar. Plan en Progress worden als één gedeelde tekst per atleet/focuspunt bewaard en door de laatste bevoegde trainer overschreven; er worden geen coachinitialen of auteurgegevens getoond. View-only coaches kunnen de pagina lezen maar niet opslaan; atleten krijgen alleen toegang wanneer `See desired improvement points` voor hen is ingeschakeld, en coach-tools-only accounts hebben geen toegang.

Trainers met bewerkrechten kunnen een `.xlsx`-matrix importeren in `Comment coaches`. De eerste kolom moet MiLa-atleetnamen bevatten en de negen focuspunten moeten in de eerste rij staan. De import valideert alle namen tegen atleten in de actieve coachweergave en weigert de volledige import bij onbekende of dubbelzinnige namen. Na expliciete bevestiging vervangt de import alleen comments van de ingelogde trainer waarvoor in het bestand een niet-lege cel staat, voor de atleten in het bestand. Lege cellen laten bestaande comments staan. Comments van andere trainers en de gedeelde velden Plan en Progress blijven intact. Een import wordt als één transactie opgeslagen.

Prio en de Other-namen zijn gedeelde atleetinstellingen, niet gekoppeld aan de coach die de laatste wijziging deed. Iedere coach met editrechten op de actieve coachweergave kan ze aanpassen en overschrijven.

## Trainer Planning

- Meerdere weken, standaard vier.
- `Print weeks` drukt de momenteel ingestelde periode van 1–12 weken af in liggend A4; navigatie en bewerkingsknoppen worden weggelaten.
- De lijst met trainerplannen toont de eigenaar/coach compact in een eigen, links uitgelijnde middelste kolom.
- Weken blijven zeven dagen breed en extra weken stapelen verticaal.
- Huidige week wordt geel gemarkeerd.
- Vorige/volgende verschuift één week.
- Dag- en weekkopiëren werkt tussen trainerplannen.
- Een gevulde AM- of PM-training kan rechtstreeks uit de Trainer Planner worden verwijderd met de compacte `×` in de cel.
- Trainingsonderdelen worden uiteindelijk in Flex Planner en AYC gebruikt.

## Year Planner

- Overzicht onder Planning voor training phases en whereabouts over een flexibele periode. Trainers beheren eigen atleten; atleten kunnen uitsluitend hun eigen, door de trainer toegestane lagen lezen.
- De periode gebruikt current/next month, outdoor, indoor, full year en een seizoensperiode zoals 2026/2027.
- Trainers kunnen Training, Whereabouts of beide lagen tonen.
- De weergave kan worden geschaald naar ongeveer 1, 3 of 12 maanden per schermbreedte en kan horizontaal scrollend of in schermbrede stukken onder elkaar worden getoond; stacked is de standaardweergave.
- Meerdere atleten kunnen tegelijk worden getoond, maar er worden standaard geen atleten voorgeselecteerd. De atletenlijst kan op `All` of op een Trainer Planning-verwijzing worden gefilterd. `All` selecteert alle zichtbare atleten. Na keuze van een specifieke Trainer Planning-groep kan de trainer direct onder `All` de aparte `Basis - groepsnaam`-planningsrij kiezen. Iedere groep heeft eigen Basis-data; bij de algemene groepskeuze `All` is er bewust geen gedeelde Basis. Historische algemene Basis-data wordt niet automatisch naar alle groepen vermenigvuldigd. Atleten zonder ingeschakelde Year Planner-laag zijn rood gemarkeerd in de selector.
- Naast Athletes staat een afzonderlijk inklapbaar Coaches-blok. Het bevat de ingelogde coach en alle coaches waarvoor die coach expliciet view- of editrechten heeft. Coaches krijgen alleen een whereabouts-rij. Deze rij mag ook bij view-only toegang worden aangepast; de uitzondering is beperkt tot coach-whereabouts en geeft geen toegang tot andere gegevens van die coach.
- Training phases gebruiken dezelfde keuzes als de Flex Planner: Recovery, Aerobe, Specific, Intense en Taper.
- Whereabouts-keuzes zijn Camp, Travel, Test, Championship, Diamond L, Race Gold, Race Silver, Race Bronze, Race Other, Expermeetings, Medical en Brinec, elk met een vaste kleur. Ze worden als echte datumranges opgeslagen, zodat een kamp of reis als één doorlopende pil met gecentreerde naam verschijnt, kan worden verkleind/verlengd en naar een andere atleet kan worden gesleept. Overlappende whereabouts, zoals een testdag binnen een kamp, blijven naast elkaar bestaan en delen de dagcel diagonaal.
- Trainingcellen slaan direct op. Gekozen trainingswaarden kunnen over een datumrange worden gesleept. Hele atletrijen kunnen per zichtbare periode met `c`/`p` worden gekopieerd voor Training en afzonderlijk voor Whereabouts. Een nieuwe of bewerkte whereabout kan in één keer op alle geselecteerde atleten worden toegepast.
- Per atleet bepaalt de trainer in Athlete settings > General afzonderlijk of de Training-calendar en/of Whereabouts-calendar in de Year Planner zichtbaar zijn. De legenda volgt die zichtbaarheid.
- Atleten zien in de Year Planner uitsluitend hun eigen atletenrij en eigen whereabouts. Coachrijen met whereabouts bestaan alleen in de coachweergave.
- In Details Camps kan een coach met editrechten voor alle deelnemers de kampnaam aanklikken en aanpassen. De nieuwe naam wordt doorgevoerd naar alle whereabouts-regels van dat kamp; een bestaande andere kampnaam kan niet per ongeluk worden samengevoegd. Een view-only coach kan de naam niet wijzigen. Een bevoegde coach kan ook een deelnemer met een kleine delete-knop uit het kamp verwijderen. Alleen de camp-whereaboutregels van die deelnemer worden verwijderd; de persoon en overige planning blijven bestaan. Atleten met `year_planner_whereabouts_enabled` zien in Planning ook Details Camps, maar alleen kampen waarvoor zij zelf geselecteerd zijn. In zo'n kamp kunnen zij hun eigen aankomst-/vertrek- en reisgegevens wijzigen; andere deelnemers blijven read-only en deelnemers toevoegen of verwijderen blijft trainer-only.
- AYC en Flex Planner tonen in de linkerbovenhoek van een AM-cel één of meerdere gekleurde dots voor de atleetgebonden Whereabouts van die dag, ook zonder training; meerdere overlappende types worden als meerdere dots weergegeven. Coach- en basisplanranges worden niet naar alle atleten doorgezet.

## Flex Planner

- Toont de effectieve planning per geselecteerde atleet.
- In Main kunnen zelfstandige trainingsonderdelen met `//` of `+` worden gescheiden; ieder onderdeel wordt apart opgeslagen en weergegeven, en telt mee in de eigen zone-totalen.
- Ondersteunt persoonlijke wijzigingen, kopiëren en drag-copy.
- Toont alle trainingsonderdelen en atleet-specifieke richttijden/tempo's.
- Toont bij een zichtbare trainingsevaluatie het Fit/Issues-bolletje naast de evaluatieknop: groen voor Fit, oranje voor Some issues en rood voor Serious issues. Zonder opgeslagen keuze blijft het bolletje weg.
- Polar A/B- en Garmin C-trainingen worden als horlogebron opgeslagen. Voor deze slots gebruiken Flex Planner, AYC en weektotalen de werkelijke meters en seconden per zone; geplande trainingen blijven hun zone-snelheden gebruiken om afstand en tijd af te leiden. De zichtbare segmenttekst behoudt de min/km-notatie uit de horlogeomschrijving zonder een extra totaal- of `actual`-label.
- Bij Polar A/B- en Garmin C-slots worden geen geplande HR-richtwaarden getoond. Garmin C toont in de resultaat-popup per lap de gemiddelde hartslag en het gemiddelde van de hartslagsamples over de laatste 15 seconden (kortere laps gebruiken hun volledige duur). Bij oudere uploads leest Garmin C de samples zo nodig opnieuw uit het originele FIT-bestand. Als er geen samples beschikbaar zijn voor het laatste-15-secondenvenster, toont die waarde `NA`; alleen de gewone gemiddelde HR kan terugvallen op het lapgemiddelde.
- Een persoonlijke wijziging blijft zichtbaar, ook wanneer de oorspronkelijke bronplanning op die datum formeel al is afgelopen.
- Een trainerplan dat via Base Planning aan een atleet is gekoppeld, blijft voor die atleet zichtbaar in Flex Planner; de Base Planning-koppeling gaat vóór de formele datumrange van het plan.
- Flex kiest het via Base Planning toegewezen trainerplan per AM/PM-dagdeel; een gedeeld (ook leeg) slot uit een ander gekoppeld plan mag die training niet verbergen. Een expliciete persoonlijke wijziging en een Flex-override behouden hun voorrang.
- Drag/kopieer van een training uit een toegankelijk trainerplan schrijft de persoonlijke override naar het Flex-plan van de coachweergave die op dat moment openstaat. Daardoor is de kopie direct zichtbaar in dezelfde Flex Planner, ook als het bronplan van een andere coach is.
- Flex haalt een toegewezen trainer-slot zo nodig rechtstreeks op vanuit Base Planning als de voorlaadlijst het plan niet bevat.
- De trainingspopup volgt bij Flex dezelfde bronkeuze als de kalendercel: een individuele Base Planning-training (of Rest) gaat vóór een gekoppeld trainerplan. Bij meerdere datumblokken wordt het blok met de laatste `effective_from` gebruikt.
- Een expliciet atleet-slot blijft in Flex Planner zichtbaar als de oude planlidmaatschap- of groepskoppeling ontbreekt.
- Een persoonlijke Flex-override kan met `Reset to plan` volledig worden verwijderd. Daarmee komt de onderliggende trainerplanning terug; velden leegmaken is niet hetzelfde als resetten.
- Een training die via de AYC-popup wordt aangepast, gebruikt dezelfde Flex Planner-plan-ID bij openen en opslaan. Zo ziet de atleet én coach dezelfde persoonlijke override in AYC en Flex Planner, ook wanneer de kalendercel naar een gekoppeld trainerplan verwijst.
- Toont bij zoneonderdelen waarvoor een handmatige Z1/Z2/Z3-HR is ingevuld ook de toepasselijke HR naast de richttijd.
- Haalt weekphase-kleuren uit de Year Planner. Meerdere fases in één week worden diagonaal gecombineerd; de oude weektype-dropdown bestaat niet meer.

## Athlete Year Calendar (AYC)

De instellingen `See session km` en `See session zones` staan in Athlete settings > General, zijn standaard gelijk ingeschakeld en kunnen door de atleet zelf of een trainer worden gewijzigd. Wanneer ze aanstaan, toont de AYC rechtsboven per sessie het totale loopvolume als zwart `T`-getal en kleine kleurpillen met alleen de kilometers per zone; Alternative telt niet mee. De totale weekafstand gebruikt dezelfde compacte `T`-notatie.

Trainingen die via `Polar A`, `Polar B` of `Garmin C` vanuit de AYC-trainingsevaluatie worden geplaatst, bewaren naast de trainingsomschrijving de gemeten segmentloads. Garmin C leest de al opgeslagen Garmin FIT-laps voor de geselecteerde atleet en gebruikt dezelfde lapherkenning en optionele AI-structuurherkenning als Polar B. Alleen `Use AM` of `Use PM` schrijft de voorgestelde training naar de AYC; zonder bruikbare laps of bij ontbrekende AI-configuratie blijft de rules-based herkenning leidend. Daardoor worden tijdgebonden trainingsdelen niet opnieuw omgerekend met de zone-snelheid van de atleet: afstand, zoneverdeling en zonetijd blijven de werkelijke horlogewaarden. De AYC toont bij een overgenomen training een klokindicator in de betreffende AM- of PM-cel.

De klokindicator is aanklikbaar en toont per herkende Main-rep de geplande afstand, tijd en min/km. Hiervoor wordt bij het opslaan een aparte verwerkte lijst op het trainingsslot bewaard. De oorspronkelijke Watch-laps blijven ongewijzigd en blijven leidend voor alle bestaande kilometer- en zonetotalen; herstel-laps worden niet als Main-reps getoond.

Coach Settings bevat onder Planning eveneens `See session km`, standaard aan. Deze coachbrede instelling toont hetzelfde sessietotaal rechtsboven in de trainingscellen van Flex Planner en Daily Coach Overview Training, met de compacte `T`-notatie zonder `km`-label.

De coachinstelling `P(ause)mode` bepaalt hoe pauzes in de kilometerberekening meetellen. `Static unless "ap"` telt alleen een expliciete `ap` als actieve Z1-pauze; gewone `p` blijft statisch. `Active unless "pp"` telt zowel `p` als `ap` actief. `sp` (seriepauze) en `pp` (passieve pauze) blijven in beide standen statisch. Tijdpauzes worden omgerekend met de Z1-snelheid van de atleet; pauzes in meters gebruiken de opgegeven afstand. Per set tellen `reps - 1` pauzes. Dezelfde extra Z1-afstand telt mee in AYC, Flex Planner, Trainer Planning en DCO, voor AM en PM.

In Athlete settings kan de coach per atleet dezelfde `P(ause)mode` instellen. De standaard volgt de coachinstelling; een expliciete atleetkeuze overschrijft die alleen voor die atleet. Het veld is niet zichtbaar of wijzigbaar voor de atleet zelf.

- Trainer kan tussen atleten schakelen; atleet ziet alleen zichzelf.
- Desktop toont een brede jaartabel; mobiel toont één week tegelijk.
- Op mobiel opent de huidige week automatisch en navigeert men met pijlen.
- De huidige week is geel en de huidige dag donkerder geel.
- Weektype staat als gekleurde pil.
- `Total` en de zoneverdeling tonen het berekende weektotaal.
- Een training met evaluatiestatus `Not done` telt niet mee in de weekkilometers, zone-/wedstrijdverdeling of ALT-minuten; de geplande training blijft zichtbaar.
- Zoneonderdelen tonen naast de indicatieve tijd de handmatige HR-grens wanneer die voor de atleet is ingevuld.
- AM en PM worden afzonderlijk getoond.
- Individuele Base Planning geldt per AM/PM-dagdeel ook wanneer een gekoppeld groepsplan daar een training heeft: `Rest` verbergt die groepstraining en een individueel Base Planning-plan bepaalt de bron. Een expliciete persoonlijke AYC/Flex-override blijft voorrang houden.
- Training en Evaluation hebben beide een zichtbare knop `Open`.
- Trainingen openen in een op mobiel beeldvullende popup, maar niet groter dan het scherm.
- Bestaande AM- én PM-trainingen worden vooraf ingevuld in de popup.
- In de AYC zijn toekomstige trainingen voor atleten alleen-lezen; coaches met eigen of gedeelde edit-toegang kunnen ook vooruit trainingen aanpassen. View-only gedeelde toegang blijft alleen-lezen.
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

Bij trainingsevaluaties wordt RPE automatisch op 0 gezet wanneer `Not done` wordt gekozen. De bestaande controle blijft staan: bij een ingevulde evaluatie is een commentaar van minimaal vier tekens vereist. Daarnaast staat de coachinstelling `Pain in training evaluations` standaard aan. Als die aanstaat, staat naast RPE een verplicht keuzemenu met 🟢 Fit, 🟠 Some issues, pls explain! en 🔴 Serious issue, talk to staff!; nieuwe evaluaties starten vooraf ingevuld op Fit. De keuze wordt per training/AM-PM opgeslagen. Uitzetten verbergt het veld en maakt Pain niet verplicht; eerder opgeslagen evaluaties worden niet aangepast en een bestaande Pain-waarde blijft behouden. Atleten met `Extended edit rights` krijgen op ieder zichtbaar dagdeel altijd AM- en PM-evaluatievelden, ook wanneer daar nog geen training staat; toekomstige evaluaties mogen dan ook worden opgeslagen.

Per training kan de atleet vastleggen:

- status: Done, More/too fast, Adjusted, Less/slower of Not done;
- RPE van 0 tot 10;
- commentaar;
- `Polar A` en `Polar B`-knoppen die de Polar-output voor de gekozen atleet en datum in een popup tonen. Polar B gebruikt voorlopig exact dezelfde output als Polar A, maar heeft een eigen analysekoppeling zodat toekomstige herkenningsverbeteringen alleen Polar B hoeven te wijzigen. Naast een bruikbare gegenereerde omschrijving staan `Use AM` en `Use PM`, waarmee WU, Main en CD naar het gekozen AYC-trainingsslot worden overgenomen. De tekst `Continuous run` wordt daarbij niet meegenomen; bestaande opgeslagen horlogeresultaten blijven zichtbaar en verwijderbaar;
- In de Model B-laptabellen staat naast `Avg HR` ook `Last 15s HR`: het gemiddelde van de laatste 15 seconden van de lap, of van de volledige lap wanneer die korter is. Dit is alleen extra weergave; de generated training line en opgeslagen trainingsvelden veranderen hierdoor niet;
- Model B herkent als eerste uitbreiding herhaalde afstandsblokken met korte herstel-laps en een langere seriepauze. Een lap die werk en herstel combineert kan als herhaling blijven meetellen wanneer de afstand in het dominante herhalingspatroon valt; bij onvoldoende zekerheid valt Model B terug op Model A.
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
- Bij wijzigen van de groep of atleet in de hoofdfilter wordt `Show all races` automatisch uitgezet; de trainer kan het daarna zelf weer aanzetten.
- De groepskeuzes in de Race Calendar tonen alleen Trainer Planning-groepen van de actieve trainer; gedelegeerde toegang voegt geen groepen van de ingelogde trainer toe.
- Atleet kiest maximaal drie afstanden per wedstrijd.
- Een wedstrijd kan als doelwedstrijd worden gemarkeerd.
- De popupfilter kan voor trainers `All`, een Trainer Planning-groep of alleen al deelnemende atleten tonen; individuele atleten zijn geen filteroptie en een atleet ziet alleen zichzelf. `Participating athletes` toont een atleet zodra minstens één Trainer-, Athlete- of Target-vakje is aangevinkt. Achter ingeklapte atleetnamen staan geen afstandspillen.
- De trainerpopup opent standaard alle atleetregels. De tabel heeft aparte, compacte kolommen voor atleet en afstand, gevolgd door Trainer, Athlete en Target; de waarden delen dezelfde gridkolommen als de koppen.
- Atleten openen de Race Calendar standaard in de compacte lijstweergave, met de afstanden als pillen achter de wedstrijdnaam.
- De Races-tegel voor atleten opent de geïntegreerde Race Calendar en niet meer de oude Race Selector. Alleen gekozen afstanden verschijnen in de compacte lijst, met de kleur van de akkoordstatus.
- In een geopende wedstrijd ziet een atleet de eigen selectiehokjes meteen; trainers blijven atleetregels eerst openklappen.
- Bij atleten werken de afstandspillen in de lijst direct bij wanneer een selectiehokje verandert, ook vóór het opslaan.
- Athlete- en Target-vinkjes worden voor atleten direct op de achtergrond opgeslagen; daarom heeft hun wedstrijdpopup geen aparte Save selections-knop.
- Ook Coach- en Target-vinkjes van trainers worden direct op de achtergrond opgeslagen; de wedstrijdpopup heeft voor geen van beide rollen nog een Save selections-knop.
- Atleten kunnen in zowel List als Calendar view een wedstrijd toevoegen aan de kalender van hun trainer en daar nieuwe afstanden aan toevoegen. Bestaande afstanden of de wedstrijd verwijderen blijft trainer-only.
- Een trainerspopup start standaard met `Participating athletes`; de popupselector kan daarna naar alle atleten of een groep schakelen.
- Met de schakelaar `Expand all` opent of sluit de trainer alle momenteel zichtbare atleetregels tegelijk.
- De kalenderweergave kleurt wedstrijden volgens de zwaarste akkoordstatus binnen de gekozen atleet/groep: licht zonder deelname, oranje/rood omlijnd bij een enkel akkoord en oranje/rood gevuld bij dubbel akkoord. Alleen trainers zien een groene badge met het aantal deelnemers boven nul.
- Trainer-, atleet- en doelwedstrijdvinkjes hebben afzonderlijke rechten. Bestaande selecties worden als wederzijds bevestigd gemigreerd.
- Een nog niet wederzijds bevestigde wedstrijd is wit met oranje rand, of met rode rand als Target aanstaat. Na trainer- én atleetakkoord wordt de pil gevuld oranje of rood.

## Athlete settings

Tabs voor atleten: General, Zones. HR, Speed, Base Planning en Ideal week. WU/CD-instellingen staan op General; de oude WU settings-tab bestaat niet meer. `Fill missing PB's` kan ontbrekende prestaties afleiden uit beschikbare PR's. De atletenlijst is sorteerbaar op naam en leeftijd, in beide richtingen.
General-settings kunnen worden opgeslagen zonder dat alle PR's al zijn ingevuld; alleen ingevulde PR-waarden worden gevalideerd en bewaard.
Onder Z1 t/m Z5 kan de trainer handmatig een HR-waarde of tekstuele HR-zone invullen, bijvoorbeeld `160-170` of `max 170`. Die tekst wordt ongewijzigd bij de trainingen getoond. De zone/snelheidsweergave toont de km/h-omrekening naast min/km.
De trainer kan per atleet `Extended edit rights` aanzetten. Daarmee mag de atleet toekomstige AYC-trainingen aanpassen en lege dagdelen vullen. `Can change base planning` is een afzonderlijk standaard uitgeschakeld vinkje waarmee de atleet ook de eigen Base Planning mag wijzigen; groepskeuzes blijven beperkt tot groepen van de eigen trainer.
In Athlete settings > Base Planning worden wijzigingen aan een dagdeel automatisch opgeslagen via dezelfde volledige formulier- en revisielogica als de knop `Save`; die knop blijft beschikbaar als expliciete handmatige opslag. Bij een fout toont de statusregel nu ook de korte foutreden.
De atleetkeuze en `Copy van...` zijn beperkt tot atleten van de coach die op dat moment actief wordt bekeken; ook de kopieeractie zelf controleert die scope.

## Tempoherkenning en totalen

Flex Planner en AYC herkennen tempo's zoals `TM`, `THM`, `T4` en `T1500` alleen als losse labels. De tekstzoeker verwijdert geen spaties meer voordat hij zoekt, zodat woorden als `ritme` niet langer onterecht als `TM` worden geteld. Afstanden blijven wel meetellen in hun normale zone.

Flex Planner en AYC kiezen voor een atleet op een datum dezelfde actieve bronplanning. Persoonlijke slots uit oude of niet meer toegewezen plannen mogen de actuele training niet overschrijven of verbergen; een Flex-override behoudt wel altijd voorrang.

## Daily Coach Overview Training

Selectie op datum, AM/PM, alle atleten, selectie, trains, geplande training en opgeslagen selecties. Opgeslagen selecties kunnen onbeperkt naast elkaar bestaan: een andere naam maakt een nieuwe selectie, dezelfde naam werkt de gekozen selectie bij. Ze worden opgeslagen per actieve trainer, zodat gedelegeerde coachweergaven geen selecties met elkaar delen. De resultaatpagina behoudt de selectie, toont atleet-specifieke tempo's, RPE en opmerkingen en heeft een Print-knop voor de gekozen atleten en dag. Naast een zichtbare trainingsevaluatie staat ook het Fit/Issues-bolletje: groen voor Fit, oranje voor Some issues en rood voor Serious issues. Zonder opgeslagen keuze blijft het bolletje weg.

## Stats

Trainer-only, nog in ontwikkeling. De hoofdpagina toont eerst uitsluitend de atleetselector; na `OK` verschijnt het kilometeroverzicht voor die selectie, met een knop terug naar Selection. Het overzicht toont per atleet de totale kilometers van deze en vorige week. De drie kolommen zijn sorteerbaar: naam alfabetisch en beide weekafstanden van hoog naar laag. De atleetnaam opent een staafgrafiek met de effectieve totale kilometers per trainingsweek. De trainer vult daar vrij het gewenste aantal maanden in; standaard staat de periode op 6 maanden. Kleine pijlen verschuiven precies één gekozen periode terug of vooruit, waarbij vooruit stopt bij de huidige periode. Onder de grafiek staan het weekgemiddelde en de hoogste en laagste week van de gekozen periode. De atleetselector gebruikt dezelfde standen, opgeslagen selecties, standaardselectie en `Trains`-lijst als de Daily Coach Overview. Opgeslagen selecties zijn per actieve trainer en ondersteunen meerdere namen. `Planned training` beperkt Stats tot atleten met geplande loopkilometers in een van de twee getoonde weken.

## Polar

Ondersteunt OAuth en synchronisatie van relevante trainings-, activiteits- en lapgegevens. `Polar A` in de AYC gebruikt dezelfde Type A Polar-verwerking als de Polar Integration-pagina en toont de sessies, beschrijving en laps in een popup. Bestaande opgeslagen horlogeresultaten blijven intact.

Wanneer horlogedata duidelijk niet aansluit op de geplande training begint de interpretatie met een rood kruis. Via `Suggest alternative plan` kan vervolgens een alternatief trainingsconcept uit de horlogedata worden gereconstrueerd. Dit concept vervangt de oude interpretatie in beeld, toont een betrouwbaarheidsschatting en vervangt de oorspronkelijke planning nooit automatisch. Naast handmatige laps kan een herhalend fartlekpatroon uit aanhoudende tempowisselingen worden herkend. Polar v4 haalt naast laps ook interval-samples op; deze worden genormaliseerd naar een tijd/afstand-profiel zodat de bestaande matcher en AI-analyse korte versnellingen en complexe intervalstructuren kunnen gebruiken. Als Polar v4 geen handmatige laps levert, worden automatische laps als pace-data getoond met lagere zekerheid; ze krijgen geen bevestigde workout-blokkenstatus.

Meerdere sporten op dezelfde dag blijven als losse activiteiten zichtbaar, maar worden niet samengevoegd in de interpretatie. Technische watch-details staan standaard ingeklapt.

## Garmin FIT uploads

Trainers kunnen per atleet in Athlete Input `Allow Garmin FIT uploads` aanzetten. Alleen deze geselecteerde atleten verschijnen op het dashboardtabblad Garmin uploads. Een trainer of de geselecteerde atleet kan daar een `.fit`-bestand of Garmin-zip uploaden. De activiteit wordt per atleet opgeslagen met de FIT-datum, het originele bestand en de genormaliseerde gegevens. De pagina toont daarnaast een lijst van opgeslagen activiteiten. In de AYC gebruikt Garmin C de opgeslagen lapgegevens van die atleet op de gekozen datum. De match-/AI-uitvoer verandert de planning pas na een expliciete keuze voor `Use AM` of `Use PM`.

Garmin C kan herhaalde, direct aaneengesloten halve afstandslaps samenvoegen tot één langere herhaling wanneer na die lapparen consequent een herstellap volgt. De herkenning controleert hiervoor eerst rechtstreeks de ruwe afstanden en lapvolgorde, inclusief eventuele langere setpauzes, en is daardoor niet afhankelijk van de zoneclassificatie van de atleet. Als de opgeslagen FIT-laps niet volledig bruikbaar zijn, gebruikt dezelfde controle de genormaliseerde `Manual laps` uit de popup, inclusief het tijdformaat `HH:MM:SS.mmm`. De laplijst is zelf chronologisch; als er geen expliciete lapindex is, gebruikt Garmin C de positie in die lijst. Het getoonde gemiddelde tempo en herstel wijzigen de onderliggende afstands- en zonetotalen niet.

## COROS

De voorbereidende partnerinfrastructuur bestaat uit een publieke statuscheck en een workout-pushendpoint volgens sectie 5.3 van de COROS API Reference. Pushes worden alleen geaccepteerd met de door COROS verstrekte `client`- en `secret`-headers, dubbele payloads leveren opnieuw succes op zonder dubbele opslag. OAuth-koppeling en verwerking naar atleettrainingen worden pas toegevoegd nadat COROS API-credentials heeft verstrekt.

De vier voor de aanvraag vereiste MiLa-logo's staan in `core/static/core/brand/coros/`.

## DCO Other — Vitals-filter

- `Show NA` staat standaard uit: alleen atleten met minimaal drie ingevulde waarden voor de gekozen vital worden getoond. Met het vinkje aan verschijnen ook de NA-regels. De keuze blijft behouden bij wisselen van vital; Vitals blijft open.
- `HR zones` is de vijfde vitalkeuze. De matrix toont Z1–Z5 horizontaal en atleten verticaal. Atleten zonder HR-invoer worden standaard verborgen; `Show NA` toont ook hen. Losse HR-getallen worden als zone-maxima weergegeven (Z1 vanaf 0, Z5 blijft de ingevoerde waarde). Zelf ingevoerde bereiken blijven staan; niet-aansluitende grenzen worden rood gemarkeerd.

## Polar Integration — Type A/B/C/D

De aparte uitleespagina haalt één gekozen kalenderdag via de bestaande Polar v4-koppeling op. De app gebruikt het Bearer-token; een API-link in de browser vraagt niet om de juiste koppeling. Bij HTTP 401 probeert de app één tokenvernieuwing; datumparsefouten krijgen alternatieve datumformaten. Andere fouten tonen de Polar-foutreden.

| Type | Uitkomst |
| --- | --- |
| A | Exacte afstand, afstand afgerond op 50 meter, duur, aparte handmatige/automatische rondes, min/km, afzonderlijke Zx- en Tx-tempoaanduidingen en gemiddelde HR uit seconde-samples per ronde. |
| B | Cumulatieve afstand, hartslag en tempo over het vorige getoonde interval; interval 1–3600 seconden. |
| C | Ruw en verwerkt tempo naast elkaar, met werkelijke vensterduur, status en reden. |
| D | Km per tempozone en HR-zone in één overzicht, plus een vaste trainingssamenvatting en optionele AI-toelichting. |

- Original Polar JSON blijft beschikbaar. A/B veranderen of schatten geen ontbrekende samples; NA betekent ontbrekend of niet berekenbaar.
- Type A sluit recordings met een bekende niet-hardloopsport uit, volgens dezelfde Polar-sportcontrole als Type D. Ontbrekende sportmetadata wordt niet automatisch uitgesloten.
- Type A genereert uit duidelijke handmatige rondes een compacte omschrijving met warming-up, op herhaalde afstand gegroepeerde hoofdsegmenten, het Z-bereik per segment, gemiddelde herstelduur per segment in seconden en een eventuele duidelijke cooling-down. Afwisselende lange tijdsblokken met korte herstelrondes worden ook als hoofdblokken herkend, inclusief gemiddelde herstelduur.
- Polar B kan, wanneer `OPENAI_API_KEY` beschikbaar is, naast de vaste herkenning een taalmodel gebruiken voor geneste intervalstructuren met meerdere afstanden of herhaalde sets. Alleen compacte numerieke lapgegevens worden verzonden; de server valideert de gestructureerde reactie en valt zonder bruikbare reactie terug op de vaste Polar B-regels.
- Eén substantiële handmatige lap met alleen een kleine GPS-restlap wordt als `Continuous run` over de volledige sessie beschreven.
- Elk herkend hoofdsegment toont ook de gewogen gemiddelde kilometertijd als compacte `(mm:ss)`-waarde, zonder eenheid zodat de omschrijving later in de planner bruikbaar blijft.
- Korte herhalingen met relatief lange herstel-laps kunnen bij een duidelijke tweedeling in snelheid eveneens worden herkend, ook wanneer werk en herstel op dezelfde afgeronde afstand uitkomen.
- Opeenvolgende korte blokken met verschillende afstanden kunnen afzonderlijk worden beschreven; een losse GPS-afwijking binnen een blok wordt via de mediane blokafstand opgevangen.
- Zonder handmatige laps toont Type A een General description voor een duurloop, met totale kilometers, gemiddeld tempo en de dichtstbijzijnde ingestelde Z-zone van de atleet.
- C gebruikt een gecentreerd venster van maximaal 15 seconden binnen rondegrenzen, pauzes en geldige data. Mogelijke stops en meetpieken blijven zichtbaar. De criteria staan in `DATA_RULES.md`.
- D gebruikt handmatige rondegemiddelden wanneer bruikbaar; anders alleen ongeflagde C-tempo's. De tempozones komen uit Athlete settings. Bekende niet-hardloopsporten worden uitgesloten en recordings worden afzonderlijk geanalyseerd.
- HR gebruikt afstandstoenames en gemiddelde hartslag van de eindpunten. De vier bovengrenzen voor Z1–Z4 zijn invoerbaar; Z1 heeft geen ondergrens, Z5 is open naar boven.
- Eerder opgeslagen Type D-grenzen gaan voor. Anders vult de app leesbare HR-grenzen uit Athlete settings aan met de geschatte preset 145/160/175/185 bpm. Deze preset moet voor de atleet worden beoordeeld. `Remember these HR limits for this athlete` bewaart grenzen en Estimated-vlag apart van Athlete settings.
- Unclassified blijft onderdeel van het totaal en toont niet betrouwbaar in te delen afstand. Alle km-weergaven zijn onafhankelijk afgerond op 100 meter.
- AI kan alleen de trainingsstructuur toelichten en wijzigt geen berekende tabel. Bij ontbrekende API-configuratie of een fout blijven de vaste berekeningen en samenvatting beschikbaar.
- Deze pagina's veranderen geen training, planning of evaluatie. De sampleweergave/verwerking is begrensd tot 24 recordinguren; ontbrekende dekking wordt niet aangevuld.

## Trainingspopups en knopcontrast

AYC, Flex Planner en Trainer Planning plaatsen hun trainingspopups onder `document.body`, boven de Bootstrap-backdrop en buiten de teambekleding. De AYC verplaatst ook de `today`-popup naar `document.body`, zodat de backdrop de dialoog niet kan afdekken en de pagina na openen niet onklikbaar blijft. Flex ondersteunt dit bij zowel fetch als HTMX; Trainer Planning bij HTMX. Polar-knoppen gebruiken witte tekst op gevulde achtergronden, onafhankelijk van teamkleur 2.

## Meeting requests

- Een atleet kan in Athlete Settings een meeting aanvragen en de eigen openstaande aanvraag annuleren. De aanvraagdatum wordt getoond.
- DCO Other > Info Quality toont aanvragen van de eigen atleten met leeftijd in dagen: groen 0–2, oranje 3–5 en rood vanaf 6 dagen.
- Een nieuwe aanvraag opent een popup voor de hoofdcoach op de eerstvolgende geladen pagina. Bevestigen markeert de huidige aanvragen als gezien; een latere nieuwe aanvraag triggert opnieuw een popup.

## Flex Planner — persoonlijke kopie op een rustdag

Een expliciete persoonlijke training (zoals een gekopieerde trainertraining) heeft voorrang op `Rest` in Base Planning. `Rest` verbergt nog steeds de gedeelde trainerplanning, maar wist/verbergt geen expliciet geplaatste atleettraining.

Bij het openen van een AYC-training gebruikt de popup de training die de kalendercel toont, ook wanneer het bewerkplan een gedeeld Flex-slot bevat. Een bestaande persoonlijke Flex-override blijft leidend; zonder die override wordt de celprefill gebruikt, met Base Planning als terugval voor rechtstreeks geopende popups.

## Flex Planner — week kopiëren en plakken

Naast iedere geselecteerde atleet staat per week een compacte `c`- en `p`-actie. `c` kopieert de zichtbare week; daarna kan `p` de volledige week naar een andere week van dezelfde atleet plakken. De bestaande Flex-rechten, overrides en racebescherming blijven gelden. Celhoogtes groeien mee met langere trainingen zodat de volledige inhoud zichtbaar blijft.
