"""
Human-OS Engine - 文件锁工具

提供跨平台的 JSON 文件安全读写，防止并发写入损坏数据。
使用线程锁 + 操作系统级文件锁（fcntl/MSVCRT）。
"""

import json
import os
import tempfile
import time
import threading
from contextlib import contextmanager

# 全局锁注册表（按文件路径）
_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_lock(path: str) -> threading.Lock:
    """获取指定文件的线程锁（进程内）"""
    abs_path = os.path.abspath(path)
    with _locks_lock:
        if abs_path not in _locks:
            _locks[abs_path] = threading.Lock()
        return _locks[abs_path]


@contextmanager
def _os_file_lock(target_path: str, timeout: float = 5.0, poll_interval: float = 0.05):
    """
    获取操作系统级文件锁（跨进程）。

    通过 sidecar `.lock` 文件锁定目标文件路径，避免多进程并发写冲突。
    """
    normalized_path = os.path.abspath(target_path)
    lock_path = f"{normalized_path}.lock"
    os.makedirs(os.path.dirname(normalized_path) or ".", exist_ok=True)
    lock_fp = open(lock_path, "a+b")
    acquired = False
    deadline = time.time() + max(timeout, 0.0)
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    # 锁住首字节，保证跨进程互斥
                    lock_fp.seek(0)
                    msvcrt.locking(lock_fp.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (OSError, BlockingIOError):
                if time.time() >= deadline:
                    raise TimeoutError(f"获取文件锁超时: {normalized_path}")
                time.sleep(poll_interval)
        yield
    finally:
        try:
            if acquired:
                if os.name == "nt":
                    import msvcrt
                    lock_fp.seek(0)
                    msvcrt.locking(lock_fp.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
        finally:
            lock_fp.close()


def safe_json_read(path: str, default=None):
    """
    安全读取 JSON 文件
    
    Args:
        path: 文件路径
        default: 文件不存在或解析失败时的默认值
    
    Returns:
        解析后的数据，或 default
    """
    if not os.path.exists(path):
        return default
    
    try:
        lock = _get_lock(path)
        with lock:
            with _os_file_lock(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def safe_json_write(path: str, data, retries: int = 3, retry_delay: float = 0.1):
    """
    安全写入 JSON 文件（原子写入 + 重试）
    
    使用临时文件 + 重命名实现原子写入，防止写入中断导致文件损坏。
    Windows 兼容：使用唯一临时文件名避免 PermissionError。
    
    Args:
        path: 目标文件路径
        data: 要写入的数据
        retries: 写入失败时的重试次数
        retry_delay: 重试间隔（秒）
    """
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    lock = _get_lock(path)
    
    for attempt in range(retries + 1):
        try:
            with lock:
                with _os_file_lock(path):
                    # 原子写入：先写临时文件，再重命名
                    # 使用唯一文件名避免 Windows PermissionError
                    dir_name = os.path.dirname(path) or "."
                    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                            f.flush()
                            os.fsync(f.fileno())

                        # 原子重命名
                        os.replace(tmp_path, path)
                    except Exception:
                        # 清理临时文件
                        if os.path.exists(tmp_path):
                            try:
                                os.remove(tmp_path)
                            except OSError:
                                pass
                        raise
            return  # 成功
            
        except (IOError, OSError) as e:
            if attempt < retries:
                time.sleep(retry_delay)
            else:
                raise
