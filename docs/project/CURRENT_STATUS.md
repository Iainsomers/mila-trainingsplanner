# Actuele status

Bijgewerkt: 18 augustus 2026.

## Productiestatus

- Productiebranch: `main`.
- Mobiele PM-trainingen vullen bestaande waarden weer vooraf in.
- Logout is op ingelogde pagina's beschikbaar en leidt naar `/login/`.
- Het MiLa-logo wordt standaard aangeboden als browser- en mobiel beginschermicoon voor iOS en Android.

## Belangrijk werkend gedrag

- AYC heeft een mobiele weekweergave met Open-knoppen, evaluaties, weekkleuren en voltooiingsvinkje.
- Trainer kan in AYC tussen atleten schakelen; atleet ziet alleen zichzelf.
- PR-invoer gebruikt afstandspecifieke tijdformaten, inclusief 400 m boven 60 seconden.
- Tijdgebaseerde trainingsonderdelen tonen tempo in min/km.
- Flex Planner houdt Alternative Z1–Z3 als aparte ALT-minuten buiten de gewone loopkilometers.
- Meerdere Alternative-blokken met `//` blijven afzonderlijke Z1/Z2/Z3-minuten in Flex, AYC en Base Planning.
- Trainerstats toont huidige en vorige weekkilometers.
- Trainerstats deelt nu de volledige atleetselectie met de DCO, inclusief opgeslagen en standaardselecties, `Trains` en `Planned training`.
- Vanuit Trainerstats opent iedere atleet een eigen grafiek met de effectieve weekkilometers over een vrij in te vullen aantal maanden, periodepijlen en een samenvatting met gemiddelde, hoogste en laagste week.
- Standard Strength is vanuit Mob/Tech beschikbaar.
- Atleten kunnen hun Base Planning alleen-lezen bekijken.
- Mobiele AYC ondersteunt gekleurde Week reports, Daily vitals via een hartpopup en compacte weekgemiddelden.
- De mobiele vitals-popup bewaart de vier dagwaarden in één gezamenlijke database-update, sluit na succes expliciet en vult opgeslagen waarden bij opnieuw openen weer correct in.
- Trainers kunnen vitals en training reports voor de geselecteerde atleet ook op toekomstige planningsdagen opslaan; voor atleten zelf blijft toekomstige invoer geblokkeerd.
- Desktop-vitals worden per gewijzigd veld opgeslagen zonder volledige paginaherlading, zodat het kalenderbeeld niet verspringt en de invoer niet terugvalt.
- Een trainer met gedeelde toegang gebruikt bij AYC-opslag dezelfde toegangsregel als bij het bekijken van de atleet; vitals en reports worden daardoor niet meer stil genegeerd voor niet-eigen atleten.
- Race Calendar combineert wedstrijd- en afstandsbeheer met de selectie per atleet. Trainer en atleet hebben eigen vinkjes, Target is gedeeld en de wedstrijdpil toont omlijnd of gevuld of er wederzijds akkoord is.
- Polar markeert een duidelijke mismatch tussen plan en horlogedata met een rood kruis. Op verzoek kan een alternatief trainingsconcept uit laps, splits of activiteitstotaal worden gereconstrueerd, zonder de planning automatisch te overschrijven.
- Polar-patroonherkenning wordt bewaakt met een synthetische horlogetestbank van positieve en misleidende scenario's; dit is de basis voor verdere tuning en eventueel een later model dat van trainercorrecties leert.
- Voor de COROS-partneraanvraag zijn een publieke statuscheck, een beveiligde en idempotente workout-pushontvanger en vier aanvraaglogo's gereed. De OAuth-koppeling en inhoudelijke verwerking wachten op officiële COROS-credentials.

## Bekende aandachtspunten

- Settings (under development) is bewust niet functioneel.
- Stats is bewust eenvoudig en nog in ontwikkeling.
- Polar/watch suggestions blijven een ontwikkelgebied; matching en compacte lapinterpretatie kunnen verder worden verbeterd.

## Documentatie

- `docs/project/` is vanaf nu de primaire overdracht.
- `CODEX_CONTEXT.md` bevat nuttige historie maar ook verouderde paden en oudere status; gebruik het alleen als naslag.
- De Word-handleiding voor atleten staat los in `docs/Handleiding_MiLa_Planner_voor_atleten.docx` en moet bij zichtbare atletenfuncties periodiek worden bijgewerkt.
