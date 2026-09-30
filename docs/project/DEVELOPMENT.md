# Ontwikkelen, testen en documenteren

Laatst inhoudelijk gecontroleerd: 28 september 2026.

## Lokaal

Projectmap op de huidige Windows-machine:

```powershell
C:\Users\iains\mila_app\mila
```

Gebruik de lokale virtual environment:

```powershell
& 'C:\Users\iains\mila_app\venv\Scripts\python.exe' manage.py runserver
& 'C:\Users\iains\mila_app\venv\Scripts\python.exe' manage.py check
& 'C:\Users\iains\mila_app\venv\Scripts\python.exe' manage.py test core
```

De productie-instellingen zijn bewust strenger dan lokaal: op Render moet
`SECRET_KEY` zijn ingesteld en wordt `DEBUG` standaard uitgeschakeld. Voor
een extra domein kan `ALLOWED_HOSTS` als komma-gescheiden environment variable
worden gezet. Lokaal vallen deze waarden terug op veilige ontwikkelwaarden.
In productie herkent Django de Render-proxy als HTTPS, stuurt HTTP door naar
HTTPS en markeert sessie- en CSRF-cookies als secure. HSTS blijft bewust uit
totdat de domeinconfiguratie definitief is gecontroleerd.
De gewone en Admin-login tellen mislukte pogingen kortstondig per IP en
gebruikersnaam. Na vijf fouten volgt tijdelijk een algemene melding; er is
geen permanente account-lockout.
Rechten voor persoonlijke atleetpagina's worden met directe-URL-regressietests
gecontroleerd: een atleet kan niet naar de persoonlijke pagina's van een andere
atleet overschakelen.
Polar OAuth bewaart tokens alleen in de daarvoor bestemde verbindingvelden;
diagnostische tokenpayloads worden ontdaan van access- en refresh-tokens. De
migratie ruimt die velden ook op voor bestaande verbindingen.

Voor COROS workout-pushes moeten na goedkeuring door COROS de Render-omgevingsvariabelen `COROS_PUSH_CLIENT` en `COROS_PUSH_SECRET` worden ingesteld. De publieke statuscheck heeft geen geheim nodig; de ontvangstroute weigert pushes zolang beide waarden ontbreken.

De afgeleide MiLa-logo's voor COROS en de mobiele beginschermiconen worden gegenereerd met `tools/generate_mila_coros_logos.py`. Commit de gegenereerde PNG-bestanden samen met een wijziging aan deze generator.

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

De aparte PAC-app heeft een eigen repository en Render-service. Wijzigingen voor PAC horen nooit in deze MiLa-repository, behalve wanneer expliciet een migratie of koppeling wordt gevraagd.

## Eenmalige accountimport

`create_athlete_accounts` maakt of actualiseert atleetlogins voor één coach op basis van een JSON-lijst met naam en wachtwoord. Het commando is bewust generiek; plaats wachtwoorden nooit in een management command, commit, document of omgeving die naar Git wordt gepusht. Voer credentials alleen tijdelijk in de Render Web Shell of via een beveiligde omgevingsvariabele in.

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
