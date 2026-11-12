# Data-, invoer- en rekenregels

- De bestaande seizoensperiode in Year Planner (`2026/27`, intern `season`) loopt van 1 oktober van het gekozen jaar t/m 30 september van het volgende jaar.

- RaceEvent heeft een optionele inclusieve `end_date`; leeg betekent één dag op `date`. Een ingevulde einddatum mag niet vóór de start liggen. Periodefilters in Race Calendar en Year Planner gebruiken overlap met het wedstrijdbereik. Iedere geselecteerde wedstrijddag blokkeert periodisatie. De evenementduur creëert geen extra AYC/Flex-trainingsafstanden.

- Year Planner leidt wedstrijddagen live af uit RaceEntry met Trainer, Athlete of Target geselecteerd voor de betreffende atleet en coach. De RaceEvent-datum en het racetype bepalen de Training-markering. Er wordt geen trainingsfase of whereabouts-record voor aangemaakt; fasewijzigingen op zulke dagen worden geweigerd, inclusief wissen. Uitvinken/verwijderen maakt een eerder opgeslagen fase weer zichtbaar.
- Voor Basis-rijen leidt Year Planner alle `RaceEvent`-records van de actieve coach met `race_type=championship` live af, onafhankelijk van deelnemers en afstanden. De inclusieve start-/einddatums blokkeren op iedere geselecteerde Basis-rij het wijzigen, wissen, plakken en uitrekken van periodisering. Andere racetypen worden niet naar Basis gekopieerd.

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

Standaardvolgorde: WU, MOB, CORE2, SPR, CORE, ALT, CD. Een opgeslagen TrainingSlot.segment_order kan deze volgorde per training aanpassen. Meerdere segmenten van hetzelfde type behouden hun onderlinge volgorde. `Main` en `Strength` zijn alleen de zichtbare namen voor CORE en CORE2.

## Parsernotatie

Onder meer ondersteund:

- `6*400m t3`;
- `t3>t15` en `z2>z5`;
- T-progressies lopen via tussenliggende labels, bijvoorbeeld `t15>t4` splitst over T15, T1, T8, T6 en T4;
- `2*(600m-400m) t15`;
- `5*(1000m z3-200m t8)`;
- progressieve zones mogen ook per onderdeel binnen een herhaalset staan, bijvoorbeeld `2*(300m z2-200m z3>z4)`; het progressieve onderdeel wordt over de tussenliggende zones verdeeld;
- Watch A/B/C-samenvattingen mogen tempo's tussen haakjes en `+` binnen een herhaalset tonen; bij opslaan worden die displaytekens omgezet naar de bestaande parsernotatie.
- De ruwe `watch_loads` blijven ongewijzigd en zijn leidend voor bestaande afstands- en zonetotalen. Een aparte, opgeslagen `watch_main_reps`-laag koppelt alleen gemeten Main-laps aan de herhalingsafstand van het opgeslagen Main-plan; herstel-laps en niet-herkende tijdblokken worden niet als reps gepresenteerd. De popup toont de nette geplande rep-afstand (bijvoorbeeld 200 m of 150 m); de werkelijk gemeten meters blijven apart bewaard en worden gebruikt voor het berekende tempo. Na Use AM/PM wordt de getoonde tijd van herhaalde Main-reps omgerekend met gemeten seconden × herkende repafstand / gemeten afstand. De afgeleide rep bewaart ook measured_seconds en measured_distance_m; tempo blijft gebaseerd op de oorspronkelijke meting. Een doorlopend blok houdt zijn opgetelde gemeten tijd. De ruwe Watch-tabel en loads veranderen niet.
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
- Slaapkwaliteit gebruikt schaal 1–10 en kan met één decimaal worden ingevoerd.
- Ochtendhartslag en HRV zijn numeriek.
- Weekgemiddelde pas tonen bij minimaal drie bruikbare waarden.
- Mobiel worden dezelfde vier gemiddelden gebruikt als desktop; er bestaat geen aparte mobiele berekening.

### Oura-import naar Daily Vitals

- Alleen de atleet zelf kan de Oura-import vanuit de AYC uitvoeren, en alleen als de coach Oura heeft toegestaan, Oura actief verbonden is en Daily Vitals zichtbaar is.
- De importer verwerkt de afgelopen veertien dagen. Een dag wordt alleen voorgesteld als er een Oura-readinessrecord voor die dag bestaat; de readiness-score zelf wordt niet getoond of opgeslagen.
- Alleen lege Daily Vitals-velden worden voorgesteld en opgeslagen. Bij een gedeeltelijk ingevulde dag kunnen uitsluitend de lege velden worden aangevuld; bestaande waarden blijven leidend. De atleet kan dagen uit de lijst verwijderen voordat `Use all` wordt gekozen.
- Oura-slaapduur in seconden wordt naar uren omgerekend en op twee decimalen afgerond; de slaapscore wordt door 10 gedeeld en op één decimaal afgerond; gemiddelde slaap-HRV wordt naar hele ms afgerond.
- De laagste hartslag tijdens slaap vult Morning HR en wordt naar de dichtstbijzijnde hele bpm afgerond. Readiness wordt niet als vital opgeslagen. Het opslaan haalt Oura-data opnieuw op en controleert de bestaande waarden opnieuw om overschrijven te voorkomen.

### Garmin Health naar Daily Vitals

- Garmin Push gebruikt afzonderlijke feeds `sleeps`, `hrv` en `dailies`. Alleen een actieve Garmin-verbinding met dezelfde door Garmin geleverde user-ID kan gegevens aan een atleet koppelen.
- `durationInSeconds` wordt naar slaapuren omgerekend en op twee decimalen afgerond. `overallSleepScore.value` wordt door 10 gedeeld en op één decimaal afgerond. `lastNightAvg` vult HRV en `restingHeartRateInBeatsPerMinute` vult Morning HR; beide worden naar hele getallen afgerond.
- De receiver vult uitsluitend lege velden. Handmatige waarden en eerdere Oura- of Garmin-waarden worden nooit overschreven. Herhaalde Push-berichten zijn daardoor veilig en leveren geen dubbele dagrecords op.

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

- Nieuwe Watch-overnames bewaren ook average_hr uit dezelfde lapberekening als de brontabel. Reps en afstandssplits nemen hun eigen lapgemiddelde over; samengevoegde blokken gebruiken een met gemeten lapduur gewogen gemiddelde, uitsluitend bij volledige HR-dekking van de bronlaps. De weergave rondt af op hele bpm. Nominale afstands-/tijdcorrecties veranderen HR niet. Voor eerdere overnames zonder average_hr is eenmaal opnieuw Use AM/PM nodig; Last 15s HR wordt niet als gemiddelde gebruikt.

- Bij het samengevoegde doorlopende blok na korte series komt Last 15s HR uit de laatste bronlap van dat blok, mits die minstens 15 s duurt. HR uit uitlopen of herstel wordt niet gebruikt. Ontbreekt de bronmeting of omvat de laatste bronlap minder dan 15 s van het langere blok, dan blijft de waarde onbekend. Losse korte reps gebruiken ongewijzigd hun gemiddelde over de volledige gemeten repduur.

- Use AM/PM bewaart `average_hr_last_15` bij de gemeten Watch-loads en geeft dit door aan de afgeleide reps/splits en de bewaarde Watch-versie. De waarde gebruikt dezelfde sampleberekening als de ruwe Garmin C-/Polar-laptabel, gebaseerd op de laatste vijftien werkelijk gemeten seconden (bij kortere laps de hele lap). Omrekening van de reptijd naar een nominale afstand verandert de HR-waarde niet. Zonder samples blijft de waarde onbekend; een lapgemiddelde wordt niet als vervanging gebruikt. Bestaande overnames zonder dit veld tonen NA totdat de training opnieuw met Use AM/PM is overgenomen; de bronactiviteit hoeft niet opnieuw door Garmin te worden verstuurd.

- De regel voor doorlopende automatische afstandssplits ondersteunt zowel 500 m (475–525 m) als 1000 m (950–1050 m). Herhaald herstel of timerpauzes blijft een reden om geen duurloop te concluderen. Het klokje toont de aangeleverde splits op hun eigen 500m-/1000m-afstand en het korte laatste restant met gemeten duur. De titel is `Recorded splits`; de oorspronkelijke laps en totalen blijven bewaard.

- De afgeleide rep van een volledige duurloop bewaart onder `splits` ook de oorspronkelijke kilometerlaps en het laatste restant voor het klokje. De kalender gebruikt uitsluitend de totale bloktijd. Laps van 950–1050 m worden in deze detailweergave met hun naar 1000 m omgerekende tijd getoond; het laatste korte restant toont gemeten duur/afstand. Gemeten tempo, pauzes en loads blijven behouden. Dit werkt ook voor eerder opgeslagen Watch-data en via de bewaarde Watch-versie bij actieve Plan-weergave.

- Minstens twee volledige opeenvolgende kilometerlaps (950–1050 m) plus een kort laatste restant, of minstens drie volledige laps zijn zonder aanvullend herstelbewijs één doorlopend blok. Enkele geïsoleerde trage kilometers maken daarvan geen herhalingsreeks. Minstens drie en ten minste 25% laps met timerpauzes vanaf 15 s, een herhaald duidelijk trager herstelpatroon of expliciete FIT rest/recovery/interval-intensity houden de intervalherkenning beschikbaar. De zone ondersteunt het label maar bewijst geen trainingsvorm; zonder zonegegevens blijft de zone leeg. Bij overname wordt het doorlopende blok met opgetelde gemeten tijd/afstand weergegeven. Deze regel geldt vóór de AI en ook voor oudere activiteiten zonder timergegevens.

- Activity Details bewaart beschikbare verschillen van clockDurationInSeconds, timerDurationInSeconds en movingDurationInSeconds per lap als clock_time, timer_time en moving_time. paused_time is verstreken lapduur minus timertijd. Grenzen binnen de sampledekking worden geïnterpoleerd; ontbrekende dekking, teruglopende tellers of ongeldige verschillen blijven onbekend. Ontbrekende timerinformatie betekent niet nul pauze. De ruwe sampletijdlijn/GPS wordt niet extra opgeslagen. Garmin C geeft de afgeleide timer-/pauzetijden aan regels en optionele AI door. FIT-lapvelden 23 (intensity) en 24 (lap_trigger) blijven apart; een handmatige lap is op zichzelf geen bewijs van een interval. Reeds opgeslagen pushes zonder deze timerfeiten krijgen die niet achteraf erbij.

- Use AM/PM bewaart afzonderlijke Plan- en Watch-momentopnamen. Wisselen via `p/w` vervangt de actieve segmenten, bron, loads en reptijden atomair. Plan gebruikt eigen planafstanden; Watch gebruikt de opgeslagen gemeten loads. De klokweergave blijft de bewaarde Watch-reptijden tonen, ook wanneer Plan actief is. Een volgende expliciete Watch-overname vernieuwt de Watch-momentopname, zonder de bewaarde Plan-momentopname te wissen.

- Bij de herkende combinatie van korte series en een doorlopend blok worden AYC-reptijden per Main-segment gekoppeld: alleen de korte werk-laps voor de series, en de opgetelde tijd/afstand van alle aaneengesloten lange-bloklaps voor het doorlopende segment. Herstel en CD blijven buiten deze tijden, maar behouden hun ruwe loads en totalen. De afgeleide repweergave wordt ook bij het lezen van bestaande Watch-slots vernieuwd; opnieuw importeren is niet vereist. Een structureel herkende maar door GPS ondergemeten herhaling krijgt na Use AM/PM een tijd omgerekend naar de herkende afstand; de gemeten tijd blijft apart bewaard en het gemeten tempo blijft gelijk.

- Bij korte herhaalseries krijgt het werkblok zijn eigen zone of zonebereik uit uitsluitend de gemeten werk-laps (bijvoorbeeld `2*(5*100m z4>z5) p45//3750m z2`). Herstel- en doorlopende laps tellen niet mee voor die werkzone. Ontbrekende zones worden niet ingevuld; een bereik beschrijft de waargenomen werkzones, niet noodzakelijk een progressief uitgevoerde training. Dit wijzigt geen lapzones of gemeten totalen.

- Watch B/C herkent ook gelijke series korte werk/herstelparen gevolgd door een doorlopend blok met gemengde kilometer-autolaps en handmatige rondegrenzen. Hiervoor zijn minstens twee gelijke series, langere seriepauzes en minstens twee consistente kilometer/rest-paren vereist. Relatieve snelheid en volgorde zijn leidend; één ondergemeten korte herhaling mag de nominale afstand uit de overige herhalingen volgen. Herstel wordt op vijf seconden samengevat. Het doorlopende blok gebruikt de consistente rondeafstand afgerond op 250 m (maximaal 5% afwijking per ronde); het wordt niet als herhaalde kilometertraining weergegeven. Een duidelijke vertraging na dit blok kan CD starten, ook als een volgende CD-lap weer Z2 is. De nominale CD-afstand wordt op 100 m afgerond. Dit zijn beschrijvingsregels: gemeten afstand, tijd, HR, tempo en zonetotalen blijven behouden. Zonder zonegegevens wordt geen zone verzonnen. Sterke structurele herkenning gaat vóór AI; de AI-instructies benoemen korte herhalingen, gemengde lapgrenzen en beperkingen van het herhaalsetschema.

- FIT-bestanden worden gelezen en per ingeschakelde atleet opgeslagen; er wordt nog geen TrainingSlot aangemaakt of gewijzigd.
- De preview gebruikt verstreken tijd, beweegtijd, afstand en lapvelden afzonderlijk. Het verschil tussen verstreken tijd en beweegtijd blijft zichtbaar als pauzetijd.
- Beschikbare standaard- en Garmin-uitbreidingsvelden worden per berichttype opgesomd. Onbekende velden blijven zichtbaar als veldnummer zodat Model C later geen informatie verliest.
- De upload is beperkt tot `.fit`-bestanden van maximaal 12 MB en is alleen beschikbaar voor atleten die de coach expliciet heeft geselecteerd.
- Een Garmin-zip mag één FIT-bestand bevatten. De oorspronkelijke upload en de genormaliseerde JSON blijven samen aan de atleet gekoppeld voor toekomstig gebruik door Watch C.
- De Garmin FIT-reader haalt record-hartslag uit veld 3 en recordtijd uit veld 253. Gecomprimeerde FIT-records laten veld 253 weg; de reader reconstrueert die tijd uit de gecomprimeerde tijdstempelheader voordat velden worden gelezen. De genormaliseerde data bewaart zo recordniveau-hartslagmetingen. Garmin C gebruikt deze metingen voor de gemiddelde HR en het gemiddelde van de HR-samples in de laatste 15 seconden van iedere getoonde lap (kortere laps gebruiken hun volledige duur). Bij laps zonder starttijd worden samples gekoppeld vanaf de activiteitstart plus de duur van voorafgaande laps. Bij ontbrekende samples toont de laatste-15-secondenwaarde `NA`; het lapgemiddelde wordt niet als vervanging getoond. De gewone gemiddelde HR mag wel het FIT-lapgemiddelde gebruiken. Deze HR-verwerking verandert geen afstand, duur, tempo of km-totalen.
- Watch C gebruikt alleen FIT-laps die aan de geselecteerde atleet zijn gekoppeld en waarvan de activiteitstart in de gekozen lokale kalenderdag valt. Lapafstand en lapduur zijn de gemeten waarden; ze worden in het Watch B-formaat aangeboden aan dezelfde herkenner en optionele AI. De AI mag de gemeten waarden niet aanpassen. Watch C controleert de volgorde en herhalingsaantallen van Main-segmenten tegen de chronologische lapdata; als de AI een herhaling mist, wordt die hersteld en worden zones op basis van de gemeten werk-laps als bereik getoond (bijvoorbeeld `Z2>Z3`). Twee direct opeenvolgende gelijke werk-laps kunnen als één langere herhaling worden samengevat wanneer de ruwe lapvolgorde daarna consequent een herstellap laat zien, ook wanneer sommige herstelstukken langere setpauzes zijn. Deze controle loopt rechtstreeks op afstand en volgorde vóór de afgeleide zoneclassificatie; ontbrekende of foutieve zone-instellingen van een atleet mogen de herkenning dus niet blokkeren. De volgorde komt uit de laplijst zelf en vereist geen aparte index. Zonder dat patroon blijft de oorspronkelijke structuur staan. Een Main-segment dat aantoonbaar dezelfde Z1-lap bevat als een expliciet CD-segment wordt niet dubbel geteld. Aangrenzende AI-segmenten met dezelfde afstand kunnen ook binnen een Main met andere afstanden tot één herhalingsreeks worden samengevoegd, maar alleen als lapdata het aantal werkherhalingen bevestigt. De reeks toont het gemeten gemiddelde tempo; dit wijzigt geen km-totalen. De WU/Main/CD-verdeling uit de herkenning is leidend voor de opgeslagen lapsegmenten; bij `WU: none` wordt geen lap als WU opgeslagen. De normale zone-/km-rekenregels blijven van kracht en de planner verandert alleen na expliciete keuze van de voorgestelde AM- of PM-training.
- De werkelijke tijd-/tempo-indicatie van een herhaald horlogesegment gebruikt laps die passen bij de herhalingsafstand én zone; wanneer er meer kandidaten zijn, begrenst de geplande herhalingscount de chronologische selectie. Zo worden verschillende korte Main-reeksen (bijvoorbeeld 200 m en 150 m) niet met elkaar of met herstel-laps vermengd; dit verandert geen km-totalen.

Garmin Activity Details: lapgrenzen komen uit de aangeleverde `laps.startTimeInSeconds`. Afstanden aan interne grenzen worden lineair geïnterpoleerd tussen gemeten cumulatieve `totalDistanceInMeters`-samples; grenzen buiten de meetdekking leveren geen lap op. Begin/einde gebruiken de gerapporteerde activiteitstotalen. Duur is de gemeten tijd tussen de lapgrenzen (verstreken tijd, inclusief eventuele pauzes). HR en Last 15s HR blijven gebaseerd op beschikbare samples; ontbrekende metingen worden niet verzonnen. Een summary zonder rondes is alleen-lezen zichtbaar in Garmin C en biedt geen interval-/WU/Main/CD-overname. Een FIT-upload met dezelfde starttijd en dezelfde totale afstand (maximaal 1 m verschil) heeft voorrang op de corresponderende pushactiviteit in Garmin C.

Garmin Activity Details kunnen geen totaalafstand bevatten. Dan blijft de afstand onbekend en wordt geen lapafstand geschat; de ontvangst en lap-/sampleaantallen worden wel vastgelegd. Zo blokkeert een afstandloze activiteit geen andere activiteiten in dezelfde batch. Een eerder ontvangen summary-afstand blijft behouden. Negatieve/ongeldige aangeleverde waarden blijven afgewezen.

## Automatische Oura-controles

- Daggrenzen en het controleschema gebruiken de laatst door het eigen atleetapparaat gemelde IANA-tijdzone, niet de coach- of servertijdzone. Zonder geldige zone wordt niet automatisch opgehaald. UTC-minuten worden naar lokale tijd vertaald voor zomer-/wintertijd en tijdzones met halve/kwartieroffsets.
- Lokale slots: 06:30, 06:40, 06:50, 07:00, 07:10, 07:20, 07:30, 07:40, 07:50, 08:00; buiten dit venster ieder heel uur. De server controleert iedere 30 s en haalt een achterstallige slotcontrole bij hervatten in. Een databaseclaim van 15 minuten voorkomt dubbele workers en kan na een crash opnieuw worden opgepakt.
- De bestaande veertiendaagse Oura-importregels blijven leidend. Readiness moet een eindige numerieke score 0–100 zijn; None, een streepje of ongeldige waarden worden overgeslagen. Reeds ingevulde velden, ook gelijktijdig handmatig ingevulde waarden, worden nooit overschreven. Dagelijkse vitals, Oura-toegang, eigen OAuth-koppeling en de opt-in moeten actief zijn. De controle schrijft geen Readiness-score.

Garmin-combinaties analyseren de bronactiviteiten afzonderlijk. Main behoudt zijn herkende structuur en lapgegevens; apart gekozen WU/CD gebruiken de totale bronafstand afgerond op 50 m en de afstandgewogen dominante bekende zone. Totale afstand en duur zijn sommen van bronactiviteiten; gaten tussen opnames tellen niet mee. Buitenste WU/CD-laps worden als zodanig bewaard en veranderen de Main-repherkenning niet. Gemeten repafstand, tijd en beide HR-waarden blijven behouden.

Bij bevestigde work/work/recovery-half-laps worden twee gemeten halve laps één nominale rep. Reptijd = som van beide gemeten tijden × nominale afstand / som gemeten afstanden. Avg HR is tijdgewogen bij volledige dekking; Last 15s HR komt uit de laatste halve lap. Onbekende sample-HR blijft NA. De ruwe rondetabel blijft ongewijzigd.

Watch WU/CD-grenzen: eenvoudige afstandsomschrijvingen worden aan opeenvolgende begin-/eindlaps gekoppeld wanneer de gemeten som maximaal 75 m afwijkt. Alleen segmentlabels worden aangepast; afstand, tijd, HR en lapzone blijven ongewijzigd. De volledige gemeten laplijst telt éénmaal mee, inclusief werkelijk geregistreerde herstelmeters. Lange stilstand wordt nooit via zonesnelheid naar extra kilometers omgerekend. Een weggelaten leidende Main-lap vanaf 1000 m wordt vóór een uitsluitend korte-repbeschrijving behouden met zijn berekende lapzone; een gewenste zone wordt niet uit een afstand of de geplande intentie verzonnen.

Gemengde korte reps na een rustige aanloop: minimaal vier werk-laps van 25–250 m en 3–60 s, snelheid minstens 2.5 m/s en minstens 1.5 maal die van de aansluitende herstel-lap (maximaal 300 m, minstens 30 s). Tussenliggende niet-verklaarde werkblokken blokkeren de regel. Gelijke kilometer-aanlooplaps worden als één WU opgeteld, inclusief hun gemeten afstand; onderscheiden lange laps na een afzonderlijke WU blijven Main. Korte reps behouden hun volgorde en zones, met nieuwe groepen bij gewijzigde nominale afstand of herstel vanaf 180 s. Herstelmeters/stilstand blijven gemeten totalen, geen extra werkreps. Een duidelijke rustige eindlap vanaf 500 m kan CD vormen. De herkenning gaat vóór AI en dominante-afstandsherkenning.

Bij gemengde korte reps is de compacte afstandsgroepering alleen een beschrijvingslaag. Twee herhaalde afstandsclusters met minstens twee waarden per cluster en een gat van minimaal 15 m mogen elk een nominale 50m-afstand krijgen uit het bovenste kwartiel; dit voorkomt dat ondergemeten 200m-reps als 150m worden ingedeeld. De nominale lapkoppeling bewaakt de klok- en pilltijden; de klok sorteert terug naar bronvolgorde. Ruwe meters, duur en HR blijven ongewijzigd. Een korte snelle eindrep mag gevolgd worden door de laatste rustige CD-lap vanaf 500 m. Afzonderlijke stilstand beïnvloedt niet het aantal werkreps of hun typische herstelduur.

Watch-totalen: een gemeten lap is wandelen als seconds > meters × 0.6 (strikt trager dan 600 s/km). De hele lap blijft buiten alle hardloopzone-, race-, tempo- en totale kilometers en hun getelde duur. Precies de grens blijft lopen. Dit is een lapgebaseerde afspraak; een lap met lopen én lange stilstand kan daardoor volledig uitgesloten worden. Ruwe meetgegevens worden niet gewijzigd. Gemeten segmentdekking blijft behouden, ook als alle laps wandelen zijn, om terugval op planafstand en dubbeltelling te voorkomen.

Afzonderlijk Main-geval: zonder aanloop wordt korte-repherkenning alleen toegepast als de volledige opname afwisselt tussen bevestigde werk- en herstellaps en eindigt met herstel. Nominale afstanden volgen dan uitsluitend de gewone 50m-afronding, zonder clusterophoging. Dit houdt bijvoorbeeld 174.91 m op 150 m. De eerdere aanloop-/clusterregel verandert hierdoor niet.

Tijdsintervallen met kilometer-autolaps: minimaal drie blokken van twee laps van 950–1050m en één restlap van 250–600m. Tussen de blokken is een aantoonbaar trager herstel van 60–180s, 100–500m en Z1/ongeclassificeerd nodig. Alle werkblokken moeten binnen vijf seconden van dezelfde hele minuutduur vanaf vijf minuten vallen; dan wordt bijvoorbeeld 5×8′ voorgesteld. Een kort stoprestant aan het einde is toegestaan. Werkafstand en -tijd worden per blok opgeteld, niet uit een nominale afstand of zonesnelheid afgeleid. Totale sessieafstand telt de oorspronkelijke meetlaps, inclusief gemeten lopend herstel en exclusief wandelen (>10:00/km).

Bij twee volledige autolaps en een kort reststuk geldt de duurloopherkenning eveneens; twee laps met timerpauzes vanaf 15 s of expliciete herstelintensiteit blokkeren die herkenning. Nominale beschrijving rondt de totale afstand op 50 m; gemeten afstand en splits blijven behouden.

Garmin D: HR-override geldt inclusief 400m of 50s, op de gemeten volledige rep vóór nominale afronding. HR komt uitsluitend uit average_hr_last_15, nooit als fallback uit Avg HR. HR-grenzen komen uit zone_hr_bpm (expliciete intervallen of max-bovengrenzen); vijf geldige stijgende niet-overlappende zones zijn vereist en er worden geen limieten geschat. Bij een samengestelde rep wordt de eind-HR-zone aan alle werklaps van die rep toegekend; herstel blijft zelfstandig. Structuurherkenning blijft de oorspronkelijke tempozones gebruiken, zodat HR geen bestaande repgrenzen wijzigt. Afstanden en tijden blijven identiek aan C; wandelen boven 10:00/km blijft uitgesloten.

Daily vitals in Staff Team Overview: per atleet en vital afzonderlijk gemiddelde, maximum en minimum over dezelfde veertien kalenderdagen, uitsluitend niet-lege waarden. Minstens drie metingen per vital; anders NA zonder range. Null telt niet mee, numerieke 0 wel. Weergave behoudt één decimaal en de bestaande eenheid, gevolgd door minimum–maximum. Rechtenfiltering vindt vóór het ophalen en aggregeren plaats.

Alternatieve lange intervalbeschrijvingen: complete werk/herstelparen, werk 800–6000m en minstens 120s, herstel maximaal 350m/30–600s en minimaal 1.5 maal trager. Minstens twee opeenvolgende groepen met elk twee of meer reps zijn vereist. Een alternatief wordt alleen aangeboden als de afstanden binnen 5% van de nominale 100m-afstand en de tijden binnen maximaal 5s of 3% van dezelfde hele minuutduur vallen. Herstel vanaf 180s wordt niet in de typische korte rep-pauze opgenomen. Afstands- en tijdskeuze gebruiken exact dezelfde meetloads; Garmin D controleert beide opties afzonderlijk op eind-HR. De oude Type A-prefixherkenning mag niet meer terugkeren zolang latere substantiële werk-laps onbeschreven blijven.


Garmin C/D End HR vervangt het vaste laatste-15s-venster: gemiddelde van geldige HR-samples over de laatste 10% van de gemeten repduur, met minimaal 15 seconden. Bij een rep korter dan 15s wordt Avg HR gebruikt. Samengestelde reps berekenen het venster over alle bijbehorende laps samen, vóór afstandsnormalisatie. Garmin D gebruikt deze waarde voor zijn bestaande 400m-of-50s-zonecontrole. HR-samples met relatieve tijd worden in Watch-loads bewaard. Oud opgeslagen laatste-15s-HR is alleen bruikbaar wanneer het nieuwe venster exact 15s is; langere vensters zonder samples blijven NA.


Trainingsfoto’s: maximaal vijf per training (Mob/Tech en Strength samen), maximaal 15 MB en 40 megapixel per inkomend bestand. Pillow decodeert echte rasterafbeeldingen, draait volgens EXIF, converteert naar JPEG, verkleint tot maximaal 2200px en maakt een thumbnail van maximaal 240px. EXIF/GPS en originele bestandsnamen worden niet opgeslagen. TrainingPhoto bevat privébinaries in de database; TrainingSegment.photo_ids bewaart UUID-referenties. Kopieën delen de onveranderlijke foto en verwijderen alleen hun eigen referentie. Afbeeldingen tellen niet mee als loopafstand.


Afwisselende middelgrote afstandsreps worden apart herkend vóór dominante-afstandsselectie: een volledige reeks werk/herstelparen, minstens vier werkreps, exact twee afwisselende nominale 50m-afstanden. Werk is 275–650m, 50–240s en minstens 2.5m/s; herstelblok maximaal 500m, 30–600s, met werksnelheid minstens 1.4 maal de gemiddelde herstelsnelheid. Aaneengesloten herstel-laps worden samen genomen. Een laatste werkrep mag zonder afsluitend herstel eindigen; één extra gemeten rep van de laatste afstand na de afwisseling blijft behouden. Beide afstanden blijven beschreven met eigen zones en typische herstelduur (herstel vanaf 180s buiten die mediaan). Nominale repkoppeling bewaart alle klokreps in bronvolgorde; gemeten meters/tijden veranderen niet. Onvolledige of niet-aantoonbaar tragere patronen vallen buiten deze regel.


Klokreps behandelen zonebereiken inclusief alle tussenliggende zones: Z3>Z5 bevat Z3, Z4 én Z5, ook bij dalende notatie. Voor expliciet bevestigde work_rep/nominal_rep_m-lapkoppelingen is de nominale afstand leidend; een latere HR-zonecorrectie mag de gemeten rep niet uit de klokfilter verwijderen. Zonder die metadata blijft de zonefilter met volledig bereik gelden.


AI-lapstructuur: minimaal 0.75 confidence; elke bronlap exact één keer toegewezen aan WU, CD, herstel, stop of werkrep. Werkrep bestaat uit opeenvolgende lapnummers, met minimaal 2m/s per lap; groepen hebben 2–30 reps met hele-minutendoel 120–1800s. Gemeten repduur mag maximaal 15s of 6% afwijken. Herstel tussen reps is 30–600s, maximaal 600m en minimaal 1.4 keer trager dan beide aangrenzende reps. Stop is minimaal 600s met minder dan 1m/s; WU/CD mogen geen langzame stop bevatten. Afstandsoptie volgt groepsmediaan op 100m afgerond, binnen 8% voor elke rep. Alle labels/zones/pauzes worden uit bronfeiten afgeleid, geen door AI bedachte meters. Unieke groepsbinding voorkomt dubbelzinnige klokmatches. Opgeslagen ai_rep/ai_group/ai_target_seconds/ai_nominal_m koppelen de echte laps aan beide opties; HR gebruikt het volledige repvenster en kilometers blijven gemeten.


Alternative-progressies verdelen uitsluitend de actieve duur gelijk over alle zones in het bereik Z1–Z3, inclusief tussenliggende zones en dalende notatie. Voorbeeld 15×3′ Z2>Z3 is 1350s Z2 + 1350s Z3; herstelnotatie verandert de actieve duur niet. Eénzoneblokken en //-samengestelde blokken volgen dezelfde gedeelde Python-regel in AYC en stats en dezelfde browserregel in Flex. Alternative blijft buiten loopkilometers. Halve minuten blijven behouden tot de weergave (maximaal één decimaal).


Lokale kandidaat voor gemengde tijdsblokken: werk is een aaneengesloten reeks Z2–Z5-laps vanaf 2.5m/s, onderbroken door trager herstel. Repduur wordt op hele minuten gegroepeerd; minimaal vier reps en twee opeenvolgende verschillende tijdsgroepen. Prefix wordt alleen als stop behandeld bij minstens 600s onder 1m/s; overige prefix is WU. Een rustige eindlap vanaf 800m en 2m/s kan CD zijn. Daarna gelden onverkort alle controles van validate_lap_structure, inclusief volledige dekking, repduur/distance-consistentie en herstelcontrast. Geen AI-verzoek nodig voor deze lokale kandidaat.

Klokoverzicht C/D splitst ook opgeslagen Main-blokken met minuten en een streepje (2×8′ - 4×4′). Bestaande gecombineerde CORE-records worden bij lezen op dezelfde manier opgesplitst; alle gemeten reps blijven zichtbaar zonder opnieuw importeren. Geneste sets, zonebereiken en temporanges blijven intact.

Enkele tijdsreeks in Garmin C/D: herken de afwisselende Main-laps als werk/herstel, minstens drie werkblokken, werktempo minimaal 2.5 m/s, herstel 30–600s en maximaal 600m, minimaal factor 1.4 trager dan aangrenzende werkblokken. Rond de mediane werkduur naar hele minuten (2–30); alle werkblokken moeten binnen max(15s, 6%) vallen. WU/CD blijven apart, een laatste herstel is optioneel. Alleen de Time-optie krijgt expliciete repidentiteiten; Distance behoudt de oorspronkelijke tekst en loads.

Gemengde korte/lange Watch-series: na de korte versnellingen worden volgende lange werk/herstelparen volledig doorlopen. Werk is 400–6000m, minstens 60s en 2.5m/s; herstel maximaal 600m, 30–600s en minstens factor 1.4 trager. Nominale afstanden ronden op 100m; elke opeenvolgende afstandsgroep heeft minstens twee reps. Een voorafgaande Z2-tussenlap blijft apart zichtbaar; een laatste werkrep mag direct doorlopen naar Z1-CD. De laatste korte versnelling mag 10–29s herstel hebben wanneer daarna een lange lap volgt. Een latere snelle lange lap mag nooit stil uit de beschrijving verdwijnen.

Alternative-blokken splitsen op top-level `+` en `//`; beide mogen door elkaar worden gebruikt. Scheidingstekens binnen haakjes en zonebereiken blijven intact. Opslag, virtuele base-slots, bestaande teksten en de Flex-browserberekening gebruiken dezelfde scheidingsregels. De actieve tijd per los blok telt mee in de eigen zone(s), met behoud van de bestaande gelijke verdeling bij zonebereiken; Alternative blijft uitgesloten van loopkilometers.

Injury/Issue Overview selecteert maximaal 25 werkelijk ingevulde AthleteDayCheck-records per atleet met trainingsdatum <= vandaag. Checked/status/RPE/pain of niet-lege commentaartekst telt als ingevuld. Volgorde is datum, slot_index (AM voor PM), id; updated_at verandert deze volgorde niet. Lege pain is onbekend, geen Fit; toekomstige of lege evaluaties worden niet meegerekend. Er geldt geen vaste terugkijkperiode.


De Injury/Issue-schuif toont de laatste N van deze 25 evaluaties (5–25, standaard 5) zonder nieuwe opslag of requests. Alleen zichtbare trainingsevaluaties leveren commentaar, RPE en effective_status voor de popup. Lege status met checked=True krijgt de bestaande Done-status; de tekst wordt veilig als tekst weergegeven. Ontbrekende evaluaties hebben geen popup.

InjuryIssueComment bewaart een unieke opmerking per (athlete, coach), los van de evaluatie van de atleet en Desired Improvements. Dezelfde coach-identiteitshulp genereert in beide overzichten initialen en deterministische kleur. Opslaan accepteert alleen de ingelogde auteur, maximaal 5000 tekens; leeg verwijdert uitsluitend diens eigen opmerking. See training is alleen lezen en schrijft geen planning/Flex-records; het leest de actuele opgeslagen sessie met persoonlijke override, baseplanning en racevoorrang, niet een historische snapshot.

Strength gebruikt het bestaande type CORE2 uitsluitend als vrije tekst. Nieuwe/gewijzigde invoer bewaart geen zone, T-type, afstand, genormaliseerde afstand of duur. Ook bestaande CORE2-records worden uitgesloten van AYC-/Flex-/DCO-/statistiek-looploads; Stats-schema v21 vernieuwt de cache. De weergave gebruikt de standaard- of aangepaste segmentvolgorde zonder de opgeslagen tekst of onderlinge volgorde van Main-reps te wijzigen. Meerdere regels en + of // binnen Strength blijven vrije tekst; opgeslagen standaarden bewaren vervolgregels.

TrainingSlot.segment_order bewaart een volledige, unieke permutatie van WU/MOB/CORE2/SPR/CORE/ALT/CD. Leeg betekent de standaard WU-MOB-CORE2-SPR-CORE-ALT-CD. De server weigert onbekende, dubbele of ontbrekende typen. Binnen hetzelfde type blijft de bronvolgorde behouden (bijvoorbeeld meerdere Main-blokken). Opslaan schrijft tevens de numerieke segment.order; display-klonen nemen de slotmetadata over. Zonder meegestuurde volgorde blijft de zichtbare bronvolgorde behouden. Standaarden gebruiken de compatibele ORDER=-regel; oude standaarden zonder die regel krijgen de standaard. Dag/weekkopieën en Watch/Plan-snapshots bewaren hun eigen volgorde. Louter verplaatsen wist geen gemeten Watch-Main-data.


Nieuwe foto’s gebruiken Strength (CORE2) via strength_photos/remove_strength_photo. Bestaande Mob/Tech-referenties blijven behouden en de oudere mob_photos-invoer blijft compatibel. Beide segmenttypen hebben dezelfde privéfoto-downloadcontrole; kopieën blijven referenties delen. Strength met alleen foto’s is geldige inhoud zonder zone of loopload.

Garmin D-tabelkolom HR Zx gebruikt per weergegeven lap/rep uitsluitend de eigen hr_tail (dezelfde End HR die rechts wordt getoond) met de ingestelde Athlete.zone_hr_bpm-grenzen. Ook niet-herkende reps en herstelrondes worden afzonderlijk geclassificeerd; er geldt geen minimumafstand/duur voor deze informatieve kolom. Ontbrekende gegevens leveren NA. De regel voor End HR zelf blijft laatste 10% met minimaal 15s, of Avg HR bij reps korter dan 15s. De D-trainingszonecorrectie vanaf 400m of 50s blijft hiervan gescheiden.

Aanvullende Garmin-afstandsherkenning: uitsluitend wanneer alle oorspronkelijke tempozones Z1 zijn en elke lap bruikbare End HR en volledige ingestelde HR-grenzen heeft. Minstens vier werk-laps in HR Z2–Z5, dezelfde nominale afstand (800–6000m, afronden op 100m, maximaal 5% afwijking), minimaal 120s, snelheid 2.5–8m/s en maximale reptijd/minimale reptijd <=1.15. Tussen ieder paar werkreps moet herstel bestaan: alle tussenlaps HR Z1, minstens 15 bpm lager dan beide aangrenzende reps, gezamenlijk 30–900s en maximaal 1.25× de nominale werkafstand, minstens factor 1.15 trager dan beide reps. Herstel mag over meerdere laps lopen. Alle grenslaps worden behouden; een rustige lopende staart wordt CD, voorafgaande langzame herstelkilometers blijven herstel. P is de afgeronde mediane gemeten tussenpauze. Dit is een fallback na gevalideerde lapstructuren; afwijzen laat bestaande herkenning intact. Repidentiteiten borgen klokvolgorde en ongewijzigde bronmeters/seconden.


Garmin timertijd (4 november 2026): C/D gebruikt geldige lap.timer_time voor getoonde duur, tempo en looploads; zonder positieve geldige timertijd blijft elapsed_time de fallback. splitTimeMillis en elapsedDurationMillis blijven de oorspronkelijke verstreken tijdlijn bevatten; HR-samples worden niet verschoven of afgekapt door de kortere looptijd. Loads bewaren elapsed_seconds zodat samengestelde End-HR-controle de bestaande bronklok blijft gebruiken. FIT-sessies gebruiken total_timer_time; Activity Details bewaren total_timer_s uit timerDurationInSeconds of summary.durationInSeconds. Bij precies één complete lap mag het gemeten activiteitstotaal als laptimertijd dienen; bij meerdere laps wordt geen pauze over laps verdeeld. Eerdere opgeslagen Activity Details zonder total_timer_s gebruiken ontvangen summary.duration_s bij preview, zonder databasewijziging. Regressie voor nieuwe en bestaande pushdetails in C en D: 17336m, 4676s verstreken, 4503s timer geeft 01:15:03 en 4:20/km, terwijl HR na timerseconde 4503 behouden blijft. 90 gerichte tests en manage.py check geslaagd; productie-/mobiele visuele controle niet uitgevoerd. Opnieuw openen herberekent previews; al via Use AM/PM opgeslagen trainingen moeten opnieuw worden toegepast voor de nieuwe looptijd.


HR-zonecontrole bij gedeeltelijke/overlappende instellingen (4 november 2026): hr_zone beoordeelt elke meting tegen alle bruikbare expliciete bereiken. Precies een match geeft een zone; overlappende waarde (bijvoorbeeld 178 bij 169-178 en 178-184) blijft NA, zonder alle andere waarden uit te schakelen. Ontbrekende/ongeldige zone blokkeert geen eenduidige match elders. Een bovengrens zonder ondergrens na een ontbrekende zone blijft onbekend; er worden geen grenzen geschat. Ongewijzigde drempels voor D-trainingscorrectie en bronmeters/tijden. Regressie met opgegeven grenzen 151 / 152-168 / 169-178 / 178-184 / 188 dekt losse lapkolom en grenswaarden. 54 gerichte tests en manage.py check slagen; productie-/mobiele visuele controle nog niet uitgevoerd.


AI-setgrenzen en pauzes (4 november 2026): lap_structure.groups accepteert optionele set_start_laps met de eerste werk-lap per set. De AI kiest de setindeling; geen nieuwe lokale herkenningsregel. Validator vereist bestaande oplopende rep-starts, gelijk aantal reps per set, minstens twee reps per set en gemeten setpauzes minstens 1.5 maal de mediane gewone pauze. P en SP worden uit bronpauzes berekend, niet uit AI-getallen; alle laps blijven uniek/volledig toegewezen en meetmeters/tijden onveranderd. Langzame aanloop-overgang mag recovery zijn voor de eerste rep, maar geen lopende lap >=2m/s. Klok-/D-matcher bindt geneste AI-setlabels aan alle oorspronkelijke repidentiteiten. Regressie met 20x400m en AI-setstarts [4,24] produceert 2x(10x400 m Z2 p60) sp318, behoudt alle twintig klokreps in C/D en wijst verzonnen/ongelijke setstarts af. 93 gerichte tests slagen; AI-service/visuele productiecontrole nog niet bevestigd.


Wandelen in AI-WU/CD (4 november 2026): een door AI aan warmup/cooldown toegewezen lap die volgens de bestaande >10:00/km-regel wandelen is, wordt binnen het gevalideerde voorstel behouden als niet-werkherstel. Geen nieuwe rep-/setherkenning; AI blijft de bronreps/setgrenzen kiezen. Wandelmeters verdwijnen uit boundary-tekst, blijven in bronloads en worden volgens bestaand beleid uitgesloten van loopkilometers. Voorkomt dat wandelende overgangslaps een verder geldig AI-voorstel geheel blokkeren en de fallback zonder pauzes terugbrengen. Regressie met verkeerd gegroepeerde bronlaps 2/3 en 43 geeft WU 3800m, CD 1450m, 2x(10x400m) p60 sp318 en bewaart alle assignments. 98 gerichte tests en manage.py check slagen; echte AI-productieuitkomst niet bevestigd.


AI-brondekking bij ontbrekende wandel-laps (4 november 2026): niet door AI toegewezen bronlaps worden uitsluitend wanneer ze onder de bestaande >10:00/km-wandelregel vallen als niet-werkherstel behouden. Geen lopende lap, rep of set wordt geraden. Ontbrekende lopende bronlaps blijven afwijzing, met exacte lap-ID-lijst voor de AI-herstelpoging en popup; te weinig werkreps krijgt een afzonderlijke melding met werkelijk aantal. Regressie laat AI stop/overgang/slotwandelen en wandelende setpauze overslaan en bewaart alsnog dezelfde volledige metingen/velden; weglaten van lopende WU wordt afgewezen. 98 gerichte tests en manage.py check slagen. Productie-AI-antwoord en resultaat nog niet bevestigd.


Doorlopende Z1-laps (5 november 2026): opeenvolgende bekende Z1-looplaps worden standaard als een blok samengevoegd, inclusief laatste gedeeltelijke lap. Minstens twee positieve meetlaps, geen expliciete FIT rest/recovery/intervalmarkering, geen wandelen >10:00/km en geen duidelijk snelheidscontrast (max/min snelheid >=1.6). Alleen timerpauzes maken van Z1-laps geen reps. Bestaande bredere kilometerherkenning blijft fallback voor andere zonepatronen; AI-opdrachten (strict C/D/FIT en legacy) bevatten dezelfde Z1-prioriteit. Beschrijvingsafstand afgerond volgens bestaande 50m-regel; bronmeters/seconden onveranderd. Regressie Kane-waarden 1005.56+1000.39+234.197m geeft 2250m Z1 in C/D met en zonder AI, ook met timerpauzes, zonder AI-verzoek. 101 gerichte tests en manage.py check slagen. Geen migratie; visuele productiecontrole niet uitgevoerd.


Use AM/PM bewaart overige trainingsvelden (5 november 2026): toepassen van horlogeresultaten A/B/C/D vervangt uitsluitend WU, Main (CORE), Alternative (ALT) en CD. Mob/Tech, Sprint en Strength worden server-side niet herschreven, ook niet wanneer een oude browser lege/afwijkende waarden of fotoverwijderingen meestuurt. Bestaande segmentrecords, parsing, programmakoppeling en fotoverwijzingen blijven behouden; bij gedeelde/Base Planning-bron worden die onderdelen gekopieerd naar de persoonlijke override zonder de bron te veranderen. Segmentvolgorde wordt overgenomen van zichtbare bron; geen auto-WU/CD over meetvelden heen. Lege ontvangen WU/ALT/CD wissen die vervangbare velden. AYC verstuurt alleen de vier bedoelde teksten plus horlogedata; Alternative gebruikt fields.alt/alternative. Watch/Plan-snapshots bevatten de volledige bewaarde training. 81 gerichte Watch/Plan-, foto-, Strength-, volgorde- en Garmin-tests geslaagd; daarna 14 Watch/Plan-tests inclusief aanvullende lege-grenzen/auto-WUCD-regressie, plus manage.py check. Geen migratie of layoutwijziging; productiecontrole nog niet uitgevoerd.

Niet-hardloopimport Garmin C/D (5 november 2026): bekende activityType anders dan hardlopen wordt `Activiteitsnaam x' Zx` in ALT. Sport/HR-metadata worden ook bewaard wanneer er wel afstand aanwezig is; die afstand gaat niet naar hardloopherkenning of looploads. Minuteafronding: floor(duur_s/60 + 0.5), minimaal 1 minuut. Zone: `hr_zone(athlete, average_hr + 10)`; alleen bij ontbrekend Garmin-gemiddelde mag het expliciet als samplegemiddelde getoonde gemiddelde worden gebruikt. Ruwe HR/duur/afstand blijven ongewijzigd zichtbaar. Geen zone bij ontbrekende HR of niet-eenduidige grensmatch. Unknown/Other/Generic/Multisport wordt niet zomaar als alternatieve sport geraden.

Een ALT-only horlogeimport gebruikt `watch_fields=alternative` en voegt een afzonderlijk ALT-segment toe; server-side worden meegezonden andere veldwaarden genegeerd. Bestaande ALT-segmenten, bronstatus, gemeten running watch_loads/reps, oorspronkelijke Plan-snapshot en segmentvolgorde blijven behouden. Een bestaande Watch-snapshot wordt bijgewerkt met alle ALT-blokken. Bij een gedeelde/Base Planning-bron worden alle bestaande segmenten en meetmetadata overgenomen naar de persoonlijke override voordat het nieuwe ALT-segment wordt toegevoegd. Activiteitsnamen zoals Strength training mogen de ALT-duur/zone niet laten verdwijnen door de Strength-parser. Athlete-weekstatistiek telt de minuten van alle ALT-segmenten ook naast meetloads, zonder loopkilometers te veranderen. ALT-totalen blijven Z1–Z3 ondersteunen.

AI-jogherstel tussen samengestelde reps (5 november 2026): uitsluitend de validator van AI-lapindelingen gebruikt nu work_speed / recovery_speed >= 1.2 voor beide volledige aangrenzende reps (voorheen 1.4). Herstel blijft volledig toegewezen, 30–600s en maximaal 600m; repafstandtolerantie 8%, volledige/chronologische brondekking en geen herstel in een werkrep blijven vereist. AI kiest het aantal aaneengesloten autolaps per rep; er is geen nieuwe lokale 4x3000m- of kilometerpatroonregel. Opdracht benoemt de 20%-drempel expliciet en illustreert groepering van meerdere kilometerrondes, ook bij jogherstel en wisselende tempozones. De korte slotlap mag de AI als direct slot-herstel classificeren. Bestaande lokale heuristieken zijn ongewijzigd. Betrouwbaarheidsgrens blijft 0.75 voor automatisch gebruiken; 0.50–0.75 blijft uitsluitend expliciet te beoordelen na identieke meetcontroles.


Bij samengestelde AI-reps in Garmin C wordt de tempozone opnieuw bepaald met de bestaande atleetreferenties uit som(gemeten meters)/som(gemeten seconden) per volledige rep. De groepszone is het bereik van deze repzones, niet van de bronautolaps. Ook AI-review, herstelvoorstellen en lokale gemengde tijdrepindeling gebruiken deze berekening. Bronlapzones en meetwaarden blijven intact. D gebruikt deze tempozone als fallback en behoudt de bestaande End HR-correctie per volledige rep.


Aanvulling korte AI-afstandsreps (5 november): afstandstolerantie max(30m, 8% van target), zowel per rep als voor groepscontrole. Herstel minimaal 15s uitsluitend wanneer beide aangrenzende reps afstandtargets <=600m en gemeten duur <=90s hebben; anders blijft minimum 30s. Maximum 600s/600m, beide snelheidsratios >=1.2 en volledige brondekking blijven gelijk. Nominale afstand wordt uitsluitend door AI voorgesteld; gemeten meters/tijden worden niet afgerond of overschreven.


Zonebereik van repgroepen (5 november): voor de AI-/samengestelde C-repgroep tellen zones met minder dan 10% van alle volledige reps niet mee in het samenvattende label. Tel aantallen reps, geen autolaps, meters of seconden; tel gelijke sets gezamenlijk. Exact 10% blijft staan. D past dezelfde samenvatting toe na HR-classificatie per volledige rep, met berekende reptempozone als fallback bij ontbrekende HR. Onbekende zones blijven in de noemer; als geen bekende zone de grens haalt, behoud het waargenomen bekende bereik. Bronlapzones, individuele repzones, HR, gemeten afstand/tijd en loads blijven behouden.


6 november — alternatief horlogegebruik: watch_fields=alternative_replace (Use) wist server-side WU/CORE/CD en vervangt ALT, ook wanneer toch looptekst wordt meegestuurd. watch_fields=alternative (Add) behoudt loopmetingen, bron, snapshots en alle bestaande segmenten en voegt het ontvangen resultaat als nieuw ALT-segment toe. Beide vereisen niet-lege ALT en een geldige watch_origin. Sportnamen zoals Strength training worden voor beide modi als alternatieve minuten geparsed. Daardoor kunnen meerdere losse Garmin-activiteiten als segmenten van één alternatieve AM- of PM-training worden gecombineerd.


Alternative-sessiesamenvatting groepeert bestaande kind=alt-loads per zone1–3 en deelt seconden door60. Toon maximaal één decimaal zonder onnodige nul. Niet optellen bij T-kilometers; dezelfde effectieve bron als bestaande totals.


## Openingsrep bij AI-intervalstructuur (6 november 2026)

C/D bepaalt in de AI-opdracht eerst werk/herstel en daarna intensiteitszones. Een Z1/Z2-openingslap kan bij dezelfde afstandsreeks horen. De validator vraagt via de bestaande ene AI-herstelpoging herbeoordeling wanneer de laatste WU-lap direct voor een herstellap en de eerste rep ligt: afstand binnen max(30m,8%) van het groepstarget, snelheid binnen 15% van de mediane groepssnelheid, herstel 30-600s en maximaal 600m, beide aangrenzende inspanningen minimaal 20% sneller. Geen lokale herindeling of confidenceverhoging. Promptvoorbeeld: 2x8x500m met p60/sp208, alle zestien reps behouden. D behoudt eigen HR-zonecorrectie.


Basis - All gebruikt een apart intern TrainingPlan met plan_kind=year_basis per actieve coach. Daardoor blijven null-basis-coachwhereabouts en bestaande basisperplan-data gescheiden en gelden bestaande per-basis datumconstraints. Intern plan wordt buiten reguliere planningskeuzes gehouden. View-only maakt geen record aan wanneer nog geen All-basis bestaat; atleten krijgen geen Basis-selectie.

Campvervoer wordt per YearPlannerWhereabout afzonderlijk opgeslagen als `transport_airport_to_camp` en `transport_camp_to_airport`, beide maximaal 160 tekens. Migratie 0148 hernoemt het voormalige `rental_car_info` naar de heenrichting zodat bestaande inhoud behouden blijft; de retourrichting begint leeg.


Garmin-structuursuggesties (6 november 2026): invoer wordt lokaal begrensd tot numerieke groepen (maximaal 8), 3-30 totale reps per groep, afstandstarget 100-10000m in stappen van 50m of 2-30 hele minuten. De AI krijgt uitsluitend de geparste getallen en originele compacte lapfeiten. AI bepaalt laptoewijzing; dezelfde meet-/confidencecontrole en maximaal een herstelpoging blijven van kracht. Targets, repaantallen en setaantallen moeten exact overeenkomen met de suggestie. Een niet-bevestigd voorstel wordt niet toegepast; meters, seconden, bronlaps en Garmin D-HR-correctie blijven behouden. Suggesties delen de bestaande cache op exacte opdracht, inclusief numerieke suggestie.


Garmin-chat: begrensde gesprekstekst gaat via CSRF-beveiligde POST naar dezelfde AI met oorspronkelijke compacte lapfeiten en bestaande toestemmingscontrole. Confidence >=0.75 en alle meetcontroles blijven nodig voor bruikbare chatvoorstellen; een tekstueel antwoord is nooit een opslagbare training. Chat mag integer doelafstanden vanaf50m gebruiken, inclusief190m; bestaande automatische analyses behouden veelvouden van50m vanaf100m. GPS-marge, gemeten meters/tijden, volledige unieke laptoewijzing, herstelcontrast en D-HR-correctie blijven gelden. Geen geforceerde match of verhoging van confidence.


Gerichte chatcorrecties gebruiken alleen server-eigen meetpreview of de vorige gecontroleerde correctie (tijdelijke cache900s per gebruiker/atleet/dag/model/activiteit). Alle te wijzigen reps moeten al expliciet work_rep=True en nominal_rep_m=bronafstand hebben; geen zoekactie naar nabije laps. Groepsaantal en tekstmatch moeten uniek overeenkomen. Iedere gemeten rep moet binnen max(30m,8%) van de nieuwe doelafstand vallen. AI-confidence>=0.75. Alleen tekstdoelafstand en nominal_rep_m veranderen; gemeten meters/seconden/HR, lapvolgorde, segmenten, zones en herstel blijven gelijk. Niet-passende gerichte correctie valt niet terug op volledige herindeling. Bij verlopen eerdere preview geen stille terugkeer naar de originele training.


Sleep length-extremen vergelijken de bestaande veertien kalenderdagen inclusief vandaag (lokale applicatiedatum), met minimaal drie ingevulde waarden. Bij gelijke extremen telt de meest recente datum. Oudere extremen en volledig gelijke slaapduren blijven neutraal. Geen wijziging van gemiddelden, NA of toegangsrechten.


7 november — Daily vitals gebruikt een daggrens om 08:00 lokale applicatietijd. Vóór 08:00 eindigt het veertiendaagse venster gisteren; ook de slaapkleur-recente dagen schuiven mee. Alleen de laagste en hoogste waarden krijgen kleur; gemiddelden blijven neutraal. Overige overzichtsdatums blijven ongewijzigd.


7 november — Extremumkleuren gelden voor alle vier Daily vitals. Sleep length, Sleep quality en HRV: laagste rood, hoogste groen. Morning HR: laagste groen, hoogste rood. Vandaag donker, één/twee dagen terug licht; oudere/volledig gelijke waarden neutraal, meest recente datum bij gedeeld extremum. Daggrens 08:00 en minimum drie waarden blijven gelden. Alleen range-eindpunten gekleurd, met datumtooltip; gemiddelden/NA en rechten ongewijzigd.


Garmin C/D duurblok met versnellingen (7 november 2026). Een doorlopend Main-blok bestaat uit opeenvolgende Z1-looplaps (minstens twee, samen minimaal 800 m), zonder FIT-intervalmarkering of meerdere langere timerpauzes. Het snelheidsverschil binnen het duurblok is maximaal 25%. Een gemeten overgangslap aan het eind van maximaal 5 m en 2 s in Z1/Z2 mag bij dat blok blijven. De automatische herkenning vereist een daaropvolgende reeks van minstens drie Z3-Z5-versnellingen rond 100 m en gemeten herstel. Dezelfde lapdekking, afstandsmarges en het snelheidscontrast van minimaal 20% tussen reps en herstel gelden. Afstanden, tijden en D-hartslagcorrectie volgen de gemeten bronlaps.


Garmin C/D gemengde afstandssets (7 november 2026). Dezelfde volgorde van minstens twee verschillende afstanden moet volledig herhaald voorkomen in Main. Ieder onderdeel wordt in opnamevolgorde gekoppeld aan één gemeten lap binnen max(30 m, 8%). Gemeten tussenlaps moeten als herstel passen bij de aangrenzende inspanningen. Zones worden pas na die koppeling samengevat. Pauzes worden getoond als de bijbehorende pauzes allemaal gemeten zijn. Dit ondersteunt ook het klokje bij reeds opgeslagen losse Main-onderdelen. Wanneer zulke losse onderdelen elk één herhaling bevatten en volledig met de klokregels overeenkomen, toont het dagdeel per onderdeel alleen geplande afstand, gemeten tijd en gemeten tempo: `1500m - 6:00 - 4:00/km`.


Garmin C/D expliciete tijdkeuze (7 november 2026). Bevat de laatste chatopdracht een herhalingsaantal en een expliciete tijdseenheid, bijvoorbeeld `4*8'`, `4×8 min` of `4 x 8 minuten`, dan wordt de lokaal uit de bronlaps herkende tijdvariant op exact aantal en hele minuten gecontroleerd. Bij een exacte match wordt die tijdvariant gekozen zonder AI-aanroep of AI-toestemming; de afstandsvariant wordt dan niet meer als twijfelkeuze aangeboden. Een afwijkend aantal of afwijkende duur wordt afgewezen. Zonder expliciete tijdseenheid blijven beide volledig passende varianten beschikbaar; de regel verandert geen bronlaps.


Garmin tijdslaps zonder afstand (7 november 2026). Wanneer Activity Details geen totale afstand bevatten, worden geldige lapstarts vanaf de activiteitstart toch bewaard. De laptijd loopt tot de volgende lapstart en voor de laatste lap tot het activiteitseinde. Gemiddelde HR gebruikt samples binnen de lap; eind-HR gebruikt de laatste 10% met minimaal 15 seconden. Afstand en tempo blijven onbekend. Tijdintervalherkenning vereist een aaneengesloten afwisselend blok van minstens drie werkdelen rond hetzelfde hele aantal minuten (marge max 15 seconden of 6%) en herstel van 15-600 seconden, tevens maximaal 75% van de werkduur. Hoogstens omliggende voor-/nablokken worden buiten de samenvatting gelaten.


Garmin C/D expliciete gemengde afstandssets (7 november 2026). Een complete setnotatie met minstens twee verschillende afstanden wordt lokaal getoetst zonder AI-aanroep. Ieder onderdeel moet in bronvolgorde passen binnen max(30 m, 8%). Bij automatische herkenning mag een later afgerond afstandslabel afwijken binnen die marge ten opzichte van de eerste set. Een gemeten wandelovergang van maximaal 600 s vooraf mag langer dan 600 m zijn. De grenzen voor herstel tussen de reps gelden afzonderlijk. Doelafstand en gemeten meters, seconden en zones blijven apart beschikbaar.

Progressieve zones binnen herhaalsets: zowel serverstatistiek als de live Flex Planner-herberekening verdeelt alleen de afstand van het betreffende onderdeel gelijk over de volledige zone-range. `2*(300m z2-200m z3>z4)` levert dus Z2 600 m, Z3 200 m en Z4 200 m; de visuele kleurverdeling gebruikt dezelfde gewichten.

Alternative-belasting is tijdgebaseerd en ondersteunt Z1 tot en met Z6. Een herhaling zoals `3x 8' z4` telt als 24 minuten ALT Z4; deze minuten blijven gescheiden van loopafstand en loopzones.


Garmin C/D gemengde tijdsuggestie (9 november 2026). De lokale controle vergelijkt alle expliciete blokken. Een aaneengesloten reeks van minstens drie gelijke tijdreps met gemeten herstel mag worden gevolgd door één afwijkend werkblok dat binnen de bestaande hele-minutenmarge valt. De voorafgaande herstelronde voldoet aan dezelfde herstelcontrole. Een expliciete slotafstand is toegestaan als de gemeten afstand binnen max(30 m, 8%) ligt. De werkelijk gemeten meters en seconden blijven leidend in het klokje.


Watch Add voor looptraining schrijft WU/Main/CD en de horlogedata. Bestaande Alternative-segmenten worden behouden, ook wanneer de zichtbare training eerst naar een persoonlijke override wordt gekopieerd. De Watch-versie bevat beide soorten training.


Korte Garmin-sets na strides (10 november 2026). Automatische herkenning vereist herhaalde dalende afstanden met duidelijk langere gemeten setpauzes. Doelafstanden volgen de mediaan per positie, afgerond op 10 m, en iedere werkronde moet binnen max(30 m, 8%) vallen. Expliciete chat controleert ook WU/CD en het aantal en de afstand van de reeds herkende strides. Het klokje bewaart de opnamevolgorde en oorspronkelijke meters en tijden.


10 november — Bij horloge-import wordt de scheiding tussen zelfstandige Main-blokken opgeslagen als //, ook als een blok begint met een geneste set. Binnen sethaakjes blijft het streepje de afstandsscheiding. Oude teksten met een los streepje voor een geneste set worden als afzonderlijke blokken gelezen.


11 november — Een herkende tijdsvariant bewaart de bijbehorende expliciete werk-/herstelkoppeling bij de standaardselectie. Bij bestaande tijdtrainingen zonder die koppeling toetst de Diary de complete reeks opnieuw met dezelfde herkenningsregels. Het getoonde tempobereik gebruikt uitsluitend de bevestigde werkreps.


Expliciete afstandsvolgorde (11 november 2026). Alleen een volledige, eenduidig passende chatsuggestie met meerdere blokken en een afsluitende herhalingsreeks vanaf 400 m kan bronlaps samenvoegen tot afstandsblokken zonder geregistreerd herstel. Elke doelrep moet passen binnen max(30 m, 8%). Iedere CORE-lap krijgt een rol. Kleine overgangslaps van maximaal 5 m en 2 s en gemeten wandelherstel worden apart behouden. De gemeten meters en seconden blijven beschikbaar. De afgeleide beschrijving bevat geen geschatte pauzeduur. Automatische intervalherkenning behoudt haar herstelvoorwaarden.
