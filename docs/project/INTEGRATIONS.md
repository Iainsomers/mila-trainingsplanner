# Koppelingen en vitals

Bijgewerkt: 19 november 2026. Dit overzicht beschrijft de huidige code en onderscheidt die van gewenste vervolgstappen. Configuratie en technische grenzen staan in [DEVELOPMENT.md](DEVELOPMENT.md); rechten in [USER_ROLES.md](USER_ROLES.md).

## Overzicht

| Koppeling | Wat MiLa nu ontvangt/verwerkt | Automatisch | Wat de gebruiker doet |
| --- | --- | --- | --- |
| Garmin activiteiten / FIT | Opnames en gemeten rondes voor horlogeanalyse, inclusief model E als apart toegestaan | Garmin-push bij geconfigureerde ontvangst; FIT ook via upload | Gecontroleerde preview via Use/Add toepassen op AM/PM |
| COROS MCP | Recente activiteiten en originele FIT in de bestaande analyseopslag | Iedere 15 minuten ontbrekende bestanden uit de laatste zeven dagen | Zelf koppelen; eventueel ontbrekende FIT handmatig ophalen via Hardware → COROS |
| Oura | Slaapduur, slaapkwaliteit, HRV en Morning HR via de bestaande vitalimport | Alleen met coachtoestemming, verbonden account, auto-import, Daily vitals en bekende apparaattijdzone | Zelf koppelen; automatische import apart aanzetten |
| Garmin Health | Beschikbare slaap-/HRV-/hartslagwaarden via afzonderlijke Health-push | Bij geconfigureerde Health-feeds | Eigen Garmin-toestemming; bestaande vitalwaarden blijven behouden |
| mySASY | Genormaliseerde metingen en een volledige, afgeschermde meetrespons voor coachinspectie | Momenteel geen automatische synchronisatie of Daily-vitalimport | Zelf eenmalig koppelen; coach onderzoekt daarna het testveld |

Een account verbinden, brongegevens ophalen, een training analyseren en die training in de Diary zetten zijn verschillende stappen. Een geslaagde verbinding bewijst niet dat alle beschikbare gegevens al geïmporteerd zijn. Een FIT-import overschrijft geen bestaande training.

## mySASY: aansluiten en inspecteren

1. Render heeft `MYSASY_CLIENT_SECRET` nodig. App-ID is standaard `31`; de secret hoort uitsluitend in de omgeving, nooit in documenten of commits.
2. Coach: Athlete settings → General → Connections → **Allow mySASY connection** aanzetten en opslaan.
3. Atleet: eigen account → Hardware → **mySASY account**. Toestemming geven, inloggen bij mySASY en na terugkeer controleren/bevestigen dat het om het eigen account gaat.
4. Coach: bij dezelfde atleet onder Connections → **View mySASY measurements** → **Fetch API test data**.
5. Onder **API test data · coach only** staat de volledige succesvolle `/measurements`-respons als leesbare JSON, inclusief onbekende en geneste velden. Credentials zijn verwijderd. Een bestaande atleetkoppeling hoeft hiervoor niet opnieuw.

Het gewone overzicht toont momenteel `compensation`, `totalPower`, `consumption`, `replenishment`, `functionalAge`, tijdstempel en detaillink. Dit zijn de reeds gemapte velden; het is geen volledige inventaris van wat de leverancier mogelijk kan leveren. De coachtest haalt met dezelfde koppeling het afgelopen 30-dagenvenster op zonder die veldselectie. Er wordt geen tweede endpoint of volledig mySASY-account geëxporteerd. Een lege meetrespons verschijnt als `[]`.

De laatste succesvolle testrespons blijft bewaard; een fout toont een melding en behoudt die respons. Een nieuwe test kan eenmaal per tien minuten en telt mee in de gedeelde limiet van 1000 aanvragen per maand. Gewoon openen leest de cache. De atleet krijgt het testvak niet; een coach met alleen kijkrechten kan alleen een al opgeslagen test bekijken. Ontkoppelen, uitschakelen of opnieuw koppelen verwijdert de vorige testgegevens.

## mySASY: doel en nog te verifiëren

De eigenaar wil mySASY gebruiken als bron voor de bestaande vitals, waaronder slaapduur, slaapkwaliteit, morning/night HR en HRV. De werkelijk aangeleverde veldnamen, eenheden, meetmomenten en beschikbaarheid moeten eerst met een verbonden atleet worden vastgesteld. Jonáš beschreef eerder een API met spectrale HRV-waarden en gaf aan dat RMSSD-ms en rusthartslag niet via die beschreven API beschikbaar waren. De eigenaar meldt dat mySASY ook de gewenste vitals bevat. Dit verschil is nog niet opgelost; trek geen algemene conclusie over de mySASY-app op basis van alleen het huidige schema.

Controleer de echte respons in het coachtestveld. Bepaal per gewenst vital het bronveld, de eenheid, datum/tijdzone en betekenis. Ontbreekt een veld, vraag de leverancier welk endpoint/toegangsrecht dat levert. Spectrale HRV-waarden mogen niet zonder onderbouwing in het bestaande HRV-ms-veld terechtkomen. Er is nog geen code die deze mySASY-waarden naar Daily vitals mapt, automatisch importeert of bestaande waarden overschrijft. `/last-training-profile` wordt evenmin opgehaald.

## Oura: tijdschema en bestaande waarden

Onder Hardware acces → Oura daily data kan een bevoegde coach per gekoppelde atleet en Oura-datum alle recordvelden uit de huidige koppeling bekijken (`sleep`, `daily_sleep` en `daily_readiness`). Actieve toestemming en zichtbaarheid van vitals zijn vereist. De pagina berekent langste slaap zonder dutjes en totale aangeboden slaap inclusief dutjes. De gegevens worden op verzoek opgehaald en niet in Diary opgeslagen.

De apparaattijdzone van de atleet bepaalt het schema: 07:30 tot en met 09:00 elke tien minuten, daarna op de hele uren 10:00–20:00. Geen controles van 21:00 tot 07:30; een achterstallige controle wordt dan uitgesteld. Een controle is geen garantie dat Oura al definitieve slaapgegevens heeft. De bestaande import vult lege velden en overschrijft geen reeds opgeslagen waarden. Dat geldt ook wanneer die eerste waarde later onjuist blijkt; er is geen automatische correctie van gevulde vitals toegevoegd.

## COROS: automatische én handmatige FIT-import

Coachtoestemming en de individuele accountkoppeling activeren de automatische controle op Render. Status/tijden staan bij coach en atleet. Dezelfde originele FIT blijft via Hardware → COROS handmatig op te halen wanneer automatische import nog niet is gebeurd. Reeds geïmporteerde activiteiten worden herkend. De gedeelde limiet is 50 downloadpogingen per 24 uur; een automatische beurt verwerkt maximaal tien bestanden. De import wordt gestopt bij ontkoppelen of uitschakelen. De eigenaar heeft de koppeling, FIT-import en automatische werking in de chat als werkend bevestigd; dit is geen onafhankelijke audit van alle productieactiviteiten.

De Hardware-pagina bevat in de COROS-kaart de afzonderlijke, expliciete **AI analysis permission** voor bestaande en toekomstige COROS FIT-imports. Dit is dezelfde FIT-AI-toestemming als bij handmatige uploads, maar een COROS-atleet heeft daarvoor geen ingeschakelde Garmin FIT-upload nodig. Alleen de atleet kan haar geven of intrekken; COROS verbinden alleen is geen AI-toestemming. Zonder toestemming blijven gemeten preview en laps beschikbaar, maar MiLa bespreekt of analyseert de FIT-opname niet met OpenAI. De achterliggende COROS-accountpagina bevat alleen koppelen, synchroniseren, importeren en ontkoppelen.

## Verificatie en vervolg

- mySASY: 35 gerichte tests voor de huidige koppeling/testfunctie en aanpalende regressies slagen; API-antwoorden zijn gemockt. Het testveld is met synthetische data op 390/1440 px gecontroleerd. De echte inhoud en succesvolle mySASY-atleetkoppeling zijn in deze chat nog niet bevestigd.
- Drie bestaande Oura-tests lopen vast op stringdatums in de activity-eventregistratie. Zie DEVELOPMENT; dit is nog niet gerepareerd.
- Garmin E bewaart correcties binnen het gesprek en gebruikt verbeterde rep/pauze-instructies. Er is geen algemene zelflerende trainings- of feedbackpipeline gebouwd. Het doel is reconstructie van uitgevoerde training, niet zelfstandig trainingsadvies.
- Push naar `main` is geen bevestiging van een geslaagde Render-deploy of ingestelde productiegeheimen. De werkelijke configuratie/deploy moet afzonderlijk worden gecontroleerd.
