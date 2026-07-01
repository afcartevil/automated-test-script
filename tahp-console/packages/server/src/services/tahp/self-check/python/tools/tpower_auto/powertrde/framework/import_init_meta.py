class ImportInitMeta(type):
    def __init__(cls, name, bases, namespace):
        super().__init__(name, bases, namespace)
        init = getattr(cls, "_import_init", None)
        if callable(init):
            init()
