import asyncio
import os
import sys
from typing import Optional

from gui_templates.default.gui_options import GuiOptions
from powertrde import env
from powertrde.env import TOOLS_DIR

from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

from powertrde.utils import misc_utils
from powertrde.utils.winctrl import win_utils
from tpytest.scheme.scheme_test_env import SchemeTestEnv


class DefaultGuiEntry:
    def _on_main_finished(self):
        try:
            GuiOptions.instance.case_scheme_sub_entry_class.on_subprocess_end(from_forced_interruption=True)
        except Exception:
            pass

    @staticmethod
    def get_overwrite_sys_argv_config_dict():
        override_config_dict: Optional[dict] = None
        if len(sys.argv) > 2:
            if sys.argv[2].startswith('--config='):
                _override_config_str = sys.argv[2][9:]
                override_config_dict = SchemeTestEnv.load_override_user_config(_override_config_str)
            elif len(sys.argv) > 3 and sys.argv[2].startswith('--device_id') and sys.argv[3]:
                override_config_dict = {'device_id': sys.argv[3]}
        return override_config_dict

    def main(self):
        try:
            return self._main()
        finally:
            try:
                print("GUI Main process exit...")
                # 结束最后一次子进程（同步结束录像）
                misc_utils.kill_process_tree(env.get_user_env_arg('sub_entry_process').pid)
                self._on_main_finished()
            except:
                pass

    def _main(self):
        if len(sys.argv) > 1 and sys.argv[1] == '--start':
            # 打开测试界面
            _g = GuiOptions.instance.gui_constants_class

            _device_id = None
            _override_config_dict = self.get_overwrite_sys_argv_config_dict()
            if _override_config_dict:
                _device_id = _override_config_dict.get('device_id')

            if _device_id:
                _g.WINDOW_TITLE_CMD += f': {_device_id}'
                _g.get_window_title_with_version_gui = lambda: f'{_g.WINDOW_TITLE_GUI} {_g.get_version()}: {_device_id}'

        # 隐藏控制台
        win_utils.set_console_title(GuiOptions.instance.gui_constants_class.WINDOW_TITLE_CMD)

        app = QApplication(sys.argv)
        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)

        window = GuiOptions.instance.gui_main_window_class()

        with open(os.path.join(TOOLS_DIR, 'qss', 'modern.qss'), encoding="utf-8") as f:
            app.setStyleSheet(f.read())

        def except_hook(cls, exception, traceback):
            sys.__excepthook__(cls, exception, traceback)

        sys.excepthook = except_hook

        # 延时一点时间，将窗口置前并将控制台隐藏
        async def delay_active():
            await asyncio.sleep(0.5)
            win_utils.minimize_window(win_utils.find_window_handle(GuiOptions.instance.gui_constants_class.WINDOW_TITLE_CMD))
            win_utils.activate_window(win_utils.find_window_handle(GuiOptions.instance.gui_constants_class.get_window_title_with_version_gui()))

        loop.create_task(delay_active())

        with loop:
            loop.run_forever()
