# Gebruikersrollen en toegang

Laatst inhoudelijk gecontroleerd: 12 augustus 2026.

## Trainer

Een trainer is doorgaans staff- of superuser en kan:

- atleten en groepen beheren;
- zones, PR's, doel-PR's, ideale week en WU/CD-instellingen beheren;
- basis- en trainerplanningen maken;
- de Flex Planner, DCO en opgeslagen trainingen gebruiken;
- wedstrijden en wedstrijdafstanden beheren;
- standaard krachtprogramma's beheren;
- rapportages en zichtbaarheid per atleet instellen;
- in de AYC tussen toegankelijke atleten schakelen;
- stats, Polar en Django Admin openen waar beschikbaar.

Een trainer ziet alleen gegevens die volgens ownership en planrelaties toegankelijk zijn.

## Atleet

Een atleetaccount is aan één `Athlete` gekoppeld. Een atleet kan uitsluitend zien en gebruiken:

- de eigen AYC;
- de eigen Athlete settings;
- de eigen wedstrijdselectie;
- het eigen dashboard en Planning-overzicht als toegangspunten;
- een logoutknop die naar de loginpagina terugkeert.

Een atleet mag niet:

- tussen atleten schakelen;
- trainer-, flex- of basisplanning beheren;
- andere atleten bekijken;
- coachinstellingen, Admin, stats of beheerfuncties openen.

## Atleteninstellingen

Een atleet kan de eigen algemene gegevens, zones/PR's, ideale week en WU/CD-instellingen zien en waar toegestaan wijzigen. De volgende trainerinstellingen blijven verborgen:

- Base Planning;
- hoeveel toekomstige weken zichtbaar zijn;
- rapportage- en zichtbaarheidsschakelaars;
- trainer- en groepstoewijzingen.

## AYC-zichtbaarheid

- De trainer kan een atleet selecteren.
- De atleet ziet automatisch uitsluitend zichzelf.
- De trainer bepaalt hoeveel toekomstige trainingsweken voor de atleet zichtbaar zijn.
- Wedstrijden mogen verder vooruit zichtbaar blijven dan trainingen.
- Rapporten en Daily vitals zijn alleen zichtbaar wanneer ze voor die atleet zijn ingeschakeld.

## Beveiligingsregel

Vertrouw niet alleen op verborgen knoppen. Iedere view en mutatie moet server-side controleren of de gebruiker de betreffende atleet, planning of training mag zien of wijzigen.
