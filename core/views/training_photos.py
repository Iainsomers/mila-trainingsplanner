from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from core.models import TrainingPhoto, TrainingSegment, TrainingSlot, Athlete
from .athlete_identity import _athlete_for_user, _is_ayc_coach_user
from .common import _filter_owned


def prepare_photo(upload):
    if upload.size > 15 * 1024 * 1024:
        raise ValueError("Each photo must be smaller than 15 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                if source.width * source.height > 40_000_000:
                    raise ValueError("Photo is too large. Choose a smaller image.")
                source.seek(0)
                image = ImageOps.exif_transpose(source).convert('RGB')
                image.thumbnail((2200, 2200))
                full = BytesIO()
                image.save(full, format='JPEG', quality=85, optimize=True)
                image.thumbnail((240, 240))
                thumb = BytesIO()
                image.save(thumb, format='JPEG', quality=80)
                return {'image': full.getvalue(), 'thumbnail': thumb.getvalue()}
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("Choose a valid photo (JPEG, PNG or WebP).")


@login_required
@require_GET
def training_photo(request, segment_id, photo_id):
    segment = get_object_or_404(TrainingSegment.objects.select_related('slot__plan'), pk=segment_id, type='MOB')
    if str(photo_id) not in segment.photo_ids:
        raise Http404
    return _serve_photo(request, segment.slot, photo_id)


@login_required
@require_GET
def training_slot_photo(request, slot_id, photo_id):
    slot = get_object_or_404(TrainingSlot.objects.select_related("plan"), pk=slot_id)
    if not any(str(photo_id) in segment.photo_ids for segment in slot.segments.filter(type__in=("MOB", "CORE2"))):
        raise Http404
    return _serve_photo(request, slot, photo_id)


def _serve_photo(request, slot, photo_id):
    if _is_ayc_coach_user(request.user):
        if slot.athlete_id:
            allowed = _filter_owned(Athlete.objects.all(), request.user).filter(pk=slot.athlete_id).exists()
        else:
            allowed = _filter_owned(type(slot.plan).objects.all(), request.user).filter(pk=slot.plan_id).exists()
    else:
        athlete = _athlete_for_user(request.user)
        # A trainer-plan assignment is specific to the effective base block,
        # weekday and AM/PM slot, rather than every workout in that plan.
        from .slots import _base_planning_slot_for_slot_reset
        base = _base_planning_slot_for_slot_reset(athlete, slot.date, slot.slot_index) if athlete else None
        allowed = bool(athlete and (
            slot.athlete_id == athlete.id or (
                slot.athlete_id is None and (
                    athlete.id in slot.plan.targeted_athlete_ids() or
                    (base and base.trainer_plan_id == slot.plan_id)
                )
            )))
    if not allowed:
        raise Http404
    photo = get_object_or_404(TrainingPhoto, pk=photo_id)
    response = HttpResponse(bytes(photo.thumbnail if request.GET.get('thumb') else photo.image), content_type='image/jpeg')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Disposition'] = 'inline; filename="training.jpg"'
    return response


def copy_photo_ids(request, values):
    """Validate reference ownership even for client-supplied week clipboards."""
    import uuid
    keys = []
    for value in values if isinstance(values, list) else []:
        try:
            keys.append(uuid.UUID(str(value)))
        except (ValueError, TypeError):
            continue
    available = {str(key) for key in _filter_owned(TrainingPhoto.objects.all(), request.user).filter(pk__in=keys).values_list('pk', flat=True)}
    return [str(key) for key in keys if str(key) in available][:5]
