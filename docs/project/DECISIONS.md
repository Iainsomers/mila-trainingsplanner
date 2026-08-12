# Productbeslissingen

Dit is geen changelog. Noteer alleen keuzes die toekomstige ontwikkeling sturen. Nieuwste beslissing bovenaan.

## 2026-08-12 — Projectkennis opsplitsen

Mila4 en de lange overdrachtsnotitie worden vervangen door thematische documenten in `docs/project/`. De actuele code blijft leidend. Documentatie wordt bij relevante gedragswijzigingen in dezelfde commit bijgewerkt, niet mechanisch na iedere kleine wijziging.

## 2026-08-12 — Logout zonder Admin

Iedere ingelogde gebruiker krijgt een logoutmogelijkheid die veilig afmeldt en naar de loginpagina gaat. Atleten hoeven daarvoor geen Admin-toegang te hebben.

## 2026-08-11 — Mobiele AYC

Mobiel toont één week, gebruikt expliciete Open-knoppen en schermpassende popups. Huidige week is geel, huidige dag donkerder geel. Evaluatievoltooiing wordt met een groen vinkje getoond. Trainerselectie blijft voor trainers beschikbaar.

## 2026-08-11 — Rollen

Atleten zien alleen hun eigen instellingen, wedstrijden en AYC. Trainers kunnen in de AYC tussen toegankelijke atleten schakelen.

## 2026-08-11 — Trainingsbenaming

Het belangrijkste trainingsdeel heet in de interface `Main`, omdat `Core` te veel op buikspiertraining lijkt. Interne datatypen blijven CORE/CORE2.

## 2026-08-11 — PR-formaten

400 m gebruikt `ss.ss` en mag boven 60 seconden uitkomen. 800/1500 gebruikt `mm:ss.ss`; 3000/5000/10.000 gebruikt `mm:ss`; halve en hele marathon gebruiken `hh:mm:ss`.

## 2026-08-11 — Tijdblokken tonen tempo

Voor trainingsonderdelen in minuten of seconden wordt richttempo in min/km getoond, niet een geschatte afstand in meters.

## 2026-08-11 — Dashboardindeling

Planning blijft de hoofdactie. Admin, Stats, Polar en een niet-functionele Settings (under development)-tegel staan onderaan het coachdashboard.

## Eerdere blijvende keuzes

- Alle zones, weekkleuren en trainingsonderdelen staan standaard aan.
- Zones worden ingevoerd als min/km.
- Standard Strength wordt als herbruikbaar blok via Mob/Tech gekozen en vanuit planning geopend.
- Doelwedstrijden worden als `Race!` duidelijker gemarkeerd dan gewone wedstrijden.
