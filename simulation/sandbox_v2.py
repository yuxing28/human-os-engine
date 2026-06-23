"""
Human-OS Engine 3.0 - 主沙盒入口

以进化自学习版为唯一主沙盒：
1. 多轮对话
2. 场景化护栏
3. LLM-as-Judge
4. 基线保存与回归比对
"""

from simulation.sandbox_core import (
    DEFAULT_SANDBOX_SEED,
    ConversationResult,
    MultiTurnSandboxRunner,
    RegressionDiff,
    SandboxSummary,
    TurnResult,
    compare_with_baseline,
    get_test_data,
    load_baseline,
    save_baseline,
    summarize_results,
)

__all__ = [
    "DEFAULT_SANDBOX_SEED",
    "TurnResult",
    "ConversationResult",
    "RegressionDiff",
    "SandboxSummary",
    "MultiTurnSandboxRunner",
    "get_test_data",
    "load_baseline",
    "save_baseline",
    "compare_with_baseline",
    "summarize_results",
]


def _print_scene_results(scene_id: str, results: list[ConversationResult], summary: SandboxSummary) -> None:
    print(f"\n{'=' * 60}")
    print(f"主沙盒: {scene_id}")
    print(f"{'=' * 60}")

    for result in results:
        status_icon = "[OK]" if result.outcome == "success" else "[FAIL]"
        avg_s = sum(t.strategy_score for t in result.turns) / len(result.turns) if result.turns else 0.0
        avg_d = sum(t.delivery_score for t in result.turns) / len(result.turns) if result.turns else 0.0
        print(f"  {status_icon} {result.persona_name}: {result.total_rounds}轮 | 综合 {result.avg_llm_score:.1f} | 策略 {avg_s:.1f} | 成品 {avg_d:.1f} | {result.outcome}")

    print("\n  汇总:")
    print(f"    成功: {summary.success_count}/{summary.total_conversations}")
    print(f"    失败: {summary.failure_count}")
    print(f"    超时: {summary.timeout_count}")
    print(f"    平均评分: {summary.avg_score:.1f}/10")
    print(f"    护栏违规: {summary.total_violations}")
    print(f"    错误轮次: {summary.total_error_turns}")
    print(f"    平均轮耗时: {summary.avg_turn_elapsed_ms:.1f}ms")
    print(f"    平均 Step2 耗时: {summary.avg_step2_elapsed_ms:.1f}ms")
    print(f"    平均 Step6 耗时: {summary.avg_step6_elapsed_ms:.1f}ms")
    print(f"    平均 Step8 耗时: {summary.avg_step8_elapsed_ms:.1f}ms")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="主沙盒：多轮进化与回归验证")
    parser.add_argument("--scene", default="all", choices=["sales", "management", "negotiation", "emotion", "all"])
    parser.add_argument("--rounds", type=int, default=5, help="每场对话最大轮数")
    parser.add_argument("--no-judge", action="store_true", help="关闭 LLM 打分")
    parser.add_argument("--save-baseline", action="store_true", help="保存当前结果为基线")
    parser.add_argument("--regression", action="store_true", help="用当前结果对比既有基线")
    parser.add_argument("--seed", type=int, default=DEFAULT_SANDBOX_SEED, help="固定随机种子，保证回归稳定")
    args = parser.parse_args()

    scenes = ["sales", "management", "negotiation", "emotion"] if args.scene == "all" else [args.scene]

    for scene_id in scenes:
        test_data = get_test_data(scene_id)
        runner = MultiTurnSandboxRunner(
            scene_id=scene_id,
            max_rounds=args.rounds,
            use_llm_judge=not args.no_judge,
            seed=args.seed,
        )
        results = runner.run_sandbox(test_data["personas"], test_data["inputs"])
        summary = summarize_results(scene_id, results)
        _print_scene_results(scene_id, results, summary)

        if args.regression:
            print("\n  回归检查:")
            diffs = compare_with_baseline(scene_id, results)
            if not diffs:
                print("    暂无基线，或还没有可对比的人格样本")
            else:
                for diff in diffs:
                    icon = "[OK]" if diff.is_identical else "[!!]"
                    detail = "一致" if diff.is_identical else f"有变化 (评分 {diff.score_delta:+.1f}, 轮次 {diff.changed_turns})"
                    print(f"    {icon} {diff.test_id}: {detail}")

        if args.save_baseline:
            path = save_baseline(scene_id, results)
            print(f"\n  基线已保存: {path}")
