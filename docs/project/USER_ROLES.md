# Gebruikersrollen en toegang

Bijgewerkt: 12 oktober 2026.

## Trainer

Een trainer is doorgaans staff- of superuser en kan:

- atleten en groepen beheren;
- zones, PR's, doel-PR's, ideale week en WU/CD-instellingen beheren;
- basis- en trainerplanningen maken;
- de Flex Planner, DCO en opgeslagen trainingen gebruiken;
- wedstrijden en wedstrijdafstanden beheren;
- standaard krachtprogramma's beheren;
- rapportages en zichtbaarheid per atleet instellen;
- in Coach Settings `Pain in training evaluations` beheren. Deze instelling is standaard aan en geldt voor de atleten van die coach, ook wanneer een bevoegde gedelegeerde trainer namens die coach werkt;
- in Staff Team Overview Information Quality het percentage geëvalueerde trainingen zien over de laatste tien kalenderdagen (inclusief vandaag; AM vanaf 12:00 en PM vanaf 21:00). Hover toont open en geëvalueerde aantallen; bij nul trainingen staat `NA`. Als de trainer geen recht heeft om evaluaties te zien of evaluaties voor de atleet zijn uitgeschakeld, blijven de gegevens verborgen;
- voor een geselecteerde atleet vitals en training reports vastleggen, ook wanneer een trainer vooruit werkt;
- in de AYC tussen toegankelijke atleten schakelen;
- in Athlete Input alfabetisch tussen atleten van de actieve coachweergave navigeren; de selectie blijft beperkt tot atleten die de trainer daar mag zien;
- Year Planner-training phases en whereabouts beheren, inclusief bulktoepassing op geselecteerde atleten;
- coach-whereabouts in de Year Planner bekijken en beheren voor zichzelf en coaches waarvoor toegang is verleend; deze uitzondering geldt uitsluitend voor coach-whereabouts, niet voor andere gegevens van een view-only coach;
- evaluatievragenlijsten maken, titel/actieve status/doelgroep (alle eigen atleten of geselecteerde losse atleten) aanpassen en ingevulde antwoorden bekijken; als kopieerbron zijn eigen formulieren en formulieren van coaches met expliciete editrechten toegestaan, zonder antwoorden of wijzigingen aan het origineel;
- Focus Points and Desired Improvements openen wanneer dit in Coach Settings is ingeschakeld; alleen eigen atleten of atleten van de actieve coachweergave zijn beschikbaar. Eigen coaches en gedelegeerde coaches met editrechten kunnen commentaar toevoegen/wijzigen en een Excel-import doen die uitsluitend hun eigen comments vervangt voor bereikbare atleten met niet-lege cellen; view-only toegang kan het overzicht alleen lezen. Commentaar blijft per coach herkenbaar;
- stats, Polar en Django Admin openen waar beschikbaar.
- Per atleet de coach-only instelling `Allow Garmin FIT uploads` beheren; alleen geselecteerde atleten verschijnen in Garmin uploads en alleen de coach kan daar bestanden uploaden.
- In de AYC `Garmin C` gebruiken voor Garmin FIT-laps van de geselecteerde, toegankelijke atleet. De server beperkt activiteiten tot die atleet en datum; de planning wordt pas na expliciete keuze voor AM of PM aangepast. `Polar A` en `Polar B` zijn de namen van de Polar-modellen.

Een trainer ziet standaard alleen de eigen gegevens. Als via `CoachAccess` toegang tot een andere trainer is gegeven, kiest de trainer op het dashboard expliciet als welke coach hij kijkt. Die keuze toont uitsluitend gegevens van die gekozen coach en mengt ze niet met de eigen atleten, plannen, wedstrijden of templates. Gedeelde toegang is standaard view-only; alleen wanneer `can_edit` aan staat mag de meekijkende trainer wijzigingen opslaan. Deze toegang is niet transitief: als trainer A trainer B mag zien en B trainer C mag zien, dan ziet A trainer C niet. Historische atleten zonder owner horen via datamigratie aan de juiste trainer te worden gekoppeld, niet via een brede zichtbaarheidsexceptie.

In Athlete settings > Base Planning zijn zowel de atleetkeuze als `Copy van...` beperkt tot atleten van de coach die op dat moment wordt bekeken. Dezelfde beperking wordt bij het kopieerverzoek server-side afgedwongen.

De trainer en atleet kunnen in Athlete settings > General de persoonlijke opties `See session km` en `See session zones` aan- of uitzetten. `See session zones` start in dezelfde stand als `See session km`.

De trainer kan daarnaast in Coach Settings > Planning de coachbrede optie `See session km` beheren voor Flex Planner en DCO Training. Deze instelling verandert de persoonlijke AYC-keuze van atleten niet.

De trainer kan in Athlete settings per atleet de `P(ause)mode` instellen. Zonder afwijkende keuze volgt de atleet de coachinstelling; de atleet ziet en wijzigt deze coach-only instelling niet.

De trainer kan in Athlete settings per atleet `See desired improvement points` inschakelen. De atleet krijgt dan toegang tot het eigen overzicht met focuspunten en kan alleen de kolom `Comments athletes` invullen. De coach kan boven de kolom `Plan` per atleet `Show to athlete` aanzetten; zolang die uitstaat ziet de atleet alleen Focus point en `Comments athletes`, en bij inschakeling ook Prio, Plan en Progress. Plan en Progress zijn gedeelde velden die bevoegde trainers onderling overschrijven; bij de atleet worden geen trainers of initialen getoond. De coachcommentaren blijven uitsluitend zichtbaar voor coaches. Coaches zien de athlete-comments in hun volledige overzicht.

De atleet en de coach kunnen in Athlete settings > General per atleet `Start op AYC` aan- of uitzetten. Standaard staat deze persoonlijke startvoorkeur uit. Als die aanstaat opent de atleet na inloggen de eigen AYC; een expliciete loginbestemming blijft voorgaan. De voorkeur geldt niet voor trainers, ook niet wanneer een trainer meerdere atleten beheert.

Iedere gebruiker kan eigen actieve wishes indienen en bewerken. Alleen de productbeheerder kan wishes van andere gebruikers bewerken; overige gebruikers kunnen die alleen bekijken en liken.

## Atleet

Een persoonlijk trainingsplan op naam van het atleetaccount maakt dat account in de AYC niet tot trainer; de eigen AYC en de beperkingen voor toekomstige trainingen blijven gelden.

Een atleetaccount is aan één `Athlete` gekoppeld. Een atleet kan uitsluitend zien en gebruiken:

- de eigen AYC;
- de eigen Athlete settings;
- de eigen wedstrijdselectie;
- de Race Calendar, waarin de atleet wedstrijden en nieuwe afstanden voor de kalender van de eigen trainer kan toevoegen en uitsluitend de eigen wedstrijdvinkjes en het gedeelde doelwedstrijdvinkje kan aanpassen; bestaande afstanden verwijderen blijft trainer-only;
- het eigen dashboard en Planning-overzicht als toegangspunten;
- actieve evaluatievragenlijsten invullen wanneer de atleet expliciet tot de doelgroep behoort, en uitsluitend de eigen antwoorden terugzien. Bestaande vragenlijsten die eerder aan groepen gekoppeld waren blijven voor die atleten beschikbaar totdat de doelgroep wordt aangepast. Als de doelgroep later wordt aangepast, blijven reeds ingediende antwoorden voor de trainer bewaard, maar kan een uitgesloten atleet de vragenlijst niet meer openen;
- de eigen Year Planner alleen lezen wanneer de trainer Training en/of Whereabouts daarvoor heeft ingeschakeld;
- de eigen `Details Camps` bekijken en eigen aankomst-/vertrek- en reisgegevens aanpassen wanneer Whereabouts-toegang is ingeschakeld; deelnemers toevoegen of verwijderen en de kampnaam aanpassen blijft trainer-only (voor de kampnaam is edittoegang tot alle deelnemers nodig);
- een logoutknop die naar de loginpagina terugkeert.

Een atleet mag niet:

- tussen atleten schakelen;
- trainer-, flex- of basisplanning beheren;
- andere atleten bekijken;
- coachinstellingen, Admin, stats of beheerfuncties openen.
- Year Planner, evaluatievragenlijsten of antwoorden van andere atleten zien of wijzigen.

## Atleteninstellingen

Een atleet kan de eigen algemene gegevens, zones/PR's, ideale week en WU/CD-instellingen zien en waar toegestaan wijzigen. Algemene gegevens en zones kunnen worden opgeslagen terwijl PR's nog gedeeltelijk leeg zijn. Base Planning is standaard alleen-lezen. Als de trainer `Can change base planning` inschakelt, mag de atleet de eigen Base Planning wijzigen, inclusief een individuele training; groepskeuzes blijven beperkt tot groepen van de eigen trainer. De volgende trainerinstellingen blijven verborgen:

- hoeveel toekomstige weken zichtbaar zijn;
- rapportage- en zichtbaarheidsschakelaars;
- trainer- en groepstoewijzingen.
- de twee Year Planner-zichtbaarheidsschakelaars en overige rapportage-/zichtbaarheidsinstellingen.

## AYC-zichtbaarheid

- De trainer kan een atleet selecteren.
- De atleet ziet automatisch uitsluitend zichzelf.
- In de AYC kan een atleet standaard alleen trainingen van vandaag en eerdere dagen aanpassen; toekomstige trainingen en lege dagdelen zijn alleen door de coach te wijzigen. Met `Extended edit rights` mag de atleet ook toekomstige trainingen aanpassen en lege AM/PM-dagdelen vullen, en zijn op zichtbare dagen altijd beide trainingsevaluatievelden beschikbaar.
- De trainer bepaalt hoeveel toekomstige trainingsweken voor de atleet zichtbaar zijn.
- Wedstrijden mogen verder vooruit zichtbaar blijven dan trainingen.
- Rapporten en Daily vitals zijn alleen zichtbaar wanneer ze voor die atleet zijn ingeschakeld.
- Year Planner Training en Whereabouts hebben afzonderlijke trainerinstellingen per atleet. Een atleet kan nooit de selectie van andere atleten zien.
- Atleten zien in de Year Planner uitsluitend hun eigen atletenrij en eigen whereabouts; coachrijen zijn alleen beschikbaar in de coachweergave.

## Beveiligingsregel

Vertrouw niet alleen op verborgen knoppen. Iedere view en mutatie moet server-side controleren of de gebruiker de betreffende atleet, planning of training mag zien of wijzigen.

Meeting requests zijn alleen door de gekoppelde atleet zelf aan te maken of te annuleren. De hoofdcoach ziet alleen aanvragen van atleten die aan hem/haar toebehoren; gedelegeerde trainers krijgen geen meeting-requestmeldingen.

## Polar-uitlezen en analysegrenzen

- Een atleet gebruikt de eigen koppeling; een trainer kiest een toegankelijke atleet. De A/B/C/D-uitleespagina sluit losse, ongerelateerde Polar-userkoppelingen uit de selectie uit.
- Een eigenaar/bevoegde trainer of de betreffende atleet mag de eigen Type D-HR-grenzen en Estimated-vlag opslaan. View-only coachtoegang geeft wel inzage/analyse maar geen recht om grenzen te bewaren.
- Een ongeldig atleetdoel wordt vóór opslag geweigerd. Een formulier met HR-waarden voor de vorige atleet wordt niet op de nieuw gekozen atleet toegepast.
- Het lezen of analyseren van Polar-data wijzigt geen planning of trainingsevaluatie.
