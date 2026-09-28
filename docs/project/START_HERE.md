# Start Here

Bijgewerkt: 28 september 2026.

## Project in één minuut

MiLa Training Planner is een Django 5.2-app voor trainers en atleten. Trainers maken trainer-, base- en flexplanning; atleten zien hun eigen AYC, wedstrijden, evaluaties en waar toegestaan hun Year Planner. Productie draait op Render vanaf GitHub-branch `main`.

- Repository: `C:\Users\iains\mila_app\mila`
- Lokale Python: `C:\Users\iains\mila_app\venv\Scripts\python.exe`
- Basale controle: `python manage.py check`
- Interface en communicatie: Engels in de app, Nederlands met de projecteigenaar.
- Voltooide wijzigingen worden normaal direct gecommit en naar `main` gepusht, tenzij de gebruiker expliciet lokaal werk vraagt.

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

## Belangrijke grenzen

- Controleer trainer-/atleetrechten server-side; verborgen knoppen zijn niet voldoende.
- Gedeelde coachtoegang is niet transitief. View-only mag nooit schrijven.
- Accounts en wachtwoorden: nooit credentials, API-sleutels, database-URL's of tijdelijke accountlijsten committen. De herbruikbare opdracht `create_athlete_accounts` accepteert credentials alleen tijdens uitvoering.
- Werk mobiele AYC altijd mee na bij zichtbare AYC-wijzigingen.

## Handige commando's

```powershell
& 'C:\Users\iains\mila_app\venv\Scripts\python.exe' manage.py check
& 'C:\Users\iains\mila_app\venv\Scripts\python.exe' manage.py test core
```

Bij modelwijzigingen: maak migraties, voer ze lokaal uit en laat Render daarna migreren via de bestaande deploystap. Zie `DEVELOPMENT.md` voor de volledige werkwijze.
