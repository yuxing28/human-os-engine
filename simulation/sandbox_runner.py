"""
Human-OS Engine - 兼容沙盒入口

说明：
老沙盒不再维护独立逻辑，这里只保留兼容壳。
真正的主沙盒已经统一到 simulation/sandbox_v2.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from simulation.sandbox_core import (
    DEFAULT_SANDBOX_SEED,
    MultiTurnSandboxRunner,
    get_test_data,
)


@dataclass
class SandboxResult:
    strategy_name: str
    scene_id: str
    total_runs: int
    passed_runs: int
    failed_runs: int
    pass_rate: float
    avg_trust_delta: float = 0.0
    avg_emotion_delta: float = 0.0
    guardrail_violations: list = field(default_factory=list)
    details: list = field(default_factory=list)

    @property
    def is_approved(self) -> bool:
        return self.pass_rate >= 0.85 and len(self.guardrail_violations) == 0


class SandboxRunner:
    """
    兼容旧调用方式。

    内部已经改成调用主沙盒的单轮快速模式，
    不再维护旧版独立判断逻辑。
    """

    def __init__(self, scene_id: str = "sales", runs_per_case: int = 3, seed: int = DEFAULT_SANDBOX_SEED):
        self.scene_id = scene_id
        self.runs_per_case = runs_per_case
        self.seed = seed
        self.runner = MultiTurnSandboxRunner(
            scene_id=self.scene_id,
            max_rounds=1,
            use_llm_judge=False,
            seed=self.seed,
        )

    def run_single(self, user_input: str, persona: dict, run_index: int = 0) -> dict:
        result = self.runner.run_conversation(persona, user_input)
        turn = result.turns[0] if result.turns else None
        output = turn.system_output if turn else ""
        violations = turn.guardrail_violations if turn else []
        passed = bool((output or "").strip()) and not any(v["severity"] == "critical" for v in violations)
        return {
            "input": user_input,
            "persona": persona["name"],
            "output": output[:200],
            "output_length": len(output),
            "passed": passed,
            "violations": violations,
            "elapsed_ms": turn.elapsed_ms if turn else 0,
        }

    def run_sandbox(self) -> SandboxResult:
        test_data = get_test_data(self.scene_id)
        personas = test_data["personas"]
        inputs = test_data["inputs"]

        details = []
        all_violations = []
        total_runs = 0
        passed_runs = 0
        failed_runs = 0
        run_index = 0

        for persona in personas:
            for user_input in inputs:
                for _ in range(self.runs_per_case):
                    result = self.run_single(user_input, persona, run_index=run_index)
                    run_index += 1
                    total_runs += 1
                    details.append(result)
                    all_violations.extend(result["violations"])
                    if result["passed"]:
                        passed_runs += 1
                    else:
                        failed_runs += 1

        pass_rate = passed_runs / total_runs if total_runs else 0.0
        return SandboxResult(
            strategy_name=f"{self.scene_id}_compat",
            scene_id=self.scene_id,
            total_runs=total_runs,
            passed_runs=passed_runs,
            failed_runs=failed_runs,
            pass_rate=pass_rate,
            guardrail_violations=all_violations,
            details=details,
        )


def run_all_scenes(runs_per_case: int = 3, seed: int = DEFAULT_SANDBOX_SEED) -> dict[str, SandboxResult]:
    scenes = ["sales", "management", "negotiation", "emotion"]
    results = {}
    for scene_id in scenes:
        runner = SandboxRunner(scene_id=scene_id, runs_per_case=runs_per_case, seed=seed)
        results[scene_id] = runner.run_sandbox()
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="兼容沙盒入口（内部转发到主沙盒）")
    parser.add_argument("--scene", default="all", choices=["sales", "management", "negotiation", "emotion", "all"])
    parser.add_argument("--runs", type=int, default=3, help="每个用例运行次数")
    parser.add_argument("--seed", type=int, default=DEFAULT_SANDBOX_SEED, help="固定随机种子")
    args = parser.parse_args()

    if args.scene == "all":
        results = run_all_scenes(runs_per_case=args.runs, seed=args.seed)
        print("兼容沙盒结果（底层已切到主沙盒）")
        for scene_id, result in results.items():
            status = "✅" if result.is_approved else "❌"
            print(f"  {status} {scene_id}: {result.pass_rate:.1%} ({result.passed_runs}/{result.total_runs})")
    else:
        runner = SandboxRunner(scene_id=args.scene, runs_per_case=args.runs, seed=args.seed)
        result = runner.run_sandbox()
        status = "✅ 通过" if result.is_approved else "❌ 未通过"
        print(f"场景: {result.scene_id}")
        print(f"总运行: {result.total_runs}")
        print(f"通过: {result.passed_runs} | 失败: {result.failed_runs}")
        print(f"通过率: {result.pass_rate:.1%}")
        print(f"护栏违规: {len(result.guardrail_violations)}")
        print(f"状态: {status}")
