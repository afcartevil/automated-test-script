"""
轻量级内嵌 i18n 实现（可隐式转换为字符串，支持全局语言切换与弱事件监听）

主要类:
  - I18n: 创建翻译对象：I18n({"en":"Hello {name}", "zh":"你好 {name}"}, key="greet")
  - I18n.format(...): 返回 I18nRendered，可隐式 str() 并在全局语言切换时自动反映新语言
  - I18n.set_locale / get_locale: 全局语言设置（线程安全）
  - add_locale_change_listener / remove_locale_change_listener: 弱引用回调管理
"""

from typing import Dict, Callable, Optional, Tuple
import threading
import weakref
import itertools

# -----------------------
# 内部：弱回调包装
# -----------------------
def _make_weak_callable(cb):
    """
    为 callback 创建可调用的弱引用封装。返回一个元组 (is_alive_func, call_func, cleanup_token)
    - 支持普通函数、lambda、bound method（WeakMethod）
    - cleanup_token 可用于从监听集合中比较移除
    """
    if hasattr(cb, "__self__") and hasattr(cb, "__func__"):  # bound method
        wm = weakref.WeakMethod(cb)

        def is_alive():
            return wm() is not None

        def call(*a, **kw):
            fn = wm()
            if fn is None:
                raise ReferenceError("referent dead")
            return fn(*a, **kw)

        token = ("wm", id(wm), getattr(cb, "__self__", None).__class__.__name__)
        return is_alive, call, token
    else:
        # functions and callable objects may be weakref-able
        try:
            wr = weakref.ref(cb)

            def is_alive():
                return wr() is not None

            def call(*a, **kw):
                fn = wr()
                if fn is None:
                    raise ReferenceError("referent dead")
                return fn(*a, **kw)

            token = ("wf", id(wr))
            return is_alive, call, token
        except TypeError:
            # not weakref-able (rare), fall back to strong ref but mark as 'strong' token
            def is_alive():
                return True

            def call(*a, **kw):
                return cb(*a, **kw)

            token = ("strong", id(cb))
            return is_alive, call, token


# -----------------------
# I18n 主体实现
# -----------------------
class I18n:
    """
    轻量 i18n 对象。

    创建:
        t = I18n({"en":"Hello {name}", "zh":"你好 {name}"}, key="greet")

    隐式字符串化:
        str(t) -> 根据当前全局 locale 返回相应文本（无格式参数）
        r = t.format(name="Alice"); str(r) -> "Hello Alice" or "你好 Alice" (随 locale 变化)

    全局 locale:
        I18n.set_locale("zh")
        I18n.get_locale()

    监听语言切换 (弱回调):
        token = I18n.add_locale_change_listener(callback)
        I18n.remove_locale_change_listener(token)
    """
    # 全局 locale 与监听集合（类变量）
    _locale_lock = threading.RLock()
    _current_locale: Optional[str] = None
    _listeners = {}  # token -> (is_alive_func, call_func)
    _listener_id_counter = itertools.count(1)
    _has_auto_init_locale = False

    # 全局 fallback locales  (例如: ["en"])
    _global_fallbacks = []

    @classmethod
    def set_global_fallbacks(cls, fallbacks):
        with cls._locale_lock:
            cls._global_fallbacks = list(fallbacks or [])

    @classmethod
    def add_locale_change_listener(cls, callback: Callable[[str, str], None]):
        """
        添加弱回调。callback(old_locale, new_locale)。
        返回 token（用于 remove）。
        """
        is_alive, call, token = _make_weak_callable(callback)
        lid = next(cls._listener_id_counter)
        with cls._locale_lock:
            cls._listeners[lid] = (is_alive, call, token)
        return lid

    @classmethod
    def remove_locale_change_listener(cls, token_id: int):
        with cls._locale_lock:
            return cls._listeners.pop(token_id, None) is not None

    @classmethod
    def _notify_locale_change(cls, old, new):
        # 复制 keys 以避免回调修改集合引发竞态
        dead = []
        with cls._locale_lock:
            items = list(cls._listeners.items())
        for lid, (is_alive, call, _tok) in items:
            if not is_alive():
                dead.append(lid)
                continue
            try:
                # call synchronously; 捕获异常避免影响其他回调
                call(old, new)
            except Exception:
                # 忽略回调异常（调用者应自行日志）
                pass
        if dead:
            with cls._locale_lock:
                for d in dead:
                    cls._listeners.pop(d, None)

    @classmethod
    def set_locale(cls, locale: Optional[str]):
        """
        设定全局当前语言（locale），为 None 表示 'no preference'。
        切换时会触发回调 (old, new)。
        """
        cls._has_auto_init_locale = True
        with cls._locale_lock:
            old = cls._current_locale
            if old == locale:
                return
            cls._current_locale = locale
        # 通知在锁外（避免死锁）
        cls._notify_locale_change(old, locale)

    @classmethod
    def get_locale(cls) -> Optional[str]:
        with cls._locale_lock:
            return cls._current_locale

    @classmethod
    def fast_create(cls, en: Optional[str] = None, zh: Optional[str] = None):
        if en is None and zh is None:
            en = ''
        _d = {}
        if en is not None:
            _d['en'] = en
        if zh is not None:
            _d['zh'] = zh
        return cls(_d)

    @classmethod
    def fast_create_as_str(cls, en: Optional[str] = None, zh: Optional[str] = None):
        return str(cls.fast_create(en, zh))

    @classmethod
    def gen_str(cls, en: Optional[str] = None, zh: Optional[str] = None):
        return cls.fast_create_as_str(en, zh)

    def __init__(
            self,
            translations: Dict[str, str],
            *,
            key: Optional[str] = None,
            fallback_locales: Optional[Tuple[str, ...]] = None,
            strict_format: bool = False
    ):
        """
        translations: dict mapping locale -> message template (using str.format)
        key: 可选标识符（仅用于调试/标识）
        fallback_locales: 可选实例级回退序列（优先于全局回退）
        strict_format: 若 True 则在格式化缺失参数时抛出异常（默认 False: 安全回退）
        """
        if not isinstance(translations, dict):
            raise TypeError("translations must be a dict of locale->str")
        self._translations = dict(translations)  # shallow copy
        self.key = key
        self.fallback_locales = list(fallback_locales or [])
        self.strict_format = bool(strict_format)
        # we keep a weakref to self for rendered objects to avoid cycles
        self_weak = weakref.ref(self)
        self._self_weak = self_weak

    # -------------------------
    # 运行时修改/查询翻译
    # -------------------------
    def set_translation(self, locale: str, text: str):
        self._translations[locale] = text

    def get_translation(self, locale: str) -> Optional[str]:
        return self._translations.get(locale)

    def available_locales(self):
        return list(self._translations.keys())

    # -------------------------
    # 回退逻辑
    # -------------------------
    def _resolve_locale_order(self, preferred: Optional[str]) -> list:
        """
        返回尝试的 locale 列表（按优先级）。
        优先级：
          1. preferred（通常来自全局 current locale）
          2. 实例级 fallback_locales（若有）
          3. 类级 global_fallbacks
          4. translations 中任意一个 key（最后保底）
        """
        order = []
        if preferred:
            order.append(preferred)
        for fb in self.fallback_locales:
            if fb not in order:
                order.append(fb)
        for fb in I18n._global_fallbacks:
            if fb not in order:
                order.append(fb)
        # finally, include any available locale not already in list
        for l in self._translations.keys():
            if l not in order:
                order.append(l)
        return order

    # -------------------------
    # 获取最终文本（未格式化）
    # -------------------------
    def _select_text_for_locale(self, locale: Optional[str]) -> str:
        order = self._resolve_locale_order(locale)
        for l in order:
            txt = self._translations.get(l)
            if txt is not None:
                return txt
        # nothing found
        return ""

    # -------------------------
    # 格式化（安全/严格两种策略）
    # -------------------------
    @staticmethod
    def _safe_format(template: str, args: tuple, kwargs: dict, strict: bool):
        if template is None:
            template = ""
        # 优先用标准 format（严格）
        try:
            return template.format(*args, **kwargs)
        except (KeyError, IndexError) as e:
            if strict:
                raise
            # 降级：用 default dict 把缺失 key 替为空串，然后再 format_map
            try:
                # positional may have caused IndexError; handle by mapping numeric keys too
                # We'll try a best-effort: attempt format with kwargs only,
                # and replace missing named keys with empty string.
                class _DefaultDict(dict):
                    def __missing__(self, key):
                        return ""

                if kwargs:
                    return template.format_map(_DefaultDict(kwargs))
                else:
                    # try remove positional placeholders by replacing {0},{1} etc with empty
                    # simple fallback: format_map won't help for positional, so do a minimal replacement
                    return template.format_map(_DefaultDict({}))
            except Exception:
                # 最后保底返回原始模板
                return template

    # -------------------------
    # 生成渲染对象（保留引用到本实例以便语言切换有效）
    # -------------------------
    def format(self, *args, **kwargs):
        """
        返回 I18nRendered：当你需要格式化并重复使用同一翻译对象时调用。
        例如：
            t = I18n({"en":"Hi {name}", "zh":"嗨 {name}"})
            r = t.format(name="Bob")
            print(str(r))  # current locale
        渲染对象保存对原 I18n 的弱引用（不会导致循环引用），并在 locale 切换时自动反映。
        """
        return I18nRendered(self._self_weak, args, kwargs, strict=self.strict_format)

    # -------------------------
    # 隐式字符串化（不带参数）
    # -------------------------
    def __str__(self):
        """
        返回当前 locale 的翻译文本。
        """
        # 尝试自动从环境获取语言
        if not self._has_auto_init_locale:
            from powertrde import env
            _tl = env.scheme.tool_language
            if _tl:
                I18n.set_locale(_tl)
            else:
                self._has_auto_init_locale = True

        cur = I18n.get_locale()
        template = self._select_text_for_locale(cur)
        return self._safe_format(template, (), {}, self.strict_format)

    def __repr__(self):
        return f"<I18n key={self.key!r} locales={list(self._translations.keys())!r}>"

    def to_str(self):
        return str(self)


# -----------------------
# 渲染器类：引用 I18n（弱引用）并保存参数
# -----------------------
class I18nRendered:
    """
    渲染对象：持有对 I18n 的弱引用与格式化参数。
    对 str() 的求值会读取当前全局 locale 并执行格式化。
    """

    def __init__(self, i18n_weakref: "weakref.ref[I18n]", args: tuple, kwargs: dict, *, strict=False):
        self._i18n_wr = i18n_weakref
        # 保存参数的浅拷贝
        self._args = tuple(args)
        self._kwargs = dict(kwargs)
        self._strict = strict

    def _get_template_and_strict(self):
        i18n_obj = self._i18n_wr()
        if i18n_obj is None:
            return "", self._strict
        cur = I18n.get_locale()
        tmpl = i18n_obj._select_text_for_locale(cur)
        # inherit strict if instance uses strict
        return tmpl, i18n_obj.strict_format or self._strict

    def __str__(self):
        # 尝试自动从环境获取语言
        if not I18n._has_auto_init_locale:
            from powertrde import env
            _tl = env.scheme.tool_language
            if _tl:
                I18n.set_locale(_tl)
            else:
                I18n._has_auto_init_locale = True

        template, strict = self._get_template_and_strict()
        return I18n._safe_format(template, self._args, self._kwargs, strict)

    def __repr__(self):
        i = self._i18n_wr()
        if i is None:
            return "<I18nRendered (orphaned)>"
        return f"<I18nRendered key={i.key!r} locales={list(i._translations.keys())!r} args={self._args} kwargs={self._kwargs}>"


I18n.set_global_fallbacks(["zh", "en"])

# -----------------------
# 使用示例与单元演示
# -----------------------
if __name__ == "__main__":
    # demo translations
    t = I18n({"en": "Hello {name}", "zh": "你好 {name}", "fr": "Bonjour {name}"}, key="greeting")
    # set defaults and fallback
    # I18n.set_global_fallbacks(["en"])
    I18n.set_locale("en")
    print(str(t))  # "Hello {name}" (no format parameters)

    r = t.format(name="Alice")
    print(str(r))  # "Hello Alice"

    I18n.set_locale("zh")
    print(str(r))  # "你好 Alice"  <-- 切换语言即时生效

    # 安全的参数缺失处理（默认 non-strict）
    t2 = I18n({"en": "User {name} logged in from {ip}"}, key="log")
    I18n.set_locale("en")
    print(str(t2.format(name="bob")))  # "User bob logged in from " (ip 替为空串)

    # 严格模式（抛出异常）
    t3 = I18n({"en": "X {0} {1}"}, key="strict", strict_format=True)
    try:
        print(str(t3.format("a")))  # IndexError -> strict 模式会抛出
    except Exception as e:
        print("strict format error:", e)


    # 监听语言切换（弱引用）
    def on_lang_change(old, new):
        print("[listener] locale changed", old, "->", new)


    token = I18n.add_locale_change_listener(on_lang_change)
    I18n.set_locale("fr")
    I18n.remove_locale_change_listener(token)
    I18n.set_locale("en")


    # 验证绑定方法的弱引用（bound method）
    class X:
        def handler(self, old, new):
            print("X.handler called", old, "->", new)


    x = X()
    tkn2 = I18n.add_locale_change_listener(x.handler)
    I18n.set_locale("zh")
    # 删除 x 后，不应再收到回调
    del x
    I18n.set_locale("en")

    print("demo done")
