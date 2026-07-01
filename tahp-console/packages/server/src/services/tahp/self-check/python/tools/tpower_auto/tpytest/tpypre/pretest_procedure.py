from powertrde.framework.logs_protocol import logs_p


class PretestProcedure:
    def __init__(self, handler):
        """
        初始化 Procedure。

        参数:
        - handler: 用于在流程中共享数据的对象。
        """
        self._handler = handler

    @property
    def handler(self):
        return self._handler

    def enter(self):
        """
        进入流程前的准备工作。
        可以在子类中重写以实现特定的初始化逻辑。
        """
        logs_p().log(f"{self.__class__.__name__}: Entering procedure.")

    def execute(self):
        """
        执行流程的主要逻辑。
        需要在子类中实现。
        """
        raise NotImplementedError("Please implement the execute method.")

    def exit(self):
        """
        退出流程后的清理工作。
        可以在子类中重写以实现特定的清理逻辑。
        """
        logs_p().log(f"{self.__class__.__name__}: Exiting procedure.")

    def run(self):
        """
        运行流程，依次调用 enter、execute 和 exit。
        """
        self.enter()
        try:
            self.execute()
        finally:
            self.exit()
