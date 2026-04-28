import json

from modules.L5 import counter_example_lib


def test_counter_example_path_not_dependent_on_cwd(monkeypatch, tmp_path):
    """默认反例库路径应锚定项目根目录，而不是当前工作目录"""
    monkeypatch.chdir(tmp_path)
    path = counter_example_lib._get_path("sales")

    assert path.name == "counter_examples.json"
    assert path.parent.name == "sales"
    assert path.parent.parent.name == "skills"
    assert "human-os-engine" in str(path)


def test_get_strategy_penalties_prunes_invalid_examples(tmp_path, monkeypatch):
    """读取惩罚前应先清掉无效 goal/strategy，避免串场数据污染运行结果"""
    sales_dir = tmp_path / "sales"
    sales_dir.mkdir(parents=True)
    path = sales_dir / "counter_examples.json"

    payload = [
        {
            "goal": "goal1",
            "strategy": "stratA",
            "context": {"emotion": "anger"},
            "timestamp": 1,
        },
        {
            "goal": "overcome_rejection",
            "strategy": "向上管理：说服保守型领导",
            "context": {"emotion": "平静"},
            "timestamp": 2,
        },
        {
            "goal": "overcome_rejection",
            "strategy": "共情+正常化",
            "context": {"emotion": "平静"},
            "timestamp": 99999999999,
        },
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(counter_example_lib, "COUNTER_EXAMPLES_DIR", str(tmp_path))
    monkeypatch.setattr(counter_example_lib.time, "time", lambda: 100000000000)

    penalties = counter_example_lib.get_strategy_penalties(
        "sales",
        "overcome_rejection",
        {"emotion": "平静"},
    )

    assert penalties == {"共情+正常化": 0.6}

    cleaned = json.loads(path.read_text(encoding="utf-8"))
    assert cleaned == [
        {
            "goal": "overcome_rejection",
            "strategy": "共情+正常化",
            "context": {"emotion": "平静"},
            "failure_type": "",
            "failure_code": "",
            "attribution": {},
            "timestamp": 99999999999,
        }
    ]


def test_infer_failure_code_should_return_f01_when_relevance_low():
    code = counter_example_lib.infer_failure_code(
        {"relevance": 3.5, "empathy": 7, "guidance": 7, "safety": 8, "overall": 5.5},
        context={},
        output_text="先说重点",
    )
    assert code.value == "F01"


def test_infer_failure_code_should_return_none_when_no_clear_failure_signal():
    code = counter_example_lib.infer_failure_code(
        {"relevance": 9, "empathy": 8, "guidance": 9, "safety": 10, "overall": 9},
        context={},
        output_text="我们继续。你最想先确认哪一块？",
    )
    assert code is None


def test_get_failure_hints_should_include_failure_code_hint(tmp_path, monkeypatch):
    sales_dir = tmp_path / "sales"
    sales_dir.mkdir(parents=True)
    path = sales_dir / "counter_examples.json"
    payload = [
        {
            "goal": "overcome_rejection",
            "strategy": "共情+正常化",
            "context": {"emotion": "平静"},
            "failure_type": "timing_error",
            "failure_code": "F02",
            "attribution": {"decision": "record_failure"},
            "timestamp": 100,
        },
        {
            "goal": "overcome_rejection",
            "strategy": "共情+正常化",
            "context": {"emotion": "平静"},
            "failure_type": "timing_error",
            "failure_code": "F02",
            "attribution": {"decision": "record_failure"},
            "timestamp": 200,
        },
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr(counter_example_lib, "COUNTER_EXAMPLES_DIR", str(tmp_path))
    monkeypatch.setattr(counter_example_lib.time, "time", lambda: 300)

    hints = counter_example_lib.get_failure_hints("sales", "overcome_rejection")
    assert any("F02" in hint for hint in hints)
