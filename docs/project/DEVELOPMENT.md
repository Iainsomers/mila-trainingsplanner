# Ontwikkelen, testen en documenteren

Laatst inhoudelijk gecontroleerd: 12 augustus 2026.

## Lokaal

Projectmap:

```powershell
C:\Users\iains\mila-trainingsplanner
```

Gebruik de lokale virtual environment:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test core
```

Voor COROS workout-pushes moeten na goedkeuring door COROS de Render-omgevingsvariabelen `COROS_PUSH_CLIENT` en `COROS_PUSH_SECRET` worden ingesteld. De publieke statuscheck heeft geen geheim nodig; de ontvangstroute weigert pushes zolang beide waarden ontbreken.

Bij modelwijzigingen:

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations
.\.venv\Scripts\python.exe manage.py migrate
```

## Teststrategie

- Begin met gerichte tests voor het gewijzigde gedrag.
- Draai daarna `manage.py check`.
- Draai waar haalbaar de volledige `core`-testset.
- Meld bestaande, niet-gerelateerde testfouten expliciet; verberg ze niet.
- Test zichtbaarheid en mutaties voor zowel trainer als atleet.
- Test mobiele UI op AM én PM en op bestaande én lege invoer.
- Polar-reconstructie heeft daarnaast een synthetische testbank in `core/tests_polar_reconstruction.py` met duurloop, progressieve loop, GPS-pieken, stops, korte versnellingen, tijdsintervallen, heuvelherhalingen en onregelmatige fartlek. Voeg bij nieuwe herkenningsregels zowel een positief als een misleidend negatief scenario toe.

## Git en Render

- Branch `main` is de productiebranch.
- Render kan na een push automatisch deployen.
- Stage alleen taakrelevante bestanden; de werkmap kan ongerelateerde gebruikersbestanden bevatten.
- Commit en push voltooide wijzigingen standaard naar `main`, zodat Render ze kan uitrollen. Sla de push over wanneer de gebruiker expliciet zegt dat de wijziging lokaal moet blijven.
- Gebruik korte, beschrijvende commits.

Nooit committen zonder expliciet verzoek:

- `db.sqlite3`;
- Office-lockbestanden zoals `~$...`;
- geheime sleutels/tokens;
- tijdelijke renders of lokale caches.

## Wanneer documentatie bijwerken?

Niet ieder bestand na iedere miniwijziging. Werk alleen de relevante bron bij:

- Nieuwe of gewijzigde functie: `FEATURES.md`.
- Rechten of zichtbaarheid: `USER_ROLES.md`.
- Layout, mobiel gedrag, labels of kleuren: `UI_RULES.md`.
- Formaten, parser of berekeningen: `DATA_RULES.md`.
- Architectuur, techniek of hoofdstructuur: `PROJECT_OVERVIEW.md`.
- Nieuwe ontwikkel-/deployafspraak: `DEVELOPMENT.md` of `AGENTS.md`.
- Bewuste productkeuze met blijvend effect: voeg één korte regel toe aan `DECISIONS.md`.
- Bekend probleem, actieve ontwikkeling of afgeronde mijlpaal: `CURRENT_STATUS.md`.

Documentatie hoort bij dezelfde commit als de functionele wijziging wanneer zij erdoor verandert. Typo's, interne refactors zonder gedragswijziging en eenmalige diagnose vereisen meestal geen documentatie-update.

## Onderhoudsmoment

Doe ongeveer maandelijks of na een grotere feature een korte documentatiecontrole:

- verwijder opgeloste punten uit Current Status;
- controleer verouderde termen en routes;
- vat Decisions niet opnieuw samen in alle andere bestanden;
- houd elk document doelgericht en bij voorkeur onder circa 200 regels.
