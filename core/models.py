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

    zone_speed_mps = models.JSONField(
        default=default_zone_speed_mps,
        blank=True,
    )

    pr_800_s = models.FloatField(null=True, blank=True)
    pr_1500_s = models.FloatField(null=True, blank=True)
    pr_3000_s = models.FloatField(null=True, blank=True)
    pr_5000_s = models.FloatField(null=True, blank=True)
    pr_10000_s = models.FloatField(null=True, blank=True)

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

    def __str__(self) -> str:
        return self.name


class TrainingPlan(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="owned_training_plans",
    )

    is_private = models.BooleanField(default=False)

    name = models.CharField(max_length=120, unique=True)

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

    text = models.CharField(max_length=300, blank=True)

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