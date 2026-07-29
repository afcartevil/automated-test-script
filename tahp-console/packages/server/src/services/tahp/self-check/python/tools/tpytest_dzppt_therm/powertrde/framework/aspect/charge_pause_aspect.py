# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Any, Callable, Optional


class ChargePauseAspect:
    """充电暂停切面：通过线程事件协调“充电期间暂停等待”。
    参数：
        owner:    拥有该切面的对象实例（用于挂载事件属性）。
        event_attr: 事件对象在 owner 上的属性名，默认 "_charge_pause_event"。
        logger:   可选的日志记录器，需具有 .info/.debug 方法。
    """
    def __init__(self, owner: Any, event_attr: str = "_charge_pause_event", logger: Optional[Any] = None) -> None:
        self._owner = owner
        self._event_attr = event_attr
        self._logger = logger

    def _ensure_event(self) -> threading.Event:
        ev = getattr(self._owner, self._event_attr, None)
        if ev is None:
            ev = threading.Event()
            setattr(self._owner, self._event_attr, ev)
            if self._logger:
                self._logger.debug(f"[ChargePauseAspect] create event on attr='{self._event_attr}'")
        return ev

    @property
    def event(self) -> threading.Event:
        return self._ensure_event()

    def begin_pause(self, reason: Optional[str] = None) -> None:
        """置位暂停事件，在进入充电等待前调用。"""
        self.event.set()
        if self._logger:
            self._logger.info(f"[ChargePauseAspect] begin_pause reason={reason}")

    def end_pause(self) -> None:
        """清除暂停事件，在充电等待结束后调用（建议放在 finally 中）。"""
        self.event.clear()
        if self._logger:
            self._logger.info("[ChargePauseAspect] end_pause")

    def is_paused(self) -> bool:
        return self.event.is_set()

    def wait(self, min_gap_sec: float = 0.0, check_interval: float = 0.5) -> None:
        """在充电期间阻塞，结束后可再等待一个缓冲时间。
        参数：
            min_gap_sec: 充电结束后的附加缓冲秒数，默认 0；用于让系统状态稳定（可选）。
            check_interval: 轮询充电状态的间隔秒数。
        """
        while self.is_paused():
            time.sleep(check_interval)
        if min_gap_sec and min_gap_sec > 0:
            time.sleep(min_gap_sec)

    def wait_effective(self, total_seconds: float, stop_event: Optional[threading.Event] = None,
                        check_interval: float = 1.0) -> bool:
        """等待 total_seconds 秒，但充电暂停期间不累计等待时间。
        返回：
            True  -> 在等待过程中被 stop_event 中断
            False -> 正常等待完成
        """
        waited = 0.0
        # 统一步进以提高计时精度
        step = max(0.1, min(check_interval, 1.0))
        while waited < total_seconds:
            if stop_event is not None and stop_event.is_set():
                return True
            if self.is_paused():
                time.sleep(step)
                continue
            # 未暂停，累计有效等待时间
            time.sleep(step)
            waited += step
        return False

    def respecting_pause(self, min_gap_sec: float = 0.0) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """装饰器：在目标函数执行前自动等待充电结束。
        用法：
            @aspect.respecting_pause(min_gap_sec=0.2)
            def do_something(...):
                ...
        """
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                self.wait(min_gap_sec=min_gap_sec)
                return fn(*args, **kwargs)

            return wrapper

        return deco