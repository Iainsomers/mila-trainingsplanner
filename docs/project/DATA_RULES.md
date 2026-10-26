# Data-, invoer- en rekenregels

Bijgewerkt: 22 oktober 2026.

## Zones

- Z1 t/m Z5 worden door gebruikers ingevoerd als tempo in min/km.
- Zones lopen op in snelheid: Z1 is het rustigst, Z5 het snelst.
- De applicatie bewaart zones als snelheid in meter per seconde.
- Z6 wordt gebruikt voor snelle/sprintonderdelen en kan uit standaardlogica komen.
- Per atleet kan voor Z1–Z5 HR-tekst worden opgeslagen, bijvoorbeeld `160-170` of `max 170`; lege waarden blijven leeg. Type D bewaart eigen numerieke analysegrenzen apart.

## PR- en doel-PR-formaten

- 400 m (T4): `ss.ss`; seconden mogen hoger dan 60 zijn, bijvoorbeeld `72.50`.
- 600 m (T6), 800 m (T8), 1000 m (T1) en 1500 m (T15): `mm:ss.ss`.
- 3000 m, 5000 m en 10.000 m: `mm:ss`.
- Halve marathon en marathon: `hh:mm:ss`.
- Dezelfde formaten gelden voor huidige PR en doel-PR.
- Oude geldige 400 m-tijden boven 60 seconden mogen niet stilzwijgend worden genormaliseerd naar maximaal 60.
- `Fill missing PB's` gebruikt de WR-verhoudingen in de keten TM, THM, T10, T5, T3, T15, T1, T8, T6, T4.

## Richttijden en richttempo

- Een looponderdeel met afstand in meters kan een richttijd tonen op basis van T- of Z-aanduiding en atleetgegevens.
- Een looponderdeel in minuten of seconden toont richttempo in min/km.
- Omrekening en afronding moeten voor Flex Planner, AYC en DCO hetzelfde zijn.
- Afgeleide trainingen moeten per atleet worden gekloond/geannoteerd zodat tempo's niet van een andere atleet worden hergebruikt.
- Als voor een zone Z1–Z5 HR-tekst is ingevuld, tonen Flex Planner en AYC die naast de indicatieve tijd als `HR...` (bijvoorbeeld `HR160`).
- Bij progressieve zones gebruikt de HR-weergave dezelfde pijlnotatie als de richttijd en neemt zij de ingevulde tussenliggende zones mee; zones zonder HR-tekst worden overgeslagen.

## Trainingsonderdelen

Volgorde: WU, MOB, SPR, CORE, CORE2, ALT, CD. Meerdere segmenten van hetzelfde type behouden hun onderlinge volgorde. `Main` en `Main 2` zijn alleen de zichtbare namen voor CORE en CORE2.

## Parsernotatie

Onder meer ondersteund:

- `6*400m t3`;
- `t3>t15` en `z2>z5`;
- T-progressies lopen via tussenliggende labels, bijvoorbeeld `t15>t4` splitst over T15, T1, T8, T6 en T4;
- `2*(600m-400m) t15`;
- `5*(1000m z3-200m t8)`;
- Watch A/B/C-samenvattingen mogen tempo's tussen haakjes en `+` binnen een herhaalset tonen; bij opslaan worden die displaytekens omgezet naar de bestaande parsernotatie.
- minuten met `'` en seconden met `"`;
- `p` is actief in de coachstand `Active unless "pp"`; `ap` is in beide coachstanden expliciet actief. `sp` (seriepauze) en `pp` (passieve pauze) zijn altijd statisch.
- `p1`/`p=1` en `ap1`/`ap=1` betekenen één minuut. Zonder tijdseenheid zijn waarden t/m 10 minuten en waarden boven 10 seconden. Een expliciete tijdseenheid blijft leidend.
- `p50m`/`p=50m` en `ap50m`/`ap=50m` betekenen een pauzeafstand van 50 meter.

Compound onderdelen moeten afstand, zone en T-label per deel correct optellen. In `Main` scheiden zowel `//` als een `+` op het hoogste niveau zelfstandige segmenten; tekens binnen haakjes blijven onderdeel van het herhaalblok. `//` blijft de scheiding voor Alternative-blokken.

Tempo-labels worden alleen herkend als afzonderlijke aanduidingen (`TM`, `THM`, `T4`, `T1500`, enzovoort), eventueel met spaties binnen het label. Vrije tekst mag geen tempo-label opleveren: `ritme` bevat bijvoorbeeld de letters `tm`, maar telt niet als TM. Deze regel geldt identiek voor Flex Planner en AYC.

## Automatische WU/CD

- Atleetinstelling gaat vóór groep-/trainerinstelling.
- Alleen toepassen als een relevant Main-onderdeel aanwezig is.
- Als automatische WU/CD bij de atleet of het trainerplan aanstaat, wordt deze bij iedere Main-training toegepast, behalve wanneer ergens in Main Z1 voorkomt.
- Een Main die uitsluitend Z2 of sneller bevat krijgt dus wel automatische WU/CD; een combinatie waarin ook Z1 staat niet.

## Weektotalen

- Total is het berekende trainingstotaal in kilometers.
- Toon daarnaast verdeling over zones en wedstrijden.
- Tijdsblokken in Alternative met Z1, Z2 of Z3 blijven aparte `ALT Z1/Z2/Z3`-minuten en worden niet omgerekend naar hardloopkilometers. Alternative Z4 en Z5 worden niet als ALT-weektotaal getoond.
- `//` splitst ook Alternative in afzonderlijke blokken, bijvoorbeeld `20' z1//10' z2//10' z3`.
- Een sessie met de evaluatiestatus `Not done` draagt niet bij aan het weektotaal, de zone-/wedstrijdkilometers of ALT-minuten. De geplande sessie blijft wel zichtbaar in de kalender.

Een atleet kan een eigen pauzemodus hebben. Zonder eigen keuze volgt de atleet de coachmodus; een coachkeuze in Athlete settings overschrijft die coachmodus voor die atleet.
- De Flex Planner past de gekozen pauzemodus toe op trainingen in zowel het AM- als het PM-dagdeel en telt de actieve pauzeafstand in het zichtbare weektotaal bij Z1 op.
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
- De mobiele spraakfunctie schrijft alleen het commentaarveld. Herkenningsresultaten worden per resultaatindex samengevoegd, zodat browser-events met eerdere transcriptie geen herhaalde tekst veroorzaken.
- Een Polar-planmismatch wordt alleen gemarkeerd bij een duidelijke afwijking: een niet-herkende geplande structuur, zeer lage interpretatiezekerheid, een groot verschil in herhalingen of meer dan 40% afstandsverschil bij een enkel afstandsblok.
- Staan op dezelfde dag meerdere sporten in Polar, dan gebruikt een gewone trainingsplanning alleen de hardloopactiviteit voor interpretatie. Alleen een planning die expliciet fietsen/cycling noemt gebruikt de fietsactiviteit. De overige activiteiten blijven afzonderlijk zichtbaar maar beïnvloeden de analyse niet.
- Een alternatief Polar-plan wordt zonder de geplande tekst bij voorkeur uit handmatige laps opgebouwd. Zonder laps worden aanhoudende tempowisselingen uit de gladgestreken snelheidscurve gebruikt om herhaalde snelle en rustige stukken te herkennen; een versnelling moet minimaal circa 12 seconden duren en duidelijk sneller zijn dan het rustige tempo. Afstand en duur van de snelle stukken moeten onderling voldoende regelmatig zijn en herstelstukken mogen niet extreem uiteenlopen. Automatische kilometerpunten en gewone onregelmatige tempovariatie gelden niet als trainingsblokken. Zonder betrouwbaar patroon wordt alleen het activiteitstotaal als doorlopend blok met lage zekerheid voorgesteld. Het blijft altijd een controleerbaar voorstel.

## Daily vitals

- DCO Other gebruikt de laatste veertien kalenderdagen, inclusief vandaag, voor de gekozen vital. Dit staat los van het weekgemiddelde in AYC.
- DCO Other HR-zones lezen `Athlete.zone_hr_bpm`. Een enkel getal is de bovengrens: Z1 wordt `0-max`, Z2–Z4 krijgen de volgende aaneengesloten ondergrens en Z5 toont voorlopig de ingevoerde waarde. Expliciete bereiken worden ongewijzigd getoond; een ondergrens die niet aansluit op de vorige bovengrens wordt als afwijkend gemarkeerd.

- Slaapuren kunnen decimalen bevatten.
- Slaapkwaliteit gebruikt schaal 1–10.
- Ochtendhartslag en HRV zijn numeriek.
- Weekgemiddelde pas tonen bij minimaal drie bruikbare waarden.
- Mobiel worden dezelfde vier gemiddelden gebruikt als desktop; er bestaat geen aparte mobiele berekening.

## Polar: ruwe samples en tempoverwerking

- A berekent min/km uit afstand en duur van iedere afzonderlijke ronde; duur blijft tot milliseconden zichtbaar. Naast de oorspronkelijke afstand wordt de rondeafstand rekenkundig afgerond naar het dichtstbijzijnde veelvoud van 50 meter; een exact half veelvoud wordt naar boven afgerond. De afzonderlijke Zx- en Tx-kolommen gebruiken het exacte rondetempo: Zx is de dichtstbijzijnde ingestelde zonesnelheid en Tx is het snelste PR-tempo dat met de rondesnelheid wordt bereikt. Ontbrekende instellingen of PR's worden niet geschat en verschijnen als NA.
- A gebruikt net als D Polar-sport-ID `1` als hardlopen. Een bekende andere sport-ID wordt uitgesloten; een ontbrekende sport-ID blijft zichtbaar omdat de sport dan niet betrouwbaar kan worden vastgesteld.
- De Type A-omschrijving gebruikt herhaalde, op 50 meter afgeronde afstanden als primaire hoofddeelstructuur; Z2 of hoger kan daarnaast een eenmalig hoofddeel markeren. Daardoor blijven herhalingen die van Z1 naar Z2 versnellen één segment en wordt het zonebereik als bijvoorbeeld `Z1>Z2` getoond. Alleen korte laps tussen herhalingen van hetzelfde segment vormen de gemiddelde herstelduur, compact genoteerd als `p` plus hele seconden (bijvoorbeeld `p87`). Een eerste unieke rustige lap van minimaal 1000 meter geldt als WU. Een CD begint bij het eerste rustige trailing blok van minimaal 1000 meter; een korte overgangslap ervoor telt niet mee. Reststukken onder 400 meter worden geen hoofddeel.
- Als korte werk- en herstellaps qua afstand niet te onderscheiden zijn, mag Type A een duidelijke tweedeling in lapsnelheid gebruiken. Alleen bij een snelheidssprong van minimaal factor 1,5 wordt de snellere groep als korte kern herkend; de representatieve afstand is de mediaan van de op 50 meter afgeronde snelle laps. De tussenliggende langzame laps blijven de pauzes, ook als hun duur groter is dan die van de kern.
- Binnen een korte kern mag één duidelijke afstandsomslag twee opeenvolgende segmenten vormen. De gekozen tweedeling moet de totale afwijking tot de twee mediane afstanden met minstens 50 meter verbeteren; bij een gelijke fout gaat de grens met de langste tussenliggende herstelduur voor. Zo kan één afwijkende GPS-lap binnen bijvoorbeeld `5×50` blijven zonder een aansluitend blok `4×100` te verbergen.
- Per hoofdsegment wordt de gemiddelde kilometertijd gewogen berekend uit de som van de werkelijke afstanden en de som van de duurtijden. De omschrijving toont alleen `(mm:ss)`, zonder `min/km` of `km/h`, zodat deze notatie later niet met een trainingseenheid in de planner botst.
- Zonder handmatige laps behandelt Type A een geldige hardlooprecording met positieve totale afstand en duur als duurloop. De General description gebruikt het gemiddelde over de volledige recording en kiest de dichtstbijzijnde ingestelde Z-snelheid; er worden geen ontbrekende laps of tempowisselingen gereconstrueerd.
- B berekent tempo uit het verschil in cumulatieve afstand en de tijd sinds de vorige getoonde regel. Eerste regel, ontbrekende afstand en niet-positieve afstandstoename geven NA. Alleen exacte sampletijdstippen worden gekoppeld; geen interpolatie of carry-forward.
- C berekent native afstandstoenames als snelheid en gebruikt een tijdgewogen, gecentreerd venster van maximaal 15 seconden. Rondegrenzen, ontbrekende/negatieve afstand en pauzes begrenzen het venster. De daadwerkelijke duur staat in de tabel.
- Mogelijke stilstand: maximaal 0,5 m/s gedurende minimaal 5 seconden. Zonder aanvullende bevestiging blijft dit Possible stop.
- Een losse hoge/lage snelheidspiek van maximaal 5 seconden wordt alleen vervangen bij minimaal 5 seconden stabiel lopen aan beide kanten. Een losse afstandspiek met negatieve terugval kan samen worden hersteld als de intacte eindpunten en omliggende samples dit ondersteunen. De ruwe data blijft gelijk.
- Polar-pauzes worden op de elapsed- of active-tijdlijn uitgelijnd. Bij onzekere uitlijning verschijnt een melding. Elapsed-pauzes worden vóór samenvoegen afzonderlijk gecontroleerd: minstens 5 opeenvolgende seconden boven 0,5 m/s spreekt een pauze tegen. Tegenstrijdige en buiten de samples gelegen markeringen worden genegeerd met uitleg; geldige geneste pauzes blijven behouden.
- Deze eerste verwerkingsregels kunnen zeer korte sprints en meetfouten verwarren. Ook langere pieken rond stoppen/hervatten kunnen blijven staan. Het gecentreerde venster kan een versnelling in voorafgaande regels zichtbaar maken. Gebruik C niet als bewijs van exact gemeten zones.

## Polar Type D: twee onafhankelijke zoneverdelingen

- Tempo: kies de dichtstbijzijnde ingestelde Z1–Z5-snelheid; grenzen liggen op de middelpunten in snelheid, niet in min/km. Onder Z1 valt bij Z1, boven Z5 bij Z5.
- Bruikbare handmatige rondes krijgen één zone op basis van afstand/duur; binnen een lange ronde wordt tempovariatie niet apart geteld. Onvolledige rondeafdekking blijft Unclassified. Automatische kilometerrondes worden niet als handmatige intervalstructuur gebruikt.
- Zonder bruikbare handmatige rondes gebruikt D alleen C-regels met status Running, op een vaste 1-secondegrid. Stops, correcties, ontbrekende data en niet-gedekte samples blijven Unclassified. De gekozen A/B/C-weergaveinterval verandert D niet.
- HR: koppel gemeten afstandstoenames aan het gemiddelde van de twee HR-eindpunten, afgerond naar de dichtstbijzijnde hele bpm. Ontbrekende HR wordt niet doorgetrokken. Verschillende samplefrequenties kunnen de dekking beperken.
- Vier strikt oplopende HR-bovengrenzen, 40–240 bpm, bepalen Z1–Z4. Z1 heeft geen ondergrens en Z5 begint één bpm boven Z4. Voor de preset 145/160/175/185 zijn de zones ≤145, 146–160, 161–175, 176–185 en ≥186 bpm.
- Unclassified is niet betrouwbaar toe te wijzen afstand en blijft in het activiteitstotaal. Lage snelheid of lage HR is op zichzelf geen reden voor Unclassified. Kleine stukken na de laatste sample kunnen oningedeeld blijven.
- Km worden per rij en per totaal afzonderlijk op 100 meter afgerond; de som van afgeronde rijen kan daardoor afwijken van het afgeronde totaal. Reken intern met de ongeronde meters. Bij duidelijke overschatting door afstandsdiscontinuïteiten wordt geen geforceerde normalisatie toegepast.
- Tempo en HR meten verschillende aspecten. HR reageert vertraagd op versnellen en herstellen; de twee zoneverdelingen hoeven niet gelijk te zijn.
- AI beschrijft een vermoedelijke trainingsstructuur, bepaalt geen zonegrenzen en verandert de vaste kilometerberekening niet.
- Model B mag herhaalde actieve rondes niet stilzwijgend weglaten: een kort groepje dat door een lange herstelpauze van vergelijkbare herhalingen is afgesplitst, wordt waar de zones overeenkomen aan het volgende of vorige blok toegevoegd. Een AI-voorstel dat een herhaald actief afstandsblok ondertelt, wordt verworpen ten gunste van de vaste herkenning.

## Garmin FIT-uploadpreview

- FIT-bestanden worden gelezen en per ingeschakelde atleet opgeslagen; er wordt nog geen TrainingSlot aangemaakt of gewijzigd.
- De preview gebruikt verstreken tijd, beweegtijd, afstand en lapvelden afzonderlijk. Het verschil tussen verstreken tijd en beweegtijd blijft zichtbaar als pauzetijd.
- Beschikbare standaard- en Garmin-uitbreidingsvelden worden per berichttype opgesomd. Onbekende velden blijven zichtbaar als veldnummer zodat Model C later geen informatie verliest.
- De upload is beperkt tot `.fit`-bestanden van maximaal 12 MB en is alleen beschikbaar voor atleten die de coach expliciet heeft geselecteerd.
- Een Garmin-zip mag één FIT-bestand bevatten. De oorspronkelijke upload en de genormaliseerde JSON blijven samen aan de atleet gekoppeld voor toekomstig gebruik door Watch C.
