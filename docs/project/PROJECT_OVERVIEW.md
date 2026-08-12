# MiLa Training Planner — projectoverzicht

Laatst inhoudelijk gecontroleerd: 12 augustus 2026.

## Doel

MiLa Training Planner ondersteunt trainers bij het maken, personaliseren en volgen van looptrainingen. Trainers bouwen plannen en analyseren belasting; atleten bekijken hun eigen planning, kiezen wedstrijden en evalueren trainingen.

## Techniek

- Django 5.2 met server-rendered templates en JavaScript voor interactieve planners en popups.
- Lokale ontwikkeling met SQLite; productie gebruikt de via `DATABASE_URL` ingestelde database.
- Bootstrap 5 voor de basisopmaak.
- WhiteNoise voor statische bestanden en Gunicorn op Render.
- Tijdzone: `Europe/Amsterdam`.
- Productie wordt vanuit branch `main` op GitHub naar Render uitgerold.

## Hoofdstructuur

De centrale gegevens zijn:

- `Athlete`: persoonsgegevens, zones, PR's, doelen, zichtbaarheid en rapportage-instellingen.
- `Group`: verzameling atleten en eventuele standaard WU/CD-instellingen.
- `TrainingPlan`: legacy- of trainerplanning, gekoppeld aan atleten en groepen.
- `TrainingSlot`: training op datum en AM/PM-slot, eventueel specifiek voor één atleet.
- `TrainingSegment`: onderdeel van een training, zoals WU, MOB, SPR, CORE, CORE2, ALT of CD.
- Wedstrijden en geselecteerde afstanden.
- Evaluaties, weekrapporten en dagelijkse waarden.
- Standaard krachtprogramma's en Polar-koppelingen.

## Planningsstroom

Trainerplanning levert de basis. Flex Planner toont en personaliseert de effectieve planning per atleet. De AYC is de uiteindelijke atletenweergave en bevat zowel basistrainingen als persoonlijke overrides.

## Terminologie

- AYC: Athlete Year Calendar, de persoonlijke jaar-/weekplanner van een atleet.
- DCO: Daily Coach Overview.
- WU/CD: warming-up en cooling-down.
- Mob/Tech: mobiliteit, techniek of standaard krachtprogramma.
- Main/Main 2: belangrijkste trainingsonderdelen; intern opgeslagen als `CORE`/`CORE2`.
- FIX: een training die specifiek voor een atleet is aangepast.

## Bronnen van waarheid

1. De actuele code en tests bepalen wat werkelijk draait.
2. `docs/project/` beschrijft de bedoelde werking en productkeuzes.
3. `CODEX_CONTEXT.md` en oudere Mila4-documenten zijn alleen historische naslag.
