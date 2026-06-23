"""Deterministic identity answer boundary.

This is intentionally narrow: it only takes over when the R1 response
obligation observation says the current turn requires truthful identity.
"""

from __future__ import annotations

from typing import Any

from config.settings import settings
from graph.state import GraphState


UNVERIFIED_IDENTITY_CLAIMS = (
    "GPT-4",
    "gpt-4",
    "Claude",
    "claude",
    "OpenAI 模型",
    "openai model",
    "基于 GPT",
    "基于GPT",
)


def _set_runtime_field(context, name: str, value):
    object.__setattr__(context, name, value)


def _runtime_trace(state: GraphState | dict, context) -> dict:
    trace = state.get("runtime_trace") if isinstance(state, dict) else None
    if not isinstance(trace, dict):
        trace = getattr(context, "runtime_trace", None)
    if not isinstance(trace, dict):
        trace = {}
    _set_runtime_field(context, "runtime_trace", trace)
    if isinstance(state, dict):
        state["runtime_trace"] = trace
    return trace


def _identity_required(trace: dict) -> bool:
    obligation = trace.get("response_obligation")
    if not isinstance(obligation, dict):
        return False
    return bool(
        obligation.get("identity_answer_required")
        or obligation.get("identity_truth_required")
        or obligation.get("expected_deliverable") == "identity_answer"
        or trace.get("identity_truth_required") is True
    )


def _ensure_identity_obligation_from_current_turn(
    state: GraphState | dict,
    context,
    trace: dict,
) -> bool:
    """Recover identity obligation for pre-Step1.8 short-circuit paths.

    Step0 can legitimately short-circuit light identity questions before the
    observation layer has populated runtime_trace. The takeover remains narrow:
    it delegates classification to the existing obligation observer and only
    marks identity when that observer says the current turn is identity_answer.
    """
    if _identity_required(trace):
        return True
    if not isinstance(state, dict):
        return False
    user_input = str(state.get("user_input", "") or "")
    if not user_input.strip():
        return False
    try:
        from graph.nodes.response_obligation_observer import infer_response_obligation

        obligation = infer_response_obligation(context, user_input)
    except Exception:
        return False
    if not isinstance(obligation, dict):
        return False
    if obligation.get("expected_deliverable") != "identity_answer":
        return False

    trace["response_obligation"] = obligation
    trace["response_obligation_source"] = obligation.get("source", "identity")
    trace["response_obligation_confidence"] = obligation.get("confidence", 0.0)
    trace["expected_deliverable"] = "identity_answer"
    trace["answer_first_required_observed"] = bool(obligation.get("answer_first_required"))
    trace["clarification_allowed_observed"] = obligation.get("clarification_allowed", "")
    trace["fallback_obligation"] = obligation.get("fallback_must_satisfy", "")
    trace["repair_obligation_required"] = bool(obligation.get("repair_required"))
    trace["identity_truth_required"] = True
    trace["identity_truth_reason"] = list(trace.get("identity_truth_reason", []) or [])
    trace["identity_truth_reason"].append("identity_truth:recovered_pre_obligation_short_circuit")
    _set_runtime_field(context, "response_obligation", obligation)
    _set_runtime_field(context, "runtime_trace", trace)
    state["runtime_trace"] = trace
    return True


def _clean_public_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    blocked_fragments = ("api_key", "secret", "token", "\\", "/", "C:", "Users")
    if any(fragment.lower() in text.lower() for fragment in blocked_fragments):
        return ""
    return text[:80]


def _provider_model_from_trace_or_settings(trace: dict) -> tuple[str, str]:
    provider = _clean_public_value(
        trace.get("llm_provider_selected")
        or trace.get("llm_provider")
        or getattr(settings, "llm_provider", "")
    )
    model = _clean_public_value(
        trace.get("llm_model")
        or getattr(settings, "deepseek_model", "")
        or getattr(settings, "deepseek_official_model", "")
        or getattr(settings, "nvidia_model", "")
    )
    if not provider:
        if getattr(settings, "deepseek_api_key", ""):
            provider = "deepseek"
        elif getattr(settings, "deepseek_official_api_key", ""):
            provider = "deepseek_official"
        elif getattr(settings, "nvidia_api_keys", ""):
            provider = "nvidia"
    return provider, model


def _contains_unverified_identity_claim(text: str, provider: str, model: str, public_name: str) -> bool:
    combined = f"{provider} {model} {public_name}".lower()
    for claim in UNVERIFIED_IDENTITY_CLAIMS:
        if claim in str(text or "") and claim.lower() not in combined:
            return True
    return False


def _build_truthful_identity_answer(context, runtime_trace: dict) -> tuple[str, dict]:
    public_name = _clean_public_value(
        getattr(settings, "public_model_name", "")
        or getattr(settings, "assistant_public_name", "")
        or getattr(settings, "app_name", "")
    )
    provider, model = _provider_model_from_trace_or_settings(runtime_trace)

    source = "safe_generic"
    reason = ["identity_truth:required_by_response_obligation"]

    if public_name and public_name != "Human-OS Engine":
        source = "settings_public_name"
        reason.append("identity_truth:used_settings_public_name")
        answer = f"我是 {public_name}，当前系统配置的对话助手。我不会冒充 GPT-4、Claude 或其他未配置模型。"
    elif provider and model:
        source = "runtime_provider_model"
        reason.append("identity_truth:used_runtime_provider_model")
        answer = (
            "我是当前系统配置的对话助手，运行在 human-os-engine 的对话引擎中。"
            f"当前后端配置的 LLM provider 是 {provider}，模型是 {model}。"
        )
    else:
        reason.append("identity_truth:used_safe_generic")
        answer = (
            "我是当前系统配置的对话助手，主要负责理解你的问题并给出建议。"
            "具体底层模型以当前系统配置为准，我不会冒充 GPT-4、Claude 或其他未配置模型。"
        )

    metadata = {
        "source": source,
        "provider": provider or None,
        "model": model or None,
        "public_name": public_name or None,
        "reason": reason,
    }
    return answer, metadata


def apply_identity_truth_takeover(
    state: GraphState | dict,
    context,
    final_output: str,
) -> str:
    """Replace identity answers with deterministic truth when required."""
    trace = _runtime_trace(state, context)
    trace.setdefault("identity_truth_takeover_used", False)
    trace.setdefault("identity_truth_source", "none")
    trace.setdefault("identity_truth_provider", None)
    trace.setdefault("identity_truth_model", None)
    trace.setdefault("identity_truth_blocked_unverified_claim", False)
    trace.setdefault("identity_truth_reason", [])

    if not _ensure_identity_obligation_from_current_turn(state, context, trace):
        _set_runtime_field(context, "runtime_trace", trace)
        return final_output

    answer, metadata = _build_truthful_identity_answer(context, trace)
    blocked = _contains_unverified_identity_claim(
        final_output,
        str(metadata.get("provider") or ""),
        str(metadata.get("model") or ""),
        str(metadata.get("public_name") or ""),
    )
    trace["identity_truth_takeover_used"] = True
    trace["identity_truth_source"] = metadata["source"]
    trace["identity_truth_provider"] = metadata["provider"]
    trace["identity_truth_model"] = metadata["model"]
    trace["identity_truth_blocked_unverified_claim"] = bool(blocked)
    existing_reasons = list(trace.get("identity_truth_reason", []) or [])
    trace["identity_truth_reason"] = list(metadata["reason"])
    for reason in existing_reasons:
        if reason not in trace["identity_truth_reason"]:
            trace["identity_truth_reason"].append(reason)
    if blocked:
        trace["identity_truth_reason"].append("identity_truth:blocked_unverified_gpt_claim")
    trace["identity_truth_required"] = True
    _set_runtime_field(context, "runtime_trace", trace)
    if isinstance(state, dict):
        state["runtime_trace"] = trace
    return answer
