# Functionele onderdelen

- Garmin C/D-chat kan bij een complete tijdreeks met precies één beperkt te lange werkrep om bevestiging vragen. Bijvoorbeeld zes werkblokken van circa 6 minuten met één 6:45: na `6*6'` verschijnt een vraag met bevestigingsknop; ook `ja` in de chat bevestigt. Pas daarna verandert de preview naar 6×6′. Use/Add blijft de afzonderlijke opslagactie. De gemeten tijden, afstanden en hartslag blijven intact.
- De openstaande Garmin-bevestiging blijft ook op de server aan dezelfde browsersessie en activiteit gekoppeld. Een getypte `ja` of `yes` werkt hierdoor ook vanuit een Diary die al vóór een update geopend was; dezelfde geldigheids- en meetcontroles blijven gelden.

- Athlete Diary heeft voor staf een optionele `Simple`-weergave. Per AM/PM-sessie blijven het bestaande hardloop-kmtotaal, de hardloop-kmtotalen per zone, de Alternative-totalen en de trainingsevaluatie zichtbaar; de trainingsinhoud, whereabouts en meetknoppen worden niet weergegeven. De normale weergave blijft standaard.

- Whereabouts biedt naast de bestaande categorieën ook `Other`. Deze categorie wordt als gewone datumrange opgeslagen en verschijnt in Year Planner en de whereabouts-markeringen van Athlete Diary.

- Individual Planner toont bij een gemeten Polar/Garmin-training hetzelfde klokje als Athlete Diary. Het opent de opgeslagen gemeten Main-reps of splits met afstand, tijd, tempo en beschikbare hartslagwaarden; het klokje opent niet het trainingsformulier.

- Alternative toont en totaliseert tijd per zone voor Z1 tot en met Z6. Z4–Z6 worden net als Z1–Z3 in sessiekoppen en weektotalen getoond, zonder als hardloopkilometers mee te tellen.

- Per atleet kan `Week view in mob diary` worden ingeschakeld. Standaard blijft mobiel één geselecteerde dag per week tonen; ingeschakeld staan alle zeven dagkaarten onder elkaar. De instelling heeft geen invloed op desktop.

- Alleen het formulier `Evaluatie seizoen 2025-2026` van Honoré Hoedt krijgt bij Filled forms de kolommen `Coach comment` en `Plan`, per gewone vraag en per matrixregel. Bevoegde edit-coaches kunnen wijzigen; view-only coaches en de betreffende atleet kunnen alleen lezen. De atleet ziet de velden bij het eigen ingevulde formulier. Wijzigingen slaan automatisch op bij verlaten van het veld. Deze notities staan apart van de atleetantwoorden in EvaluationResponse.coach_feedback en wijzigen de antwoorden of submitted_at niet. Bestaande ingevulde formulieren krijgen lege coachvelden; andere vragenlijsten behouden hun weergave.

- Flex Planner toont het rode verwijderkruisje ook bij handmatig ingevoerde races, in AM en PM. Een verwijderde handmatige race uit een bronplanning blijft met een lege persoonlijke override onderdrukt. Races met een actieve Race Calendar-koppeling behouden hun bescherming.

- Year Planner-periodisatie biedt naast Recovery, Aerobe, Specific, Intense en Taper ook Racing (mediumblauw). Racing ondersteunt kiezen, leegmaken, slepen en rij-kopiëren; de fasekleur loopt mee in de weekkleuren van Flex Planner, AYC en Trainer Planning. Het blijft losstaan van echte Race Calendar-wedstrijden.

- Periodisatierijen kopiëren/plakken in Year Planner slaat de hele zichtbare rij met één batchverzoek en één databasetransactie op, ook bij 12 maanden. De kopie wordt pas na succesvolle opslag getoond; fouten laten geen gedeeltelijke rij achter. Opeenvolgende opslagacties worden geserialiseerd en de planner wacht tijdens opslaan met nieuwe bediening. Wedstrijddagen worden server-side overgeslagen en blijven beschermd. Ook schilderen gebruikt batchopslag in plaats van losse verzoeken per dag.

- Add race vraagt standaard alleen een datum. `Multiple days` klapt een optionele `Until`-einddatum open; uitschakelen maakt de wedstrijd weer eendaags. De einddatum is inclusief en mag niet vóór de start liggen. De lijst en popup tonen het datumbereik. Race Calendar en de Training-laag van Year Planner tonen alle wedstrijddagen, ook over maand-/jaargrenzen; alle dagen blokkeren fasewijzigingen. Bestaande races blijven eendaags. Bestaande AYC/Flex-raceafstanden blijven gekoppeld aan de startdatum; de duur van het evenement verdubbelt de trainingsafstand niet automatisch.

- Periodisatieblokken (Recovery/Aerobe/Specific/Intense/Taper) in Year Planner hebben sleepgrepen aan hun begin en einde, ook over maandgrenzen in de zichtbare periode. Verlengingen nemen de gekozen fase over op aangrenzende dagen; inkorten maakt de vrijgekomen dagen leeg. Wedstrijddagen vormen een grens. Slepen geeft direct een voorbeeld, loslaten slaat de volledige wijziging atomair op; Escape annuleert en bij een opslagfout wordt het voorbeeld teruggedraaid. Atleten blijven alleen-lezen.

- Race filter biedt naast Group en Athlete ook Race Type met All en de zes racetypes. Het typefilter combineert met de overige filters en blijft behouden bij periode-/jaarnavigatie en opslaan; Show all races toont uitsluitend races van het gekozen type.

- De groene deelnemeraantallen per afstand in de Race Calendar-lijst worden direct na succesvol automatisch opslaan bijgewerkt, inclusief het verschijnen bij de eerste selectie en verdwijnen bij de laatste uitschrijving. Ze volgen de actieve groeps-/atleetfilter; meerdere vinkjes voor dezelfde atleet/afstand tellen één keer.

- Een race kan alleen verwijderd worden als er geen atleet meer aan gekoppeld is via Trainer-, Athlete- of Target-selectie. Deze controle geldt voor alle atleten, los van filters, en wordt server-side afgedwongen. De Delete race-knop staat linksonder en wordt na opslaan van selecties direct bijgewerkt.

- Geselecteerde Race Calendar-wedstrijden (Trainer, Athlete of Target aangevinkt) verschijnen per atleet op de Training-laag van Year Planner in hun Race Type-kleur, nooit als Whereabouts. Meerdere afstanden van dezelfde wedstrijd tellen als één markering; bij meerdere wedstrijden op één dag delen de kleuren de cel. De wedstrijdnaam staat vast in de cel; hover toont de voor die atleet geselecteerde afstand(en). Wedstrijddagen hebben geen fasekeuze en zijn ook server-side tegen fasewijzigingen beschermd. Bestaande fases blijven onder de wedstrijd bewaard en verschijnen weer na uitvinken. Terugkeren vanuit Race Calendar ververst de planner met behoud van de URL-selectie.
- Championships uit de Race Calendar verschijnen daarnaast als gedeelde rode kalenderlaag op iedere geselecteerde `Basis`-rij, zonder dat een atleet, afstand of Attend-keuze nodig is. Gewone races blijven uitsluitend aan hun geselecteerde atleten gekoppeld. Een meerdaags championship vult iedere dag tot en met de einddatum; deze dagen zijn ook in Basis server-side beschermd tegen periodiseringswijzigingen.

- Races hebben een opgeslagen Race Type: Championship, Race Other, Diamond League, Race Gold, Race Zilver of Race Bronze. Bestaande en nieuwe races beginnen als Race Other. Coaches wijzigen dit direct onder Manage distances; de keuze slaat automatisch op en de lijstomlijning volgt direct de Year Planner-legendakleur. Atleten kunnen het gedeelde racetype alleen lezen.

- Year Planner heeft naast de legenda een `Race Calendar`-knop die de bestaande werkende racelijst binnen de pagina opent. Dezelfde knop keert terug naar de ongewijzigde planner met behoud van de selectie. De geïntegreerde weergave biedt alleen de lijst, inclusief perioden, filters, toevoegen, afstanden en wedstrijdkeuzes; de losse Race Calendar behoudt List/Calendar. Bestaande coach-/atleetrechten blijven gelden.

## Privacyverklaring

- De openbare Engelstalige privacyverklaring is beschikbaar via `/privacy/` en gelinkt vanaf de loginpagina. De tekst beschrijft de gegevenscategorieën, doeleinden, coach-/atleetzichtbaarheid, bewaartermijnen, beveiligingsmaatregelen, minderjarigen en externe diensten (Render, Oura en jsDelivr).
- De Oura-koppeling ondersteunt OAuth-autorisatie. De Oura-testpagina kan de afgelopen 14 dagen slaap- en readiness-samenvattingen ophalen en alleen tijdelijk tonen; previewdata wordt daar niet opgeslagen.
- De Engelstalige Terms of Service is openbaar beschikbaar via `/terms/`, met links naar de privacyverklaring. Beide documenten zijn bereikbaar vanaf de loginpagina.
- Atleten hebben alleen wanneer hun coach `Allow Oura connection` inschakelt onder `More > Hardware` een aparte tegel met de optionele Oura OAuth-koppeling. De verbinding is per eigen atleetaccount, vraagt expliciete wellness-toestemming en een bevestiging van volwassenheid/ouderlijke toestemming, vraagt alleen de `daily`-scope en kan vanuit dezelfde tegel worden getest of losgekoppeld. Na koppelen, annuleren of loskoppelen keert de atleet terug naar Hardware. Coaches kunnen via het dashboard hun eigen aangesloten atleten in een tijdelijke testpreview ophalen. De AYC biedt de atleet ook `Use Oura data` wanneer Daily Vitals zichtbaar is en Oura is verbonden. De atleet kan maximaal 14 dagen met readiness-data bekijken, dagen verwijderen en met `Use all` geselecteerde waarden opslaan. Readiness is alleen een verborgen dagfilter; bestaande velden worden nooit overschreven, slaapkwaliteit is de Oura-slaapscore gedeeld door 10, gemiddelde slaap-HRV en laagste slaap-HR worden afgerond op hele bpm/ms. Laagste slaap-HR vult Morning HR. Dagen zonder readiness of zonder nieuwe invulbare waarden worden niet voorgesteld. Uitschakelen door de coach trekt de token in (waar mogelijk) en verwijdert de lokaal opgeslagen koppeling.
- De coach kan per atleet `Allow Polar access` inschakelen; standaard staat dit uit. Alleen met toestemming ziet de atleet de Polar-tegel en Polar A/B-knoppen in de AYC. Polar-pagina's en data-endpoints controleren dezelfde toestemming; coachgebruik blijft beschikbaar.

Bijgewerkt: 29 oktober 2026.

## Dashboard en Planning

In New, Plans, Wishes kan de maker een eigen actieve wish bewerken. De productbeheerder (`admin`) kan iedere actieve wish bewerken. Andere gebruikers hebben geen Edit-knop en wijzigingen worden ook server-side geweigerd.

In Athlete Input staat boven de tabs voor trainers steeds de naam van de geselecteerde atleet. De aanduiding blijft zichtbaar wanneer tussen tabs wordt gewisseld; in de eigen Athlete settings van een atleet wordt deze niet getoond. Naast de naam kunnen trainers alfabetisch naar de vorige of volgende atleet binnen de actieve coachweergave gaan; het huidige tabblad blijft behouden.

Het coachdashboard toont Planning bovenaan. Onder `Coach dashboard` staat voor trainers met gedeelde toegang een `View as coach`-keuze. Standaard kijkt een trainer als zichzelf; na selectie van een andere toegestane coach tonen plannings- en beheerschermen alleen de gegevens van die coach. De dropdown toont of die toegang view-only of edit is; bij view-only worden schrijfacties server-side geblokkeerd. Settings is een werkende dashboardtegel voor coachinstellingen, waaronder Planning Camps. De Oura-testtegel staat onderaan bij de testpanelen en verschijnt alleen als de coach een aangesloten Oura-atleet heeft. Stats en Polar houden hun under-development-aanduiding.

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
- Whereabouts-keuzes zijn Camp, Travel, Test, Championship, Diamond L, Race Gold, Race Silver, Race Bronze, Race Other, Expermeetings, Medical, Brinec en Other, elk met een vaste kleur. Ze worden als echte datumranges opgeslagen, zodat een kamp of reis als één doorlopende pil met gecentreerde naam verschijnt en kan worden verkleind/verlengd. Gewoon slepen verplaatst de range, ook naar een andere atleet; `Ctrl` ingedrukt houden tijdens het slepen maakt een kopie. Tijdens het slepen staat bij de aanwijzer duidelijk `Move` of `+ Copy`. Overlappende whereabouts, zoals een testdag binnen een kamp, blijven naast elkaar bestaan en delen de dagcel diagonaal.
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

Ondersteunde onderdelen zijn WU, Mob/Tech, Sprint, Main, Strength, Alternative en CD. Standaard krachtprogramma's kunnen vanuit Mob/Tech worden geopend. Afstanden tonen waar mogelijk richttijden; tijdsblokken tonen richttempo in min/km. Progressive ranges zoals `z2>z4` en `t5>t15` nemen de tussenliggende Z/T-stappen mee in de kleurverdeling en kilometertelling. Alternative-tijdsblokken in Z1, Z2 en Z3 worden in de weektotalen afzonderlijk als ALT-minuten getoond en tellen niet mee als loopkilometers. Net als bij Main scheidt `//` meerdere Alternative-blokken.

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

## Garmin-verbinding en AI-toestemming

- Trainer-only `Allow Garmin Connection` in Athlete settings staat standaard uit. Alleen toegestane atleten zien onderaan het dashboard de Garmin-tegel. Dit staat los van `Allow Garmin FIT uploads`.
- De atleet autoriseert Garmin via OAuth2 PKCE. Datatoestemming is vereist; het afzonderlijke OpenAI-vinkje is optioneel en standaard uit. Alleen de atleet kan toestemming geven. Zonder AI-toestemming gebruikt Garmin C uitsluitend vaste lapherkenning.
- `Withdraw AI permission` staat op het eigen dashboard en in Athlete settings wanneer Garmin is toegestaan. Dit registreert intrekking, blokkeert nieuwe Garmin-AI-analyse, wist lokale tokens en probeert Garmin uit te schrijven. Bij een Garmin-fout meldt het dashboard hoe de atleet de koppeling ook in Garmin Connect kan verwijderen. De trainerinstelling blijft aan zodat bewust opnieuw verbinden mogelijk is. Reeds geïmporteerde activiteiten blijven behouden.
- Traineruitschakeling ontkoppelt eveneens en maakt lopende OAuth-pogingen ongeldig. AI-toestemmingsdatum, tekstversie en laatste intrekkingsdatum blijven bewaard.

Information Quality toont in beide hoverteksten `Last: dd-mm-yyyy`: de recentste kalenderdatum met ingevulde vitals respectievelijk een trainingsevaluatie, ook buiten het tien-dagenvenster. Lege en toekomstige records tellen niet mee; zonder gegevens staat `Last: —`. Bestaande inzagerechten blijven gelden.

Honoré Hoedts `Evaluatie seizoen 2025-2026`: verbeterpunten tonen bij alle bestaande en nieuwe antwoorden de extra rijen Algemeen (bovenaan), Atletische vorming en Kracht (na Z4-5). De extra rijen gebruiken vaste tekstsleutels; oorspronkelijke rijnummers, antwoorden, coachfeedback en inzenddatums worden niet gemigreerd of herschreven. Tekstvakken voor antwoorden en coachfeedback groeien mee bij openen, typen en vensterwijzigingen; hun compacte minimum blijft behouden.

Onderaan het coachdashboard staat de alleen-lezen tegel `Garmin (under construction)`. De tegel is een gewone navigatielink naar `/coach/garmin/`, een afzonderlijk alleen-lezen scherm met de verbonden atleten van de actieve coachweergave. De lijst staat niet op het dashboard. Een atleet telt alleen mee met trainerstoestemming en een opgeslagen Garmin-verbinding. De tegel heeft geen verdere acties en is verborgen voor atleten en het beperkte Coach Tools-account.

In Garmin Connections opent een klik op een verbonden atleet een afzonderlijke lijst met datum en afstand van alle GarminActivity-records voor die atleet, nieuwste eerst. Alleen verbonden atleten van de actieve coachweergave zijn bereikbaar, ook via directe URLs. Dit overzicht combineert opgeslagen FIT-imports met ontvangen Garmin Activity Summaries; het haalt geen historisch Garmin-archief op.

## Garmin Activity Summary Push

- Migratie 0131 voegt een unieke Garmin user-ID aan verbindingen toe en bewaart ontvangen samenvattingen apart van volledige FIT-activiteiten. Nieuwe OAuth-koppelingen vragen de user-ID op bij Garmin; bestaande koppelingen worden bij ontvangst per verzoek één voor één met Garmin gematcht. Bij een tijdelijke fout of nog ontbrekende koppelingen retourneert de ontvanger 503 zodat Garmin opnieuw kan aanbieden. Er wordt nooit op naam of e-mailadres gematcht.
- `/integrations/garmin/activities/<private-key>/` accepteert uitsluitend Activity Summaries in Push-formaat: `activities` met `userId`, `activityId` (of `summaryId`), `startTimeInSeconds`, optioneel `startTimeOffsetInSeconds` en `distanceInMeters`. Ping/callbackURL-verzoeken worden niet uitgevoerd. De ontvanger slaat alleen activiteit-ID, starttijd, datum op het apparaat, afstand en ontvangstdatum op. Dezelfde activiteit wordt bijgewerkt bij een herhaling; batches met ongeldige gegevens worden vóór opslag geweigerd.
- De callback-URL heeft een eigen ontvangstcode, afgeleid van de bestaande Garmin-appsecret en Django-secret. Er is geen extra environment variable nodig. Alleen een superuser of productbeheerder ziet de volledige privé-URL onder `Garmin receiving setup` op de Garmin Connections-pagina. Deze pagina wordt niet gecachet. In Garmin API Tools moet Activity Summaries op Push en deze URL ingesteld/ingeschakeld worden.
- Uitschakelen/ontkoppelen blokkeert nieuwe ontvangst; de ontvanger controleert de actieve koppeling bij iedere opslag. AI is niet betrokken bij deze ontvangst. Bestaande FIT-uploads en ontvangen samenvattingen blijven behouden na ontkoppelen en verschijnen op datum gesorteerd in de eenvoudige lijst.

Op de Garmin-trainingslijst ziet iedere bevoegde coach de kopieerbare Garmin User ID van die atleet voor Summary Resender. Bij oude verbindingen haalt MiLa de ID rechtstreeks bij Garmin op. Een fout wist de koppeling niet; de coach kan opnieuw laden. Andere atleten en niet-toegankelijke coaches zien de ID niet. De pagina toont ook wanneer de laatste automatische Garmin-training is opgeslagen; deze tijdstempel bevestigt geen mislukte of nog niet aangeboden berichten.

## Garmin C — automatisch ontvangen activiteiten

Garmin C leest voor de geselecteerde atleet/datum zowel FIT-uploads als automatisch ontvangen activiteitensamenvattingen. Samenvattingen zonder rondes zijn zichtbaar met afstand/duur voor zover bekend, maar zonder Use AM/PM of AI-analyse. Activity Details leveren gemeten rondes en HR aan dezelfde bestaande C-herkenning; hiervoor moet bij Garmin `ACTIVITY – Activity Details` met dezelfde privé-URL worden ingeschakeld. Migratie 0132 bewaart duur en genormaliseerde detaildata. Herhaalde gewone summaries wissen bestaande details niet. Er worden geen GPS-coördinaten of ruwe tokens uit details bewaard.

Garmin C maakt expliciet onderscheid tussen alleen een opgeslagen summary en ontvangen details zonder bruikbare rondes. Nieuwe detailberichten bewaren een ontvangsttijd, lap-/sampleaantallen en de reden waarom rondes niet bruikbaar zijn. De oude melding om Activity Details aan te zetten wordt niet meer getoond bij reeds ontvangen details. Garmin C sorteert alle activiteiten chronologisch, inclusief summary-only regels. Een resend-verzoek geldt niet als bevestiging van ontvangst.

Information Quality bevat `Last active in MiLa`: het laatste succesvolle interactieve gebruik door de atleet zelf (HTML-paginabezoek of POST/formulieropslag). Vandaag is groen, gisteren oranje, ouder rood; zonder registratie staat NA. Registratie start bij de uitrol van migratie 0133 en wordt niet verzonnen op basis van oude login-, coach-, Garmin- of evaluatiedatums. Coachbezoeken, AJAX/background GETs, prefetch, geweigerde verzoeken en automatische imports tellen niet mee.

Race Calendar ondersteunt periode `season`: 1 oktober van het gekozen jaar t/m 30 september van het volgende jaar. Lijstweergave verdeelt de gefilterde wedstrijden chronologisch over drie evenwichtige kolommen; filter- en opslagacties behouden de seizoenkeuze.

Race Calendar heeft per atleet een onafhankelijke Attend-keuze zonder afstand. Attend telt mee als deelname en verhindert verwijderen van een gekoppelde wedstrijd. De Year Planner toont naam en racetypekleur; AYC en Flex tonen de wedstrijd zonder afstand/kilometers. Afstandselecties blijven onafhankelijk en vervangen de afstandloze weergave zonder dubbele wedstrijd. Beide kalenders lezen de racekoppelingen rechtstreeks, zodat AYC deze ook toont zonder trainerplanlidmaatschap.
# Garmin-ontvangst per training — 1 november 2026

De klokjespopup toont naast Last 15s HR ook Avg HR over de rep/split. Nieuwe overnames bewaren beide waarden en behouden ze bij Watch/Plan-wisselen. Samengevoegde blokken gebruiken een tijdgewogen lapgemiddelde bij volledige HR-dekking.

De klokjespopup toont Last 15s HR achter min/km. Deze meting blijft bij nieuwe overnames ook behouden bij wisselen tussen Watch en Plan. Eerder overgenomen trainingen zonder opgeslagen laatste-15-seconden-HR tonen NA; opnieuw Use AM/PM bewaart de beschikbare waarde uit de bestaande bronactiviteit.

Ook regelmatige 500m-laps zonder aanvullend herstelbewijs worden als één duurloopblok voorgesteld. De klokjespopup houdt de 500m-tussentijden en het laatste korte restant beschikbaar.

Bij een als één duurloopblok herkende kilometerreeks toont het AYC-klokje de afzonderlijke kilometerlaps en het laatste korte restant. De kalender houdt één blok met de totale gemeten tijd. Kilometerreptijden worden naar 1000 m omgerekend; het laatste restant houdt zijn gemeten duur. Stops blijven inbegrepen.

Watch B/Garmin C beschrijft gelijke kilometerlaps zonder aanvullend herstelbewijs als een doorlopend afstandsblok, bijvoorbeeld 27300 m Z1 in plaats van 27×1000 m. Losse stops blijven mogelijk; terugkerende timerpauzes of werk/herstel houden intervalherkenning beschikbaar. Nieuwe Garmin-details bewaren de beschikbare timer- en pauzeduur per lap voor herkenning. De gemeten lapafstand, verstreken tijd en HR blijven ongewijzigd.

Na Use AM/PM worden de tijden van herhaalde Main-reps in de kalender en het klokje omgerekend naar de herkende repafstand. De ruwe Garmin-tabel behoudt gemeten afstand en tijd. De klokjespopup licht de omrekening toe; tempo en gemeten totalen veranderen niet.

Bij Use AM/PM vanuit Polar A/B of Garmin C wordt het oorspronkelijke plan vóór de eerste overname apart bewaard. Naast het klokje opent `p/w` een popup met Watch en Plan. Bevoegde gebruikers kunnen beide kanten op wisselen; beide trainingsversies en de Watch-reptijden blijven bewaard. Herhaalde Watch-overnames behouden de eerste momentopname. Eerder overschreven trainingen zonder momentopname krijgen geen herstelknop. Migraties 0135 en 0136 zijn vereist. Bestaande Watch-overnames met een bewaard plan krijgen bij de eerste wissel ook een bewaarde Watch-versie.

Garmin C herkent korte herhaalseries gevolgd door een doorlopend blok, ook als kilometer-autolaps de handmatig gemarkeerde rondjes opdelen. Bij voldoende structuur wordt bijvoorbeeld `2*(5*100m) p45//3750m z2` voorgesteld. Uitlopen binnen dezelfde opname kan als CD worden onderscheiden; apart opgenomen activiteiten blijven afzonderlijk. De ruwe rondetabel verandert niet. Dezelfde conservatieve herkenning is beschikbaar in Watch B; AI mag deze duidelijk gemeten structuur niet vervangen door alleen de langere laps.

Het coachoverzicht met Garmin-activiteiten toont per training starttijd, laatste ontvangsttijd, of details ontvangen zijn met hun afzonderlijke ontvangsttijd, en het aantal opgeslagen bruikbare laps. Een herhaalde summary kan de laatste ontvangsttijd wijzigen zonder nieuwe details. Ontvangen details met nul bruikbare laps blijven herkenbaar als ontvangen. Handmatige FIT-bestanden tonen hun uploadtijd, bron en lapaantal afzonderlijk. De compacte diagnostiek staat onder de trainingsdatum en behoudt de bestaande coachrechten.

## Information Quality — ALL

Boven de atleten staat ALL met het gemiddelde van de zichtbare atleetpercentages voor Evaluated en Vitals. NA en niet-toegankelijke gegevens tellen niet mee; 0% telt wel mee. Zonder beschikbare percentages staat NA.

## Automatische Oura-vitals

Athlete Settings > General bevat Automatically import Oura vitals, standaard uit, instelbaar door de atleet zelf en bevoegde trainers. Dit vereist toegestane en verbonden Oura plus ingeschakelde dagelijkse vitals. Een geldige Readiness-score is voorwaarde; alleen lege slaapduur-, slaapkwaliteit-, Morning HR- en HRV-velden worden aangevuld. Bestaande waarden blijven behouden. Readiness zelf wordt niet geïmporteerd.

MiLa bewaart de IANA-tijdzone van het eigen apparaat van de atleet. Coaches veranderen die niet met hun apparaat. Zolang de tijdzone onbekend is, wacht de automatische import. Het schema is lokaal 06:30 t/m 08:00 iedere tien minuten, daarbuiten ieder heel uur, inclusief zomer-/wintertijd. Na reizen volgt de nieuwe tijdzone zodra de atleet MiLa daar opent. De achtergrondcontrole draait op Render zonder geopende browser; de uitvoercontrole gebeurt iedere 30 seconden en gemiste controles worden bij hervatten ingehaald. Athlete Settings toont de bekende tijdzone en tijd sinds de laatste controle.

## Garmin Health-vitals

De aparte Garmin Health Push-ontvanger verwerkt Dailies, HRV Summary en Sleeps voor verbonden atleten. Daarmee worden de vier bestaande Daily vitals — Sleep length, Sleep quality, Morning HR en HRV — automatisch aangevuld. Alleen lege velden worden gevuld; handmatige invoer en eerder geïmporteerde waarden blijven leidend. De privé-ontvangst-URL is uitsluitend zichtbaar voor productbeheer op de Garmin-coachpagina.

## Garmin C — activiteiten samenvoegen

Selecteer twee of drie activiteiten van dezelfde atleet/dag in Garmin C en kies per activiteit WU, Main of CD. Combine maakt bovenaan een nieuwe preview met Use AM/PM; er is precies één Main en iedere rol komt maximaal eenmaal voor, in chronologische volgorde. Alleen activiteiten met bruikbare analyse en laps zijn selecteerbaar. Een bestaande WU/CD in Main mag niet dubbel worden toegevoegd. Losse activiteiten blijven behouden; opslaan gebeurt pas bij Use AM/PM en behoudt de bestaande Watch/Plan-wissel.

Garmin C controleert ook na het samenvoegen van meerdere zone-/herstelgroepen of snelle opeenvolgende halve autolaps volledige reps vormen. Zo worden 24×500m-delen met herstel na ieder paar als 12×1000m beschreven. Het klokje gebruikt de opgetelde tijd, tijdgewogen Avg HR en Last 15s HR van de tweede helft; hersteltijd telt niet mee in de rep.

Garmin C bewaart een lang gemeten Main-blok vóór korte reps ook wanneer de automatische beschrijving uitsluitend de korte reps bevatte. Expliciete WU/CD worden op hun gemeten begin-/eindlaps aangesloten. De AYC-totalen herstellen die aansluiting ook bij oudere Watch-overnames, zodat WU/CD niet bovenop dezelfde gemeten kilometers worden geteld. Voor een vernieuwde beschrijving blijft opnieuw Use AM/PM nodig.

Garmin C/Watch B herkennen nu ook een rustige aanloop met kilometer-autolaps, gevolgd door korte versnellingen en wisselende korte werk/herstel-laps. Die korte werkblokken gaan niet verloren achter de dominante kilometerafstand. WU, Main en een duidelijke rustige uitloop blijven apart; afstanden worden nominaal op 50 m samengevat zonder extra reps te verzinnen. Gemarkeerde herstel-laps blijven buiten de klokreps, maar hun gemeten meters blijven onderdeel van de totalen.

Gemengde korte Garmin-reps worden compact per nominale afstand gegroepeerd met hun zonebereik en typische herstelduur. Het klokje bewaart de werkelijke chronologische repvolgorde, ook wanneer de beschrijving bijvoorbeeld 200m- en 150m-reps groepeert. Een laatste korte rep direct vóór een duidelijke rustige uitloop blijft behouden; CD verdwijnt daardoor niet.

Gemeten Watch-laps trager dan 10:00 min/km gelden als wandelen en tellen niet mee in zonekilometers, sessieafstand en weektotalen. Precies 10:00 telt nog mee. Ruwe laps, gemeten duur/afstand en HR blijven beschikbaar; ook bestaande Watch-overnames gebruiken deze totalenregel zonder nieuwe import. Dit geldt voor Watch A/B en Garmin C, niet voor berekende geplande trainingen.

Een los opgenomen Main met uitsluitend afwisselende korte werk-/herstelparen gebruikt dezelfde compacte afstandsgroepen, maar behoudt de gewone afronding op 50 m. Een snelle lap onder 175 m blijft hier 150 m; herstel-laps tellen niet als reps. De bestaande herkenning met aanloop en GPS-afstandsclusters blijft ongewijzigd.

Garmin C/Watch B herkennen gelijke tijdsherhalingen die door kilometer-autolaps zijn opgesplitst, bijvoorbeeld 5×8′ p90. De beschrijving blijft tijdsgebaseerd. Het klokje toont per volledige herhaling de opgetelde gemeten tijd, afstand en HR. Sessie- en weekkilometers komen uitsluitend uit de gemeten laps, met de bestaande wandeluitsluiting; zonesnelheden schatten geen extra afstand.

Ook twee volledige kilometer-autolaps met een kort reststuk vormen zonder herstelbewijs één doorlopend blok (bijvoorbeeld 2162.83m → 2150m Z1). Het klokje bewaart beide kilometers en het reststuk; sessiekilometers blijven gemeten.

Garmin Combine: een activiteit met bruikbare gemeten laps maar zonder herkende Main-beschrijving kan als WU of CD worden geselecteerd. Alleen de activiteit in de Main-rol vereist een gegenereerde training; de Main-optie is uitgeschakeld bij niet-herkende activiteiten. Summary-only activiteiten blijven uitgesloten.

## Garmin D — zonecontrole met hartslag

Naast Garmin C staat Garmin D. D gebruikt dezelfde activiteitselectie, trainingsstructuur, combinatiebediening en gemeten afstanden/tijden. Voor een rep van minstens 400 gemeten meter óf 50 gemeten seconden gaat de zone uit End HR vóór de tempozone Z1–Z5. De ingestelde HR-grenzen van de atleet zijn leidend; ontbrekende/ongeldige HR of grenzen behouden de tempozone. Korte reps blijven op tempo. Bij samengestelde reps, zoals 5×8′ met kilometer-autolaps, gebruikt het volledige blok de End HR over het volledige blok. D krijgt een eigen opgeslagen bron, kloklabel en Watch/Plan-momentopname; C en de brondata worden niet gewijzigd.

Staff Team Overview > Vitals heeft één Daily vitals-tab voor Sleep length, Sleep quality, Morning HR en HRV, met per atleet vier kolommen. Elke cel toont het veertiendaagse gemiddelde gevolgd door (laagste–hoogste). Per vital zijn minstens drie niet-lege metingen vereist; 0 telt mee. Show NA toont ook atleten zonder voldoende gegevens voor enig vital. Zonder die optie worden alleen volledig onbeschikbare rijen verborgen; ontbrekende cellen blijven NA. HR zones blijft een afzonderlijke tab en oude vital-links openen de gezamenlijke tabel.

Details Camps toont per deelnemer Comments direct na Accommodation. Het compacte tekstveld ondersteunt meerdere regels, maximaal 2000 tekens, automatische opslag, sorteren en de bestaande Copy/Paste-actie. Bewerkrechten volgen dezelfde deelnemerrechten als de reisgegevens; read-only rijen tonen opgeslagen opmerkingen.

Details Camps bewaart vervoer per deelnemer in twee richtingen: `Transport from Airport to Camp` en `Transport from Camp to Airport`. Het voormalige veld `Rental Car Info` wordt met behoud van bestaande inhoud de heenrichting. Beide velden ondersteunen automatisch opslaan, sorteren en Copy/Paste en volgen dezelfde deelnemerrechten als de overige kampgegevens.

Garmin C/D bieden bij herhaalde lange intervalgroepen die zowel bij vaste afstanden als hele minuten passen twee keuzes: Distance en Time. De gekozen beschrijving en bijbehorende HR-zonecontrole worden door Use AM/PM en Combine overgenomen. Bij meerdere duidelijk verschillende afstandsgroepen staat Distance standaard geselecteerd. Bij één reeks waarvan alle werkblokken strak rond hetzelfde hele aantal minuten liggen, staat Time standaard geselecteerd en blijft Distance als handmatige keuze beschikbaar. Dezelfde meetlaps bepalen altijd de kilometers; de klok behoudt alle reps bij beide keuzes.

Een expliciete Chat-opdracht met één tijdsreeks, zoals `4*8'`, wordt eerst lokaal vergeleken met de reeds herkende gemeten tijdvariant. Alleen exact overeenkomende aantallen en hele minuten worden gekozen; hiervoor is geen AI-aanroep of AI-toestemming nodig. Een afwijkende vraag, bijvoorbeeld vijf herhalingen bij vier gemeten werkblokken, blijft afgewezen.


Garmin C/D gebruiken End HR: laatste 10% van de volledige gemeten repduur, minimaal 15s; onder 15s Avg HR. Dit geldt ook voor gereconstrueerde reps en D-zonecontrole. Eerder gebruikte lange Watch-reps zonder opgeslagen HR-samples moeten opnieuw via Use AM/PM worden overgenomen om de nieuwe eind-HR te tonen; opnieuw verzenden vanuit Garmin is niet nodig als details al beschikbaar zijn.


Stats: de wekelijkse afstandsgrafiek is gestapeld per Z1–Z6, met de bestaande MiLa-zonekleuren en Z1 onderaan. Legenda en tooltip tonen zone/zonekilometers plus weektotaal. Dezelfde effectieve loads bepalen totalen en zoneverdeling; wandelen en Alternative blijven uitgesloten. Onbekende zones krijgen zo nodig een grijs Other-deel zodat de totale balkhoogte behouden blijft.


Strength in de trainingspopup ondersteunt maximaal vijf trainingsfoto’s naast vrije tekst; nieuwe uploads staan standaard bij Strength. Bestaande Mob/Tech-foto’s blijven op hun oorspronkelijke segment staan. Add photos opent de camera/bibliotheekkeuze van de browser; geselecteerde foto’s krijgen direct een preview. Save bewaart ze, Remove verwijdert de koppeling bij Save. Een thumbnail opent de volledige JPEG in een nieuw tabblad voor zoomen. Beschikbaar in Trainer/Flex en AYC, volgens bestaande bewerkrechten; ook een foto zonder tekst is een geldige Strength-training. Dag-/weekkopieën en Watch/Plan-snapshots nemen fotoreferenties mee. Saved Trainings blijven tekstsjablonen.


Garmin C/D herkennen een volledige afwisseling van twee middelgrote repafstanden met trager herstel als beide afstandsgroepen, bijvoorbeeld 6×400m + 6×300m. Beide groepen behouden hun eigen zones/pauzes en alle gemeten reps blijven zichtbaar in de klokpopup.


Garmin C/D kunnen een door AI voorgestelde lapindeling gebruiken voor lange tijdsintervallen met automatische splits en verschillende repduren. De AI verwijst naar originele lapnummers; de server controleert volledige dekking, unieke/toenemende reps, werk/herstelcontrast en nabijheid van hele minuten. Een geldig voorstel levert Distance en Time met dezelfde meetloads. Voorbeeld: drie doorlopende laps samen 8:02, gevolgd door 8:01 en vier circa 4-minutenreps. De bestaande AI-toestemming en vaste fallback blijven gelden.


Duidelijke gemengde lange tijdsblokken worden ook lokaal voorgesteld: aaneengesloten snellere laps vormen één werkblok, langzame onderbrekingen herstel. Minstens twee verschillende tijdsgroepen zijn vereist. Dezelfde lapvalidator maakt Distance/Time-opties, onafhankelijk van AI-toestemming of beschikbaarheid. AI blijft beschikbaar voor interpretaties die deze vaste controle niet kan afleiden.

Garmin C/D bieden ook Time bij één complete reeks van N gelijkdurende werkblokken (minstens drie), afgewisseld met duidelijk trager herstel. Dit geldt algemeen voor hele minuten van 2–30 minuten, met maximaal 15s of 6% afwijking. Werkafstand mag variëren; de bestaande Distance-beschrijving en gemeten meters/seconden blijven behouden. De tijdsvariant bewaart expliciete repkoppelingen, ook na de D-hartslagcontrole.

Garmin C/D: korte versnellingen gevolgd door langere afstandsseries blijven samen in de beschrijving. Een zesde versnelling met kort overgangsherstel wordt behouden wanneer daarna een lang blok volgt. Latere series vereisen herhaalde nominale afstanden en duidelijk trager herstel; onverklaarde latere snelle lange laps verhinderen een onvolledige korte-repbeschrijving. De 33-lapregressie bewaart 6×50m, een circa 900m tussenlap, 3×800m, 5×500m en circa 1000m CD, met alle gemeten klokreps en bronmeters in C/D.

Alternative accepteert nu zowel `+` als `//` tussen losse trainingsblokken, net als Main. Dit geldt bij opslaan, voor bestaande gecombineerde teksten, Base Planning en de Flex-browsertotalen. Voorbeeld: `25'z1 + 3*10' z2 + 25'z1 elliptical` telt 50 minuten Z1 en 30 minuten Z2, zonder loopkilometers. Scheidingstekens binnen haakjes blijven onderdeel van de herhaalde set.

Staff Team Overview heeft een tab Injury/Issue Overview. Per toegankelijke atleet staan standaard vijf bolletjes voor de laatste ingevulde trainingsevaluaties tot en met vandaag, op trainingsdatum en AM/PM gesorteerd (nieuwste rechts). Een schuifje toont direct 5 tot 25 evaluaties, standaard 5. Een klik op een werkelijk ingevulde evaluatie opent een leesbare popup met datum, AM/PM, commentaartekst, RPE en het oorspronkelijke Done/Adjusted/Not done-statussymbool en label. Fit is groen, Some issue geel en Serious issue rood. Ontbrekende indicaties of evaluaties zijn grijs; afgeschermde of uitgeschakelde trainingsrapporten tonen geen bolletjes. Tooltip/toegankelijk label vermeldt datum, AM/PM en status. Dit overzicht gebruikt geen tiendaags venster.

Injury/Issue Overview: de evaluatiepopup heeft See training. Deze opent een alleen-lezen popup met de momenteel opgeslagen training voor dezelfde atleet, datum en AM/PM, inclusief Main/Strength-labels. Persoonlijke/Flex-/Watch-aanpassingen en expliciet lege overrides worden meegenomen; baseplanning en wedstrijden volgen de kalenderregels. Back to evaluation keert terug zonder de geselecteerde evaluatie te verliezen. Dit is geen historische trainingssnapshot.

Naast de bolletjes staat Comments coaches met rechts een +. Net als bij Desired Improvements bewerkt elke trainer alleen de eigen opmerking per atleet; lege opslag verwijdert alleen die eigen tekst. Andere auteurs blijven behouden. Initialen (eerste/laatste naamdeel, bijvoorbeeld Piet van Driel = PD) en stabiele trainerkleur worden met Desired Improvements gedeeld. Alleen coaches met bewerkrechten en trainingsevaluatie-toegang mogen schrijven; view-only kan alleen lezen.

Het voormalige Main 2 heet Strength in Trainer Planner, AYC, Flex Planner, baseplanning, opgeslagen standaarden en trainingsdetails. Het blijft intern CORE2, zodat bestaande teksten behouden blijven. Strength is vrij tekstveld zonder zone-, tempo- of afstandsvalidatie; ook een training met uitsluitend Strength is toegestaan. In formulier en training volgt Strength de instelbare segmentvolgorde. Strength telt niet mee als loopafstand, looptijd of zonetotaal, ook niet bij oudere opgeslagen numerieke/zonegegevens. Mob/Tech-standaardprogramma’s blijven afzonderlijk beschikbaar.

Trainingssegmenten staan in formulier en trainingsweergave op afzonderlijke regels. Standaard: WU, Mob/Tech, Strength, Sprint, Main, Alternative, CD. In het gedeelde Trainer/AYC/Flex-formulier kunnen segmentvelden worden gesleept of met omhoog/omlaag-pijltjes verplaatst. De volgorde wordt per training opgeslagen en bij heropenen en in alle drie planners gevolgd. Meerdere Main-/Alternative-blokken behouden onderling hun bestaande volgorde. Dag-/weekkopieën, opgeslagen standaarden en afzonderlijke Watch-/Plan-versies nemen de volgorde mee. Rechten en read-only-trainingen blijven ongewijzigd.

Garmin D: HR Zx in Recorded laps en Automatic laps is een rechtstreekse koppeling van de End HR op diezelfde regel aan de ingestelde hartslagzones van de atleet. De kolom is onafhankelijk van herkende werkreps, trainingsbeschrijving en de 400m/50s-correctiedrempel. Ontbrekende End HR of onbruikbare HR-grenzen tonen NA, zonder terugval op de tempozone. Pace Zx blijft de oorspronkelijke tempozone tonen. De bestaande zonecorrectie van de gegenereerde training blijft een aparte berekening.

Garmin C/D hebben een aanvullende, conservatieve afstandsregel wanneer alle tempozones Z1 zijn maar de gemeten eind-HR een duidelijke werk/herstelreeks toont. Minstens vier vergelijkbare lange werkreps, vaste afstand en duidelijk lagere herstel-HR zijn vereist. Gesplitste herstelrondes en langere herstelafstanden blijven zichtbaar. Voor de 15-lapregressie ontstaat 6×1000m, met bronlaps 1/4/6/8/10/12 en circa 1400m CD; de rustige kilometer van 12:13 blijft herstel. C behoudt tempozones; D corrigeert de volledige werkreps met de bestaande HR-zoneberekening.


## AI-afstandsgroepen (4 november 2026)

De bestaande AI-lapindeling ondersteunt nu ook target_meters naast target_seconds (per groep precies een doeltype). AI kiest de bronlaps en nominale afstand; de server valideert volledige, unieke dekking, chronologie, herstel en maximaal 8% afstandsafwijking. Geen nieuwe patroonherkenningsregel toegevoegd. Afstandsgroepen behouden alle gemeten meters/seconden en krijgen geen verzonnen Time-alternatief. Geldt voor Garmin C en D binnen bestaande AI-toestemming; bestaande vaste herkenningen blijven als voorrang/fallback bestaan. Regressie met gemockt AI-antwoord: 2000m WU, lange stop, 17x500m inclusief 531.92m-uitbijter en laatste werkrep; alle 17 kloktijden behouden. 88 gerichte tests en manage.py check geslaagd. Echte AI-service, Render-deploy en visuele productiecontrole nog niet bevestigd.


Garmin AI-diagnose (4 november 2026): C/D vraagt nu uitsluitend lap_structure/confidence in plaats van ook de oude segmenten/sets-optie. De oudere Polar-aanroep blijft compatibel. Per activiteit verschijnt een compacte status: toegepast, toestemming ontbreekt, serversleutel ontbreekt, servicefout, onbruikbaar/afgewezen antwoord of vaste herkenning zonder AI. Geen ruwe foutantwoorden of sleutels naar de browser. Productiecasus 17x500m nog niet bevestigd: lokale omgeving heeft geen serversleutel/atleet59; productiereden vereist de nieuwe status na deploy. 106 gerichte tests slagen, plus manage.py check. Bredere Polar Raw-tests hebben vier bestaande rechtenmockfouten (SimpleNamespace als user-id); de overige herkenningsasserties slagen na behoud legacycompatibiliteit.


Garmin herstellen na intrekken (4 november 2026): dashboard behoudt een hersteltegel bij garmin_ai_withdrawn_at, ook als de coachschakelaar inmiddels uit staat. In dat geval alleen uitleg om de coach Allow Garmin Connection te laten inschakelen; endpointrechten blijven ongewijzigd. Een bestaande verbinding zonder geldige AI-toestemming toont opnieuw het toestemmings-/OAuth-formulier. Intrekken verwijdert lokale tokens, remote ontkoppeling blijft best effort; nooit automatisch toestemming herstellen. Tests: 19 Garmin Connection-regressies en manage.py check slagen. Geen migratie; visuele mobiele/productiecontrole nog niet uitgevoerd.


FIT AI-toestemming (4 november 2026): uploadscherm bevat voor atleten een optioneel, standaard uitgeschakeld vakje met Save AI permission, apart van bestand uploaden. Geldt voor bestaande/toekomstige eigen FIT-bestanden inclusief Coros, zonder Garmin OAuth. Coach ziet alleen status/uitleg en kan nooit toestemming namens een atleet opslaan; endpoint controleert eigen atleet en uploadrecht. Migratie 0144 voegt fit_ai_consent_at, fit_ai_withdrawn_at en fit_ai_consent_version toe. Intrekken verwijdert geen bestanden en raakt Garmin-koppeling/toestemming niet. C/D kiest toestemming per activiteitbron: GarminActivity gebruikt FIT-toestemming, ontvangen Garmin-details blijven de bestaande Garmin-toestemming gebruiken. Geen AI zonder geldige toestemming of bij ingetrokken uploadrecht. Privacytekst bijgewerkt. 60 gerichte Garmin-/Watch-tests en manage.py check geslaagd; visuele desktop-/mobiele controle en productie-uitrol nog niet bevestigd.


Download originele FIT-upload (4 november 2026): Saved Garmin activities op het uploadscherm heeft Download original. GET-route garmin_upload_download retourneert ongewijzigde raw_file met veilige attachment-bestandsnaam, private/no-store en nosniff; oorspronkelijke ZIP blijft ZIP. Zelfde uploadrecht/toegankelijke atleet vereist; eigen atleet of bevoegde coach, geen Coach Tools-only of vreemde atleet, 404 zonder bronbestand. 21 gerichte tests en manage.py check slagen. Geen migratie. Kilometerafwijking Daan blijft open en vereist brononderzoek; deze wijziging maakt het bronbestand downloadbaar. Visuele desktop-/mobiele controle nog niet uitgevoerd.


AI-voorstel ter beoordeling (4 november 2026): automatische acceptatie blijft confidence >=0.75 vereisen. Een AI-voorstel met geldige score 0.50-0.75 kan na volledige identieke lap-/meetvalidatie als aparte keuze AI proposal — review worden aangeboden. Fallback blijft standaard geselecteerd; alleen expliciet kiezen vervangt fields/loads voor Use AM/PM. Ongeldige/ontbrekende laps blijven afgewezen. Zelfgerapporteerde modelscore is geen gemeten juistheidspercentage. Toestemming en maximaal een AI-herstelpoging ongewijzigd; C/D behandelen voorstel dezelfde wijze inclusief HR-correctie en klokmetadata. Regressies bewaken .70 zonder automatische acceptatie, afwijzing van verzonnen laps, optionele C/D-preview en ongewijzigde standaardvelden. 97 gerichte tests en manage.py check slagen. Echte productie-indeling en visuele controle nog niet bevestigd.


Activiteiten zonder afstand (4 november 2026): Garmin Activity Details missing_distance behoudt nu ook geldige hartslagsamples en beperkte summaryvelden activityType, average/maxHeartRateInBeatsPerMinute en activeKilocalories. C/D-summarykaart toont sport, aangeleverde gemiddelde/max-HR, actieve kcal en ontvangen HR-sampleaantal. Alleen indien Garmin geen HR-samenvatting levert, afzonderlijk benoemde samplegemiddelde/max; geen afstanden, pace of looploads geschat en geen AI-aanroep voor deze kaart. GPS/overige raw data blijven uitgesloten. Oude missing_distance-ontvangsten bevatten deze velden niet: nieuwe/resend Activity Details vereist; originele FIT-upload kan brongegevens ter inspectie leveren. 34 gerichte tests en manage.py check slagen; visuele desktop-/mobiel-/productiecontrole niet uitgevoerd.


Championships in Trainer Planner (5 november 2026): alle RaceEvent-records met race_type=championship van de planeigenaar verschijnen als extra rode pill in de juiste dagkop van elk trainerplan. Alleen evenementnaam; geen deelnemers, afstanden of deelnamefilter. Meerdaagse evenementen gelden inclusief einddatum en worden op de zichtbare weken begrensd. Meerdere evenementen leveren aparte pills; titels worden geescaped, breken af in smalle kolommen en blijven in Print weeks zichtbaar. Geen trainingsslots, kopieerdata of kilometers toegevoegd. Toegang volgt het bestaande plan-/coachbereik, ook gedeelde view-only coach. Vijf gerichte championship-/kleurtests en manage.py check geslaagd; geen migratie. Visuele desktop-/mobiele controle nog niet uitgevoerd.


Doorlopende Z1-laps (5 november 2026): opeenvolgende bekende Z1-looplaps worden standaard als een blok samengevoegd, inclusief laatste gedeeltelijke lap. Minstens twee positieve meetlaps, geen expliciete FIT rest/recovery/intervalmarkering, geen wandelen >10:00/km en geen duidelijk snelheidscontrast (max/min snelheid >=1.6). Alleen timerpauzes maken van Z1-laps geen reps. Bestaande bredere kilometerherkenning blijft fallback voor andere zonepatronen; AI-opdrachten (strict C/D/FIT en legacy) bevatten dezelfde Z1-prioriteit. Beschrijvingsafstand afgerond volgens bestaande 50m-regel; bronmeters/seconden onveranderd. Regressie Kane-waarden 1005.56+1000.39+234.197m geeft 2250m Z1 in C/D met en zonder AI, ook met timerpauzes, zonder AI-verzoek. 101 gerichte tests en manage.py check slagen. Geen migratie; visuele productiecontrole niet uitgevoerd.


Evaluatie per dagdeel (5 november 2026): desktop AM-/PM-previewhelften en mobiele AM-/PM-knoppen openen uitsluitend hun eigen evaluatie. Popup toont datum/dagdeel en actuele weergegeven training (alle tekstsegmenten in weergavevolgorde, veilig als tekst); Watch/Plan-keuze blijft gevolgd. Alleen zichtbare dagdeel wordt gevalideerd/opgeslagen; bestaand status/RPE/pain/commentaar en Watch-resultaat van het andere dagdeel blijven ongemoeid. Herinnering Evaluate opent de bijbehorende slot_index. Compacte flex-popup met scrollbaar middendeel, vaste ombrekende knoppen, 16px mobiele invoervelden, max92dvh en toetsenbordbediening desktop. 9 gerichte tests inclusief werkelijk uitgevoerde JS-open-/savehandlers, behoud PM bij AM-opslag, bestaande evaluatie-/pain-/herinnerings-/mobieltests en manage.py check slagen. Synthetische gerenderde popup visueel gecontroleerd in Chromium op 390x844 en 1440x900; mobiel 390px documentbreedte en dialoog volledig binnen viewport. Geen migratie; productiecontrole nog niet uitgevoerd.


Use AM/PM bewaart overige trainingsvelden (5 november 2026): toepassen van horlogeresultaten A/B/C/D vervangt uitsluitend WU, Main (CORE), Alternative (ALT) en CD. Mob/Tech, Sprint en Strength worden server-side niet herschreven, ook niet wanneer een oude browser lege/afwijkende waarden of fotoverwijderingen meestuurt. Bestaande segmentrecords, parsing, programmakoppeling en fotoverwijzingen blijven behouden; bij gedeelde/Base Planning-bron worden die onderdelen gekopieerd naar de persoonlijke override zonder de bron te veranderen. Segmentvolgorde wordt overgenomen van zichtbare bron; geen auto-WU/CD over meetvelden heen. Lege ontvangen WU/ALT/CD wissen die vervangbare velden. AYC verstuurt alleen de vier bedoelde teksten plus horlogedata; Alternative gebruikt fields.alt/alternative. Watch/Plan-snapshots bevatten de volledige bewaarde training. 81 gerichte Watch/Plan-, foto-, Strength-, volgorde- en Garmin-tests geslaagd; daarna 14 Watch/Plan-tests inclusief aanvullende lege-grenzen/auto-WUCD-regressie, plus manage.py check. Geen migratie of layoutwijziging; productiecontrole nog niet uitgevoerd.

## Niet-hardloopactiviteiten naar Alternative — 5 november 2026

Garmin C en D genereren voor een bekende niet-hardloopsport een compacte tekst zoals `Elliptical 90' Z2` of `Pilates 46' Z1`, ook zonder afstand of laps. Duur wordt afgerond op hele minuten. Bij een herkende tijdsintervalreeks wordt per werkblok de eind-HR (met lapgemiddelde als terugval) naar een zone vertaald; verschillende gemeten werkzones worden als bereik getoond, bijvoorbeeld `16×3' p45 Z2>Z3`. Zonder zo'n reeks wordt het gemiddelde van de hele activiteit gebruikt. Op iedere gebruikte HR komt eerst de persoonlijke `Alternative HR correction (Alternative → Running)`, waarna de eigen HR-grenzen worden toegepast. Deze correctie staat standaard op +10 bpm, kan door coach en atleet in Athlete Info > Training defaults worden gewijzigd en mag niet negatief zijn. Ontbrekende HR of ontbrekende/ambigue zonegrenzen geven uitleg zonder een zone te verzinnen; sport en duur blijven wel een toepasbare Alternative met Use/Add AM/PM. Use AM/PM vervangt de gekozen dagdeeltraining door de ontvangen Alternative. Add AM/PM voegt de activiteit als afzonderlijk Alternative-segment toe en behoudt bestaande segmenten, zodat bijvoorbeeld Strength en Elliptical samen één dagdeeltraining met twee segmenten vormen. Een lege training krijgt alleen Alternative; een overgeërfde training wordt persoonlijk gekopieerd. Alleen meetgegevens worden lokaal gebruikt, zonder AI-aanroep. Hardloopactiviteiten houden hun bestaande analyse en importgedrag.

Activity Details zonder afstand bewaren voor bekende niet-hardloopsporten ook de expliciete Garmin-lapgrenzen als tijdslaps. De popup toont per lap duur, gemiddelde HR en eind-HR; afstand en tempo blijven `NA`. Een duidelijke afwisselende reeks van minstens drie vrijwel gelijke hele-minutenwerkblokken met kortere herstelblokken wordt lokaal samengevat, ook met één voor- en/of nablok, bijvoorbeeld `Elliptical 6×8' p180`. Zonder zo'n volledig patroon blijft de totale Alternative-tekst staan.

De Alternative-totalen herkennen herhalingsnotatie met `*`, `x` en `×` ook achter de activiteitnaam. Een automatisch gegenereerde tekst als `Elliptical 16×3' p45 Z2>Z3` telt daardoor meteen alle zestien werkblokken en verdeelt de 48 actieve minuten gelijk over Z2 en Z3.

Coach Athlete Info opent rechtstreeks de alfabetisch eerste toegankelijke atleet in Athlete input. De voormalige tussenpagina met de atletentabel wordt niet meer getoond. Bovenaan Athlete input staat een alfabetische selector voor alle atleten binnen de actieve coachweergave; wisselen behoudt de actieve tab. New athlete blijft op dezelfde pagina beschikbaar. Na aanmaken opent direct het nieuwe profiel. De persoonlijke Athlete settings van een atleet blijft rechtstreeks het eigen profiel zonder selector.

AI en kilometer-autolaps (5 november 2026): de opdracht voor Garmin C/D/FIT verduidelijkt dat meerdere ononderbroken kilometerlaps één langere afstandsrep kunnen vormen, met voorbeelden voor 3000m- en 2000m-reps en een doorlopende duurloop als tegenvoorbeeld. De AI blijft de brongroepering kiezen; geen nieuwe lokale herkenningsregel. De generieke AI-validator vereist minimaal 20% hogere werksnelheid dan de gemeten herstelsnelheid bij beide aangrenzende reps, naast de bestaande dekking-, afstand-, duur- en betrouwbaarheidscontroles.


Garmin C/D AI-latentie (5 november 2026): automatisch goedgekeurde AI-indelingen worden 24 uur gecachet per atleet en exacte opdracht (inclusief meetwaarden, zones en model). C en D delen dit voorstel; actuele toestemming blijft voor ieder gebruik vereist. De standaard Django-cache is proceslokaal: andere workers/herstarts kunnen opnieuw AI vragen. Afwijzingen, reviews en servicefouten worden niet gecachet. Strict AI-verzoeken wachten maximaal 12s per eerste netwerkpoging en 6s voor één herstelpoging (voorheen 25+15); meerdere activiteiten kunnen nog steeds optellen. De popup onderscheidt confidence- of meetafwijzing, zonder twee confidencegrenzen achter elkaar. Screenshotcasus confidence 0,42 bewijst geen meetfout; stabiele live 4×3000-herkenning blijft onbevestigd. Geen lokale patroonherkenning of confidenceverhoging toegevoegd.


Garmin C/D opent de gemeten preview zonder AI-verzoek (preview=measured) en vraagt daarna automatisch de AI-analyse in een afzonderlijk browserverzoek op. Resultaten blijven bruikbaar bij een AI-fout. Zonder gebruikersinteractie verschijnt de analyse automatisch; na interactie biedt Show analysis deze expliciet aan, zodat combinatiekeuzes niet worden overschreven. Toestemming en atleetrechten worden voor beide verzoeken opnieuw gecontroleerd.


Garmin C toont voor 4×3000 m met alle volledige reps in Z2 uitsluitend Z2, ook als enkele kilometer-autolaps Z3 zijn. Verschillende volledige repzones kunnen wel Z2>Z3 opleveren. D behoudt de hartslagcorrectie na deze tempobepaling.


AI-structuur C/D ondersteunt korte afstandssets met herstel onder 30s: bijvoorbeeld drie sets van acht 300m met 28-30s pauze en langere setpauzes. Modelopdracht benoemt target_meters voor korte reps, alle reps in één groep en set_start_laps voor gelijke sets. Validator geeft afzonderlijke feedback voor ongeldige afstandtarget, tijdtarget of repaantal.


C/D-repsamenvatting negeert zeldzame zones onder 10% van de reps binnen dezelfde groep. Bijvoorbeeld één Z5-rep van 24 vergroot Z3>Z4 niet naar Z3>Z5. Exact 10% telt mee; één van vier blijft dus zichtbaar. Alle afzonderlijke bronlaps en metingen blijven behouden.


6 november — alternatieve horlogetrainingen: Use AM/PM vult Alternative en wist WU/Main/CD. Alleen bij ALT-resultaten verschijnen daarnaast Add AM/Add PM; deze voegen ieder ontvangen resultaat als apart Alternative-segment toe en behouden de rest van de training. Zo kunnen meerdere Garmin-activiteiten in één AM- of PM-training worden gecombineerd. Mob/Tech, Sprint en Strength blijven bij beide acties behouden.


6 november — Information Quality: Vitals toont NA wanneer Evaluated NA is. Show NA is een schakelaar, standaard uit; rijen met Evaluated NA blijven verborgen tot inschakelen. 0% blijft zichtbaar. NA telt niet mee in ALL-gemiddelden. Toegangsbeperkingen blijven gelden; zonder vitalsrechten blijft de afgeschermde weergave behouden.


6 november — coachdashboard bundelt Polar en beide Garmin-tegels onder Hardware acces. De tegel opent een apart overzicht met de bestaande namen en bestemmingen; Garmin uploads behoudt de bestaande voorwaarde dat toegankelijke uploadatleten aanwezig zijn. Stats en eventueel Oura blijven op het dashboard.


6 november — Trainer Planning opent standaard met 12 zichtbare weken (voorheen 4). De bestaande weekkeuze en navigatie blijven behouden; ongeldige weekinvoer valt terug op 12. Gerichte standaard-/expliciete-/ongeldige-weektest en manage.py check geslaagd.


6 november — Evaluations-tegel verplaatst van Dashboard naar Planning > Views, voor coaches en atleten. De instelling evaluations_enabled van de actieve coach/eigen coach en coach-tools-only-beperking blijven van kracht. Bestaande evaluatiepagina, rechten en inhoud ongewijzigd. Tegel gebruikt responsieve Planning-kolommen. Gerichte evaluatieflow en modulezichtbaarheid voor coach/atleet plus manage.py check gecontroleerd.


6 november — coachdashboard heeft optionele Under Dev-tegel, waaronder Stats en Hardware acces staan. Coach Settings > Modules > Under Dev staat standaard uit, per actieve coach opgeslagen. Uitgeschakeld toont dashboard ook bij directe section=under_dev/hardware geen submenu. Bestaande individuele functionaliteit/rechten behouden.


6 november — Coach tools, Settings, Under Dev en New, Plans, Wishes verhuisd van regulier Dashboard naar Planning > More. Atleten krijgen New, Plans, Wishes eveneens onder Planning, zonder coachtegels. Under Dev blijft afhankelijk van actieve coachmodule. Bestaande coach-tools-only-accounts houden hun enige directe Coach tools-ingang omdat Planning voor hen niet beschikbaar is.


6 november — View as coach verplaatst van Dashboard naar bovenaan Planning. Selectie via POST op Planning gebruikt dezelfde toegestane coachkeuzes en actieve sessie als voorheen. Directe Dashboard-terugknoppen verwijderd uit onderliggende pagina’s; submenuverwijzingen naar Under Dev/Hardware blijven behouden.


6 november — atleten vinden Garmin connection en Garmin uploads nu in Planning in plaats van Dashboard. Bestaande eigen-atleetrechten, coachtoestemming, AI-toestemming en uploadvoorwaarden blijven behouden. Garmin OAuth-/intrekkingsstatus keert terug naar Planning.


6 november — hoofdpagina /planning/ heet nu Mila Planner (paginakop en browsertitel). Evaluations heeft een Back-knop naar deze hoofdpagina. Bestaande terugknoppen naar planning_overview met label Planner/Planning/Back to Planning heten consequent Back; links naar specifieke planners en annuleerknoppen blijven ongewijzigd. Gerichte titel-/evaluatienavigatie-/module-/coachselectietests en manage.py check geslaagd.


6 november — Coach tools, New/Plans/Wishes en Coach Settings hebben Back naar Mila Planner. Atleten vinden Garmin connection/uploads achter Hardware in More naast New/Plans/Wishes. Eigen rechten/consent behouden; Garmin-statusredirects openen dit Hardware-overzicht. Coachtegel Athletes en atleettegel Athlete settings heten Athlete info.


6 november — zichtbare namen: Athlete Year Calendar → Athlete Diary, Trainer Planning → General Plans, Flex Planner → Individual planner. Interne routes, typecodes en plannamen voor herkenning blijven behouden. Inloggen start standaard op Mila Planner (/planning/); expliciete next-bestemming blijft voorrang hebben. Atleetoptie Start on Diary behoudt bestaande start_on_ayc-instelling. Gewoon openen van / leidt ook naar Mila Planner, met bestaande Diary-startuitzondering; Under Dev/Hardware en Oura-statusweergave blijven bereikbaar.


6 november — Individual planner heet Individual Plans; Focus Points and Desired Improvements heet Improvements; Details Camps heet Camps. Namen aangepast in tegels, bijbehorende paginatitels en instellingslabels. Routes, modellen en rechten behouden.


6 november — Standards-groep op hoofdpagina vervangen door coachtegel Standard Trainings onder More. Submenu /planning/?section=standards bevat Saved Trainings en Standard Strength met bestaande bestemmingen/rechten. Overige categorieën behouden.


6 november — Evaluations voor coaches verplaatst van Views naar Coach Plannings; de atleetingang blijft onder Views. Coachvolgorde aangepast volgens UI_RULES, met bestaande modulezichtbaarheid en rechten behouden.


Atleethoofdpagina: nieuwe Views-volgorde met Evaluations achteraan; losse racekalendertegel verwijderd, bestaande racefunctie en Year Planner-ingang blijven behouden. Rechten voor Year Planner, Camps en Improvements blijven ongewijzigd.


6 november — More is in-/uitklapbaar voor coaches en atleten, standaard ingeklapt. Klein rood telbolletje naast More toont hetzelfde aantal New-items als New/Plans/Wishes: publicaties uit afgelopen14 dagen, ook0. Telling verandert niet door open-/dichtklappen; alle bestaande tegels/rechten behouden.


6 november — Django Admin-tegel verplaatst van oud dashboard naar More op Mila Planner. Alleen zichtbaar voor het ingelogde coach-adminaccount (bestaande productbeheerdercontrole), onafhankelijk van actieve coachselectie. Bestaande Django-adminrechten behouden. Twaalf gerichte tests en manage.py check geslaagd.


6 november — Athlete Diary toont nu ook op mobiel de Alternative-weekminuten per zone (ALT Z1/Z2/Z3) bij de hardloopkilometers. Gebruikt dezelfde bestaande weektotalen als desktop, inclusief uitsluiting van niet-uitgevoerde dagdelen.


6 november — Diary-sessietotalen bevatten naast T/loopzones een A met Alternative-minuten per zone. Zowel AM/PM als mobiele/desktopweergave gebruiken dezelfde bestaande ALT-loads; ook bij gecombineerde loop-/ALT-sessies. Zichtbaarheid volgt See session zones. Geen verandering aan loopafstand of weekberekening.


6 november — Year Planner heeft Basis - All wanneer Group=All, naast bestaande Basis per General Plan. Basis selecteren verstuurt direct het formulier, ook zonder geselecteerde atleet. Eigen periodisering en whereabouts per coach; geen automatische toepassing op atleten. Bestaande Use for all selected rows blijft beschikbaar.


Year Planner Group=All toont nu afzonderlijke Basis-keuzes voor alle toegankelijke General Plans (bijvoorbeeld MID en LONG), naast Basis - All. Meerdere Basis-schema’s kunnen samen worden geselecteerd en getoond zonder losse atleet. Iedere Basis behoudt eigen opgeslagen data.


## Garmin C/D - Suggest structure (6 november 2026)

Naast Use AM/PM staat bij loopresultaten een compact invoerveld met Suggest. Voorbeelden: 16x500m, 2x8x500m, 2x(8x500m), 4x3min of groepen met +. Het model toetst de suggestie aan de oorspronkelijke laps van de gekozen activiteit; de server controleert targets, aantallen, sets en bestaande meetvoorwaarden. Bij succes wordt alleen de preview vervangen met gemeten laptijden, herstel en eigen C/D-zones; opslaan blijft expliciet via Use AM/PM. Bij afwijzing blijft het huidige resultaat behouden. Bestaande Garmin-/FIT-AI-toestemming blijft vereist. Atleten zien geen AI-modelnamen, diagnostische statusregels, afwijsdetails of analysenotities; coaches wel.


Garmin C/D chat (6 november): het losse Suggest-veld is vervangen door Chat naast Use AM/PM. Opent een ombrekend chatpaneel per activiteit met vrije tekst, gesprekshistorie en Send (Enter verstuurt, Shift+Enter nieuwe regel). Gebruiker kan om uitleg of een wijziging vragen. Een antwoord zonder gevalideerde structuur houdt de huidige preview intact; alleen een volledig gecontroleerde lapindeling levert een nieuw bruikbaar voorstel. Opslaan blijft Use AM/PM. Gesprek blijft alleen tijdens de geopende popup bewaard.


Garmin C/D-chat: gerichte afstandscorrectie binnen bestaande expliciet gemarkeerde reps. AI stelt uitsluitend count/from_m/to_m voor; server wijzigt alleen een unieke bestaande groep en bijbehorende nominal_rep_m. Bijvoorbeeld zes200m-reps worden185m, terwijl150m-reps, WU/CD, zones, pauzes en bronmetingen gelijk blijven. Geen hergroepering. Ontbrekende/ambigue repkoppeling of onpassende meting geeft geen bruikbaar correctievoorstel.


6 november — Year Planner-layout als één samenhangende wijziging: compacte periode-/weergavebalk, Race Calendar/Camps rechtsboven, inklapbare Legend, inklapbare Selection met aantallen en aparte Basis/Athletes/Coaches. Selection onthoudt open/dicht tijdens selecteren. Kalender heeft maandbanden, horizontale datumlabels, lichte daglijnen en sterkere week-/maandgrenzen; namen blijven vast bij horizontaal scrollen. Onderliggende data-/selectie-/opslagregels ongewijzigd.


Staff Team Overview kleurt bij Sleep length de laagste en hoogste slaapduur afzonderlijk: kortste vandaag donkerrood, gisteren/eergisteren lichtrood; langste vandaag donkergroen, gisteren/eergisteren lichtgroen. Gemiddelde en andere vitals blijven neutraal.


7 november — Daily vitals gebruikt een daggrens om 08:00 lokale applicatietijd. Vóór 08:00 eindigt het veertiendaagse venster gisteren; ook de slaapkleur-recente dagen schuiven mee. Alleen de laagste en hoogste waarden krijgen kleur; gemiddelden blijven neutraal. Overige overzichtsdatums blijven ongewijzigd.


7 november — Extremumkleuren gelden voor alle vier Daily vitals. Sleep length, Sleep quality en HRV: laagste rood, hoogste groen. Morning HR: laagste groen, hoogste rood. Vandaag donker, één/twee dagen terug licht; oudere/volledig gelijke waarden neutraal, meest recente datum bij gedeeld extremum. Daggrens 08:00 en minimum drie waarden blijven gelden. Alleen range-eindpunten gekleurd, met datumtooltip; gemiddelden/NA en rechten ongewijzigd.


Garmin C/D toont een stabiele Z1-duurloop met een duidelijk gemeten slotserie van minstens drie korte versnellingen als twee blokken in Main. De gemeten preview herkent dit direct. De AI-chat kan dezelfde indeling voorstellen via continuous_main_laps.


Garmin C/D controleert een expliciete chatinvoer zoals 2*(1700m-1200m-850m) rechtstreeks tegen de bronlaps. Bij een match krijgt de preview de gevraagde setstructuur met gemeten zones en pauzes.


Garmin C/D herkent ook een reeks van minstens drie vrijwel gelijke tijdreps met een apart slotblok. De gemeten preview toont de reeks en het slotblok afzonderlijk. In chat kan het slotblok als hele minuten of als passende doelafstand worden aangevraagd.


9 november — Bij een loopresultaat in Athlete Diary voegen Add AM en Add PM de looptraining toe naast de bestaande Alternative. Ze vervangen de loopvelden WU, Main en CD in het gekozen dagdeel en nemen de gemeten looplaps mee.


10 november — Garmin C/D kan korte versnellingen gevolgd door dalende afstandssets in opnamevolgorde tonen. Expliciete chatnotatie zoals 4800m//3*50m//3*(200m-190m-150m)//1950m wordt lokaal tegen alle vier fasen getoetst.


Garmin C/D-chat kan een volledige afstandsvolgorde zoals 1650m//1600m//8*500m aan opeenvolgende bronlaps koppelen. De expliciete suggestie levert de herhalingscontext wanneer herstel niet is geregistreerd. De chat vermeldt dat de herstelduur onbekend is.


Garmin C/D-chat kan op verzoek losse afstandsblokken voor de herhalingen in Main plaatsen. Een expliciet no wu vereist een voorstel zonder warming-up. Coaches krijgen een waarschuwing als een voorgestelde warming-up Z2 bevat.
