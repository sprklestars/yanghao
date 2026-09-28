"""跨进程共享的小型 JSON 状态存储。

API 和守护进程是两个进程，内存里的黑名单、养号档案传不过去，所以统一落到
``backend/state/*.json``：按 ``(mtime, size)`` 自动重载（别的进程改完这边能读到），
写入用「临时文件 + 原子替换」，避免读到半截内容。
"""

import json
import os
import threading
from pathlib import Path


class JsonStore:
    """一个 JSON 文件的小封装；线程安全，按文件戳自动重载。"""

    def __init__(self, path: Path | str):
        self._path = Path(path)
        self._lock = threading.RLock()
        self._stamp: tuple[int, int] | None = None
        self._data: dict = {}

    @property
    def path(self) -> Path:
        return self._path

    def _current_stamp(self) -> tuple[int, int] | None:
        try:
            stat = self._path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def changed(self) -> bool:
        """文件是否被别的进程改过（用于"只在必要时重载"，保住对象引用）。"""
        with self._lock:
            return self._current_stamp() != self._stamp

    def load(self, force: bool = False) -> dict:
        """返回数据的浅拷贝；文件变了会自动重读。"""
        with self._lock:
            stamp = self._current_stamp()
            if stamp is None:
                if force or self._data:
                    self._data = {}
                    self._stamp = None
                return dict(self._data)

            if not force and stamp == self._stamp:
                return dict(self._data)

            try:
                raw = json.loads(self._path.read_text(encoding="utf-8") or "{}")
            except (OSError, ValueError):
                return dict(self._data)  # 读坏了就沿用内存副本

            self._data = raw if isinstance(raw, dict) else {}
            self._stamp = stamp
            return dict(self._data)

    def save(self, data: dict) -> None:
        with self._lock:
            self._data = dict(data)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_name(self._path.name + ".tmp")
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            try:
                os.replace(tmp, self._path)
            except OSError:
                # Windows 上偶发"目标被占用/ACL 拒绝"，退化为直接覆盖写，
                # 保证状态至少能落盘（这份数据很小，可接受）
                self._path.write_text(
                    json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                try:
                    tmp.unlink()
                except OSError:
                    pass
            self._stamp = self._current_stamp()
