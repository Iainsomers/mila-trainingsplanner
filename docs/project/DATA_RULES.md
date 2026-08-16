# Data-, invoer- en rekenregels

Laatst inhoudelijk gecontroleerd: 15 augustus 2026.

## Zones

- Z1 t/m Z5 worden door gebruikers ingevoerd als tempo in min/km.
- Zones lopen op in snelheid: Z1 is het rustigst, Z5 het snelst.
- De applicatie bewaart zones als snelheid in meter per seconde.
- Z6 wordt gebruikt voor snelle/sprintonderdelen en kan uit standaardlogica komen.

## PR- en doel-PR-formaten

- 400 m (T4): `ss.ss`; seconden mogen hoger dan 60 zijn, bijvoorbeeld `72.50`.
- 800 m en 1500 m: `mm:ss.ss`.
- 3000 m, 5000 m en 10.000 m: `mm:ss`.
- Halve marathon en marathon: `hh:mm:ss`.
- Dezelfde formaten gelden voor huidige PR en doel-PR.
- Oude geldige 400 m-tijden boven 60 seconden mogen niet stilzwijgend worden genormaliseerd naar maximaal 60.

## Richttijden en richttempo

- Een looponderdeel met afstand in meters kan een richttijd tonen op basis van T- of Z-aanduiding en atleetgegevens.
- Een looponderdeel in minuten of seconden toont richttempo in min/km.
- Omrekening en afronding moeten voor Flex Planner, AYC en DCO hetzelfde zijn.
- Afgeleide trainingen moeten per atleet worden gekloond/geannoteerd zodat tempo's niet van een andere atleet worden hergebruikt.

## Trainingsonderdelen

Volgorde: WU, MOB, SPR, CORE, CORE2, ALT, CD. Meerdere segmenten van hetzelfde type behouden hun onderlinge volgorde. `Main` en `Main 2` zijn alleen de zichtbare namen voor CORE en CORE2.

## Parsernotatie

Onder meer ondersteund:

- `6*400m t3`;
- `t3>t15` en `z2>z5`;
- `2*(600m-400m) t15`;
- `5*(1000m z3-200m t8)`;
- minuten met `'` en seconden met `"`;
- `p` voor pauze en `sp` voor seriepauze.

Compound onderdelen moeten afstand, zone en T-label per deel correct optellen.

## Automatische WU/CD

- Atleetinstelling gaat vóór groep-/trainerinstelling.
- Alleen toepassen als een relevant Main-onderdeel aanwezig is.
- Als automatische WU/CD bij de atleet of het trainerplan aanstaat, wordt deze bij iedere Main-training toegepast, behalve wanneer ergens in Main Z1 voorkomt.
- Een Main die uitsluitend Z2 of sneller bevat krijgt dus wel automatische WU/CD; een combinatie waarin ook Z1 staat niet.

## Weektotalen

- Total is het berekende trainingstotaal in kilometers.
- Toon daarnaast verdeling over zones en wedstrijden.
- Stats vergelijkt het totaal van de huidige kalenderweek met de vorige kalenderweek.

## Wedstrijden

- Atleet selecteert maximaal drie afstanden per wedstrijd.
- Trainer kan alleen het trainervinkje wijzigen; atleet alleen het atleetvinkje; beiden mogen Target wijzigen.
- Een selectie is bevestigd wanneer trainer en atleet beiden hebben aangevinkt. Target bepaalt rood versus oranje, bevestiging bepaalt omlijnd versus gevuld.
- Doelwedstrijd verschijnt als `Race!`; overige geselecteerde wedstrijd als `Race`.

## Evaluaties

- Status is per AM/PM-training.
- RPE ligt tussen 0 en 10.
- Bij handmatige invoer is betekenisvol commentaar vereist volgens de actuele validatie.
- Gekoppelde horlogedata kan delen van de invoer voorstellen of aanvullen.
- Een dag is voltooid wanneer alle aanwezige trainingen een effectieve status hebben.

## Daily vitals

- Slaapuren kunnen decimalen bevatten.
- Slaapkwaliteit gebruikt schaal 1–10.
- Ochtendhartslag en HRV zijn numeriek.
- Weekgemiddelde pas tonen bij minimaal drie bruikbare waarden.
- Mobiel worden dezelfde vier gemiddelden gebruikt als desktop; er bestaat geen aparte mobiele berekening.
