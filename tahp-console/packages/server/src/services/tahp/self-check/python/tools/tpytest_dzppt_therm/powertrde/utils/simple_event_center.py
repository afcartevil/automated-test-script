import copy
from typing import Callable, Dict, List, Optional


class SimpleEvent:
    def __init__(self, name: str, *args, sender=None, tag=None, **kwargs):
        super().__init__()
        self._is_stop_propagate = False
        self._is_disposed = False
        self._name = name
        self.args = args
        self.kwargs = kwargs
        self.current_listener = None
        self.sender = sender
        self.tag = tag
        self.return_arg = None

    @property
    def name(self):
        return self._name

    @property
    def is_available(self):
        return not self._is_disposed and not self._is_stop_propagate

    def stop_propagate(self):
        self._is_stop_propagate = True

    def dispose(self):
        self._is_disposed = True
        self.current_listener = None

    def reuse(self):
        self._is_disposed = False
        self.current_listener = None
        self._is_stop_propagate = False
        self.return_arg = None

    def clone_and_reuse(self, sender):
        ins = copy.copy(self)
        ins.reuse()
        ins.sender = sender
        return ins


class SimpleEventListener:
    def __init__(self, listen_event_name: str, on_event_callback: Callable[[SimpleEvent], None]):
        self._listen_event_name = listen_event_name
        self.on_event_callback = on_event_callback
        self._is_available = True

    @property
    def listen_event_name(self):
        return self._listen_event_name

    @property
    def is_available(self):
        return self._is_available

    def invoke(self, event: SimpleEvent):
        event.current_listener = self
        self.on_event_callback(event)

    def dispose(self):
        self._is_available = False
        self.on_event_callback = None


class _InnerCountCtrl:
    def __init__(self, count, item_set):
        self.count = count
        self.item_set = item_set


class SimpleEventCenter:
    _instance: 'SimpleEventCenter' = None

    @staticmethod
    def get_instance() -> 'SimpleEventCenter':
        if not SimpleEventCenter._instance:
            SimpleEventCenter._instance = SimpleEventCenter()
        return SimpleEventCenter._instance

    def __init__(self):
        self._listeners: Dict[str, List[SimpleEventListener]] = {}
        self._dispatching_count: Dict[str, _InnerCountCtrl] = {}
        self.on_dispatch_event: Optional[Callable[[SimpleEvent], None]] = None

    def add_listener_directly(self, listener: SimpleEventListener):
        if listener.listen_event_name in self._listeners:
            self._listeners[listener.listen_event_name].append(listener)
        else:
            self._listeners[listener.listen_event_name] = [listener]

    def add_listener(self, listen_event_name: str,
                     on_event_callback: Callable[[SimpleEvent], None]) -> SimpleEventListener:
        listener = SimpleEventListener(listen_event_name, on_event_callback)
        self.add_listener_directly(listener)
        return listener

    def send_event(self, e: SimpleEvent):
        event_name = e.name
        if self.on_dispatch_event:
            self.on_dispatch_event(e)
        listeners_set = self._listeners.get(event_name)
        if not listeners_set:
            return
        count_item = None
        try:
            if event_name in self._dispatching_count:
                count_item = self._dispatching_count[event_name]
                count_item.count += 1
            else:
                count_item = _InnerCountCtrl(1, set())
                self._dispatching_count[event_name] = count_item
            for listener in listeners_set:
                if not e.is_available:
                    break
                if listener.is_available:
                    listener.invoke(e)
                else:
                    count_item.item_set.add(listener)
        finally:
            e.dispose()
            if count_item:
                count_item.count -= 1
                if not count_item.count:
                    if count_item.item_set:
                        new_listeners_set = [item for item in listeners_set if item not in count_item.item_set]
                        self._listeners[event_name] = new_listeners_set
                        count_item.item_set.clear()

    def dispatch_event(self, event_name: str, *args, sender=None, tag=None, **kwargs):
        e = SimpleEvent(event_name, *args, sender=sender, tag=tag, **kwargs)
        self.send_event(e)
        return e
