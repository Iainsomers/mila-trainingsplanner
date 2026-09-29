# Actuele status

Bijgewerkt: 28 september 2026.

## Productiestatus

- Productiebranch: `main`; pushes deployen automatisch op Render.
- MiLa is de planner voor trainers en atleten. PAC is een aparte Render-service en repository voor Match Overview en de PR-database.
- Het MiLa-logo wordt als browser- en beginschermicoon aangeboden op iOS en Android.

## Belangrijk werkend gedrag

- Trainers kunnen eigen gegevens bekijken of expliciet als een toegankelijke coach kijken. Die toegang is niet transitief; view-only blijft server-side read-only.
- Atleten zien uitsluitend zichzelf in AYC, settings, races, evaluaties en, waar ingesteld, Year Planner.
- Flex Planner toont de effectieve, gepersonaliseerde planning. Het verwijderen van een flex-override onderdrukt een basistraining correct.
- Weekphase-kleuren komen uit Year Planner en verschijnen ook in Flex Planner, AYC en Trainer Planning. Bij meerdere fases krijgt de week een gecombineerde kleur.
- Year Planner ondersteunt één, drie of twaalf maanden, stacked of scrollend. Whereabouts zijn verplaatsbare en schaalbare datumranges met benoemde pills, diagonale overlapweergave, rij-kopiëren en bulktoepassing op de geselecteerde atleten.
- Trainers kunnen in de Year Planner per gekozen Trainer Planning-groep direct onder `All` een eigen `Basis - groepsnaam`-rij selecteren. Basisgegevens van verschillende groepen blijven gescheiden.
- Per atleet zijn Year Planner Training en Whereabouts afzonderlijk zichtbaar te maken. De atleetweergave is alleen-lezen en de legenda volgt de toegestane lagen.
- Base Planning gebruikt handmatig instelbare, aaneengesloten datumblokken. De oude onderliggende Save/Cancel-knoppen zijn verwijderd; wijzigingen blijven op de actieve tab na opslaan.
- Mobiele AYC heeft Open-knoppen, AM/PM-evaluaties, week reports, daily vitals en een popup voor niet-ingevulde evaluaties van de afgelopen zes dagen. De huidige dag en oudere trainingen tellen niet mee.
- Mobiele evaluatiecommentaren ondersteunen Nederlandse spraak-naar-tekst. Herkenningsresultaten worden per resultaatindex verwerkt om dubbele of drievoudige tekst te voorkomen.
- Evaluations ondersteunt actieve coachvragenlijsten, gewone en matrixvragen, kopiëren vanuit bestaande lijsten, verwijderen, inklapbare lijsten en ingevulde antwoorden per atleet.
- Coach Tools in MiLa bevat Track Timer voor 100–1600 m, doeltijdvisualisatie, drie-atletenmodus en tussentijden.
- Parser ondersteunt T1 en T6, progressieve Z/T-ranges met tussenliggende labels, compoundblokken en pauzenotatie `p`/`sp`.
- Polar v3/v4-integratie en reconstructies bestaan. Polar v4-samples worden nu naast laps opgehaald en aan de tijd/afstand-matcher doorgegeven; complexe workoutmatching blijft een actief ontwikkelgebied.

## Recente onderhoudsafspraken

- Nieuwe Mila-chats starten met `AGENTS.md` en `docs/project/START_HERE.md`; `CODEX_CONTEXT.md` is alleen nog een verwijzing.
- Voor eenmalige accountimports bestaan generieke Django-management commands. Passwords en database-URLs horen nooit in Git.

## Bekende aandachtspunten

- Settings (under development) is bewust niet functioneel.
- Daily Coach Overview Vitals is zichtbaar als toekomstige, niet-aanklikbare tab.
- Stats is bewust eenvoudig en nog in ontwikkeling.
- Polar/watch suggestions, vooral automatische workoutmatching zonder handmatige laps, hebben verdere testgevallen en verfijning nodig.
- E-mail-, WhatsApp- of pushreminders voor openstaande evaluaties zijn nog niet gebouwd; de huidige herinnering is alleen de AYC-popup.
