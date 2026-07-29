from typing import Optional

from powertrde import env
import os

from powertrde.utils import yaml_utils


class DefaultGuiConstants:
    SCHEME_NAME = 'default'
    GUI_DISPLAY_TITLE = '通用测试启动器'
    DEFAULT_VERSION = '1.0.0'
    WINDOW_TITLE_CMD = 'DEFAULT CMD'
    WINDOW_TITLE_GUI = 'DEFAULT GUI'
    SUPPORT_RETEST = False
    SUPPORT_TASKID = False
    SUPPORT_POWER_MONITOR = False
    SUPPORT_HVPM = False

    _version_cache: Optional[str] = None

    @classmethod
    def get_version(cls):
        if cls._version_cache is None:
            version_file = os.path.join(env.PROJ_DIR, f'{cls.SCHEME_NAME}_version.yaml')
            try:
                # with open(version_file, 'r', encoding='utf-8') as file:
                #     cls._version_cache = file.read().strip()
                config = yaml_utils.read_yaml(version_file)
                cls._version_cache = config['version']
            except Exception:
                pass
            if not cls._version_cache:
                cls._version_cache = cls.DEFAULT_VERSION
        return cls._version_cache

    @classmethod
    def get_window_title_with_version_gui(cls):
        from powertrde.env import PUBLISH_MODE
        if not PUBLISH_MODE:
            return cls.WINDOW_TITLE_GUI + ' ' + cls.get_version() + f'  ⌈CN⌋'
        if PUBLISH_MODE == 'odm':
            return cls.WINDOW_TITLE_GUI + ' ' + cls.get_version() + f'  ⌈ODM⌋'
        return cls.WINDOW_TITLE_GUI + ' ' + cls.get_version() + f'  ⌈{PUBLISH_MODE}⌋'

    @classmethod
    def get_sop_link(cls):
        sop_link = {
            'link': 'https://transsioner.feishu.cn/wiki/TiRcw3P8IiUQioko52AcqDbtnub',
            'name': 'Default-SOP',
        }
        return sop_link
