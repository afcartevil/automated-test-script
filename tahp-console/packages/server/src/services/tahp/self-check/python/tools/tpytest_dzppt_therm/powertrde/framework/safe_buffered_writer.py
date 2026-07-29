import threading
import time
import os
from typing import List, Optional

from powertrde import env


class _GlobalFlusher:
    _writers: List["SafeBufferedWriter"] = []
    _lock = threading.Lock()
    _thread: Optional[threading.Thread] = None
    _stop = threading.Event()
    _hooks_registered = False
    _temp_writers = []

    @classmethod
    def initialize(cls):
        """在主线程调用，注册退出/信号钩子并启动后台线程（一次性）。"""
        with cls._lock:
            if not cls._hooks_registered:
                cls._register_exit_hooks()
                cls._hooks_registered = True
            if cls._thread is None:
                cls._thread = threading.Thread(target=cls._run, daemon=True)
                cls._thread.start()

    @classmethod
    def register(cls, writer: "SafeBufferedWriter"):
        """将新增的写入器加入列表；后台线程已由 initialize 启动。"""
        with cls._lock:
            cls._writers.append(writer)

    @classmethod
    def unregister(cls, writer: "SafeBufferedWriter"):
        """从列表移除写入器；若无任何写入器，则停止后台线程。"""
        with cls._lock:
            if writer in cls._writers:
                cls._writers.remove(writer)
            # if not cls._writers:
            #     cls._stop.set()

    @classmethod
    def _run(cls):
        """后台线程：每秒检查一次所有写入器，看是否到达其下次 flush 时间。"""
        while not cls._stop.wait(1.0):
            now = time.time()
            with cls._lock:
                for w in cls._writers:
                    if now >= w.next_flush_time:
                        cls._temp_writers.append(w)

            if cls._temp_writers:
                for w in cls._temp_writers:
                    try:
                        w.flush(request_flush_time=now)
                    except Exception:
                        pass
                cls._temp_writers.clear()

    @classmethod
    def flush_all(cls):
        # 标记停止，刷新所有并关闭
        now = time.time()
        with cls._lock:
            for w in cls._writers:
                try:
                    w.flush(request_flush_time=now)
                except Exception:
                    pass

    @classmethod
    def close_all(cls):
        with cls._lock:
            writers = list(cls._writers)
            cls._writers.clear()
        for w in writers:
            try:
                w.close()
            except Exception:
                pass

    @classmethod
    def _register_exit_hooks(cls):
        """注册 atexit 及主线程信号钩子，一次性完成。"""

        def _close_all_with_stop(*_):
            # 标记停止，刷新所有并关闭
            cls._stop.set()
            with cls._lock:
                writers = list(cls._writers)
            for w in writers:
                try:
                    w.close()
                except Exception:
                    pass

        env.interrupt_signal_manager.register(_close_all_with_stop)
        # atexit.register(_close_all_with_stop)
        # if threading.current_thread() is threading.main_thread():
        #     try:
        #         signal.signal(signal.SIGINT, _close_all_with_stop)
        #         signal.signal(signal.SIGTERM, _close_all_with_stop)
        #     except ValueError:
        #         # 某些环境下无法注册信号
        #         pass


class SafeBufferedWriter:
    @staticmethod
    def initialize_flusher():
        """
        提前在主线程调用一次，完成全局钩子注册及后台线程启动，
        之后各实例只需 register 即可，无需重复钩子注册。
        """
        _GlobalFlusher.initialize()

    def __init__(self,
                 path: str,
                 flush_interval: float = 5.0,
                 max_buffer_size: int = 64 * 1024,
                 encoding: str = 'utf-8'):
        """
        :param path: 输出文件路径
        :param flush_interval: 定时刷盘间隔（秒）
        :param max_buffer_size: 缓冲区字节阈值，达到即刻刷盘
        :param encoding: 文本编码
        """
        self._file = open(path, 'a', encoding=encoding)
        self._encoding = encoding
        self._buffer: List[bytes] = []
        self._buffer_size = 0
        self._lock = threading.Lock()
        self._flush_interval = flush_interval
        self._max_buffer_size = max_buffer_size
        # 最后一次刷盘时间
        self._last_flush_time = time.time()
        self._next_flush_time = None

        # 注册到全局刷新器
        _GlobalFlusher.register(self)

    @property
    def last_flush_time(self):
        return self._last_flush_time

    @last_flush_time.setter
    def last_flush_time(self, value):
        self._last_flush_time = value
        self._next_flush_time = None

    @property
    def next_flush_time(self):
        if self._next_flush_time is None:
            self._next_flush_time = self._last_flush_time + self._flush_interval
        return self._next_flush_time

    def write(self, text: str) -> None:
        """线程安全地写入内存缓冲，并在累积到阈值时立即刷盘。"""
        data = text.encode(self._encoding)
        with self._lock:
            self._buffer.append(data)
            self._buffer_size += len(data)
            if self._buffer_size >= self._max_buffer_size:
                self.flush(with_lock=False)

    def flush(self, request_flush_time=None, with_lock=True):
        if request_flush_time and request_flush_time <= self._last_flush_time:
            return

        if with_lock:
            self._lock.acquire(blocking=True)
        try:
            self._flush_locked()
            if not request_flush_time:
                request_flush_time = time.time()
            self.last_flush_time = request_flush_time
        finally:
            if with_lock:
                self._lock.release()

    def _flush_locked(self):
        """
        （必须在持锁情况下调用）将缓冲区内容写入磁盘并 fsync。
        """
        if not self._buffer:
            return
        try:
            for chunk in self._buffer:
                self._file.write(chunk.decode(self._encoding))
            self._file.flush()
            os.fsync(self._file.fileno())
        except Exception:
            pass
        finally:
            self._buffer.clear()
            self._buffer_size = 0

    def close(self):
        """停止刷新并关闭文件，做一次最终刷盘。"""
        with self._lock:
            self._flush_locked()
            try:
                self._file.close()
            except Exception:
                pass
        _GlobalFlusher.unregister(self)

    @classmethod
    def flush_all(cls):
        _GlobalFlusher.flush_all()

    @classmethod
    def close_all(cls):
        _GlobalFlusher.close_all()
