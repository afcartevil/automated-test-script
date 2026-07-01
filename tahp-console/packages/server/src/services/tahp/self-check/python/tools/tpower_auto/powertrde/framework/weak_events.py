import weakref
import types


class WeakEvents:
    """
    实现弱引用事件的类，支持 += 添加、-= 移除回调，并在触发事件时自动清理已失效的回调。
    """

    def __init__(self):
        super().__init__()
        self._handlers = []

    def add(self, handler):
        if handler is None:
            return
        # 如果是绑定方法，则转换为 WeakMethod，否则直接存储
        if isinstance(handler, types.MethodType):
            # 绑定方法使用 WeakMethod，能自动在对象被回收时失效
            ref = weakref.WeakMethod(handler)
            self._handlers.append(ref)
        else:
            # 普通函数（或其他可调用对象）使用强引用保存
            self._handlers.append(handler)

    def remove(self, handler):
        if handler is None:
            return
        # 遍历 handlers，找到匹配的回调进行移除
        for stored in self._handlers[:]:
            if isinstance(stored, weakref.WeakMethod):
                if stored() is handler:
                    self._handlers.remove(stored)
            else:
                if stored == handler:
                    self._handlers.remove(stored)

    def fire(self, *args, **kwargs):
        if not self._handlers:
            return
        # 遍历回调列表时先复制一份，避免在遍历时修改列表
        for stored in self._handlers[:]:
            if isinstance(stored, weakref.WeakMethod):
                callback = stored()
                if callback is not None:
                    callback(*args, **kwargs)
                else:
                    # 如果回调对象已被回收，则清除该引用
                    self._handlers.remove(stored)
            else:
                stored(*args, **kwargs)

    __call__ = fire

    def __bool__(self):
        return bool(self._handlers)

    def __iadd__(self, handler):
        self.add(handler)
        return self

    def __isub__(self, handler):
        self.remove(handler)
        return self
