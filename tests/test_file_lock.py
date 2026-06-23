import multiprocessing as mp
import time

from utils.file_lock import _os_file_lock, safe_json_read, safe_json_write


def _writer_worker(path: str, worker_id: int, rounds: int):
    for idx in range(rounds):
        payload = {
            "worker_id": worker_id,
            "round": idx,
            "message": f"writer-{worker_id}-{idx}",
            "values": list(range(10)),
        }
        safe_json_write(path, payload)
        time.sleep(0.01)


def test_safe_json_write_survives_multi_process_contention(tmp_path):
    target = str(tmp_path / "shared.json")
    ctx = mp.get_context("spawn")
    processes = [
        ctx.Process(target=_writer_worker, args=(target, worker_id, 8))
        for worker_id in range(4)
    ]

    for proc in processes:
        proc.start()
    for proc in processes:
        proc.join(timeout=20)

    for proc in processes:
        assert proc.exitcode == 0, f"writer process failed: pid={proc.pid}, exit={proc.exitcode}"

    data = safe_json_read(target)
    assert isinstance(data, dict)
    assert set(data.keys()) == {"worker_id", "round", "message", "values"}
    assert isinstance(data["worker_id"], int)
    assert isinstance(data["round"], int)
    assert data["message"].startswith("writer-")
    assert data["values"] == list(range(10))


def test_os_file_lock_times_out_when_contended(tmp_path):
    target = str(tmp_path / "contended.json")

    with _os_file_lock(target, timeout=1.0):
        start = time.time()
        try:
            with _os_file_lock(target, timeout=0.2, poll_interval=0.05):
                raise AssertionError("nested lock unexpectedly acquired")
        except TimeoutError:
            elapsed = time.time() - start

    assert elapsed >= 0.15

