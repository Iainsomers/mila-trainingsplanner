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
from core.garmin_e import (
    apply_explicit_zone_labels,
    ask_model,
    checked_proposal,
    complete_partial_running_proposal,
    lap_facts,
    prefer_measured_time_groups,
)
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


def conversation_identity(user_id, athlete_id, start, facts):
    fingerprint = hashlib.sha256(json.dumps([facts,[]],
        sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return hashlib.sha256(str((user_id,athlete_id,start,fingerprint)).encode()).hexdigest()


def visible_history(history):
    return [{"role":m["role"],"content":m["content"]} for m in history if not m.get("automatic")]


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
    selection_text = request.POST.get("combine")
    combine_token = request.POST.get("combine_token") or request.GET.get("combine_token")
    combining = bool(selection_text)
    combined_seed = None
    if selection_text or combine_token:
        try:
            if selection_text:
                if len(selection_text)>4000:
                    raise ValueError("Choose at most three activities.")
                selection = json.loads(selection_text)
            else:
                signed = signing.loads(combine_token,salt="garmin-e-combine",max_age=86400)
                if signed[:3]!=[request.user.pk,athlete.pk,request.GET.get("date")]:
                    raise ValueError("Reopen Garmin E and combine these activities again.")
                selection = signed[3]
            from core.garmin_e_combine import combine_recordings, shifted_main_proposal
            main_start = next((item.get("start") for item in selection
                               if isinstance(item,dict) and item.get("role")=="main"),None) if isinstance(selection,list) else None
            main_source = next((s for s in results if s.get("start")==main_start),None)
            main_state = None
            if main_source and len(main_source.get("parts") or [])==1:
                raw_part = main_source["parts"][0]
                if raw_part.get("watch_loads") and (raw_part.get("training_fields") or {}).get("main"):
                    identity = conversation_identity(request.user.pk,athlete.pk,main_start,lap_facts(raw_part))
                    stored = GarminEConversation.objects.filter(user=request.user,athlete=athlete,activity_key=identity).first()
                    if stored and (stored.state.get("part") or {}).get("e_usable"):
                        main_state = stored.state
                        raw_part["training_fields"] = deepcopy(main_state["part"]["training_fields"])
            combined,ordered,ranges = combine_recordings(results,selection)
            combined["e_combine_token"] = signing.dumps(
                [request.user.pk,athlete.pk,request.GET.get("date"),ordered],salt="garmin-e-combine")
            if main_state and main_state.get("proposal"):
                try:
                    proposal = shifted_main_proposal(main_state["proposal"],ranges)
                    candidate = checked_proposal(combined["parts"][0],proposal,
                        athlete=athlete,zone_basis=main_state["basis"])
                    combined_seed = dict(proposal=proposal,part=candidate,basis=main_state["basis"],
                        history=[{"role":"assistant","content":"Je gecontroleerde Main is gecombineerd met de gekozen WU/CD. Alle gemeten laps blijven behouden en zijn opnieuw genummerd."}])
                except (ValueError,KeyError,TypeError):
                    pass
            results = [combined]
        except (signing.BadSignature,ValueError,KeyError,TypeError) as exc:
            return JsonResponse({"ok":False,"message":str(exc) or "Invalid combination.","results":[]},status=400)
    message = None
    analyzing = request.POST.get("analyze") in {"auto","1"}
    auto_analysis = request.POST.get("analyze") == "auto"
    if request.method == "POST" and not combining:
        if not analyzing:
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
        if session.get("e_combine_token"):
            permitted = ((not session["e_requires_fit"] or fit_permission) and
                         (not session["e_requires_push"] or push_permission))
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
            identity = conversation_identity(request.user.pk,athlete.pk,session.get("start"),facts)
            conversation,_ = GarminEConversation.objects.get_or_create(user=request.user,athlete=athlete,
                activity_key=identity,defaults={"state":combined_seed or {}})
            state = conversation.state or {"history":[],"part":deepcopy(part),"proposal":None,"basis":"auto"}
            # One complete Alternative lap needs no model interpretation or interval
            # split. Validate it through the same compiler, including old conversations
            # that only discussed it and never returned a usable assignment.
            if (request.method == "GET" and is_alternative and len(facts)==1
                    and not state["part"].get("e_usable") and not state.get("pending")
                    and state["basis"] in {"auto","hr"}
                    and abs(facts[0]["duration_s"]-float(part.get("alternative_duration_s") or 0))<.001):
                seconds = facts[0]["duration_s"]
                target = max(1,round(seconds/60)*60)
                if abs(target-seconds)>max(15,target*.06):
                    target = max(1,round(seconds))
                proposal = {"reps":[{"laps":[1],"target_seconds":target}]}
                try:
                    candidate = checked_proposal(part,proposal,athlete=athlete,zone_basis="hr")
                    compact = {**proposal,"format":"compact"}
                    try:
                        candidate = checked_proposal(part,compact,athlete=athlete,zone_basis="hr")
                        proposal = compact
                    except ValueError:
                        pass  # Missing HR/limits: keep exact measured duration without a zone.
                    updated_state = deepcopy(state)
                    updated_state.update(part=candidate,proposal=proposal,basis="hr")
                    updated_state["history"].append({"role":"assistant","content":
                        f"Lap 1 bevat één opgenomen tijdsblok van {seconds:g} seconden. "
                        "Dit blok staat klaar om te gebruiken; binnen deze lap zijn geen afzonderlijke intervallen vastgelegd. "
                        "De gemeten duur en hartslag blijven behouden."})
                    GarminEConversation.objects.filter(pk=conversation.pk,state=conversation.state).filter(
                        Q(busy_until__isnull=True)|Q(busy_until__lt=timezone.now())).update(
                            state=updated_state,updated_at=timezone.now())
                    conversation.refresh_from_db()
                    state = conversation.state or state
                except (ValueError,KeyError,TypeError,OverflowError):
                    pass  # Unsupported measurements still require the ordinary E analysis.
            if (request.GET.get("preview") == "measured" or combining) and message is None and not analyzing:
                if state["history"]:
                    session["parts"] = [state["part"]]
                    session["parts"][0]["e_history"] = visible_history(state["history"])
                else:
                    part["ai_structure_status"] = "e_ready"
                    part["e_auto_analyze"] = True
                continue
            if message is None and state["history"] and (not analyzing or auto_analysis):
                session["parts"] = [state["part"]]
                session["parts"][0]["e_history"] = visible_history(state["history"])
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
                initial_analysis = message is None
                turn = {"role":"user","content":message or
                    "Analyseer de hele opname en geef direct een volledig bruikbaar voorstel als de laps dat ondersteunen. Leg het patroon uit. Vraag alleen iets als de meetgegevens echt onduidelijk zijn."}
                if initial_analysis:
                    turn["automatic"] = True
                history = state["history"] + [turn]
                compact_requested = bool(is_alternative and any(
                    m["role"]=="user" and re.search(r"compact|notatie|\d+\s*['′].*(?://|[×x*]\s*\()|\d+\s*[×x*]\s*\d+:\d{2}|\bwu\s+\d+:\d{2}",m["content"],re.I)
                    for m in history))
                current = {"training":state["part"].get("training_fields") if state["part"].get("e_usable") else None,
                           "zone_basis":state["basis"],"hr_limits":athlete.zone_hr_bpm,
                           "activity_type":part.get("alternative_label") if is_alternative else "Running",
                           "alternative_hr_correction":athlete.alternative_hr_correction if is_alternative else None,
                           "requested_presentation":"compact" if compact_requested else None,
                           "initial_analysis":initial_analysis,
                           "checked_assignment":state["proposal"],"pending_confirmation":state.get("pending")}
                deadline = monotonic()+26
                initial_retry_used = False
                try:
                    answer = ask_model(facts,history,current,timeout=16)
                except OSError:
                    remaining = deadline-monotonic()
                    if remaining < 3:
                        raise
                    answer = ask_model(
                        facts, history, current,
                        "The previous service request timed out. Answer concisely now; return a complete proposal "
                        "when supported and do not repeat the conversation.",
                        timeout=min(8, remaining),
                    )
                    initial_retry_used = True
                proposal = answer.get("proposal")
                basis = answer.get("zone_basis",state["basis"])
                if isinstance(proposal, dict):
                    proposal = deepcopy(proposal)
                    prior_labels = (state.get("proposal") or {}).get("zone_labels")
                    if isinstance(prior_labels, list):
                        proposal["zone_labels"] = deepcopy(prior_labels)
                    else:
                        proposal.pop("zone_labels", None)
                labeled_proposal, explicit_zone_update = apply_explicit_zone_labels(
                    proposal if proposal is not None else state.get("proposal"), message
                )
                if explicit_zone_update:
                    proposal = labeled_proposal
                action_requested = bool(message and (
                    re.search(r"\b(?:voorstel|proposal|gebruik|gebruiken|use|usen|apply|toepassen|overnemen|aanpassen|corrigeer|update)\b",message,re.I)
                    or explicit_zone_update
                    or (re.fullmatch(r"(?:ja|yes|ok|doe maar)[.!]?",message,re.I) and state["history"]
                        and re.search(r"voorstel|gebruik|use|apply|toepassen",state["history"][-1]["content"],re.I))))
                wants_update = (initial_analysis or action_requested or answer.get("intent") == "update" or
                    (compact_requested and (state.get("proposal") or {}).get("format")!="compact"))
                repair_used = initial_retry_used
                confirmed = bool(state.get("pending") and message and re.fullmatch(
                    r"(?:ja|yes|zeker|ok|doe maar)(?:[.!]|,? (?:klopt|graag|doen|dat klopt))?",
                    message.strip(),re.I))
                if confirmed:
                    proposal = state["pending"]["proposal"]
                    basis = state["pending"]["basis"]
                error, candidate = None, None
                time_group_adjusted = False
                if basis not in {"auto","pace","hr"}:
                    raise ValueError("Garmin E returned an invalid zone basis.")
                if proposal is None and basis != state["basis"]:
                    proposal = state["proposal"]
                if (proposal is None and wants_update) or (compact_requested and isinstance(proposal,dict) and proposal.get("format")!="compact"):
                    remaining = deadline-monotonic()
                    if remaining >= 3:
                        answer = ask_model(facts,history,current,
                            ("Initial analysis must immediately provide a usable complete proposal when the measured pattern is clear. Do not ask the user whether to create it. "
                             if initial_analysis else
                             "The user wants the agreed correction in the usable preview, but no proposal was returned. ") +
                            "Return intent:update and the FULL updated lap assignment, preserving untouched laps. "
                            "For requested compact Alternative notation include proposal.format=compact and presentation targets/zones matching the request and measured evidence. "
                            "If unsupported, explain the concrete measurement mismatch without claiming an update.",
                            timeout=min(20,remaining))
                        proposal = answer.get("proposal")
                        basis = answer.get("zone_basis",state["basis"])
                        repair_used = True
                if proposal is not None:
                    try:
                        if wants_update:
                            proposal = complete_partial_running_proposal(part, proposal)
                        proposal, time_group_adjusted = prefer_measured_time_groups(part, proposal)
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
                                    if wants_update:
                                        proposal = complete_partial_running_proposal(part, proposal)
                                    proposal, time_group_adjusted = prefer_measured_time_groups(part, proposal)
                                    if compact_requested and proposal.get("format")!="compact":
                                        raise ValueError("De gevraagde compacte notatie ontbreekt nog in de laptoewijzing.")
                                    candidate = checked_proposal(part,proposal,athlete=athlete,zone_basis=basis,
                                        confirmed_overrun=answer.get("confirmation_required") is True)
                                    error = None
                                except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError) as exc:
                                    error = str(exc)
                reply = answer["reply"]
                if wants_update and not candidate and (error or answer.get("intent") == "update"):
                    reply = "Het gecontroleerde voorstel is niet aangepast." + ("\n\n" + error if error else " De gevraagde wijziging leverde nog geen bruikbaar voorstel op.")
                if candidate and time_group_adjusted:
                    reply += "\n\nDe werkblokken hebben vrijwel exact dezelfde hele-minuutduur; daarom toont het gecontroleerde voorstel deze groep als tijdreps."
                if error:
                    reply += "\n\nDit voorstel kan ik nog niet toepassen op de metingen: "+error
                if candidate and answer.get("confirmation_required") is True and not confirmed:
                    state["pending"] = {"proposal":proposal,"basis":basis}
                    candidate = None
                    reply += "\n\nAntwoord ‘ja’ als je dit voorstel wilt gebruiken; de gemeten tijden blijven behouden."
                updated = candidate or deepcopy(state["part"])
                updated.pop("e_history",None)
                if not candidate and wants_update and not state.get("pending"):
                    reply += ("\n\nHet bruikbare voorstel hieronder is nog niet bijgewerkt; de vorige gecontroleerde versie staat er nog."
                              if state["part"].get("e_usable") else
                              "\n\nEr is nog geen gecontroleerd bruikbaar voorstel; zie de toelichting hierboven.")
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
                session["parts"] = [{**updated,"e_history":visible_history(state["history"])}]
            except TimeoutError:
                updated = deepcopy(state["part"])
                updated["chat_reply"] = "Garmin E kreeg niet op tijd antwoord. Het gesprek en je laatste gecontroleerde voorstel zijn behouden. Probeer het opnieuw."
                updated["ai_structure_status"] = "e_error"
                session["parts"] = [updated]
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
