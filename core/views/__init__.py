# core/views/__init__.py
# Explicit exports to avoid name collisions from import *

# coach
from .coach import (
    dashboard_view,
    coach_console_view,
    settings_view,
    coach_plans_view,
    coach_plan_create_view,
    coach_plan_edit_view,
    coach_athletes_view,
    coach_athlete_create_view,
    coach_athlete_edit_view,
    coach_groups_view,
    coach_group_create_view,
    coach_group_edit_view,
    coach_assignments_view,
    coach_assignment_edit_view,
)

# calendar
from .calendar import (
    calendar_view,
    calendar_test,
)

# slots
from .slots import (
    week_copy,
    week_paste,
    week_clipboard_clear,
    slot_detail,
    slot_open,
    slot_copy,
    slot_paste,
    slot_reset_override,
    slot_clipboard_clear,
    slot_modal,
)

# legacy targets (only what urls.py uses)
from .legacy_targets import (
    plan_targets_view,
    plan_targets_modal,
)
