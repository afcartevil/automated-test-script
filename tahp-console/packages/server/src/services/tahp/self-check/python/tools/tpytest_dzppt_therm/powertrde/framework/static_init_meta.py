import threading


class StaticInitMeta(type):
    def __init__(cls, name, bases, namespace):
        super().__init__(name, bases, namespace)
        cls._static_initialized = False
        cls._static_lock = threading.Lock()

    def __getattribute__(cls, attr_name):
        # 对“类属性访问”拦截，触发一次静态初始化
        skip = {
            '_static_initialized', '_static_lock', '_static_init',
            '__dict__', '__class__', '__mro__', '__name__', '__qualname__',
            '__module__', '__doc__', '__slots__',
        }
        if (not cls._static_initialized) and (attr_name not in skip):
            with cls._static_lock:
                if not cls._static_initialized:
                    init = cls.__dict__.get('_static_init', None)
                    if callable(init):
                        init()
                    cls._static_initialized = True
        return super().__getattribute__(attr_name)

    def __call__(cls, *args, **kwargs):
        # 在“构造实例”之前，也触发一次静态初始化
        if not cls._static_initialized:
            with cls._static_lock:
                if not cls._static_initialized:
                    init = cls.__dict__.get('_static_init', None)
                    if callable(init):
                        init()
                    cls._static_initialized = True
        # 然后再走正常的实例创建流程
        return super().__call__(*args, **kwargs)
