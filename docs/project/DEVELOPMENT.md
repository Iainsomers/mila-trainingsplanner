# Ontwikkelen, testen en documenteren

Bijgewerkt: 12 oktober 2026.

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
HTTPS en markeert sessie- en CSRF-cookies als secure. HSTS staat in productie
voorzichtig aan met een termijn van één dag, zonder subdomeinen of preload.
Aanvullend zet Django op iedere response `Referrer-Policy: same-origin`,
`X-Content-Type-Options: nosniff` en
`Cross-Origin-Opener-Policy: same-origin-allow-popups`. Die laatste variant
behoudt de werking van OAuth-popups, waaronder Polar.
De gewone en Admin-login tellen mislukte pogingen kortstondig per IP en
gebruikersnaam. Na vijf fouten volgt tijdelijk een algemene melding; er is
geen permanente account-lockout.
Rechten voor persoonlijke atleetpagina's worden met directe-URL-regressietests
gecontroleerd: een atleet kan niet naar de persoonlijke pagina's van een andere
atleet overschakelen.
Polar OAuth bewaart tokens alleen in de daarvoor bestemde verbindingvelden;
diagnostische tokenpayloads worden ontdaan van access- en refresh-tokens. De
migratie ruimt die velden ook op voor bestaande verbindingen.

De optionele Oura-OAuth-koppeling gebruikt Render-omgevingsvariabelen
`OURA_CLIENT_ID` en `OURA_CLIENT_SECRET`. De geregistreerde redirect-URI is
`https://mila-trainingsplanner.onrender.com/integrations/oura/callback/`.
De OAuth-flow vraagt alleen `daily` aan en slaat de tokenrespons niet als ruwe
diagnostiek op. De Oura-testpagina haalt op verzoek maximaal 14 dagen aan
slaap- en readiness-samenvattingen op en toont die uitsluitend tijdelijk in de
pagina. De atleet kan in de AYC afzonderlijk een importpreview opvragen en na
het verwijderen van ongewenste dagen `Use all` kiezen. Readiness is alleen een
verborgen voorwaarde; alleen lege slaapuren-, slaapkwaliteit- en HRV-velden
worden bijgewerkt. De importer haalt bij het opslaan de data opnieuw op en
controleert nogmaals op bestaande waarden. Oura's laagste slaap-HR vult Morning
HR en wordt afgerond op hele bpm.
API-verzoeken gebruiken een herkenbare `User-Agent`; OAuth-refresh bewaart het
vervangen refresh-token.

Voer voor een dependencycontrole `pip-audit -r requirements.txt` uit. De
productierequirements zijn op 1 oktober 2026 bijgewerkt naar versies zonder
bekende kwetsbaarheden volgens de scan.

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

## Polar en trainingspopups: gerichte validatie

```powershell
& 'C:\Users\iains\mila_app\venv\Scripts\python.exe' manage.py test core.tests_polar_raw core.tests_polar_processing core.tests_polar_analysis core.tests_polar_reconstruction --noinput
& 'C:\Users\iains\mila_app\venv\Scripts\python.exe' manage.py check
& 'C:\Users\iains\mila_app\venv\Scripts\python.exe' manage.py makemigrations --check --dry-run
```

- Neem `0096_polar_analysis_settings` mee in de bestaande Render-migratiestap. Type D gebruikt deze tabel; alleen templates deployen is onvoldoende.
- De optionele AI-toelichting gebruikt `OPENAI_API_KEY` en optioneel `OPENAI_MODEL`; zonder sleutel of bij netwerkfouten blijven de vaste resultaten beschikbaar. Commit nooit configuratiewaarden of tokens.
- Voor nieuwe pauzeregels: test tegenstrijdige/geneste pauzes, geldige stops, GPS-drift en één losse GPS-sprong. Gebruik synthetische fixtures; zet geen volledige persoonsgebonden JSON in Git.
- Voor popups: reproduceer teambranding met isolation/stacking context en een echte Bootstrap-backdrop. Controleer Flex via fetch én HTMX en Trainer Planning via HTMX, op 390 en 1440 px, voor AM/PM en lege/bestaande trainingen. Test invoer, Save en Close; wacht op de popupanimatie vóór sluiten.
- De volledige core-suite is niet opnieuw gedraaid voor de recente Polar/popupfixes; gerichte controles staan in `CURRENT_STATUS.md`.

## Documentatie op Render

Automatische Oura-vitals: migratie 0137 voegt opt-in, apparaattijdzone en laatste/volgende controle toe. In Render start WSGI automatisch een lichte achtergrondthread per webproces (`RENDER=true`); databaseclaims voorkomen dubbele controles bij meerdere workers of overlappende deploys. De thread controleert iedere 30 seconden op verschuldigde atleten en blijft onafhankelijk van browserbezoeken actief zolang de webservice draait. De webservice moet continu draaien: een slapende Free-service voert geen achtergrondwerk uit (https://render.com/docs/free). Er wordt geen extra betaalde service aangemaakt. Bij een aparte scheduler kan `OURA_AUTO_IMPORT_WORKER=0` worden gezet en `python manage.py sync_oura` iedere minuut draaien. Buiten Render staat de thread standaard uit; lokaal alleen expliciet met `OURA_AUTO_IMPORT_WORKER=1`. Mislukkingen loggen uitsluitend fouttypen; tokens, API-responses, namen en gezondheidswaarden niet. Gerichte tests: `manage.py test core.tests_oura_auto core.tests_oura`. De eigenaar doet de visuele controle.

De projectdocumentatie is bronmateriaal in `docs/project/` en wordt met main naar dezelfde Render-checkout uitgerold. Er bestaat geen aparte publieke documentatiepagina in deze app. Een Git-push bevestigt de repositorywijziging, niet zelfstandig de voltooiing van de Render-deploy.

## Garmin OAuth-configuratie

Migratie `0130` voegt de Garmin-rechten, laatste AI-toestemming/intrekking en aparte tokenopslag toe. Stel op Render `GARMIN_CLIENT_ID` en `GARMIN_CLIENT_SECRET` in; `GARMIN_REDIRECT_URI` is optioneel en standaard `https://mila-trainingsplanner.onrender.com/integrations/garmin/callback/`. Registreer exact die callback bij Garmin. Zonder configuratie blijft Connect Garmin uitgeschakeld en doet de server geen autorisatieverzoek.

OAuth volgt Garmins officiële OAuth2 PKCE-specificatie: https://developerportal.garmin.com/sites/default/files/OAuth2PKCE_1.pdf. State, gebruikers-/atleetbinding, eenmalige callback, tien minuten geldigheid en wijzigingen van toestemming worden gecontroleerd. Activity Summary Push-ontvangst is toegevoegd in migratie 0131; de endpoint moet nog in Garmin API Tools op Push worden ingesteld voordat echte aanlevering start. Externe OAuth en ontkoppeling zijn met gemockte HTTP-responses getest; een echte Garmin-test vereist geconfigureerde sleutels.

Garmin Push: gebruik de privé-URL uit `Garmin receiving setup` op `/coach/garmin/` als superuser/productbeheerder. Configureer Activities (`activities`) en Activity Details (`activityDetails`) in Push-modus met dezelfde URL. De code gebruikt de gepubliceerde Garmin OAuth2 PKCE-specificatie voor user-ID-opvragen. Het Activity Summary Push-formaat is gecontroleerd tegen Garmins oorspronkelijke Activity API-specificatie (oudere versie 1.0.2); de huidige ingelogde API Tools-configuratie en een echte Garmin-push moeten nog worden geverifieerd. De receiver haalt geen callbackURL op en ondersteunt geen Ping/Pull- of FIT-fileberichten. Activity Details worden tot gemeten rondes en HR gereduceerd. Deel de private URL niet in chat/logs; wijziging van de appsecret of Django-secret roteert de ontvangstcode en vereist aanpassing van de URL bij Garmin. Test: `manage.py test core.tests_garmin_push core.tests_garmin_connection`.

Garmin C gebruikt vanaf migratie 0132 ook de pushgegevens. Details-payloads zijn begrensd tot 8 MB; gewone summaries blijven begrensd tot 1 MB. Gerichte integratietests: `manage.py test core.tests_garmin_c_push core.tests_garmin_push core.tests_garmin_connection`. Bij een al ontvangen summary kan Summary Resender na inschakeling van Activity Details de beschikbare details opnieuw aanbieden; bestaande summaries worden niet achteraf van ontbrekende duur/rondes voorzien.

Bij de WSGI-start met automatische Oura-controle wordt de URL/view-importgraaf eerst op de hoofdthread geladen. Start geen achtergrondthread die views importeert voordat die initialisatie klaar is: gelijktijdige eerste imports kunnen op modulelocks vastlopen en andere endpoints blokkeren. Koude-startregressie: `manage.py test core.tests_wsgi_startup`.

De kleine Garmin-combinatiehelper staat als JavaScript-templatepartial naast de kalender en wordt direct in het AYC-script opgenomen. `node core/tests_garmin_combine.js` test dezelfde bron; de AYC-paginatest controleert bovendien dat de gerenderde functie uitvoerbaar is.

Garmin D vereist migratie 0138 (TrainingSlot.source-keuze). Gerichte controles: core.tests_garmin_d, core.tests_garmin_c_push, core.tests_watch_structure en core.tests_watch_plan. HR-controle draait lokaal op bestaande lapfeiten; er is geen extra Garmin-scope, HR-schatting of AI-aanroep voor deze controle.

Migratie 0139 voegt camp_comments toe voor de Comments-kolom in Details Camps. Neem deze mee in de bestaande Render-migratiestap.


YearPlannerEntry heeft standaard ordering via athlete__name. Gebruik bij select_for_update voor Basis-rijen expliciet order_by("date"): een Basis-rij heeft geen atleet en PostgreSQL weigert FOR UPDATE op de nullable zijde van een outer join. De YearPlannerTests bewaken de SQL-vorm ook onder SQLite.


Mob/Tech-foto’s vereisen Pillow==13.0.0 en migratie 0140_trainingsegment_photo_ids_trainingphoto. Binaries staan in de productiedatabase (dus geen vluchtige Render-schijf of extra storage-account). Dag/weekkopieën en snapshots bewaren alleen UUID-referenties; kopieer nooit de foto-bytes naar sessies of JSON. Gerichte tests: core.tests_training_photos en core.tests_watch_plan. AYC verstuurt eigen multipart-FormData; Trainer/Flex gebruikt hx-encoding=multipart/form-data. Beide opslagroutes moeten foto’s behouden.


Genereer fotolinks via training_slot_photo (slot-id + foto-UUID), niet via de vluchtige segment-id. De route controleert steeds de actuele MOB-segmenten van dat slot. Coachrechten voor persoonlijke slots volgen de atleet; gedeelde slots volgen het plan. De oude segmentroute blijft beschikbaar voor nog bestaande segmenten.


Nieuwe AI-lapvoorstellen in polar_raw worden door core/watch_ai_structure.py gevalideerd voordat Garmin C/D ze gebruiken. Het bestaande API-verzoek bevat alleen numerieke lapfeiten en markers; geen extra HR/GPS/persoonsgegevens. Geen extra AI-aanroep of scopes. Unit/integratietests core.tests_watch_ai_structure gebruiken gemockte AI-responses, inclusief consent-uitgeschakeld, kwaadaardige/ongeldige indelingen, twee previews, zes klokreps en onveranderde meetkilometers. De oudere AI-responsevorm blijft compatibel; zonder geldig voorstel volgt vaste herkenning.


AI-herstel na afgewezen lapindeling (4 november 2026): validator levert optioneel een vaste servergeschreven afwijsreden per controlefase. Garmin C/D vraagt bij een ongeldig lapvoorstel maximaal eenmaal een nieuw volledig AI-voorstel met oorspronkelijke anonieme lapfeiten plus die feedback (extra verzoek maximaal 15s; bestaande toestemming blijft vereist). Tweede voorstel doorloopt identieke controles; bij falen blijft gemeten fallback met zichtbare afwijsreden. Geen ruwe servicefouten/modelpayloads of tokens in browserfeedback. Regressies dekken herstel van langzame overgang in warmup, een tweede afwijzing, exact twee verzoeken, behouden meetwaarden en succesvolle setindeling. 94 gerichte tests en manage.py check slagen. De productie-afwijsreden voor Daans opname is nog niet bevestigd; eerdere gemockte AI-test bewijst geen echte service-uitkomst.


AI-opdracht en confidence verduidelijkt (4 november 2026): strict Garmin C/D gebruikt een zelfstandige lap-only opdracht en systeembericht, zonder tegenstrijdige legacy segments/sets-instructies of oude schema-beperkingen. Opdracht benoemt gemeten werk/herstel/setgrenzen, langzame overgangslaps en grenzen van de bestaande validator. Geen andere confidencegrens: geldige numerieke score vereist 0.75-1.00. Afwijzing noemt nu exacte score of ontbrekend/ongeldig getal; bools/NaN/strings worden niet als score geaccepteerd. Legacy Polar-pad ongewijzigd. 95 gerichte tests en manage.py check slagen; echte AI-score/uitkomst voor productieopname nog niet geverifieerd.


Gerichte AI-repcorrectie (4 november 2026): de ene herstelpoging krijgt nu het oorspronkelijke numerieke AI-voorstel als assistant-context plus validatiefout. Alleen bekende structuurvelden/numerieke waarden worden teruggestuurd, geen willekeurige modeltekst. Repfouten zijn opgesplitst naar concrete lap-ID-volgorde, gemeten meters versus doelmeters, seconden versus tijdtarget, en langzame herstel-lap in werkrep. Lap-only opdracht verduidelijkt dat elke reps-entry precies een herhaling is en geen volledige set. 46 gerichte tests slagen; daarna 14 AI-tests met nieuwe herstelcontext-/foutdetailregressies en manage.py check slagen. Productievoorstel nog niet beschikbaar; geen bevestiging van de specifieke lapfout op productie.


Trainingsstructuur-model opgewaardeerd (4 november 2026): Garmin C/D en FIT-AI gebruiken in strict_lap_structure nu standaard gpt-5.4-mini met reasoning_effort=low, zonder temperature. Dedicated WATCH_STRUCTURE_MODEL kan een expliciet compatibel reasoning-model instellen; bestaande globale OPENAI_MODEL blijft uitsluitend het legacy Polar-pad bepalen. Daardoor houdt een oude OPENAI_MODEL=gpt-4o-mini de nieuwe structuurherkenning niet tegen. Dezelfde parameters gelden voor de ene herstelpoging. Popup toont AI model: plus de werkelijk gekozen modelnaam, uitsluitend na AI-aanroep. Aanvankelijk overwogen zwaarste model is op verzoek van eigenaar niet gekozen; middenweg GPT-5.4 mini. Officiële API-bronnen: https://developers.openai.com/api/docs/models/gpt-5.4-mini en https://developers.openai.com/api/docs/guides/latest-model (reasoning-parameters). Lokale modelresolver tweemaal niet bereikbaar; keuze geverifieerd via opgehaalde officiële modelpagina. 99 gerichte tests en manage.py check slagen; verzoekparameters en modeloverride inclusief herstel getest met gemockte API. Geen lokale API-sleutel, dus geen echte modelaanroep of productie-kwaliteit/latentie bevestigd. Geen migratie nodig.

AI-autolapopdracht (5 november 2026): voorbeelden en tegenvoorbeelden voor samengestelde afstandsreps staan als recording_boundaries bij de bestaande lap-only opdracht, voor eerste verzoek én herstelverzoek. Model, endpoint, gegevensset en toestemmingscontrole blijven gelijk. Gebruik bij regressies de echte translate/endpoint-stroom plus gemockte modelantwoorden; maak duidelijk dat dit de verwerking van een AI-antwoord bevestigt, niet de live modelkwaliteit. Bron voor instructies plus gevarieerde voorbeelden: officiële OpenAI Docs https://developers.openai.com/api/docs/guides/prompt-engineering#few-shot-learning.


Migratie 0145_coachsettings_under_dev_enabled voegt de standaard uitgeschakelde Under Dev-module toe. Lokaal toegepast; Render moet de migratie via de bestaande deploystap uitvoeren.
