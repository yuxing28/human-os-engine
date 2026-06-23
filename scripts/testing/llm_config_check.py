"""
LLM 配置体检脚本

目标：
1. 不泄露任何 key 内容
2. 给出“能不能跑”的明确结论
3. 提前发现常见配置坑（只配了历史变量、关键路由缺失等）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings


def _build_report(strict: bool) -> dict:
    nvidia_keys = settings.get_api_keys()
    has_nvidia = len(nvidia_keys) > 0
    has_deepseek_primary = bool((settings.deepseek_api_key or "").strip())
    has_deepseek_official = bool((settings.deepseek_official_api_key or "").strip())
    has_deepseek_any = has_deepseek_primary or has_deepseek_official

    warnings: list[str] = []
    errors: list[str] = []

    if not has_nvidia:
        errors.append("未配置 NVIDIA_API_KEYS：FAST/STANDARD 路由无法运行。")

    if not has_deepseek_any:
        warnings.append("未配置 DEEPSEEK_API_KEY / DEEPSEEK_OFFICIAL_API_KEY：DEEP 路由将回退到 NVIDIA。")

    if not (settings.nvidia_model or "").strip():
        warnings.append("NVIDIA_MODEL 为空：评估链路的 NVIDIA 回退能力会受影响。")

    if strict and not has_deepseek_primary:
        errors.append("严格模式要求 DEEPSEEK_API_KEY 已配置（用于深度生成主链）。")

    env_path = PROJECT_ROOT / ".env"
    scnet_detected = False
    if env_path.exists():
        try:
            text = env_path.read_text(encoding="utf-8", errors="replace")
            scnet_detected = "SCNET_API_KEYS=" in text or "SCNET_BASE_URL=" in text or "SCNET_MODEL=" in text
        except OSError:
            scnet_detected = False
    if scnet_detected:
        warnings.append("检测到 SCNET_* 历史变量：当前主链未使用，可保留但建议标注为“历史兼容”。")

    report = {
        "timestamp": time.time(),
        "strict_mode": strict,
        "summary": {
            "nvidia_key_count": len(nvidia_keys),
            "has_deepseek_primary": has_deepseek_primary,
            "has_deepseek_official": has_deepseek_official,
            "nvidia_base_url_configured": bool((settings.nvidia_base_url or "").strip()),
            "deepseek_base_url_configured": bool((settings.deepseek_base_url or "").strip()),
            "deepseek_official_base_url_configured": bool((settings.deepseek_official_base_url or "").strip()),
        },
        "models": {
            "nvidia_model": settings.nvidia_model,
            "deepseek_model": settings.deepseek_model,
            "deepseek_official_model": settings.deepseek_official_model,
        },
        "warnings": warnings,
        "errors": errors,
        "ok": len(errors) == 0,
    }
    return report


def _print_human_report(report: dict) -> None:
    print("=== LLM 配置体检 ===")
    print(f"NVIDIA keys: {report['summary']['nvidia_key_count']}")
    print(
        "DeepSeek: "
        f"primary={'yes' if report['summary']['has_deepseek_primary'] else 'no'}, "
        f"official={'yes' if report['summary']['has_deepseek_official'] else 'no'}"
    )
    print(f"结果: {'通过' if report['ok'] else '失败'}")

    if report["warnings"]:
        print("\n[提醒]")
        for item in report["warnings"]:
            print(f"- {item}")

    if report["errors"]:
        print("\n[问题]")
        for item in report["errors"]:
            print(f"- {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 配置体检（不泄露 key）")
    parser.add_argument("--strict", action="store_true", help="严格模式：强制要求 DEEPSEEK_API_KEY 存在")
    parser.add_argument(
        "--output-path",
        default=str(PROJECT_ROOT / "data" / "llm_config_check_report.json"),
        help="输出报告路径（JSON）",
    )
    args = parser.parse_args()

    report = _build_report(strict=args.strict)
    _print_human_report(report)

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {output_path}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
