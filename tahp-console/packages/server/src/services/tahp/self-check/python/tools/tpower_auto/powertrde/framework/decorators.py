import inspect
from functools import wraps


def finally_call(cleanup_func, **extra_kwargs):
    """
    装饰器，用于在函数执行后始终执行清理操作，同时你也可以传递额外的参数给清理函数。
    清理函数 cleanup_func 可以是无参数的，它可以携带魔术参数 'exception' 和 'func'，
    如果其参数包含 'exception' 或 'func'，分别用于传递异常信息和被装饰的函数本身。
    在清理函数中，你可以根据需要执行任何清理操作，例如关闭数据库连接、释放资源等。
    :param cleanup_func: 清理函数，在函数执行后调用
    :return: 装饰器
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            exception_raised = None  # 用于存储异常信息
            try:
                # 执行目标函数
                return func(*args, **kwargs)
            except Exception as e:
                exception_raised = e
                raise
            finally:
                # 获取cleanup_func的参数信息
                sig = inspect.signature(cleanup_func)
                param_names = sig.parameters.keys()

                # 构建要传递给cleanup_func的参数
                cleanup_kwargs = {}
                pre_finally_call = None
                post_finally_call = None
                self = None
                if 'self' in param_names:
                    self = args[0]
                    cleanup_kwargs['self'] = self
                    pre_finally_call = getattr(self, '_on_pre_finally_call', None)
                    post_finally_call = getattr(self, '_on_post_finally_call', None)
                if 'exception' in param_names:
                    cleanup_kwargs['exception'] = exception_raised
                if 'func' in param_names:
                    cleanup_kwargs['func'] = func

                # 添加额外的键值对参数
                for key, value in extra_kwargs.items():
                    if key in param_names:
                        cleanup_kwargs[key] = value

                # 执行预清理方法
                if callable(pre_finally_call):
                    pre_finally_call(exception_raised, func, cleanup_func)

                # 执行清理方法，传递必要的参数
                cleanup_func(**cleanup_kwargs)

                # 执行后清理方法
                if callable(post_finally_call):
                    post_finally_call(exception_raised, func, cleanup_func)

        return wrapper

    return decorator


def overwrite(method):
    # def wrapper(cls):
    #     if not hasattr(super(cls, cls), method.__name__):
    #         raise TypeError(f"Method '{method.__name__}' does not override any method in the base class.")
    #     return method
    return method


def recommended_override(func):
    """推荐子类重写的方法"""
    # import warnings
    # import functools
    #
    # @functools.wraps(func)
    # def wrapper(*args, **kwargs):
    #     cls = args[0].__class__.__name__
    #     base_cls = func.__qualname__.split('.')[0]
    #     warnings.warn(
    #         f"{cls} 正在调用基类推荐重写的方法 {func.__name__}，请考虑在子类中覆写它。",
    #         category=UserWarning
    #     )
    #     return func(*args, **kwargs)
    #
    # wrapper.__recommended_override__ = True
    # return wrapper
    return func
