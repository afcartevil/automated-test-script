# func_timeout_injector.py
"""
动态检测并注入 / 更新 func_set_timeout 的工具（兼容 kata198/func_timeout 的实现）
功能：
 - is_wrapped_by_func_timeout(func): 检测是否已被 func_set_timeout 包装
 - update_timeout_in_wrapper(wrapper, new_timeout): 就地更新 wrapper 的 defaultTimeout（若可能）
 - replace_definition_with_wrapper(orig_func, new_wrapper): 尝试把模块或类定义上的引用替换为 new_wrapper
 - ensure_func_set_timeout(func, timeout, allow_override=False): 主入口：保证 func 在定义处（或至少为该 item）被 func_set_timeout(timeout) 包裹且只包一次
"""
from types import FunctionType, MethodType
import inspect
import logging
import functools

logger = logging.getLogger(__name__)

# 用于记录已经注入过的底层原始函数 id（防止重复注入）
_INJECTED_FN_IDS = set()


def _make_cell(value):
    """构造一个新的 closure cell（常用技巧）"""
    # lambda 会创建一个闭包，其 __closure__[0] 就是持有 value 的 cell
    return (lambda x=value: lambda: x)().__closure__[0]


def _rebuild_function_with_new_closure(func, new_cells):
    """
    使用 func.__code__ / func.__globals__ / func.__name__ / func.__defaults__ / new closure 重建 function
    返回新的 function object（并尽量拷贝元数据）
    """
    newf = FunctionType(func.__code__, func.__globals__, name=func.__name__,
                        argdefs=func.__defaults__, closure=new_cells)
    # 复制属性（保留 wraps 元数据）
    try:
        newf.__kwdefaults__ = func.__kwdefaults__
    except Exception:
        pass
    try:
        newf.__annotations__ = getattr(func, '__annotations__', {})
    except Exception:
        pass
    # preserve __qualname__ and docstring
    newf.__qualname__ = getattr(func, '__qualname__', newf.__name__)
    newf.__doc__ = getattr(func, '__doc__', None)
    # try to preserve __wrapped__ chain if any
    if hasattr(func, "__wrapped__"):
        try:
            newf.__wrapped__ = func.__wrapped__
        except Exception:
            pass
    return functools.update_wrapper(newf, getattr(func, "__wrapped__", func), assigned=functools.WRAPPER_ASSIGNMENTS)


def is_func_timeout_wrapper(func):
    """
    检测 func（可能是 wrapper）是否调用了 func_timeout（即由 func_set_timeout 生成的 wrapper）。
    返回 tuple (wrapper_obj, info_dict) 或 None
    info_dict 包含： 'found_name': freevar name like 'defaultTimeout' 或 'timeoutFunction'
                     'freevars': wrapper.__code__.co_freevars
                     'cell_values': tuple of closure cell values (if any)
    说明：会沿着 __wrapped__ 链向下扫描到第一个匹配到的 wrapper。
    """
    cur = func
    while cur is not None:
        if not isinstance(cur, FunctionType):
            # bound method -> get underlying function
            if isinstance(cur, MethodType):
                cur = cur.__func__
            else:
                break
        code = cur.__code__
        names = code.co_names
        # heuristic: func_timeout 必然在 co_names 中（因为 wrapper 内调用了 func_timeout）
        if 'func_timeout' in names or 'FunctionTimedOut' in names:
            freevars = code.co_freevars or ()
            closure_vals = tuple(c.cell_contents for c in (cur.__closure__ or ())) if cur.__closure__ else ()
            # prefer defaultTimeout if present
            found = None
            for candidate in ('defaultTimeout', 'timeoutFunction'):
                if candidate in freevars:
                    found = candidate
                    break
            return cur, {'found_name': found, 'freevars': freevars, 'cell_values': closure_vals}
        # move on
        if hasattr(cur, '__wrapped__'):
            cur = getattr(cur, '__wrapped__')
        else:
            break
    return None


def _find_owner_and_replace(func, new_callable):
    """
    尝试把 func 所在的位置替换为 new_callable。
    可能的场景：
      - module-level function: setattr(module, name, new_callable)
      - class-level function/method: setattr(cls, name, new_callable)
      - instance bound method: 替换类属性
    返回 True if replaced.
    """
    # bound method -> use underlying function and class
    if isinstance(func, MethodType):
        func = func.__func__
        inst = func.__self__ if hasattr(func, '__self__') else None

    mod = inspect.getmodule(func)
    name = getattr(func, "__name__", None)
    qualname = getattr(func, "__qualname__", "")
    # 1) try module-level replacement
    if mod and name:
        try:
            if getattr(mod, name, None) is func:
                setattr(mod, name, new_callable)
                logger.debug("Replaced module-level function %s in module %s", name, mod)
                return True
        except Exception:
            pass
    # 2) try class-level replacement using qualname
    # qualname for method: "ClassName.func"
    if mod and qualname and '.' in qualname:
        cls_name = qualname.split('.')[0]
        cls = getattr(mod, cls_name, None)
        if isinstance(cls, type):
            try:
                existing = getattr(cls, name, None)
                # Python stores function as function object on class; bound method comes at access time
                if existing is func or (isinstance(existing, (FunctionType, classmethod, staticmethod))):
                    # set new as function (not bound); if existing was staticmethod/classmethod, preserve descriptor type
                    if isinstance(existing, staticmethod):
                        setattr(cls, name, staticmethod(new_callable))
                    elif isinstance(existing, classmethod):
                        setattr(cls, name, classmethod(new_callable))
                    else:
                        setattr(cls, name, new_callable)
                    logger.debug("Replaced class-level method %s.%s", cls_name, name)
                    return True
            except Exception:
                pass
    # 3) fallback: iterate over loaded modules to find a reference? (too invasive) -> skip
    return False


def _wrap_with_func_set_timeout(func, timeout, allow_override=False, func_set_timeout_decorator=None):
    """
    生成由 func_set_timeout(timeout, allowOverride) 产生的包装函数对象（不负责替换定义处）
    func_set_timeout_decorator: 注入时可传入实际的库装饰器（便于单测/解耦）
    """
    if func_set_timeout_decorator is None:
        # 延迟导入，避免顶层依赖问题
        try:
            from func_timeout import func_set_timeout as _fst
            func_set_timeout_decorator = _fst
        except Exception as e:
            raise RuntimeError("无法导入 func_set_timeout 库: %s" % e)
    decorator = func_set_timeout_decorator(timeout, allowOverride=allow_override)
    new_wrapper = decorator(func)
    # 标记新 wrapper，便于未来识别（非必须）
    try:
        setattr(new_wrapper, "__func_set_timeout_wrapper__", True)
        setattr(new_wrapper, "__timeout_value__", float(timeout))
    except Exception:
        pass
    return new_wrapper


def _try_update_wrapper_default_timeout(wrapper_func, new_timeout):
    """
    尝试就地更新 wrapper_func 闭包里的 defaultTimeout 值（适用于 func_set_timeout 生成的 wrapper）
    返回 True if 成功（即新的函数对象已替换并 caller 可置换）
    实现：
      - 查找 wrapper_func.__code__.co_freevars 中是否有 'defaultTimeout'
      - 如果存在，构造新的 closure cell tuple，并用 types.FunctionType 重建函数对象返回
    注意：调用方需负责把新的函数对象替换到定义处（module/class）或 item 上。
    """
    if not isinstance(wrapper_func, FunctionType):
        return None
    freevars = wrapper_func.__code__.co_freevars or ()
    if 'defaultTimeout' not in freevars:
        return None
    # find index
    idx = freevars.index('defaultTimeout')
    old_cells = wrapper_func.__closure__ or ()
    # build new cells: copy all old, but replace idx with new cell for new_timeout
    new_cells = []
    for i, cell in enumerate(old_cells):
        if i == idx:
            new_cells.append(_make_cell(float(new_timeout)))
        else:
            new_cells.append(cell)
    # ensure length matches co_freevars
    new_cells_tuple = tuple(new_cells)
    new_func = _rebuild_function_with_new_closure(wrapper_func, new_cells_tuple)
    # preserve some markers
    try:
        if hasattr(wrapper_func, "__func_set_timeout_wrapper__"):
            setattr(new_func, "__func_set_timeout_wrapper__", getattr(wrapper_func, "__func_set_timeout_wrapper__"))
    except Exception:
        pass
    return new_func


def ensure_func_set_timeout(target_callable, timeout, allow_override=False, func_set_timeout_decorator=None):
    """
    主接口：确保 target_callable（可以是 module function, class method, bound method, or plain function）
    在其定义处（module/class）被用 func_set_timeout(timeout) 包裹，且只做一次注入。
    行为：
      1. 若 target 已经被注入（有标记或 id 在 _INJECTED_FN_IDS），直接返回 True
      2. 检查是否已有 func_set_timeout 生成的 wrapper：
           2a. 若找到 wrapper 且 wrapper 的闭包包含 defaultTimeout: 就地更新闭包值并尝试替换定义处的引用
           2b. 若找到 wrapper 但无法修改（例如使用 timeoutFunction），则用新的 wrapper 替换定义处
      3. 若没有找到 wrapper：尝试在定义处直接替换原函数为新的 wrapper（推荐）
      4. 若无法替换定义处（比如动态生成的函数、无法定位 owner）：不会污染原始函数，而是返回新的 wrapper 供 caller 在 item 上做 per-item 替换
    返回 (success: bool, applied_callable: callable)
      - success 表示是否已在定义处将包装器设置好（True）或只能返回局部 wrapper (False)
      - applied_callable 是最终用于执行的可调用（若替换定义处则是模块/类上的 wrapper；否则为 per-item wrapper）
    """
    # normalize possible bound method to underlying function
    orig = target_callable
    bound_to_instance = False
    if isinstance(target_callable, MethodType):
        bound_to_instance = True
        target_fn = target_callable.__func__
    else:
        target_fn = target_callable

    if not isinstance(target_fn, FunctionType):
        # can't handle non-function
        return False, target_callable

    # Avoid duplicate injections
    if getattr(target_fn, "__timeout_injected_by_injector__", False) or (id(target_fn) in _INJECTED_FN_IDS):
        logger.debug("函数 %s 已被标记为已注入，跳过", getattr(target_fn, "__name__", repr(target_fn)))
        return True, target_callable

    # 1) 检测是否已有 func_set_timeout wrapper
    found = is_func_timeout_wrapper(target_fn)
    if found:
        wrapper, info = found
        logger.debug("检测到已存在的 func_set_timeout wrapper for %s, info=%s", getattr(target_fn, '__name__', '?'),
                     info)
        # 若 wrapper 闭包包含 defaultTimeout（可更新），尝试就地更新并替换定义处
        newf = _try_update_wrapper_default_timeout(wrapper, timeout)
        if newf is not None:
            replaced = _find_owner_and_replace(wrapper, newf)
            if replaced:
                # mark underlying original function as injected
                try:
                    setattr(getattr(newf, "__wrapped__", newf), "__timeout_injected_by_injector__", True)
                except Exception:
                    pass
                _INJECTED_FN_IDS.add(id(getattr(newf, "__wrapped__", newf)))
                logger.info("已就地更新 wrapper 的 defaultTimeout 并替换定义处")
                return True, newf
            else:
                # can't replace global definition; return per-item wrapper
                logger.info("就地更新成功，但无法替换定义处，返回局部 wrapper")
                try:
                    setattr(getattr(newf, "__wrapped__", newf), "__timeout_injected_by_injector__", True)
                except Exception:
                    pass
                _INJECTED_FN_IDS.add(id(getattr(newf, "__wrapped__", newf)))
                return False, newf
        else:
            # wrapper exists but not modifiable in place (e.g. dynamic timeoutFunction) -> create new wrapper and replace definition
            try:
                new_wrapper = _wrap_with_func_set_timeout(getattr(wrapper, "__wrapped__", wrapper), timeout,
                                                          allow_override, func_set_timeout_decorator)
            except Exception as e:
                logger.exception("创建新 wrapper 失败: %s", e)
                return False, target_callable
            replaced = _find_owner_and_replace(wrapper, new_wrapper)
            if replaced:
                try:
                    setattr(getattr(new_wrapper, "__wrapped__", new_wrapper), "__timeout_injected_by_injector__", True)
                except Exception:
                    pass
                _INJECTED_FN_IDS.add(id(getattr(new_wrapper, "__wrapped__", new_wrapper)))
                logger.info("已用新的 wrapper 替换定义处")
                return True, new_wrapper
            else:
                logger.info("无法替换定义处，返回局部 new_wrapper")
                _INJECTED_FN_IDS.add(id(getattr(new_wrapper, "__wrapped__", new_wrapper)))
                return False, new_wrapper

    # 2) 未检测到已有 wrapper：直接创建并尝试替换定义处
    try:
        new_wrapper = _wrap_with_func_set_timeout(target_fn, timeout, allow_override, func_set_timeout_decorator)
    except Exception as e:
        logger.exception("用 func_set_timeout 包装函数失败: %s", e)
        return False, target_callable
    # try replace where original was defined
    replaced = _find_owner_and_replace(target_fn, new_wrapper)
    if replaced:
        try:
            setattr(getattr(new_wrapper, "__wrapped__", new_wrapper), "__timeout_injected_by_injector__", True)
        except Exception:
            pass
        _INJECTED_FN_IDS.add(id(getattr(new_wrapper, "__wrapped__", new_wrapper)))
        logger.info("已在定义处替换 %s 为 func_set_timeout wrapper", getattr(target_fn, '__name__', '?'))
        return True, new_wrapper
    else:
        # fallback: return wrapper for per-item application
        logger.info("无法修改定义处，返回局部 wrapper 以在 item 上替换")
        _INJECTED_FN_IDS.add(id(getattr(new_wrapper, "__wrapped__", new_wrapper)))
        return False, new_wrapper
