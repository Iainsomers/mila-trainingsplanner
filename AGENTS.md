# MiLa Planner — werkinstructies

Lees vóór een wijziging de relevante documenten in `docs/project/`:

- `PROJECT_OVERVIEW.md` voor architectuur en begrippen.
- `USER_ROLES.md` voor rechten en zichtbaarheid.
- `FEATURES.md` voor bestaand gedrag.
- `UI_RULES.md` voor interface-afspraken.
- `DATA_RULES.md` voor tijd-, zone- en rekenregels.
- `DEVELOPMENT.md` voor lokaal testen en deployen.
- `DECISIONS.md` voor bewuste productkeuzes.
- `CURRENT_STATUS.md` voor actuele status en bekende problemen.

## Harde afspraken

- Communiceer met de projecteigenaar in het Nederlands.
- Controleer de actuele code; documentatie beschrijft de bedoeling maar kan achterlopen.
- Atleten mogen alleen hun eigen instellingen, wedstrijden en AYC zien.
- Trainers moeten in de AYC tussen toegankelijke atleten kunnen schakelen.
- Gebruik in de gebruikersinterface `Main` en `Main 2`; `CORE` en `CORE2` blijven interne datatypen.
- Behoud de compacte MiLa-stijl en test wijzigingen ook voor mobiel.
- Voer bij codewijzigingen minstens gerichte tests en `manage.py check` uit.
- Commit geen lokale database, tijdelijke Office-bestanden of geheime gegevens.
- Voltooide wijzigingen worden standaard met de relevante bestanden gecommit en naar `main` gepusht, zodat Render ze kan uitrollen. Niet pushen wanneer de gebruiker expliciet zegt dat iets lokaal moet blijven.
- Werk na een functionele wijziging de relevante projectdocumentatie bij volgens `docs/project/DEVELOPMENT.md`.

`CODEX_CONTEXT.md` is een historische overdracht en niet meer de primaire bron.
