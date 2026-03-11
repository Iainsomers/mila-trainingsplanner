# TrainPlan/models2.py

from django.db import models
from django.core.exceptions import ValidationError


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

    name = models.CharField(max_length=120, unique=True)
    birth_year = models.PositiveIntegerField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    vdot = models.FloatField(null=True, blank=True)

    def __str__(self) -> str:
        return self.name


class Group(models.Model):
    name = models.CharField(max_length=120, unique=True)
    athletes = models.ManyToManyField(Athlete, related_name="groups", blank=True)

    def __str__(self) -> str:
        return self.name


class TrainingSlot(models.Model):
    """
    Eén vakje in de kalender:
    - date: de dag
    - slot_index: 1 of 2 (twee vakjes per dag)
    - doelgroep: athletes en/of groups (voor wie geldt dit plan)
    """
    SLOT_CHOICES = [(1, "Slot 1"), (2, "Slot 2")]

    date = models.DateField()
    slot_index = models.PositiveSmallIntegerField(choices=SLOT_CHOICES)

    # doelgroep (optioneel in coach-only; later kunnen we dit verplicht maken)
    athletes = models.ManyToManyField(Athlete, blank=True, related_name="training_slots")
    groups = models.ManyToManyField(Group, blank=True, related_name="training_slots")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "slot_index"],
                name="unique_trainingslot_per_day_and_slot",
            )
        ]
        ordering = ["-date", "slot_index"]

    def __str__(self) -> str:
        return f"{self.date} – slot {self.slot_index}"

    def core_text(self) -> str:
        """
        Tekst die in de kalender getoond wordt:
        = tekst van het eerste CORE-segment (op order, dan id).
        Als er geen Core-segment is: lege string.
        """
        core = self.segments.filter(type="CORE").order_by("order", "id").first()
        return core.text.strip() if core and core.text else ""

    def targeted_athlete_ids(self) -> set[int]:
        """
        Helper: alle atleten die 'bij dit slot horen' via directe selectie en via groepen.
        (Handig voor logs en later permissions.)
        """
        ids = set(self.athletes.values_list("id", flat=True))
        ids |= set(self.groups.values_list("athletes__id", flat=True))
        ids.discard(None)
        return ids


class TrainingSegment(models.Model):
    """
    Segmenten die onder Tab 'Plan' vallen.
    In het slot kunnen meerdere segmenten staan (WU, CORE, SPR, CD, etc.)
    """
    TYPE_CHOICES = [
        ("WU", "WU"),
        ("CORE", "Core"),
        ("SPR", "Sprints"),
        ("CD", "CD"),
        # later uitbreidbaar...
    ]

    ZONE_CHOICES = [
        ("1", "Zone 1"),
        ("2", "Zone 2"),
        ("3", "Zone 3"),
        ("4", "Zone 4"),
        ("5", "Zone 5"),
        ("6", "Zone 6"),
    ]

    slot = models.ForeignKey(
        TrainingSlot, on_delete=models.CASCADE, related_name="segments"
    )

    # volgorde binnen de training (we tonen dit niet in de UI, maar het is handig voor sortering)
    order = models.PositiveIntegerField(default=1)

    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    zone = models.CharField(max_length=1, choices=ZONE_CHOICES, default="1")

    reps = models.PositiveIntegerField(default=1)
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    duration_s = models.PositiveIntegerField(null=True, blank=True)

    # Vrij tekstveld: bij CORE komt hier bv. "6×1000m" in, en dát tonen we in de kalender.
    text = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return f"{self.slot} – {self.get_type_display()} (Z{self.zone})"

    @property
    def total_distance_m(self) -> int:
        if not self.distance_m:
            return 0
        return int(self.reps) * int(self.distance_m)

    def clean(self):
        super().clean()
        # Kleine sanity check: voorkom negatieve/lege onzin (reps is PositiveIntegerField)
        if self.type == "CORE" and not (self.text or "").strip():
            # In de uiteindelijke popup willen we dit echt afdwingen.
            # Dit helpt alvast bij admin/manual edits.
            raise ValidationError("CORE-segment moet een tekst hebben (bijv. '6×1000m').")


class TrainingLog(models.Model):
    """
    Log per atleet per slot (coach-only nu; later atleten zelf invullen).
    Atleten mogen later alleen hun eigen log zien.
    """
    slot = models.ForeignKey(TrainingSlot, on_delete=models.CASCADE, related_name="logs")
    athlete = models.ForeignKey(Athlete, on_delete=models.CASCADE, related_name="logs")

    completed = models.BooleanField(default=False)
    rpe = models.PositiveIntegerField(null=True, blank=True)  # 1–10
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
            return

        # Als er een doelgroep is ingesteld (athletes/groups), moet deze athlete daarin zitten.
        # Als doelgroep leeg is, laten we het toe (coach-only fase is flexibel).
        targeted = self.slot.targeted_athlete_ids()
        if targeted and self.athlete_id not in targeted:
            raise ValidationError("Deze atleet hoort niet bij de doelgroep van dit trainingsslot.")
