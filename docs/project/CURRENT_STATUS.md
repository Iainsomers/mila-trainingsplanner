# Actuele status

Bijgewerkt: 12 augustus 2026.

## Productiestatus

- Productiebranch: `main`.
- Laatst in deze task gepushte commit: `2e0f163` (`Add logout button for athlete users`).
- Mobiele PM-trainingen vullen bestaande waarden weer vooraf in.
- Logout is op ingelogde pagina's beschikbaar en leidt naar `/login/`.

## Belangrijk werkend gedrag

- AYC heeft een mobiele weekweergave met Open-knoppen, evaluaties, weekkleuren en voltooiingsvinkje.
- Trainer kan in AYC tussen atleten schakelen; atleet ziet alleen zichzelf.
- PR-invoer gebruikt afstandspecifieke tijdformaten, inclusief 400 m boven 60 seconden.
- Tijdgebaseerde trainingsonderdelen tonen tempo in min/km.
- Trainerstats toont huidige en vorige weekkilometers.
- Standard Strength is vanuit Mob/Tech beschikbaar.

## Bekende aandachtspunten

- De volledige `core`-testset had op 12 augustus 2026 één bestaande fout: de test voor automatische WU/CD bij een uitsluitend Z1/Z2 Main verwacht geen WU/CD, terwijl de actuele code die wel toevoegt. Beslis eerst welke productregel gewenst is en breng code, test en `DATA_RULES.md` daarna samen in lijn.
- Settings (under development) is bewust niet functioneel.
- Stats is bewust eenvoudig en nog in ontwikkeling.
- Polar/watch suggestions blijven een ontwikkelgebied; matching en compacte lapinterpretatie kunnen verder worden verbeterd.

## Documentatie

- `docs/project/` is vanaf nu de primaire overdracht.
- `CODEX_CONTEXT.md` bevat nuttige historie maar ook verouderde paden en oudere status; gebruik het alleen als naslag.
- De Word-handleiding voor atleten staat los in `docs/Handleiding_MiLa_Planner_voor_atleten.docx` en moet bij zichtbare atletenfuncties periodiek worden bijgewerkt.
