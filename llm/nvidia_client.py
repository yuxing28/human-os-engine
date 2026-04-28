"""
Human-OS Engine - LLM 客户端（双平台路由）

封装 LangChain 的 NVIDIA AI Endpoints 调用。
支持：
1. 多个 API Key 轮询（避免限速）
2. 按任务类型选择模型（快速/深度）
3. 超时处理和重试
4. 双平台路由：话术生成 → DeepSeek，其他 → NVIDIA
"""

import time
from enum import Enum
from typing import Generator
import httpx
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_openai import ChatOpenAI
from config.settings import settings
from utils.logger import warning, error, info


class TaskType(str, Enum):
    """任务类型"""
    FAST = "fast"           # 快速判断（元控制器）→ NVIDIA
    STANDARD = "standard"   # 标准任务（知识路由）→ NVIDIA
    DEEP = "deep"           # 深度生成（话术润色）→ DeepSeek


# 模型配置（基于实际速率测试，2026-04-01）
# 可用模型：
# - qwen/qwen2.5-coder-32b-instruct: 2.5s
# - moonshotai/kimi-k2-thinking: 6.1s
# - meta/llama-3.1-70b-instruct: 8.9s
# - deepseek-ai/deepseek-v3.1: 8.7s（中文最强，推荐）
# - deepseek-ai/deepseek-r1-distill-qwen-32b: 2.7s
# 不可用：deepseek-v3.2(超时), glm5(超时), minimax-m2.5(超时)
MODEL_CONFIG = {
    TaskType.FAST: {
        "model": "qwen/qwen2.5-coder-32b-instruct",  # 2.5s，最快中文模型
        "temperature": 0.2,
        "max_tokens": 256,
        "timeout": 15,
    },
    TaskType.STANDARD: {
        "model": "qwen/qwen2.5-coder-32b-instruct",  # 实测更稳更快，统一非最终输出主路由
        "temperature": 0.2,
        "max_tokens": 512,
        "timeout": 15,
    },
    TaskType.DEEP: {
        "model": "deepseek-ai/deepseek-v3.1",  # 8.7s，中文最强
        "temperature": 0.25,
        "max_tokens": 512,
        "timeout": 30,
    },
}

# Key 轮询状态（线程安全）
import threading
_key_lock = threading.Lock()
_current_key_index = 0
_key_failure_count: dict[int, int] = {}

# 记录最后一次调用的提供商（用于调试和监控）
_last_provider: str = "unknown"
_provider_lock = threading.Lock()


def get_last_provider() -> str:
    """获取最后一次 LLM 调用的提供商名称"""
    with _provider_lock:
        return _last_provider


def _short_error_message(error: Exception | str, limit: int = 200) -> str:
    text = str(error or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[:limit]


def _ensure_llm_trace(runtime_trace: dict | None) -> dict | None:
    if not isinstance(runtime_trace, dict):
        return None
    runtime_trace.setdefault("llm_call_count", 0)
    runtime_trace.setdefault("llm_call_detail", [])
    runtime_trace.setdefault("llm_call_success_count", 0)
    runtime_trace.setdefault("llm_call_fail_count", 0)
    runtime_trace.setdefault("llm_fallback_count", 0)
    runtime_trace.setdefault("llm_provider", "unknown")
    runtime_trace.setdefault("llm_model", "")
    runtime_trace.setdefault("llm_endpoint_configured", False)
    runtime_trace.setdefault("llm_error_type", [])
    runtime_trace.setdefault("llm_error_stage", [])
    runtime_trace.setdefault("llm_retry_count", 0)
    runtime_trace.setdefault("output_path", "fallback")
    runtime_trace.setdefault("llm_fast_path_disabled", False)
    runtime_trace.setdefault("llm_normal_path_used", False)
    runtime_trace.setdefault("llm_provider_resolution", {})
    runtime_trace.setdefault("llm_provider_candidates", [])
    runtime_trace.setdefault("llm_provider_selected", "")
    runtime_trace.setdefault("llm_provider_unavailable_reason", [])
    runtime_trace.setdefault("llm_provider_fallback_used", False)
    runtime_trace.setdefault("llm_health_check_passed", False)
    runtime_trace.setdefault("llm_health_check_error", "")
    runtime_trace.setdefault("env_loaded_from", settings.env_file_path)
    return runtime_trace


def _append_unique(items: list, value) -> None:
    if value not in items:
        items.append(value)


def _provider_available(provider: str) -> tuple[bool, str]:
    provider = str(provider or "").strip().lower()
    if provider == "xfyun_maas":
        if not settings.deepseek_api_key:
            return False, "xfyun_missing_key"
        if not settings.deepseek_base_url:
            return False, "xfyun_missing_base_url"
        return True, ""
    if provider == "deepseek_official":
        if not settings.deepseek_official_api_key:
            return False, "deepseek_official_missing_key"
        return True, ""
    if provider == "nvidia":
        if not settings.get_api_keys():
            return False, "nvidia_missing_key"
        if not settings.nvidia_base_url:
            return False, "nvidia_missing_base_url"
        return True, ""
    return False, "unknown_provider"


def _resolve_active_llm_provider(
    runtime_trace: dict | None = None,
    *,
    allow_nvidia: bool = True,
) -> dict:
    trace = _ensure_llm_trace(runtime_trace)
    explicit = str(getattr(settings, "llm_provider", "") or "").strip().lower()
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    for provider in ["xfyun_maas", "deepseek_official"]:
        if provider not in candidates:
            candidates.append(provider)
    if allow_nvidia and "nvidia" not in candidates:
        candidates.append("nvidia")

    unavailable: list[str] = []
    selected = ""
    fallback_used = False

    for idx, provider in enumerate(candidates):
        ok, reason = _provider_available(provider)
        if ok:
            selected = provider
            fallback_used = bool(idx > 0)
            break
        if reason:
            unavailable.append(f"{provider}:{reason}")

    if trace is not None:
        trace["env_loaded_from"] = settings.env_file_path
        trace["llm_provider_candidates"] = candidates
        trace["llm_provider_selected"] = selected
        trace["llm_provider_fallback_used"] = fallback_used
        trace["llm_provider_resolution"] = {
            "explicit_provider": explicit or "auto",
            "selected": selected or "fallback_only",
            "allow_nvidia": allow_nvidia,
        }
        trace["llm_health_check_passed"] = bool(selected)
        trace["llm_health_check_error"] = "" if selected else "no_configured_provider"
        for item in unavailable:
            _append_unique(trace.setdefault("llm_provider_unavailable_reason", []), item)
        if not allow_nvidia and any(item == "nvidia:nvidia_missing_key" for item in unavailable):
            _append_unique(trace.setdefault("llm_provider_unavailable_reason", []), "llm_provider_unavailable:nvidia_missing_key")
        if fallback_used and selected == "xfyun_maas":
            _append_unique(trace.setdefault("llm_provider_unavailable_reason", []), "llm_provider_fallback:xfyun_maas")
    return {
        "selected": selected,
        "candidates": candidates,
        "fallback_used": fallback_used,
        "unavailable": unavailable,
    }


def _record_llm_trace(
    runtime_trace: dict | None,
    *,
    stage: str,
    provider: str,
    model: str,
    stream: bool,
    success: bool,
    latency_ms: float,
    fallback_triggered: bool = False,
    error_type: str = "",
    error_message_short: str = "",
    endpoint_configured: bool = False,
) -> None:
    trace = _ensure_llm_trace(runtime_trace)
    if trace is None:
        return
    trace["llm_call_count"] = int(trace.get("llm_call_count", 0) or 0) + 1
    if success:
        trace["llm_call_success_count"] = int(trace.get("llm_call_success_count", 0) or 0) + 1
        trace["llm_provider"] = provider
        trace["llm_model"] = model
        trace["llm_endpoint_configured"] = endpoint_configured
    else:
        trace["llm_call_fail_count"] = int(trace.get("llm_call_fail_count", 0) or 0) + 1
        if error_type:
            _append_unique(trace.setdefault("llm_error_type", []), error_type)
        if stage:
            _append_unique(trace.setdefault("llm_error_stage", []), stage)
    if fallback_triggered:
        trace["llm_fallback_count"] = int(trace.get("llm_fallback_count", 0) or 0) + 1
    trace.setdefault("llm_call_detail", []).append(
        {
            "stage": stage,
            "provider": provider,
            "model": model,
            "stream": bool(stream),
            "success": bool(success),
            "latency_ms": round(float(latency_ms or 0.0), 1),
            "error_type": error_type or "",
            "error_message_short": _short_error_message(error_message_short),
            "fallback_triggered": bool(fallback_triggered),
        }
    )


def get_next_api_key() -> str:
    """获取下一个可用的 API Key（线程安全）"""
    global _current_key_index

    keys = settings.get_api_keys()
    if not keys:
        raise ValueError("未配置 NVIDIA API Key，请在 .env 文件中设置 NVIDIA_API_KEYS")

    with _key_lock:
        # 尝试所有 Key，找到一个失败次数最少的
        for _ in range(len(keys)):
            key = keys[_current_key_index]
            failure_count = _key_failure_count.get(_current_key_index, 0)

            if failure_count < 3:  # 失败次数少于 3 次的 Key 可用
                return key

            # 切换到下一个 Key
            _current_key_index = (_current_key_index + 1) % len(keys)

        # 所有 Key 都失败过，重置计数器并使用第一个
        _key_failure_count.clear()
        _current_key_index = 0
        return keys[0]


def mark_key_failed():
    """标记当前 Key 失败（线程安全）"""
    global _current_key_index
    with _key_lock:
        _key_failure_count[_current_key_index] = _key_failure_count.get(_current_key_index, 0) + 1
        _current_key_index = (_current_key_index + 1) % len(settings.get_api_keys())


def select_model(task_type: TaskType = TaskType.STANDARD) -> dict:
    """根据任务类型选择模型配置"""
    return MODEL_CONFIG.get(task_type, MODEL_CONFIG[TaskType.STANDARD])


def get_nvidia_client(task_type: TaskType = TaskType.STANDARD) -> ChatNVIDIA:
    """获取 NVIDIA NIM 客户端"""
    api_key = get_next_api_key()
    config = select_model(task_type)

    return ChatNVIDIA(
        model=config["model"],
        api_key=api_key,
        base_url=settings.nvidia_base_url,
        temperature=config["temperature"],
        max_completion_tokens=config["max_tokens"],
    )


def get_deepseek_client() -> ChatOpenAI:
    """获取 DeepSeek 官方客户端（兼容 OpenAI 接口）"""
    if not settings.deepseek_api_key:
        raise ValueError("未配置 DEEPSEEK_API_KEY，请在 .env 文件中设置")

    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=MODEL_CONFIG[TaskType.DEEP]["temperature"],
        max_tokens=512,
        timeout=MODEL_CONFIG[TaskType.DEEP]["timeout"],
    )


def get_deepseek_official_client() -> ChatOpenAI:
    """获取 DeepSeek 官方客户端（可选的第二降级层）"""
    if not settings.deepseek_official_api_key:
        raise ValueError("未配置 DEEPSEEK_OFFICIAL_API_KEY，请在 .env 文件中设置")

    return ChatOpenAI(
        model=settings.deepseek_official_model,
        api_key=settings.deepseek_official_api_key,
        base_url=settings.deepseek_official_base_url,
        temperature=MODEL_CONFIG[TaskType.DEEP]["temperature"],
        max_tokens=512,
        timeout=MODEL_CONFIG[TaskType.DEEP]["timeout"],
    )


def _invoke_deepseek(
    messages: list,
    prompt: str,
    system_prompt: str,
    fallback: bool,
    runtime_trace: dict | None = None,
    stage: str = "unknown",
) -> str:
    """话术生成专用三级降级架构：讯飞 → DeepSeek官方 → NVIDIA"""
    global _last_provider
    
    # 第一优先级：讯飞 astron-code-latest
    last_error = None
    for attempt in range(2):
        try:
            started = time.perf_counter()
            client = get_deepseek_client()
            response = client.invoke(messages)
            with _provider_lock:
                _last_provider = "XunFei Astron"
            _record_llm_trace(
                runtime_trace,
                stage=stage,
                provider="xfyun_maas",
                model=settings.deepseek_model,
                stream=False,
                success=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                endpoint_configured=bool(settings.deepseek_base_url),
            )
            if isinstance(runtime_trace, dict):
                runtime_trace["output_path"] = "llm"
            return response.content
        except Exception as e:
            last_error = e
            error_msg = str(e)
            warning(f"讯飞API调用失败 [deep] (尝试 {attempt + 1}/2): {error_msg[:100]}")
            _record_llm_trace(
                runtime_trace,
                stage=stage,
                provider="xfyun_maas",
                model=settings.deepseek_model,
                stream=False,
                success=False,
                latency_ms=0.0,
                fallback_triggered=bool(fallback),
                error_type=classify_error(e).value,
                error_message_short=error_msg,
                endpoint_configured=bool(settings.deepseek_base_url),
            )
            if isinstance(runtime_trace, dict):
                runtime_trace["llm_retry_count"] = int(runtime_trace.get("llm_retry_count", 0) or 0) + 1
            time.sleep(0.4)
            continue
        
        # 第二优先级：DeepSeek官方API（新增中间降级层）
        if fallback and settings.deepseek_official_api_key:
            info("回退到 DeepSeek 官方API...")
            try:
                started = time.perf_counter()
                client = get_deepseek_official_client()
                response = client.invoke(messages)
                with _provider_lock:
                    _last_provider = "DeepSeek Official"
                _record_llm_trace(
                    runtime_trace,
                    stage=stage,
                    provider="deepseek_official",
                    model=settings.deepseek_official_model,
                    stream=False,
                    success=True,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    endpoint_configured=bool(settings.deepseek_official_base_url),
                )
                if isinstance(runtime_trace, dict):
                    runtime_trace["output_path"] = "llm"
                return response.content
            except Exception as e2:
                warning(f"DeepSeek官方调用失败: {str(e2)[:100]}")
                _record_llm_trace(
                    runtime_trace,
                    stage=stage,
                    provider="deepseek_official",
                    model=settings.deepseek_official_model,
                    stream=False,
                    success=False,
                    latency_ms=0.0,
                    fallback_triggered=True,
                    error_type=classify_error(e2).value,
                    error_message_short=str(e2),
                    endpoint_configured=bool(settings.deepseek_official_base_url),
                )
        
    if fallback and settings.deepseek_official_api_key:
        info("回退到 DeepSeek 官方API...")
        try:
            started = time.perf_counter()
            client = get_deepseek_official_client()
            response = client.invoke(messages)
            with _provider_lock:
                _last_provider = "DeepSeek Official"
            _record_llm_trace(
                runtime_trace,
                stage=stage,
                provider="deepseek_official",
                model=settings.deepseek_official_model,
                stream=False,
                success=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                endpoint_configured=bool(settings.deepseek_official_base_url),
            )
            if isinstance(runtime_trace, dict):
                runtime_trace["output_path"] = "llm"
            return response.content
        except Exception as e2:
            warning(f"DeepSeek官方调用失败: {str(e2)[:100]}")
            _record_llm_trace(
                runtime_trace,
                stage=stage,
                provider="deepseek_official",
                model=settings.deepseek_official_model,
                stream=False,
                success=False,
                latency_ms=0.0,
                fallback_triggered=True,
                error_type=classify_error(e2).value,
                error_message_short=str(e2),
                endpoint_configured=bool(settings.deepseek_official_base_url),
            )

    if fallback:
        info("最终回退到 NVIDIA 模型...")
        return _invoke_nvidia(messages, prompt, system_prompt, TaskType.DEEP, fallback=False, runtime_trace=runtime_trace, stage=stage)
    raise last_error if last_error else TimeoutError("deepseek_invoke_failed")


def _invoke_general_fallback_llm(
    messages: list,
    stage: str,
    runtime_trace: dict | None,
) -> str:
    """当 NVIDIA 链路不稳时，回退到当前项目里更稳定的通用 LLM。"""
    resolution = _resolve_active_llm_provider(runtime_trace, allow_nvidia=False)
    if resolution.get("selected") == "xfyun_maas":
        return _invoke_deepseek(
            messages,
            prompt="",
            system_prompt="",
            fallback=False,
            runtime_trace=runtime_trace,
            stage=stage,
        )
    if resolution.get("selected") == "deepseek_official":
        started = time.perf_counter()
        client = get_deepseek_official_client()
        response = client.invoke(messages)
        _record_llm_trace(
            runtime_trace,
            stage=stage,
            provider="deepseek_official",
            model=settings.deepseek_official_model,
            stream=False,
            success=True,
            latency_ms=(time.perf_counter() - started) * 1000,
            endpoint_configured=bool(settings.deepseek_official_base_url),
        )
        if isinstance(runtime_trace, dict):
            runtime_trace["output_path"] = "llm"
        return response.content
    raise TimeoutError("no_general_fallback_llm_available")


def _invoke_nvidia(
    messages: list,
    prompt: str,
    system_prompt: str,
    task_type: TaskType,
    fallback: bool,
    runtime_trace: dict | None = None,
    stage: str = "unknown",
) -> str:
    """NVIDIA 平台调用（元控制器/知识路由等）"""
    global _last_provider
    keys = settings.get_api_keys()
    max_retries = len(keys) if keys else 1

    for attempt in range(max_retries):
        try:
            started = time.perf_counter()
            client = get_nvidia_client(task_type)
            response = client.invoke(messages)
            with _provider_lock:
                _last_provider = f"NVIDIA({MODEL_CONFIG[task_type]['model']})"
            _record_llm_trace(
                runtime_trace,
                stage=stage,
                provider="nvidia",
                model=MODEL_CONFIG[task_type]["model"],
                stream=False,
                success=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                endpoint_configured=bool(settings.nvidia_base_url),
            )
            if isinstance(runtime_trace, dict):
                runtime_trace["output_path"] = "llm"
            return response.content

        except Exception as e:
            error_msg = str(e)
            warning(f"NVIDIA 调用失败 [{task_type.value}] (尝试 {attempt + 1}/{max_retries}): {error_msg[:100]}")
            _record_llm_trace(
                runtime_trace,
                stage=stage,
                provider="nvidia",
                model=MODEL_CONFIG[task_type]["model"],
                stream=False,
                success=False,
                latency_ms=0.0,
                fallback_triggered=bool(fallback),
                error_type=classify_error(e).value,
                error_message_short=error_msg,
                endpoint_configured=bool(settings.nvidia_base_url),
            )
            if isinstance(runtime_trace, dict):
                runtime_trace["llm_retry_count"] = int(runtime_trace.get("llm_retry_count", 0) or 0) + 1

            # 如果是限速或认证错误，切换 Key
            if "429" in error_msg or "401" in error_msg or "rate" in error_msg.lower():
                mark_key_failed()
                time.sleep(0.5)
                continue
            else:
                # 其他错误，如果允许 fallback 且回退到快速模型
                if fallback and task_type != TaskType.FAST:
                    info("回退到快速模型...")
                    return _invoke_nvidia(messages, prompt, system_prompt, TaskType.FAST, fallback=False, runtime_trace=runtime_trace, stage=stage)
                raise

    # 所有 Key 都失败
    raise Exception("所有 NVIDIA API Key 都调用失败，请检查 Key 是否有效")


# ===== 便捷函数 =====

def invoke_llm(
    prompt: str,
    system_prompt: str = "",
    task_type: TaskType = TaskType.STANDARD,
    runtime_trace: dict | None = None,
    stage: str = "unknown",
) -> str:
    """通用 LLM 调用入口（路由到 DeepSeek 或 NVIDIA）"""
    _resolve_active_llm_provider(runtime_trace, allow_nvidia=True)
    messages = []
    if system_prompt:
        messages.append(("system", system_prompt))
    messages.append(("human", prompt))

    if task_type == TaskType.DEEP:
        if _resolve_active_llm_provider(runtime_trace, allow_nvidia=True).get("selected") in {"xfyun_maas", "deepseek_official"}:
            return _invoke_deepseek(messages, prompt, system_prompt, fallback=True, runtime_trace=runtime_trace, stage=stage)
        else:
            return _invoke_nvidia(messages, prompt, system_prompt, task_type, fallback=True, runtime_trace=runtime_trace, stage=stage)
    else:
        if _resolve_active_llm_provider(runtime_trace, allow_nvidia=True).get("selected") in {"xfyun_maas", "deepseek_official"}:
            if isinstance(runtime_trace, dict):
                runtime_trace["llm_normal_path_used"] = True
            return _invoke_general_fallback_llm(messages, stage, runtime_trace)
        try:
            return _invoke_nvidia(messages, prompt, system_prompt, task_type, fallback=True, runtime_trace=runtime_trace, stage=stage)
        except Exception:
            if isinstance(runtime_trace, dict):
                runtime_trace["llm_normal_path_used"] = True
            return _invoke_general_fallback_llm(messages, stage, runtime_trace)


def invoke_fast(
    prompt: str,
    system_prompt: str = "",
    runtime_trace: dict | None = None,
    stage: str = "unknown",
) -> str:
    """快速调用（元控制器等）— 绕过 LangChain 直接使用 httpx 减少开销"""
    resolution = _resolve_active_llm_provider(runtime_trace, allow_nvidia=True)
    if resolution.get("selected") in {"xfyun_maas", "deepseek_official"}:
        if isinstance(runtime_trace, dict):
            runtime_trace["llm_fast_path_disabled"] = True
            runtime_trace["llm_normal_path_used"] = True
        messages = []
        if system_prompt:
            messages.append(("system", system_prompt))
        messages.append(("human", prompt))
        return _invoke_general_fallback_llm(messages, stage, runtime_trace)

    config = select_model(TaskType.FAST)
    url = (settings.nvidia_base_url or "https://integrate.api.nvidia.com/v1").rstrip("/") + "/chat/completions"
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
    }
    
    # 先给 raw fast 一次机会；不稳就直接切到可用主路径，别长时间卡死。
    for _ in range(1):
        api_key = get_next_api_key()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            started = time.perf_counter()
            with httpx.Client(timeout=min(max(config.get("timeout", 15), 10), 12)) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                _record_llm_trace(
                    runtime_trace,
                    stage=stage,
                    provider="nvidia_fast_raw",
                    model=config["model"],
                    stream=False,
                    success=True,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    endpoint_configured=bool(settings.nvidia_base_url),
                )
                if isinstance(runtime_trace, dict):
                    runtime_trace["output_path"] = "llm"
                return content
        except Exception as e:
            _record_llm_trace(
                runtime_trace,
                stage=stage,
                provider="nvidia_fast_raw",
                model=config["model"],
                stream=False,
                success=False,
                latency_ms=0.0,
                fallback_triggered=True,
                error_type=classify_error(e).value,
                error_message_short=str(e),
                endpoint_configured=bool(settings.nvidia_base_url),
            )
            mark_key_failed()
            continue

    if isinstance(runtime_trace, dict):
        runtime_trace["llm_fast_path_disabled"] = True
        runtime_trace["llm_normal_path_used"] = True
    if _resolve_active_llm_provider(runtime_trace, allow_nvidia=True).get("selected") in {"xfyun_maas", "deepseek_official"}:
        return _invoke_general_fallback_llm(messages, stage, runtime_trace)
    return _invoke_nvidia(
        messages,
        prompt,
        system_prompt,
        TaskType.FAST,
        fallback=False,
        runtime_trace=runtime_trace,
        stage=stage,
    )


def invoke_standard(prompt: str, system_prompt: str = "", runtime_trace: dict | None = None, stage: str = "unknown") -> str:
    """标准调用（知识路由等）"""
    return invoke_llm(prompt, system_prompt, TaskType.STANDARD, runtime_trace=runtime_trace, stage=stage)


def invoke_deep(prompt: str, system_prompt: str = "", runtime_trace: dict | None = None, stage: str = "unknown") -> str:
    """深度调用（话术生成等）"""
    return invoke_llm(prompt, system_prompt, TaskType.DEEP, runtime_trace=runtime_trace, stage=stage)


def invoke_stream(
    prompt: str,
    system_prompt: str = "",
    runtime_trace: dict | None = None,
    stage: str = "unknown",
) -> Generator[str, None, None]:
    """
    流式调用：逐 token 生成 LLM 响应
    使用 DeepSeek 模型（话术生成）
    """
    global _last_provider
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # 优先使用 DeepSeek
    resolution = _resolve_active_llm_provider(runtime_trace, allow_nvidia=True)
    if resolution.get("selected") in {"xfyun_maas", "deepseek_official"}:
        try:
            started = time.perf_counter()
            provider_name = resolution.get("selected")
            client = get_deepseek_client() if provider_name == "xfyun_maas" else get_deepseek_official_client()
            for chunk in client.stream(messages):
                content = chunk.content if hasattr(chunk, "content") and chunk.content else ""
                if content:
                    yield content
            with _provider_lock:
                _last_provider = "XunFei Astron(stream)" if provider_name == "xfyun_maas" else "DeepSeek Official(stream)"
            _record_llm_trace(
                runtime_trace,
                stage=stage,
                provider=provider_name,
                model=settings.deepseek_model if provider_name == "xfyun_maas" else settings.deepseek_official_model,
                stream=True,
                success=True,
                latency_ms=(time.perf_counter() - started) * 1000,
                endpoint_configured=bool(settings.deepseek_base_url if provider_name == "xfyun_maas" else settings.deepseek_official_base_url),
            )
            if isinstance(runtime_trace, dict):
                runtime_trace["output_path"] = "llm"
            return
        except Exception as e:
            warning(f"DeepSeek 流式调用失败，回退到 NVIDIA: {e}")
            _record_llm_trace(
                runtime_trace,
                stage=stage,
                provider="xfyun_maas",
                model=settings.deepseek_model,
                stream=True,
                success=False,
                latency_ms=0.0,
                fallback_triggered=True,
                error_type=classify_error(e).value,
                error_message_short=str(e),
                endpoint_configured=bool(settings.deepseek_base_url),
            )

    # 回退到 NVIDIA LangChain 流式
    try:
        started = time.perf_counter()
        client = get_nvidia_client(TaskType.DEEP)
        for chunk in client.stream(messages):
            content = chunk.content if hasattr(chunk, "content") and chunk.content else ""
            if content:
                yield content
        with _provider_lock:
            _last_provider = f"NVIDIA({MODEL_CONFIG[TaskType.DEEP]['model']})(stream)"
        _record_llm_trace(
            runtime_trace,
            stage=stage,
            provider="nvidia",
            model=MODEL_CONFIG[TaskType.DEEP]["model"],
            stream=True,
            success=True,
            latency_ms=(time.perf_counter() - started) * 1000,
            endpoint_configured=bool(settings.nvidia_base_url),
        )
        if isinstance(runtime_trace, dict):
            runtime_trace["output_path"] = "llm"
    except Exception as e:
        error(f"流式 LLM 调用完全失败: {e}")
        _record_llm_trace(
            runtime_trace,
            stage=stage,
            provider="nvidia",
            model=MODEL_CONFIG[TaskType.DEEP]["model"],
            stream=True,
            success=False,
            latency_ms=0.0,
            fallback_triggered=True,
            error_type=classify_error(e).value,
            error_message_short=str(e),
            endpoint_configured=bool(settings.nvidia_base_url),
        )
        if isinstance(runtime_trace, dict):
            runtime_trace["llm_normal_path_used"] = True
        try:
            response = invoke_deep(prompt, system_prompt, runtime_trace=runtime_trace, stage=stage)
            if response:
                if isinstance(runtime_trace, dict):
                    runtime_trace["output_path"] = "llm"
                yield response
                return
        except Exception as fallback_exc:
            _record_llm_trace(
                runtime_trace,
                stage=stage,
                provider="stream_non_stream_fallback",
                model=MODEL_CONFIG[TaskType.DEEP]["model"],
                stream=False,
                success=False,
                latency_ms=0.0,
                fallback_triggered=True,
                error_type=classify_error(fallback_exc).value,
                error_message_short=str(fallback_exc),
                endpoint_configured=True,
            )
        if isinstance(runtime_trace, dict):
            runtime_trace["output_path"] = "fallback"
        yield "[流式生成失败，使用默认回复]"


# ===== 错误分类（层 3：简化为 5 类） =====

class LLMErrorType(str, Enum):
    NETWORK = "network"           # 网络错误（连接超时、DNS 等）
    RATE_LIMIT = "rate_limit"     # 限流（429）
    MODEL_ERROR = "model_error"   # 模型错误（无效模型、超时等）
    AUTH_ERROR = "auth_error"     # 认证错误（401/403）
    UNKNOWN = "unknown"           # 未知错误


def classify_error(error: Exception) -> LLMErrorType:
    """错误分类"""
    error_msg = str(error).lower()
    if "429" in error_msg or "rate" in error_msg or "limit" in error_msg:
        return LLMErrorType.RATE_LIMIT
    if "401" in error_msg or "403" in error_msg or "auth" in error_msg or "unauthorized" in error_msg:
        return LLMErrorType.AUTH_ERROR
    if "connection" in error_msg or "timeout" in error_msg or "dns" in error_msg or "network" in error_msg:
        return LLMErrorType.NETWORK
    if "model" in error_msg or "invalid" in error_msg or "timeout" in error_msg:
        return LLMErrorType.MODEL_ERROR
    return LLMErrorType.UNKNOWN


def get_retry_delay(attempt: int, error_type: LLMErrorType = LLMErrorType.UNKNOWN) -> float:
    """
    指数退避 + 抖动重试
    
    基础 500ms，最大 16s，25% 随机抖动
    """
    base = min(0.5 * (2 ** (attempt - 1)), 16.0)
    jitter = base * 0.25 * (time.time() % 1.0)  # 简单抖动
    return base + jitter


# ===== 测试入口 =====

if __name__ == "__main__":
    print(f"已配置 {len(settings.get_api_keys())} 个 API Key")
    print(f"Base URL: {settings.nvidia_base_url}")
    print()

    # 测试快速调用
    print("=== 测试快速模型 ===")
    start = time.time()
    try:
        response = invoke_fast("用一句话回答：2+2等于几？")
        elapsed = time.time() - start
        print(f"响应: {response[:100]}")
        print(f"耗时: {elapsed:.2f}秒")
    except Exception as e:
        print(f"失败: {e}")

    print()

    # 测试标准调用
    print("=== 测试标准模型 ===")
    start = time.time()
    try:
        response = invoke_standard("简要说明什么是复利效应？")
        elapsed = time.time() - start
        print(f"响应: {response[:100]}")
        print(f"耗时: {elapsed:.2f}秒")
    except Exception as e:
        print(f"失败: {e}")
