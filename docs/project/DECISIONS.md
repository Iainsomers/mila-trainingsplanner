# Productbeslissingen

Dit is geen changelog. Noteer alleen keuzes die toekomstige ontwikkeling sturen. Nieuwste beslissing bovenaan.

## 2026-10-20 — Focus-pointprioriteit en Other-namen zijn gedeeld per atleet

Prio (—/🥇/🥈/🥉) en aangepaste namen van Other 1–3 horen bij de atleet, niet bij een coach. Iedere coach met editrechten op die atleet kan deze waarden aanpassen; een lege Other-naam toont de standaardnaam. Per atleet kan een medaille maar één keer voorkomen; bij toekenning schuiven dezelfde en lagere posities door, en een keuze voor — verwijdert de prioriteit en vult de resterende volgorde op.

## 2026-10-20 — Focus point-commentaar blijft per coach apart

Coachcommentaren bij Focus Points worden afzonderlijk per atleet, focuspunt en coach bewaard. Overschrijven van commentaar van andere coaches is een expliciete, standaard uitgeschakelde keuze; het wist alleen commentaren bij datzelfde focuspunt. De eerste implementatiefase maakt alleen de kolom `Comment coaches` functioneel.

Excel-import van Focus Points vervangt alleen de comments van de ingelogde coach waarvoor een niet-lege cel is ingevuld, bij de in het bestand genoemde bereikbare atleten. Lege cellen laten bestaande comments staan; ontbrekende/ambigue atleten blokkeren de volledige import. Coachcomments van anderen en Plan/Progress blijven ongemoeid.

## 2026-10-20 — Vragenlijststatus en doelgroep zijn aparte keuzes

`Active` bepaalt of een vragenlijst ingevuld kan worden. `Available to` staat altijd apart in beeld en kiest tussen alle atleten of geselecteerde losse atleten. Bij de geselecteerde doelgroep moet minimaal één eigen atleet worden gekozen. Oude vragenlijsten met groepsdoelgroepen blijven werken totdat ze worden bewerkt; dan wordt de huidige groepssamenstelling omgezet in expliciete atleetkeuzes. Een coach mag als kopieerbron alleen eigen vragenlijsten en vragenlijsten van coaches met expliciete editrechten gebruiken; kopiëren neemt geen antwoorden over en verandert de bron niet.

## 2026-10-20 — Bestaande vragenlijsten veilig aanpassen

Na aanmaak zijn titel, actieve status en doelgroep bewerkbaar; de vragenstructuur blijft voorlopig ongewijzigd zodat bestaande antwoorden bij dezelfde vraag blijven horen. Het wijzigen van de doelgroep verwijdert geen antwoorden. Atleten buiten de nieuwe doelgroep kunnen de vragenlijst niet meer openen, terwijl de trainer historische antwoorden blijft zien. Een toekomstige inhoudelijke wijziging met bestaande antwoorden vraagt om versiebeheer.

## 2026-10-12 — Vaste zoneberekening, afzonderlijke AI-interpretatie

Polar Type D berekent kilometers deterministisch op basis van tempo en HR. AI beschrijft uitsluitend een mogelijke trainingsstructuur en verandert geen totalen of planning. Ontbrekende dekking blijft Unclassified; geen geforceerde zone op basis van het geplande trainingstype.

## 2026-10-12 — Analyse-HR blijft apart en herkenbaar geschat

Type D bewaart vier HR-bovengrenzen per atleet in PolarAnalysisSettings, met Estimated-vlag. Deze opslag overschrijft geen HR-tekst in Athlete settings. Z1 heeft geen ondergrens; Z5 is open naar boven. De preset 145/160/175/185 is geen algemeen vastgesteld profiel.

## 2026-10-12 — Pauzemetadata vereist consistentie

Een Polar-pauzemarkering die aanhoudende afstandstoename tegenspreekt mag gemeten loopdata niet verbergen. Ruwe waarden blijven intact; genegeerde markeringen en correcties krijgen een zichtbare reden.

## 2026-10-22 — Actieve pauzes tellen als Z1-afstand

Alleen een losse `p` is actief; `sp` en `pp` blijven statisch. De coach kiest `Always static` of `Active unless "pp"`. Actieve pauzes tellen per set `reps - 1`; tijd wordt met de persoonlijke Z1-snelheid omgerekend en meters worden letterlijk toegevoegd. Niet-berekenbare pauzes leveren 0 m op.

## 2026-10-19 — Individuele Base Planning is leidend per dagdeel

De individuele Base Planning bepaalt in AYC en Flex Planner de trainingsbron per AM/PM-dagdeel, ook wanneer een gekoppeld groepsplan daar een training bevat. `Rest` onderdrukt die groepstraining. Een expliciete persoonlijke trainingsoverride blijft voorrang houden.

## 2026-10-07 — Atletenrechten blijven gescheiden

`Extended edit rights` bepaalt of een atleet toekomstige AYC-trainingen en lege dagdelen mag wijzigen. `Can change base planning` is een afzonderlijk trainerrecht voor de eigen Base Planning. Het ene recht activeert het andere niet.

## 2026-10-07 — Gedeelde whereabouts zijn read-only

De coach kan in Coach Settings `Shared athlete whereabouts in Year Planner` inschakelen. Atleten met Whereabouts-toegang zien dan whereabouts van andere atleten van dezelfde coach en van gerelateerde coaches, maar nooit hun trainingen of mutaties. Standaard staat deze zichtbaarheid uit.

## 2026-10-07 — Tempoherkenning vereist een los label

Flex Planner en AYC tellen alleen expliciete, losstaande tempo-aanduidingen mee als TM/T-label. Vrije tekst zoals `ritme` mag nooit door een toevallige lettercombinatie als TM worden geïnterpreteerd.

## 2026-09-28 — Eén actuele overdracht

`AGENTS.md` en `docs/project/START_HERE.md` zijn de startpunten voor een nieuwe Mila-chat. `CODEX_CONTEXT.md` is alleen nog een korte verwijzing; oude operationele inhoud is verwijderd om verkeerde aannames te voorkomen.

## 2026-09-24 — Evaluaties als twee afzonderlijke stromen

Trainingsevaluaties blijven in AYC per AM/PM. Losse coachvragenlijsten leven onder Evaluations en zijn voor atleten alleen zichtbaar wanneer ze actief zijn. Openstaande AYC-evaluaties van de afgelopen week krijgen een verplichte herinneringspopup; de huidige dag en oudere trainingen niet.

## 2026-09-20 — Year Planner als bron voor weekfases

Training phases worden uitsluitend in Year Planner beheerd en bepalen de weekkleuren in Flex Planner, AYC en Trainer Planning. Meerdere fases in één week worden als gecombineerde kleur weergegeven.

## 2026-09-12 — Scheiding van PAC en MiLa

Track Timer blijft een MiLa Coach Tool. Match Overview en PR-database ontwikkelen verder in het zelfstandige PAC-project, met een eigen deployment en toegangsmodel.

## 2026-08-16 — Race Calendar als gezamenlijke basis

Trainer en atleet beheren wedstrijddeelname vanuit dezelfde Race Calendar-popup. Trainer- en atleetakkoord blijven gescheiden; een wedstrijdpil wordt pas gevuld als beiden akkoord zijn. Target bepaalt of de status oranje of rood is.

## 2026-08-15 — Standaard naar Render

Voltooide wijzigingen worden standaard gecommit en naar `main` gepusht zodat Render ze kan uitrollen. Alleen bij een expliciet verzoek om iets lokaal te houden wordt niet gepusht.

## 2026-08-17 — Polar-planmismatch en reconstructie

Een duidelijke afwijking tussen planning en horlogedata wordt met een rood kruis gemarkeerd. De trainer kan expliciet een alternatief plan laten reconstrueren uit de horlogedata. Dit wordt als concept met betrouwbaarheid getoond en overschrijft de oorspronkelijke training niet automatisch.

## 2026-08-15 — Base Planning en mobiele rapportage voor atleten

Atleten zien Base Planning als alleen-lezen tab. In de mobiele AYC verschijnen ingeschakelde Week reports als vier gekleurde vakken onder de week. Daily vitals worden per dag via een hartknop en popup ingevoerd. De vier weekgemiddelden blijven zichtbaar in compacte vorm en verschijnen pas bij minimaal drie bruikbare waarden.

## 2026-08-12 — Projectkennis opsplitsen

Mila4 en de lange overdrachtsnotitie worden vervangen door thematische documenten in `docs/project/`. De actuele code blijft leidend. Documentatie wordt bij relevante gedragswijzigingen in dezelfde commit bijgewerkt, niet mechanisch na iedere kleine wijziging.

## 2026-08-12 — Logout zonder Admin

Iedere ingelogde gebruiker krijgt een logoutmogelijkheid die veilig afmeldt en naar de loginpagina gaat. Atleten hoeven daarvoor geen Admin-toegang te hebben.

## 2026-08-11 — Mobiele AYC

Mobiel toont één week, gebruikt expliciete Open-knoppen en schermpassende popups. Huidige week is geel, huidige dag donkerder geel. Evaluatievoltooiing wordt met een groen vinkje getoond. Trainerselectie blijft voor trainers beschikbaar.

## 2026-08-11 — Rollen

Atleten zien alleen hun eigen instellingen, wedstrijden en AYC. Trainers kunnen in de AYC tussen toegankelijke atleten schakelen.

## 2026-08-11 — Trainingsbenaming

Het belangrijkste trainingsdeel heet in de interface `Main`, omdat `Core` te veel op buikspiertraining lijkt. Interne datatypen blijven CORE/CORE2.

## 2026-08-11 — PR-formaten

400 m gebruikt `ss.ss` en mag boven 60 seconden uitkomen. 800/1500 gebruikt `mm:ss.ss`; 3000/5000/10.000 gebruikt `mm:ss`; halve en hele marathon gebruiken `hh:mm:ss`.

## 2026-08-11 — Tijdblokken tonen tempo

Voor trainingsonderdelen in minuten of seconden wordt richttempo in min/km getoond, niet een geschatte afstand in meters.

## 2026-08-11 — Dashboardindeling

Planning blijft de hoofdactie. Admin, Stats, Polar en een niet-functionele Settings (under development)-tegel staan onderaan het coachdashboard.

## Eerdere blijvende keuzes

- Alle zones, weekkleuren en trainingsonderdelen staan standaard aan.
- Zones worden ingevoerd als min/km.
- Standard Strength wordt als herbruikbaar blok via Mob/Tech gekozen en vanuit planning geopend.
- Doelwedstrijden worden als `Race!` duidelijker gemarkeerd dan gewone wedstrijden.
