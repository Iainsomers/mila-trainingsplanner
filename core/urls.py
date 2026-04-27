from django.urls import path

# Import views explicitly to avoid any name collisions via views/__init__.py
from core.views.coach import (
    dashboard_view,
    settings_view,
    coach_console_view,
    coach_plans_view,
    coach_plan_create_view,
    coach_plan_edit_view,
    coach_plan_delete_view,
    coach_athletes_view,
    coach_athlete_create_view,
    coach_athlete_edit_view,
    coach_groups_view,
    coach_group_create_view,
    coach_group_edit_view,
    coach_assignments_view,
    coach_assignment_edit_view,
)

from core.views.calendar import (
    calendar_view,
    calendar_test,
    week_phase_set,
    athlete_week_phase_set,
    athlete_year_calendar_view,
)

from core.views.legacy_targets import (
    plan_targets_view,
    plan_targets_modal,
)

from core.views.slots import (
    slot_open,
    slot_detail,
    slot_modal,
    slot_copy,
    slot_paste,
    slot_reset_override,
    slot_clipboard_clear,
    week_copy,
    week_paste,
    week_clipboard_clear,
)

from core.views.stats_debug import stats_debug_view


urlpatterns = [
    # Dashboard / settings
    path("", dashboard_view, name="dashboard"),
    path("settings/", settings_view, name="settings"),

    # Coach console
    path("coach/", coach_console_view, name="coach_console"),

    # Coach: Plans CRUD
    path("coach/plans/", coach_plans_view, name="coach_plans"),
    path("coach/plans/new/", coach_plan_create_view, name="coach_plan_create"),
    path("coach/plans/<int:plan_id>/edit/", coach_plan_edit_view, name="coach_plan_edit"),
    path("coach/plans/<int:plan_id>/delete/", coach_plan_delete_view, name="coach_plan_delete"),

    # Coach: Athletes CRUD
    path("coach/athletes/", coach_athletes_view, name="coach_athletes"),
    path("coach/athletes/new/", coach_athlete_create_view, name="coach_athlete_create"),
    path("coach/athletes/<int:athlete_id>/edit/", coach_athlete_edit_view, name="coach_athlete_edit"),

    # Coach: Groups CRUD
    path("coach/groups/", coach_groups_view, name="coach_groups"),
    path("coach/groups/new/", coach_group_create_view, name="coach_group_create"),
    path("coach/groups/<int:group_id>/edit/", coach_group_edit_view, name="coach_group_edit"),

    # Coach: Assignments (editable)
    path("coach/assignments/", coach_assignments_view, name="coach_assignments"),
    path("coach/assignments/<int:plan_id>/edit/", coach_assignment_edit_view, name="coach_assignment_edit"),

    # Calendar
    path("calendar/", calendar_view, name="calendar"),
    path("calendar-test/", calendar_test, name="calendar_test"),

    # Athlete console
    path("athlete/year/", athlete_year_calendar_view, name="athlete_year_calendar"),

    # ✅ Week phase (server-side, HTMX)
    path("week-phase/<int:y>/<int:m>/<int:d>/", week_phase_set, name="week_phase_set"),
    path("athlete-week-phase/<int:y>/<int:m>/<int:d>/", athlete_week_phase_set, name="athlete_week_phase_set"),

    # Plan targets (legacy; may be removed later)
    path("plans/<int:plan_id>/targets/", plan_targets_view, name="plan_targets"),
    path("plans/<int:plan_id>/targets-modal/", plan_targets_modal, name="plan_targets_modal"),

    # Slot endpoints
    path("slot-open/<int:y>/<int:m>/<int:d>/<int:slot_index>/", slot_open, name="slot_open"),
    path("slot/<int:slot_id>/", slot_detail, name="slot_detail"),
    path("slot-modal/<int:yyyy>/<int:mm>/<int:dd>/<int:slot_index>/", slot_modal, name="slot_modal"),
    path("slot-copy/<int:yyyy>/<int:mm>/<int:dd>/<int:slot_index>/", slot_copy, name="slot_copy"),
    path("slot-paste/<int:yyyy>/<int:mm>/<int:dd>/<int:slot_index>/", slot_paste, name="slot_paste"),
    path("slot-reset-override/<int:yyyy>/<int:mm>/<int:dd>/<int:slot_index>/", slot_reset_override, name="slot_reset_override"),
    path("slot-clipboard-clear/", slot_clipboard_clear, name="slot_clipboard_clear"),

    # Week copy/paste (BASE only)
    path("week-copy/<int:yyyy>/<int:mm>/<int:dd>/", week_copy, name="week_copy"),
    path("week-paste/<int:yyyy>/<int:mm>/<int:dd>/", week_paste, name="week_paste"),
    path("week-clipboard-clear/", week_clipboard_clear, name="week_clipboard_clear"),

    # Stats debug
    path("stats-debug/", stats_debug_view, name="stats_debug"),
]
