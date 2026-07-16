from django.db import models
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.conf import settings


DEFAULT_ZONE_SPEED_MPS = {
    "1": 2.8,
    "2": 3.1,
    "3": 3.4,
    "4": 3.8,
    "5": 4.2,
    "6": 4.6,
}


def default_zone_speed_mps():
    # callable default for JSONField
    return dict(DEFAULT_ZONE_SPEED_MPS)


class CoachSettings(models.Model):
    """
    Persistente coach-voorkeuren (per ingelogde User).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coach_settings",
    )

    # Calendar
    show_all_zones = models.BooleanField(default=True)
    highlight_current_week = models.BooleanField(default=True)
    calendar_show_only_core = models.BooleanField(default=True)

    # ✅ Weekcolors Y/N (als No: toon alleen woord, geen kleur)
    weekcolors_enabled = models.BooleanField(default=True)

    # Coach Console
    zone_input_unit = models.CharField(max_length=10, default="pace")

    # Trainingsbuilder (Core + Alternative zijn altijd zichtbaar)
    tb_show_wu = models.BooleanField(default=True)
    tb_show_mob = models.BooleanField(default=True)
    tb_show_sprint = models.BooleanField(default=True)
    tb_show_core2 = models.BooleanField(default=True)
    tb_show_cd = models.BooleanField(default=True)

    # Default WU/CD settings for newly created athletes.
    auto_wucd_enabled = models.BooleanField(default=False)
    auto_wu_m = models.PositiveIntegerField(default=0)
    auto_cd_m = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"CoachSettings({self.user_id})"


class Athlete(models.Model):
    """
    Minimal Athlete model for coach-only phase.
    Later we can link Athlete <-> User for athlete login.
    """
    GENDER_CHOICES = [
        ("M", "Man"),
        ("V", "Vrouw"),
        ("X", "Anders"),
    ]

    ZONE_METHOD_CHOICES = [
        ("manual", "Manual"),
        ("pb", "PB"),
        ("hr", "HR"),
        ("lactate", "Lactate"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="owned_athletes",
    )

    is_private = models.BooleanField(default=False)

    name = models.CharField(max_length=120, unique=True)
    birth_year = models.PositiveIntegerField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    vdot = models.FloatField(null=True, blank=True)

    zone_method = models.CharField(
        max_length=20,
        choices=ZONE_METHOD_CHOICES,
        default="manual",
    )

    view_weeks_ahead = models.IntegerField(default=2)

    training_reports_enabled = models.BooleanField(default=True)
    week_report_enabled = models.BooleanField(default=False)
    daily_vitals_enabled = models.BooleanField(default=False)

    auto_wucd_enabled = models.BooleanField(default=False)
    auto_wu_m = models.PositiveIntegerField(default=0)
    auto_cd_m = models.PositiveIntegerField(default=0)

    zone_speed_mps = models.JSONField(
        default=default_zone_speed_mps,
        blank=True,
    )

    pr_800_s = models.FloatField(null=True, blank=True)
    pr_1500_s = models.FloatField(null=True, blank=True)
    pr_3000_s = models.FloatField(null=True, blank=True)
    pr_5000_s = models.FloatField(null=True, blank=True)
    pr_10000_s = models.FloatField(null=True, blank=True)
    pr_tm_s = models.FloatField(null=True, blank=True)
    pr_thm_s = models.FloatField(null=True, blank=True)
    pr_400_s = models.FloatField(null=True, blank=True)
    target_pr_800_s = models.FloatField(null=True, blank=True)
    target_pr_1500_s = models.FloatField(null=True, blank=True)
    target_pr_3000_s = models.FloatField(null=True, blank=True)
    target_pr_5000_s = models.FloatField(null=True, blank=True)
    target_pr_10000_s = models.FloatField(null=True, blank=True)
    target_pr_tm_s = models.FloatField(null=True, blank=True)
    target_pr_thm_s = models.FloatField(null=True, blank=True)
    target_pr_400_s = models.FloatField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name

    def get_zone_speed_mps(self) -> dict:
        data = self.zone_speed_mps if isinstance(self.zone_speed_mps, dict) else {}
        out = {}
        for z, dv in DEFAULT_ZONE_SPEED_MPS.items():
            v = data.get(z, dv)
            try:
                out[z] = float(v)
            except (TypeError, ValueError):
                out[z] = float(dv)
        return out


class Group(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="owned_groups",
    )

    name = models.CharField(max_length=120, unique=True)
    athletes = models.ManyToManyField(Athlete, related_name="groups", blank=True)

    auto_wucd_enabled = models.BooleanField(default=False)
    auto_wu_m = models.PositiveIntegerField(default=0)
    auto_cd_m = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return self.name


class TrainingPlan(models.Model):
    PLAN_KIND_LEGACY = "legacy"
    PLAN_KIND_TRAINER = "trainer"
    PLAN_KIND_CHOICES = [
        (PLAN_KIND_LEGACY, "Legacy plan"),
        (PLAN_KIND_TRAINER, "Trainer planning"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="owned_training_plans",
    )

    is_private = models.BooleanField(default=False)

    name = models.CharField(max_length=120, unique=True)

    plan_kind = models.CharField(
        max_length=20,
        choices=PLAN_KIND_CHOICES,
        default=PLAN_KIND_LEGACY,
        db_index=True,
    )

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    athletes = models.ManyToManyField(
        Athlete,
        through="PlanMembership",
        related_name="plans",
        blank=True,
    )

    groups = models.ManyToManyField(
        Group,
        related_name="plans",
        blank=True,
    )

    auto_wucd_enabled = models.BooleanField(default=False)
    auto_wu_m = models.PositiveIntegerField(default=0)
    auto_cd_m = models.PositiveIntegerField(default=0)

    week_phases_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def targeted_athlete_ids(self) -> set[int]:
        ids = set(self.athletes.values_list("id", flat=True))
        ids |= set(self.groups.values_list("athletes__id", flat=True))
        ids.discard(None)
        return ids


class PlanWeekPhase(models.Model):
    PHASE_CHOICES = [
        ("", "—"),
        ("recovery", "Recovery"),
        ("aerobe", "Aerobe"),
        ("specific", "Specific"),
        ("intense", "Intense"),
        ("taper", "Taper"),
    ]

    plan = models.ForeignKey(
        TrainingPlan,
        on_delete=models.CASCADE,
        related_name="week_phases",
    )
    week_start = models.DateField()
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "week_start"],
                name="unique_week_phase_per_plan_and_week_start",
            )
        ]
        ordering = ["plan__name", "week_start"]

    def __str__(self) -> str:
        p = self.phase or ""
        return f"{self.plan} · {self.week_start} · {p or '—'}"


class AthleteWeekPhaseOverride(models.Model):
    PHASE_CHOICES = PlanWeekPhase.PHASE_CHOICES

    plan = models.ForeignKey(
        TrainingPlan,
        on_delete=models.CASCADE,
        related_name="athlete_week_phase_overrides",
    )
    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="week_phase_overrides",
    )
    week_start = models.DateField()
    phase = models.CharField(max_length=20, choices=PHASE_CHOICES, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "athlete", "week_start"],
                name="unique_week_phase_override_per_plan_athlete_week",
            )
        ]
        ordering = ["plan__name", "athlete__name", "week_start"]

    def __str__(self) -> str:
        p = self.phase or ""
        return f"{self.plan} · {self.athlete} · {self.week_start} · {p or '—'}"


def get_default_plan_id() -> int | None:
    try:
        plan = TrainingPlan.objects.filter(name="Default").only("id").first()
        return plan.id if plan else None
    except Exception:
        return None


class PlanMembership(models.Model):
    plan = models.ForeignKey(
        TrainingPlan,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="plan_memberships",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "athlete"],
                name="unique_membership_per_plan_and_athlete",
            )
        ]
        ordering = ["plan__name", "athlete__name"]

    def __str__(self) -> str:
        return f"{self.plan} – {self.athlete}"


class AthleteBasePlanningBlock(models.Model):
    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="base_planning_blocks",
    )

    label = models.CharField(max_length=120, blank=True, default="")
    start_month = models.PositiveSmallIntegerField()
    start_day = models.PositiveSmallIntegerField()
    end_month = models.PositiveSmallIntegerField()
    end_day = models.PositiveSmallIntegerField()
    sort_order = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["athlete__name", "sort_order", "start_month", "start_day", "id"]

    def __str__(self) -> str:
        label = self.label or f"{self.start_day:02d}-{self.start_month:02d} t/m {self.end_day:02d}-{self.end_month:02d}"
        return f"{self.athlete} - {label}"

    @property
    def start_md(self) -> str:
        return f"{self.start_day:02d}-{self.start_month:02d}"

    @property
    def end_md(self) -> str:
        return f"{self.end_day:02d}-{self.end_month:02d}"


class AthleteBasePlanningSlot(models.Model):
    MODE_REST = "rest"
    MODE_TRAINING = "training"
    MODE_TRAINER = "trainer"
    MODE_CHOICES = [
        (MODE_REST, "Rust"),
        (MODE_TRAINING, "Training"),
        (MODE_TRAINER, "Groep"),
    ]

    WEEKDAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    block = models.ForeignKey(
        AthleteBasePlanningBlock,
        on_delete=models.CASCADE,
        related_name="slots",
    )
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES)
    slot_index = models.PositiveSmallIntegerField(choices=[(1, "AM"), (2, "PM")])
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_REST)
    trainer_plan = models.ForeignKey(
        TrainingPlan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="base_planning_slots",
    )
    training_text = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["block", "weekday", "slot_index"],
                name="unique_base_planning_slot_per_block_weekday_slot",
            )
        ]
        ordering = ["block__sort_order", "weekday", "slot_index"]

    def __str__(self) -> str:
        return f"{self.block} - {self.weekday}/{self.slot_index}: {self.mode}"


class TrainingSlot(models.Model):
    SLOT_CHOICES = [(1, "Slot 1"), (2, "Slot 2")]

    date = models.DateField()
    slot_index = models.PositiveSmallIntegerField(choices=SLOT_CHOICES)

    plan = models.ForeignKey(
        TrainingPlan,
        on_delete=models.CASCADE,
        related_name="slots",
        default=get_default_plan_id,
    )

    athlete = models.ForeignKey(
        Athlete,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="personal_slots",
    )

    athletes = models.ManyToManyField(Athlete, blank=True, related_name="training_slots")
    groups = models.ManyToManyField(Group, blank=True, related_name="training_slots")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "date", "slot_index"],
                condition=Q(athlete__isnull=True),
                name="unique_base_slot_per_plan_day_and_slot",
            ),
            models.UniqueConstraint(
                fields=["plan", "athlete", "date", "slot_index"],
                condition=Q(athlete__isnull=False),
                name="unique_override_slot_per_plan_athlete_day_and_slot",
            ),
        ]
        ordering = ["-date", "slot_index"]

    def __str__(self) -> str:
        if self.athlete_id:
            return f"{self.plan} · {self.athlete} · {self.date} – slot {self.slot_index}"
        return f"{self.plan} · {self.date} – slot {self.slot_index}"

    def core_text(self) -> str:
        cores = self.segments.filter(type="CORE").order_by("order", "id")
        parts = [seg.text.strip() for seg in cores if seg.text and seg.text.strip()]
        return " // ".join(parts)

    def targeted_athlete_ids(self) -> set[int]:
        if self.athlete_id:
            return {int(self.athlete_id)}
        return self.plan.targeted_athlete_ids()


class TrainingSegment(models.Model):
    TYPE_CHOICES = [
        ("WU", "WU"),
        ("CORE", "Core"),
        ("CORE2", "2nd Core"),
        ("ALT", "Alternative"),
        ("MOB", "Mob/Tech"),
        ("SPR", "Sprint"),
        ("CD", "CD"),
    ]

    ZONE_CHOICES = [
        ("1", "Zone 1"),
        ("2", "Zone 2"),
        ("3", "Zone 3"),
        ("4", "Zone 4"),
        ("5", "Zone 5"),
        ("6", "Zone 6"),
    ]

    SPECIAL_CHOICES = [
        ("", "—"),
        ("STRENGTH", "Strength"),
        ("RACE", "Race"),
        ("IMPORTANT_RACE", "Important Race"),
    ]

    T_TYPE_CHOICES = [
        ("", "—"),
        ("800", "T800"),
        ("1500", "T1500"),
        ("3000", "T3000"),
        ("5000", "T5000"),
        ("10000", "T10000"),
    ]


    slot = models.ForeignKey(
        TrainingSlot, on_delete=models.CASCADE, related_name="segments"
    )

    order = models.PositiveIntegerField(default=1)

    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    zone = models.CharField(max_length=1, choices=ZONE_CHOICES, default="1")

    special = models.CharField(
        max_length=20, choices=SPECIAL_CHOICES, blank=True, default=""
    )

    t_type = models.CharField(
        max_length=10, choices=T_TYPE_CHOICES, blank=True, default=""
    )

    reps = models.PositiveIntegerField(default=1)
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    duration_s = models.PositiveIntegerField(null=True, blank=True)

    norm_distance_m = models.PositiveIntegerField(null=True, blank=True)

    text = models.TextField(blank=True)

    parse_ok = models.BooleanField(default=False)
    parse_message = models.CharField(max_length=300, blank=True, default="")
    parsed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        extras = []
        if self.t_type:
            extras.append(f"T{self.t_type}")
        if self.special:
            extras.append(self.special)
        extra = f", {', '.join(extras)}" if extras else ""
        return f"{self.slot} – {self.get_type_display()} (Z{self.zone}{extra})"

    @property
    def total_distance_m(self) -> int:
        if not self.distance_m:
            return 0
        return int(self.reps) * int(self.distance_m)

    def clean(self):
        super().clean()
        if self.type in ("CORE", "CORE2", "ALT") and not (self.text or "").strip():
            raise ValidationError("Dit segment moet een tekst hebben (bijv. '6×1000m' of een alternatief).")


class TrainingLog(models.Model):
    slot = models.ForeignKey(TrainingSlot, on_delete=models.CASCADE, related_name="logs")
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name="logs")

    completed = models.BooleanField(default=False)
    rpe = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["slot", "athlete"],
                name="unique_log_per_slot_and_athlete",
            )
        ]
        ordering = ["-slot__date", "slot__slot_index", "athlete__name"]

    def __str__(self) -> str:
        return f"Log: {self.athlete} – {self.slot}"

    def clean(self):
        super().clean()

        if not self.slot_id or not self.athlete_id:
            returns

        targeted = self.slot.targeted_athlete_ids()
        if targeted and self.athlete_id not in targeted:
            raise ValidationError("Deze atleet hoort niet bij de doelgroep van dit trainingsslot.")


class SavedTrainingTemplate(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="saved_training_templates",
    )

    name = models.CharField(max_length=120)
    text = models.TextField()
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name", "id"]

    def __str__(self) -> str:
        return self.name


class RaceEvent(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="race_events",
    )

    name = models.CharField(max_length=160)
    date = models.DateField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "name", "id"]

    def __str__(self) -> str:
        return f"{self.name} · {self.date}"


class RaceEventDistance(models.Model):
    DISTANCE_CHOICES = [
        ("300", "300m"),
        ("400", "400m"),
        ("600", "600m"),
        ("800", "800m"),
        ("1000", "1000m"),
        ("1500", "1500m"),
        ("1609", "1609m"),
        ("3000", "3000m"),
        ("5000", "5000m"),
        ("10000", "10000m"),
        ("1000S", "1000m S"),
        ("1500S", "1500m S"),
        ("2000S", "2000m S"),
        ("3000S", "3000m S"),
        ("custom", "x meter"),
    ]

    race = models.ForeignKey(
        RaceEvent,
        on_delete=models.CASCADE,
        related_name="distances",
    )
    distance = models.CharField(max_length=20, choices=DISTANCE_CHOICES)
    custom_distance_m = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["race__date", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["race", "distance", "custom_distance_m"],
                name="unique_race_event_distance",
            )
        ]

    @property
    def display_distance(self) -> str:
        if self.distance == "custom" and self.custom_distance_m:
            return f"{self.custom_distance_m}m"
        return dict(self.DISTANCE_CHOICES).get(self.distance, self.distance)

    def __str__(self) -> str:
        return f"{self.race} · {self.display_distance}"

class RaceEntry(models.Model):
    race_distance = models.ForeignKey(
        RaceEventDistance,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name="race_entries",
    )

    coach_selected = models.BooleanField(default=False)
    athlete_selected = models.BooleanField(default=False)
    target_selected = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["race_distance__race__date", "race_distance__id", "athlete__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["race_distance", "athlete"],
                name="unique_race_entry_per_distance_athlete",
            )
        ]

    def __str__(self) -> str:
        flags = []
        if self.coach_selected:
            flags.append("coach")
        if self.athlete_selected:
            flags.append("athlete")
        if self.target_selected:
            flags.append("target")
        suffix = ", ".join(flags) if flags else "—"
        return f"{self.race_distance} · {self.athlete} · {suffix}"


# =============================
# NEW: Coach access (trainer sharing)
# =============================
class CoachAccess(models.Model):
    """
    Defines that 'grantee' (trainer) has access to all data owned by 'owner'.
    Example:
        owner = trainer B
        grantee = trainer A

    => Trainer A can see data of trainer B
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shared_with_others",
    )

    grantee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_to_other_coaches",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "grantee"],
                name="unique_coach_access",
            )
        ]

    def __str__(self):
        return f"{self.grantee} can access {self.owner}"

class AthleteWeekReport(models.Model):
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name="week_reports")
    week_start = models.DateField()

    comm_athlete = models.TextField(blank=True, default="")
    comm_trainer = models.TextField(blank=True, default="")
    match_report = models.TextField(blank=True, default="")
    injuries = models.TextField(blank=True, default="")

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_week_reports",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["athlete", "week_start"],
                name="unique_week_report_per_athlete_week",
            )
        ]
        ordering = ["-week_start", "athlete__name"]

    def __str__(self):
        return f"{self.athlete} - week {self.week_start}"


class AthleteDailyVital(models.Model):
    date = models.DateField()
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name="daily_vitals")

    sleep_hours = models.FloatField(null=True, blank=True)
    sleep_quality = models.PositiveSmallIntegerField(null=True, blank=True)
    morning_hr = models.PositiveSmallIntegerField(null=True, blank=True)
    hrv = models.PositiveSmallIntegerField(null=True, blank=True)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_daily_vitals",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "athlete"],
                name="unique_daily_vitals_per_day_athlete",
            )
        ]
        ordering = ["-date", "athlete__name"]

    def __str__(self):
        return f"{self.athlete} - vitals {self.date}"


class AthleteDayComment(models.Model):
    date = models.DateField()
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name="day_comments")
    text = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_comments",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "athlete"],
                name="unique_comment_per_day_athlete",
            )
        ]

    def __str__(self):
        return f"{self.athlete} - {self.date}"


class AthleteDayCheck(models.Model):
    STATUS_NONE = ""
    STATUS_DONE_AS_PLANNED = "done_as_planned"
    STATUS_TOO_HARD_FAST = "too_hard_fast"
    STATUS_ADJUSTED_OK = "adjusted_ok"
    STATUS_LIGHTER_SLOWER = "lighter_slower"
    STATUS_NOT_DONE = "not_done"

    STATUS_CHOICES = [
        (STATUS_NONE, "—"),
        (STATUS_DONE_AS_PLANNED, "✓ Training done as planned"),
        (STATUS_TOO_HARD_FAST, "↑ Too much / too fast"),
        (STATUS_ADJUSTED_OK, "✓ Adjusted, not harder or easier"),
        (STATUS_LIGHTER_SLOWER, "↓ Lighter / slower"),
        (STATUS_NOT_DONE, "✕ Training not done"),
    ]

    date = models.DateField()
    slot_index = models.PositiveSmallIntegerField(default=1)
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name="day_checks")
    checked = models.BooleanField(default=False)
    rpe = models.PositiveSmallIntegerField(null=True, blank=True)
    comment = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        blank=True,
        default=STATUS_NONE,
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="updated_checks",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "athlete", "slot_index"],
                name="unique_check_per_day_athlete_slot",
            )
        ]

    @property
    def effective_status(self):
        if self.status:
            return self.status
        if self.checked:
            return self.STATUS_DONE_AS_PLANNED
        return self.STATUS_NONE

    def __str__(self):
        return f"{self.athlete} - {self.date} ({self.effective_status or '—'})"
