"""Opt-in Garmin E: free conversation over measured, server-owned recordings."""
from copy import copy, deepcopy
import hashlib
import json
import re
from time import monotonic

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db.models import Q
from django.http import JsonResponse, QueryDict
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.models import Athlete, GarminEConversation
from core.garmin_e import ask_model, checked_proposal, lap_facts
from core.views.garmin import ai_allowed, fit_ai_allowed


def preview_digest(fields, loads):
    def canonical(value):
        if isinstance(value,dict):
            return {key:canonical(item) for key,item in value.items()}
        if isinstance(value,list):
            return [canonical(item) for item in value]
        # Browsers do not preserve Python's 38 versus 38.0 spelling.
        # Normalize only equal integral numbers; never round measured fractions.
        if isinstance(value,float) and value.is_integer():
            return int(value)
        return value
    return hashlib.sha256(json.dumps(canonical([fields,loads]),
        sort_keys=True,separators=(",",":")).encode()).hexdigest()


@login_required
@require_http_methods(["GET","POST"])
def garmin_type_e_ayc_view(request):
    from core.views.coach import _filter_owned, _athlete_for_user, garmin_type_c_ayc_view
    athlete_id = request.GET.get("athlete","")
    if request.user.is_staff or request.user.is_superuser:
        athlete = _filter_owned(Athlete.objects.all(),request).filter(pk=athlete_id).first() if athlete_id.isdigit() else None
    else:
        athlete = _athlete_for_user(request.user)
        if athlete and str(athlete.pk) != athlete_id:
            athlete = None
    if not athlete:
        return JsonResponse({"ok":False,"message":"Athlete not found.","results":[]},status=404)
    if not athlete.garmin_model_e_enabled:
        return JsonResponse({"ok":False,"message":"Garmin E is not enabled for this athlete.","results":[]},status=403)
    GarminEConversation.objects.filter(user=request.user,updated_at__lt=timezone.now()-timezone.timedelta(days=7)).delete()
    # The measured C reader is reused solely to decode recordings, never its chat.
    measured_request = copy(request)
    measured_request.method = "GET"
    measured_request.GET = QueryDict("",mutable=True)
    for key in ("athlete","date"):
        measured_request.GET[key] = request.GET.get(key,"")
    measured_request.GET["preview"] = "measured"
    measured_request.POST = QueryDict("")
    response = garmin_type_c_ayc_view(measured_request)
    if response.status_code != 200:
        return response
    data = json.loads(response.content)
    results = data.get("results",[])
    message = None
    if request.method == "POST":
        try:
            incoming = json.loads(request.POST.get("chat",""))
            message = incoming[-1]["content"]
            if (len(request.POST.get("chat","")) > 30000 or incoming[-1]["role"] != "user"
                    or not isinstance(message,str) or not 1 <= len(message.strip()) <= 3000):
                raise ValueError
            message = message.strip()
        except (ValueError,TypeError,KeyError,IndexError):
            return JsonResponse({"ok":False,"message":"Please send a shorter message.","results":[]},status=400)
        results = [s for s in results if s.get("start") == request.GET.get("suggestion_session")]
        if len(results)!=1:
            return JsonResponse({"ok":False,"message":"Activity not found. Reopen Garmin E.","results":[]},status=404)
    push_permission, fit_permission = ai_allowed(athlete), fit_ai_allowed(athlete)
    for session in results:
        permitted = fit_permission if session.get("is_fit_upload") else push_permission
        for part in session.get("parts",[]):
            part["e_usable"] = False
            part["e_zone_basis"] = "auto"
            part.pop("training_alternatives",None)
            if len(session.get("parts",[])) != 1:
                part["ai_structure_status"] = "e_unavailable"
                continue
            fields = part.get("training_fields") or {}
            is_alternative = bool(fields.get("alt"))
            if not ((part.get("watch_loads") and fields.get("main"))
                    or (is_alternative and part.get("alternative_laps"))):
                part["ai_structure_status"] = "e_unavailable"
                continue
            try:
                facts = lap_facts(part)
            except (ValueError,KeyError,TypeError):
                continue
            if not 1 <= len(facts) <= 200:
                part["ai_structure_status"] = "e_unavailable"
                continue
            if not permitted:
                part["ai_structure_status"] = "e_unavailable"
                part["chat_reply"] = "AI consent is required before Garmin E can analyze or discuss this recording."
                continue
            # Keep existing conversation identities stable across save-format fixes.
            fingerprint = hashlib.sha256(json.dumps([facts,[]],
                sort_keys=True,separators=(",",":")).encode()).hexdigest()
            key = "garmin-e:"+hashlib.sha256(str((request.user.pk,athlete.pk,
                session.get("start"),fingerprint)).encode()).hexdigest()
            conversation,_ = GarminEConversation.objects.get_or_create(user=request.user,athlete=athlete,
                activity_key=key.split(":")[1],defaults={"state":{}})
            state = conversation.state or {"history":[],"part":deepcopy(part),"proposal":None,"basis":"auto"}
            if request.GET.get("preview") == "measured" and message is None:
                if state["history"]:
                    session["parts"] = [state["part"]]
                    session["parts"][0]["e_history"] = state["history"]
                else:
                    part["ai_structure_status"] = "e_ready"
                continue
            if message is None and state["history"]:
                session["parts"] = [state["part"]]
                session["parts"][0]["e_history"] = state["history"]
                continue
            acquired = GarminEConversation.objects.filter(pk=conversation.pk).filter(
                Q(busy_until__isnull=True)|Q(busy_until__lt=timezone.now())).update(
                    busy_until=timezone.now()+timezone.timedelta(seconds=70))
            if not acquired:
                return JsonResponse({"ok":False,"message":"Garmin E is still answering. Please wait.","results":[]},status=409)
            conversation.refresh_from_db()
            state = conversation.state or {"history":[],"part":deepcopy(part),"proposal":None,"basis":"auto"}
            try:
                if message and re.fullmatch(r"(?:nee|no|cancel|annuleer)[.!]?",message,re.I):
                    state.pop("pending",None)
                history = state["history"] + [{"role":"user","content":message or
                    "Bekijk deze hele training. Welk patroon zie je? Leg je waarneming uit en geef alleen een voorstel als de laps dit ondersteunen."}]
                compact_requested = bool(is_alternative and any(
                    m["role"]=="user" and re.search(r"compact|notatie|\d+\s*['′].*(?://|[×x*]\s*\()",m["content"],re.I)
                    for m in history))
                current = {"training":state["part"].get("training_fields") if state["part"].get("e_usable") else None,
                           "zone_basis":state["basis"],"hr_limits":athlete.zone_hr_bpm,
                           "activity_type":part.get("alternative_label") if is_alternative else "Running",
                           "alternative_hr_correction":athlete.alternative_hr_correction if is_alternative else None,
                           "requested_presentation":"compact" if compact_requested else None,
                           "checked_assignment":state["proposal"],"pending_confirmation":state.get("pending")}
                deadline = monotonic()+25
                answer = ask_model(facts,history,current)
                proposal = answer.get("proposal")
                basis = answer.get("zone_basis",state["basis"])
                action_requested = bool(message and (
                    re.search(r"\b(?:voorstel|proposal|gebruik|gebruiken|use|usen|apply|toepassen|overnemen|aanpassen|corrigeer|update)\b",message,re.I)
                    or (re.fullmatch(r"(?:ja|yes|ok|doe maar)[.!]?",message,re.I) and state["history"]
                        and re.search(r"voorstel|gebruik|use|apply|toepassen",state["history"][-1]["content"],re.I))))
                wants_update = (action_requested or answer.get("intent") == "update" or
                    (compact_requested and (state.get("proposal") or {}).get("format")!="compact"))
                repair_used = False
                confirmed = bool(state.get("pending") and message and re.fullmatch(
                    r"(?:ja|yes|zeker|ok|doe maar)(?:[.!]|,? (?:klopt|graag|doen|dat klopt))?",
                    message.strip(),re.I))
                if confirmed:
                    proposal = state["pending"]["proposal"]
                    basis = state["pending"]["basis"]
                error, candidate = None, None
                if basis not in {"auto","pace","hr"}:
                    raise ValueError("Garmin E returned an invalid zone basis.")
                if proposal is None and basis != state["basis"]:
                    proposal = state["proposal"]
                if (proposal is None and wants_update) or (compact_requested and isinstance(proposal,dict) and proposal.get("format")!="compact"):
                    remaining = deadline-monotonic()
                    if remaining >= 3:
                        answer = ask_model(facts,history,current,
                            "The user wants the agreed correction in the usable preview, but no proposal was returned. "
                            "Return intent:update and the FULL updated lap assignment, preserving untouched laps. "
                            "For requested compact Alternative notation include proposal.format=compact and presentation targets/zones matching the request and measured evidence. "
                            "If unsupported, explain the concrete measurement mismatch without claiming an update.",
                            timeout=min(20,remaining))
                        proposal = answer.get("proposal")
                        basis = answer.get("zone_basis",state["basis"])
                        repair_used = True
                if proposal is not None:
                    try:
                        if compact_requested and proposal.get("format")!="compact":
                            raise ValueError("De gevraagde compacte notatie ontbreekt nog in de laptoewijzing.")
                        candidate = checked_proposal(part,proposal,athlete=athlete,zone_basis=basis,
                            confirmed_overrun=confirmed or answer.get("confirmation_required") is True)
                    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError) as exc:
                        error = str(exc)
                        # One repair, with the original facts and concrete measurement feedback.
                        remaining = deadline-monotonic()
                        if remaining >= 3 and not repair_used:
                            answer = ask_model(facts,history,current,error,timeout=min(20,remaining))
                            proposal = answer.get("proposal")
                            basis = answer.get("zone_basis",state["basis"])
                            if proposal is not None:
                                try:
                                    if compact_requested and proposal.get("format")!="compact":
                                        raise ValueError("De gevraagde compacte notatie ontbreekt nog in de laptoewijzing.")
                                    candidate = checked_proposal(part,proposal,athlete=athlete,zone_basis=basis,
                                        confirmed_overrun=answer.get("confirmation_required") is True)
                                    error = None
                                except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError) as exc:
                                    error = str(exc)
                reply = answer["reply"]
                if error:
                    reply += "\n\nDit voorstel kan ik nog niet toepassen op de metingen: "+error
                if candidate and answer.get("confirmation_required") is True and not confirmed:
                    state["pending"] = {"proposal":proposal,"basis":basis}
                    candidate = None
                    reply += "\n\nAntwoord ‘ja’ als je dit voorstel wilt gebruiken; de gemeten tijden blijven behouden."
                updated = candidate or deepcopy(state["part"])
                updated.pop("e_history",None)
                if not candidate and wants_update and not state.get("pending"):
                    reply += "\n\nHet bruikbare voorstel hieronder is nog niet bijgewerkt; de vorige gecontroleerde versie staat er nog."
                updated["e_update_note"] = ("Voorstel bijgewerkt vanuit de gemeten laps." if candidate else
                    "Voorstel ongewijzigd; zie het antwoord hierboven." if wants_update else "")
                updated["chat_reply"] = reply
                if candidate:
                    state.pop("pending",None)
                    updated["e_validation"] = signing.dumps(
                        [request.user.pk,athlete.pk,request.GET.get("date"),preview_digest(
                            updated["training_fields"],updated["watch_loads"])],salt="garmin-e-save")
                    state.update(proposal=proposal,basis=basis)
                history.append({"role":"assistant","content":reply})
                state.update(part=updated,history=history[-20:])
                GarminEConversation.objects.filter(pk=conversation.pk).update(state=state,updated_at=timezone.now())
                session["parts"] = [{**updated,"e_history":state["history"]}]
            except (OSError,ValueError,KeyError,TypeError,IndexError):
                updated = deepcopy(state["part"])
                updated["chat_reply"] = "Garmin E kon dit bericht niet afronden. Je laatste gecontroleerde voorstel blijft behouden. Probeer het opnieuw."
                updated["ai_structure_status"] = "e_error"
                session["parts"] = [updated]
            finally:
                GarminEConversation.objects.filter(pk=conversation.pk).update(busy_until=None)
    for session in results:
        for part in session.get("parts",[]):
            part["description_label"] = "Checked E preview" if part.get("e_usable") else "Measured preview"
            if part.get("e_usable"):
                part["e_validation"] = signing.dumps(
                    [request.user.pk,athlete.pk,request.GET.get("date"),
                     preview_digest(part["training_fields"],part["watch_loads"])],salt="garmin-e-save")
    return JsonResponse({"ok":True,"results":results,"model":"E","message":data.get("message","")})
