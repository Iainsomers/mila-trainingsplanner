# Start Here

Bijgewerkt: 29 oktober 2026.

## Project in één minuut

MiLa Training Planner is een Django 5.2-app voor trainers en atleten. Trainers maken trainer-, base- en flexplanning; atleten zien hun eigen AYC, wedstrijden, evaluaties en waar toegestaan hun Year Planner. Productie draait op Render vanaf GitHub-branch `main`.

- Repository: `C:\Users\iains\mila-trainingsplanner`
- Lokale Python: `C:\Users\iains\mila-trainingsplanner\.venv\Scripts\python.exe`
- Basale controle: `& '.\\.venv\\Scripts\\python.exe' manage.py check`
- Interface en communicatie: Engels in de app, Nederlands met de projecteigenaar.
- Voltooide wijzigingen worden normaal direct gecommit en naar `main` gepusht, tenzij de gebruiker expliciet lokaal werk vraagt.

## Handoff voor een nieuwe chat — 29 oktober 2026

- De laatste afgeronde wijziging is commit `fcb0b49` (`Add Flex Planner week copy and paste`).
- Flex Planner heeft per geselecteerde atleet en week een compacte `c`- en `p`-actie. `c` kopieert de zichtbare week; `p` plakt die week naar een andere week van dezelfde atleet. Racecellen worden niet overschreven. Rijen groeien mee zodat langere trainingen volledig zichtbaar blijven.
- Lokaal gevalideerd: `manage.py check`, template-compilatie en 12 gerichte `FlexPlannerAltTotalsTests` slagen.
- De eigenaar meldde na een latere Render-deploy een HTTP 500 en wil die deploy mogelijk terugdraaien. Controleer in Render eerst welke deploy live staat voordat je verder pusht. Een dashboard-rollback kan autodeploy tijdelijk uitschakelen; ga dus niet alleen op de Git-status af.
- De oorzaak is inmiddels lokaal gereproduceerd: het nieuwe Flex-weekclipboard riep `order_by()` aan op virtuele weergavesegmenten. Dit gebruikt nu `all()`; een echte paginatest met AM en PM bewaakt deze fout. De Render-status blijft afzonderlijk te bevestigen.
- Ongecommitteerde lokale handleidingen, render-uitvoer en tijdelijke Office-bestanden zijn bewust buiten de wijziging gehouden en mogen niet worden meegestaged.

## Leesvolgorde voor nieuw werk

1. Lees `AGENTS.md`.
2. Lees dit bestand en de relevante documenten in deze map.
3. Controleer altijd de actuele code: documentatie beschrijft intentie, code en tests zijn leidend.
4. Behoud ongerelateerde, lokale bestanden. In deze werkmap horen `Mila4.docx` en `atletiek_fetch_list.txt` niet in commits.

## Huidige productvorm

- Planning: Athletes, Trainer planning, Flex Planner, Races, Year Planner, AYC/DCO en opgeslagen standaarden.
- Year Planner is de bron voor weekphase-kleuren in Flex Planner, AYC en Trainer Planning.
- Atleten zien de Year Planner alleen wanneer de trainer dat afzonderlijk toestaat voor Training en/of Whereabouts.
- Mobiele AYC heeft evaluatiepopups, een openstaande-evaluaties-prompt en spraak-naar-tekst voor commentaar.
- Evaluations is een apart vragenlijstonderdeel voor trainers en atleten.
- Coach Tools in MiLa bevat alleen Track Timer. Match Overview en PR-database horen bij het aparte PAC-project.
- Athlete settings bevat `Extended edit rights` voor toekomstige AYC-trainingen en lege dagdelen. `Can change base planning` is een afzonderlijk recht waarmee een atleet de eigen Base Planning mag aanpassen.

## Polar-analyse en recente fixes

- Polar Integration biedt Type A (totalen/rondes), B (ruwe samples), C (verwerkt tempo) en D (één overzicht met km per tempozone en hartslagzone).
- Type D rekent vaste totalen uit code; AI geeft alleen een optionele toelichting. HR-grenzen worden per atleet apart opgeslagen met een Estimated-vlag. Zie `FEATURES.md` en `DATA_RULES.md` voor methoden en onzekerheden.
- Polar-pauzemarkeringen worden tegen afstandssamples gecontroleerd; tegenstrijdige markeringen mogen loopgegevens niet verbergen.
- Trainingspopups in AYC, Flex Planner en Trainer Planning staan buiten de stacking context van de teambekleding en blijven boven de backdrop klikbaar.
- DCO Other toont dagelijkse vitals-gemiddelden. `Show NA` staat standaard uit; de keuze en het geopende Vitals-blok blijven behouden bij wisselen van vital.
- Migratie `0096_polar_analysis_settings` hoort bij Type D. Nieuwe deploys moeten deze meenemen via de bestaande Render-migratiestap.

## Nieuwe campbasis

- Coach Settings bevat een per coach opgeslagen `Planning Camps`-schakelaar, standaard uit.
- Bij inschakeling verschijnt Details Camps in de Coach plannings-sectie. Genoemde Camp-whereabouts met dezelfde kampnaam worden als een kamp herkend, ook wanneer deelnemers verschillende datums hebben. Het overzicht bevat atleten en toegankelijke coaches; de brede detailpagina laat individuele aankomst-/vertrekdatums en in-/uitvluchtgegevens automatisch opslaan. Aangepaste datums worden direct in dezelfde Year Planner-range opgeslagen. Deelnemersregels kunnen worden gekopieerd en geplakt; coachregels zijn lichtgeel.
- Atleten zien uitsluitend hun eigen Year Planner-rij en eigen whereabouts. Coaches zijn alleen zichtbaar als rijen in de coachweergave.

## Belangrijke grenzen

- Controleer trainer-/atleetrechten server-side; verborgen knoppen zijn niet voldoende.
- Gedeelde coachtoegang is niet transitief. View-only mag nooit schrijven.
- Accounts en wachtwoorden: nooit credentials, API-sleutels, database-URL's of tijdelijke accountlijsten committen. De herbruikbare opdracht `create_athlete_accounts` accepteert credentials alleen tijdens uitvoering.
- Tempoherkenning gebruikt alleen losse labels; vrije tekst zoals `ritme` mag nooit als `TM` worden geteld.
- Werk mobiele AYC altijd mee na bij zichtbare AYC-wijzigingen.

## Handige commando's

```powershell
& 'C:\Users\iains\mila-trainingsplanner\.venv\Scripts\python.exe' manage.py check
& 'C:\Users\iains\mila-trainingsplanner\.venv\Scripts\python.exe' manage.py test core
```

Bij modelwijzigingen: maak migraties, voer ze lokaal uit en laat Render daarna migreren via de bestaande deploystap. Zie `DEVELOPMENT.md` voor de volledige werkwijze.
