from pathlib import Path

from scripts.run_merge_gate import evaluate_doc_consistency


def _build_workspace(tmp_path: Path, *, tests_count: int, scenes_count: int, readme_tests: int, readme_scenes: int, summary_tests: int, summary_scenes: int) -> Path:
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "01_active").mkdir(parents=True, exist_ok=True)

    for i in range(tests_count):
        (tmp_path / "tests" / f"test_{i}.py").write_text("pass\n", encoding="utf-8")
    for i in range(scenes_count):
        (tmp_path / "skills" / f"scene_{i}").mkdir(parents=True, exist_ok=True)

    readme = (
        f"[![Tests](https://img.shields.io/badge/tests-{readme_tests}%20files-brightgreen.svg)](tests/)\n"
        f"[![Scenes](https://img.shields.io/badge/scenes-{readme_scenes}-orange.svg)](skills/)\n"
    )
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")

    summary = (
        "| 指标 | 数值 |\n"
        "|:---|:---|\n"
        f"| 场景配置 | {summary_scenes} |\n"
        f"| 测试文件 | {summary_tests} |\n"
    )
    (tmp_path / "docs" / "01_active" / "PROJECT_SUMMARY.md").write_text(summary, encoding="utf-8")
    return tmp_path


def test_evaluate_doc_consistency_should_pass_when_counts_match(tmp_path: Path):
    base_dir = _build_workspace(
        tmp_path,
        tests_count=3,
        scenes_count=2,
        readme_tests=3,
        readme_scenes=2,
        summary_tests=3,
        summary_scenes=2,
    )
    passed, reasons = evaluate_doc_consistency(base_dir)
    assert passed is True
    assert reasons == []


def test_evaluate_doc_consistency_should_fail_when_counts_mismatch(tmp_path: Path):
    base_dir = _build_workspace(
        tmp_path,
        tests_count=3,
        scenes_count=2,
        readme_tests=4,
        readme_scenes=1,
        summary_tests=5,
        summary_scenes=9,
    )
    passed, reasons = evaluate_doc_consistency(base_dir)
    assert passed is False
    assert any("README tests 徽章不一致" in r for r in reasons)
    assert any("README scenes 徽章不一致" in r for r in reasons)
    assert any("PROJECT_SUMMARY 测试文件数不一致" in r for r in reasons)
    assert any("PROJECT_SUMMARY 场景配置数不一致" in r for r in reasons)
