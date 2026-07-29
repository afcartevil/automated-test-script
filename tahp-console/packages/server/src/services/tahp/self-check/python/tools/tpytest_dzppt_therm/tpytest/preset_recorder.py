import os.path
import shutil
from typing import Union, Tuple, Optional

import uiautomator2
from PIL.Image import Resampling

from powertrde import env
from powertrde.env import GET_TEAM_PRE_RECORDS_DIR
from powertrde.framework.weak_events import WeakEvents
from powertrde.utils.trde import adb
from powertrde.utils import yaml_utils, path_utils, misc_utils
from powertrde.utils.u2_extends.u2utils import U2DeviceProtocol


def get_static_save_root_dir():
    return GET_TEAM_PRE_RECORDS_DIR()


def get_dynamic_save_root_dir():
    return os.path.join(env.get_cache_dir(), 'app_control_data')


def _get_static_save_dir(record_group: str):
    root_dir = get_static_save_root_dir()
    if not record_group:
        return root_dir
    return os.path.join(root_dir, record_group)


class PresetRecords:
    def __init__(self, parent: 'PresetRecordGroups', name: str, records: dict, is_debug_fallback: bool,
                 is_static: bool):
        self.parent = parent
        self._records = misc_utils.convert_dict_to_lowercase_key_dict(records) if records is not None else {}
        self.is_debug_fallback = is_debug_fallback
        self.is_static = is_static
        self.name = name

    def update(self, key: str, value):
        lower_key = key.lower()
        self._records[lower_key] = value

    def delete(self, key: str):
        lower_key = key.lower()
        del self._records[lower_key]

    def get(self, key: str, debug_fallback_value=None):
        lower_key = key.lower()
        if debug_fallback_value and self.is_debug_fallback and lower_key not in self._records:
            print(f"** DEBUG 请注意：{self.name} -> {key} 记录不存在而发生 fallback 到 {debug_fallback_value}")
            return self._convert_pic_value(debug_fallback_value)
        return self._convert_pic_value(self._records[lower_key])

    def get_with_fallback(self, key: str, debug_fallback_value=None):
        lower_key = key.lower()
        return self._convert_pic_value(self._records.get(lower_key, debug_fallback_value))

    def has(self, key: str):
        return bool(key.lower() in self._records)

    @property
    def is_available(self):
        return bool(self.name)

    def _convert_pic_value(self, value):
        if not isinstance(value, str):
            return value
        if value.startswith('__pic__'):
            if self.is_static:
                save_dir = _get_static_save_dir(self.name)
            else:
                save_dir = self.parent.save_dir
            return os.path.join(save_dir, value[7:])
        return value


class PresetRecordGroups:
    def __init__(self, device_model: str, device_sn: str, groups_dict: dict, save_dir: str, is_debug_fallback: bool,
                 static_groups_dict: Optional[dict] = None, bind_recorder_record_events: bool = False):
        self.device_model = device_model
        self.device_sn = device_sn
        self.save_dir = save_dir
        self._groups_dict = {}
        self._with_static_groups = (static_groups_dict is not None)
        self._static_groups_dict = {}
        self._is_debug_fallback = is_debug_fallback
        self._has_bind_recorder_events = False
        _is_static = bool(self.device_model == 'static')
        self._empty_records = PresetRecords(self, '', {}, is_debug_fallback, _is_static)
        for k, v in groups_dict.items():
            self._groups_dict[k.lower()] = PresetRecords(self, k, v, is_debug_fallback, _is_static)
        if static_groups_dict:
            for k, v in static_groups_dict.items():
                self._static_groups_dict[k.lower()] = PresetRecords(self, k, v, is_debug_fallback, True)
        if bind_recorder_record_events:
            self.bind_recorder_record_events()

    @property
    def groups_dict(self):
        return self._groups_dict

    @property
    def is_static(self):
        return self.device_model == 'static'

    def get_static(self, group_name: str):
        lower_name = group_name.lower()
        if self.is_static:
            return self.get(lower_name)
        return self._static_groups_dict.get(lower_name, self._empty_records)

    def get(self, group_name: str):
        lower_name = group_name.lower()
        return self._groups_dict.get(lower_name, self._empty_records)

    def has(self, group_name: str):
        lower_name = group_name.lower()
        return bool(lower_name in self._groups_dict)

    def has_static(self, group_name: str):
        lower_name = group_name.lower()
        return bool(lower_name in self._static_groups_dict)

    def main(self):
        return self.get('main')

    def static_main(self):
        return self.get_static('main')

    def bind_recorder_record_events(self):
        if not self._has_bind_recorder_events:
            self._has_bind_recorder_events = True
            PresetRecorder.on_record_events += self._on_recorder_record
            PresetRecorder.on_delete_record_events += self._on_recorder_delete_record

    def unbind_recorder_record_events(self):
        if self._has_bind_recorder_events:
            self._has_bind_recorder_events = False
            PresetRecorder.on_record_events -= self._on_recorder_record
            PresetRecorder.on_delete_record_events -= self._on_recorder_delete_record

    def _on_recorder_record(self, device_model: str, device_sn: str, record_group: str, key: str, msg):
        lower_key = key.lower()
        lower_group = record_group.lower()
        if self.device_model == device_model and self.device_sn == device_sn:
            records = self.get(lower_group)
            if not records.is_available:
                records = PresetRecords(self, record_group, {lower_key: msg}, self._is_debug_fallback,
                                        device_model == 'static')
                self._groups_dict[lower_group] = records
            else:
                records.update(lower_key, msg)
        elif self._with_static_groups and device_model == 'static':
            records = self.get_static(lower_group)
            if not records.is_available:
                records = PresetRecords(self, record_group, {lower_key: msg}, self._is_debug_fallback, True)
                self._static_groups_dict[lower_group] = records
            else:
                records.update(lower_key, msg)

    def _on_recorder_delete_record(self, device_model: str, device_sn: str, record_group: str, key: str):
        lower_key = key.lower()
        if self._with_static_groups and device_model == 'static':
            if not record_group:
                self._static_groups_dict.clear()
            elif not lower_key:
                if self.has_static(record_group):
                    del self._static_groups_dict[record_group]
            else:
                node = self.get_static(record_group)
                if node.is_available and node.has(lower_key):
                    node.delete(lower_key)
        elif self.device_model == device_model and self.device_sn == device_sn:
            if not record_group:
                self._groups_dict.clear()
            elif not lower_key:
                if self.has(record_group):
                    del self._groups_dict[record_group]
            else:
                node = self.get(record_group)
                if node.is_available and node.has(lower_key):
                    node.delete(lower_key)


class PresetRecorder:
    # on_record: Optional[Callable[[str, str, str, str, Any], None]] = None
    # on_delete_record: Optional[Callable[[str, str, str, str], None]] = None
    on_record_events = WeakEvents()
    on_delete_record_events = WeakEvents()

    @staticmethod
    def get_save_dir(device_model: str, device_sn: str):
        if device_model == 'static':
            return PresetRecorder.get_static_save_dir(device_sn)
        if env.scheme.name:
            return os.path.join(get_dynamic_save_root_dir(), env.scheme.name, device_model,
                                device_sn)
        else:
            return os.path.join(get_dynamic_save_root_dir(), '_shared', device_model, device_sn)

    @staticmethod
    def get_static_save_root_dir():
        return get_static_save_root_dir()

    @staticmethod
    def get_static_save_dir(record_group: str):
        return _get_static_save_dir(record_group)

    @staticmethod
    def clear_records(device_model: str, device_sn: str):
        shutil.rmtree(PresetRecorder.get_save_dir(device_model, device_sn), ignore_errors=True)
        if PresetRecorder.on_record_events:
            PresetRecorder.on_record_events(device_model, device_sn, '', '')

    @staticmethod
    def clear_static_records():
        PresetRecorder.clear_records('static', '')

    @staticmethod
    def clear_record_u2d(u2d: Union[uiautomator2.Device, U2DeviceProtocol]):
        PresetRecorder.clear_records(adb.device_model_simple(u2d.serial), u2d.serial)

    @staticmethod
    def delete_records(device_model: str, device_sn: str, record_group: str):
        save_dir = PresetRecorder.get_save_dir(device_model, device_sn)
        target_file = os.path.join(save_dir, record_group + '.yaml')
        if os.path.exists(target_file):
            os.remove(target_file)
            for pic in path_utils.find_files_with_prefix(save_dir, f'{record_group}_', True):
                if os.path.isfile(pic):
                    os.remove(pic)
                else:
                    shutil.rmtree(pic)
        if PresetRecorder.on_delete_record_events:
            PresetRecorder.on_delete_record_events(device_model, device_sn, record_group, '')

    @staticmethod
    def delete_static_records(record_group: str):
        save_dir = PresetRecorder.get_static_save_dir(record_group)
        if os.path.exists(save_dir):
            shutil.rmtree(save_dir, ignore_errors=True)
        PresetRecorder.delete_records('static', record_group, record_group)

    @staticmethod
    def delete_record_item(device_model: str, device_sn: str, record_group: str, item_key: str):
        save_dir = PresetRecorder.get_save_dir(device_model, device_sn)
        target_file = os.path.join(save_dir, record_group + '.yaml')
        if os.path.exists(target_file):
            exist_dict = yaml_utils.read_yaml(target_file)
            if exist_dict and item_key in exist_dict:
                item_value = exist_dict[item_key]
                del exist_dict[item_key]
                if isinstance(item_value, str) and item_value.startswith('__pic__'):
                    target_pic_file = item_value[7:]
                    target_pic_file = os.path.join(save_dir, target_pic_file)
                    if os.path.exists(target_pic_file):
                        if os.path.isfile(target_pic_file):
                            os.remove(target_pic_file)
                        else:
                            shutil.rmtree(target_pic_file)
                if not exist_dict:
                    os.remove(target_file)
                else:
                    yaml_utils.write_yaml(exist_dict, target_file)
        if PresetRecorder.on_delete_record_events:
            PresetRecorder.on_delete_record_events(device_model, device_sn, record_group, item_key)

    @staticmethod
    def delete_static_record_item(record_group: str, item_key: str):
        PresetRecorder.delete_record_item('static', record_group, record_group, item_key)

    @staticmethod
    def load_record_groups(device_model: str, device_sn: str, is_debug_fallback: bool, with_static_records=True,
                           bind_recorder_record_events=True):
        save_dir = PresetRecorder.get_save_dir(device_model, device_sn)
        ret_dict = {}
        static_dict = None

        def _load_static_dict():
            _ret_dict = {}
            _static_save_dir = PresetRecorder.get_static_save_root_dir()
            if not os.path.exists(_static_save_dir):
                return _ret_dict
            for d in os.listdir(_static_save_dir):
                sub_save_dir = os.path.join(_static_save_dir, d)
                if os.path.isdir(sub_save_dir):
                    for _file in os.listdir(sub_save_dir):
                        if _file.endswith('.yaml'):
                            _record_group = _file.replace('.yaml', '')
                            _ret_dict[_record_group] = yaml_utils.read_yaml(os.path.join(sub_save_dir, _file), False)
            return _ret_dict

        if not os.path.exists(save_dir):
            if with_static_records:
                static_dict = _load_static_dict()
            return PresetRecordGroups(device_model, device_sn, ret_dict, save_dir, is_debug_fallback, static_dict,
                                      bind_recorder_record_events=bind_recorder_record_events)

        if device_model == 'static':
            assert not device_sn, 'If you load a static record node, the device_sn arg must be empty!'
            ret_dict = _load_static_dict()
            return PresetRecordGroups('static', '', ret_dict, PresetRecorder.get_static_save_root_dir(),
                                      is_debug_fallback, bind_recorder_record_events=bind_recorder_record_events)
        else:
            for file in os.listdir(save_dir):
                if file.endswith('.yaml'):
                    record_group = file.replace('.yaml', '')
                    ret_dict[record_group] = yaml_utils.read_yaml(os.path.join(save_dir, file), False)
            if with_static_records:
                static_dict = _load_static_dict()
            return PresetRecordGroups(device_model, device_sn, ret_dict, save_dir, is_debug_fallback, static_dict,
                                      bind_recorder_record_events=bind_recorder_record_events)

    @staticmethod
    def load_static_record_groups(is_debug_fallback: bool):
        return PresetRecorder.load_record_groups('static', '', is_debug_fallback, False)

    @staticmethod
    def record(device_model: str, device_sn: str, record_group: str, key: str, msg):
        save_dir = PresetRecorder.get_save_dir(device_model, device_sn)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
        save_file_path = os.path.join(save_dir, f'{record_group}.yaml')
        exist_dict = yaml_utils.read_yaml(save_file_path, True)
        if not exist_dict:
            exist_dict = {key: msg}
        else:
            exist_dict[key] = msg
        yaml_utils.write_yaml(exist_dict, save_file_path, False)
        if PresetRecorder.on_record_events:
            PresetRecorder.on_record_events(device_model, device_sn, record_group, key, msg)

    @staticmethod
    def record_static(record_group: str, key: str, msg):
        PresetRecorder.record('static', record_group, record_group, key, msg)

    @staticmethod
    def record_main(device_model: str, device_sn: str, key: str, msg):
        PresetRecorder.record(device_model, device_sn, 'main', key, msg)

    @staticmethod
    def record_static_main(key: str, msg):
        PresetRecorder.record_main('static', 'main', key, msg)

    @staticmethod
    def record_pos_u2d(u2d: Union[uiautomator2.Device, U2DeviceProtocol], control_app: str, control_key: str, point: Tuple[float, float],
                       record_in_static=False):
        if not (0 <= point[0] <= 1 and 0 <= point[1] <= 1):
            screen_width, screen_height = u2d.window_size()
            point = (point[0] / screen_width, point[1] / screen_height)
        assert 0 <= point[0] <= 1, "中心 X 坐标超出屏幕范围"
        assert 0 <= point[1] <= 1, "中心 Y 坐标超出屏幕范围"
        if record_in_static:
            PresetRecorder.record('static', control_app, control_app, control_key, point)
        else:
            model = adb.device_model_simple(u2d.serial)
            PresetRecorder.record(model, u2d.serial, control_app, control_key, point)

    @staticmethod
    def record_static_pos_u2d(u2d: Union[uiautomator2.Device, U2DeviceProtocol], control_app: str, control_key: str, point: Tuple[float, float]):
        PresetRecorder.record_pos_u2d(u2d, control_app, control_key, point, True)

    @staticmethod
    def record_control_pos_u2o(u2d: Union[uiautomator2.Device, U2DeviceProtocol],
                               control_app: str, control_key: str,
                               u2o: Union[
                                   uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                               offset=(0.0, 0.0),
                               center_relative_offset=(0.5, 0.5),
                               record_in_static=False):
        screen_width, screen_height = u2d.window_size()

        if isinstance(u2o, uiautomator2.xpath.XPathSelector):
            center_pos = u2o.get().offset(center_relative_offset[0], center_relative_offset[1])
        elif isinstance(u2o, uiautomator2.xpath.XMLElement):
            center_pos = u2o.offset(center_relative_offset[0], center_relative_offset[1])
        elif isinstance(u2o, str):
            center_pos = u2d.xpath(u2o).get().offset(center_relative_offset[0], center_relative_offset[1])
        else:
            center_pos = u2o.center(center_relative_offset)

        px = (center_pos[0] + offset[0]) / screen_width
        py = (center_pos[1] + offset[1]) / screen_height

        px, py = PresetRecorder.pos_convert_to_portrait(px, py, u2d.orientation)

        assert 0 <= px <= 1, "中心 X 坐标超出屏幕范围"
        assert 0 <= py <= 1, "中心 Y 坐标超出屏幕范围"
        if record_in_static:
            PresetRecorder.record('static', control_app, control_app, control_key, (px, py))
        else:
            model = adb.device_model_simple(u2d.serial)
            PresetRecorder.record(model, u2d.serial, control_app, control_key, (px, py))

    @staticmethod
    def record_pic_u2d(u2d: Union[uiautomator2.Device, U2DeviceProtocol], control_app: str, control_key: str,
                       pic_bounds: Tuple[float, float, float, float], record_in_static=False):
        g_pos = control_key.find('/')
        sub_key = None
        if g_pos > 0:
            sub_key = control_key[g_pos + 1:]
            control_key = control_key[:g_pos]

        screenshot = u2d.screenshot()
        orig_width, orig_height = screenshot.size
        if orig_width < orig_height:
            scale = 720 / orig_width
            new_width = 720
            new_height = int(orig_height * scale)
        else:
            scale = 720 / orig_height
            new_height = 720
            new_width = int(orig_width * scale)
        resized_screenshot = screenshot.resize((new_width, new_height), Resampling.LANCZOS)
        left, top, right, bottom = new_width * pic_bounds[0], new_height * pic_bounds[1], new_width * pic_bounds[
            2], new_height * pic_bounds[3]

        # 截取控件所在区域
        control_image = resized_screenshot.crop((left, top, right, bottom))

        # 如果是横屏，则进行翻转
        orientation = u2d.orientation
        if orientation == 'left':
            control_image = control_image.rotate(270, expand=True)
        elif orientation == 'right':
            control_image = control_image.rotate(90, expand=True)

        # 保存图片
        if sub_key:
            base_filename = f'{sub_key}.png'
            filename = f'{control_app}_{control_key}'
        else:
            base_filename = f'{control_app}_{control_key}.png'
            filename = base_filename
        if record_in_static:
            if sub_key:
                img_dir = os.path.join(PresetRecorder.get_static_save_dir(control_app), f'{control_app}_{control_key}')
                if not os.path.exists(img_dir):
                    os.makedirs(img_dir)
            else:
                img_dir = PresetRecorder.get_static_save_dir(control_app)
            PresetRecorder.record('static', control_app, control_app, control_key,
                                  f'__pic__{filename}')
            control_image.save(os.path.join(img_dir, base_filename))
        else:
            model = adb.device_model_simple(u2d.serial)
            if sub_key:
                img_dir = os.path.join(PresetRecorder.get_save_dir(model, u2d.serial), f'{control_app}_{control_key}')
                if not os.path.exists(img_dir):
                    os.makedirs(img_dir)
            else:
                img_dir = PresetRecorder.get_save_dir(model, u2d.serial)
            PresetRecorder.record(model, u2d.serial, control_app, control_key,
                                  f'__pic__{filename}')
            control_image.save(os.path.join(img_dir, base_filename))

    @staticmethod
    def record_control_pic_u2o(u2d: Union[uiautomator2.Device, U2DeviceProtocol], control_app: str, control_key: str,
                               u2o: Union[
                                   uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                               pos_offset=(0.0, 0.0), size_offset=(0.0, 0.0),
                               record_in_static=False):
        """
        记录控件图片以备后续图像识别使用。
        :param u2d: 设备对象
        :param control_app: 控件所属的应用名称，用于保存文件名
        :param control_key: 控件名称，用于保存文件名
        :param u2o: 控件对象，可以是UiObject、XPathSelector或XMLElement
        :param pos_offset: 控件位置的偏移量（x, y）
        :param size_offset: 控件大小的偏移量（width, height）
        :param record_in_static: 是否录制在静态资源中（所有项目通用的模板资源）
        """
        g_pos = control_key.find('/')
        sub_key = None
        if g_pos > 0:
            sub_key = control_key[g_pos + 1:]
            control_key = control_key[:g_pos]

        # 初始化边界变量
        left, top, right, bottom = 0, 0, 0, 0

        if isinstance(u2o, uiautomator2.UiObject):
            left, top, right, bottom = u2o.bounds()
        elif isinstance(u2o, uiautomator2.xpath.XPathSelector):
            left, top, right, bottom = u2o.get().bounds
        elif isinstance(u2o, uiautomator2.xpath.XMLElement):
            left, top, right, bottom = u2o.bounds
        elif isinstance(u2o, str):
            left, top, right, bottom = u2d.xpath(u2o).get().bounds
        else:
            raise ValueError(f'Not support u2o arg for value {u2o}')

        # 获取屏幕截图
        screenshot = u2d.screenshot()

        # 获取截图的尺寸
        orig_width, orig_height = screenshot.size

        # 计算缩放比例
        if orig_width < orig_height:
            scale = 720 / orig_width
            new_width = 720
            new_height = int(orig_height * scale)
        else:
            scale = 720 / orig_height
            new_height = 720
            new_width = int(orig_width * scale)

        # 调整截图尺寸
        resized_screenshot = screenshot.resize((new_width, new_height), Resampling.LANCZOS)

        # 根据缩放比例调整控件的边界
        left = int(left * scale)
        top = int(top * scale)
        right = int(right * scale)
        bottom = int(bottom * scale)

        # 计算位置和大小的偏移
        width = right - left
        height = bottom - top
        left += int(width * pos_offset[0])
        top += int(height * pos_offset[1])
        right = left + int(width * (1 + size_offset[0]))
        bottom = top + int(height * (1 + size_offset[1]))

        # 截取控件所在区域
        control_image = resized_screenshot.crop((left, top, right, bottom))

        # 如果是横屏，则进行翻转
        orientation = u2d.orientation
        if orientation == 'left':
            control_image = control_image.rotate(270, expand=True)
        elif orientation == 'right':
            control_image = control_image.rotate(90, expand=True)

        # 保存图片
        if sub_key:
            base_filename = f'{sub_key}.png'
            filename = f'{control_app}_{control_key}'
        else:
            base_filename = f'{control_app}_{control_key}.png'
            filename = base_filename
        if record_in_static:
            if sub_key:
                img_dir = os.path.join(PresetRecorder.get_static_save_dir(control_app), f'{control_app}_{control_key}')
                if not os.path.exists(img_dir):
                    os.makedirs(img_dir)
            else:
                img_dir = PresetRecorder.get_static_save_dir(control_app)
            PresetRecorder.record('static', control_app, control_app, control_key,
                                  f'__pic__{filename}')
            control_image.save(os.path.join(img_dir, base_filename))
        else:
            model = adb.device_model_simple(u2d.serial)
            if sub_key:
                img_dir = os.path.join(PresetRecorder.get_save_dir(model, u2d.serial), f'{control_app}_{control_key}')
                if not os.path.exists(img_dir):
                    os.makedirs(img_dir)
            else:
                img_dir = PresetRecorder.get_save_dir(model, u2d.serial)
            PresetRecorder.record(model, u2d.serial, control_app, control_key,
                                  f'__pic__{filename}')
            control_image.save(os.path.join(img_dir, base_filename))

    @staticmethod
    def pos_convert_to_portrait(x, y, direction):
        if direction == 'left':
            x_prime = 1 - y
            y_prime = x
        elif direction == 'right':
            x_prime = y
            y_prime = 1 - x
        else:
            return x, y
        return x_prime, y_prime

    @staticmethod
    def create_recorder_node(device_model: str, device_sn: str, group_name: str):
        return PresetRecorderNode(device_model, device_sn, group_name)

    @staticmethod
    def create_static_recorder_node(group_name: str):
        return PresetRecorderNode('static', group_name, group_name)

    @staticmethod
    def create_recorder_node_u2d(u2d: Union[uiautomator2.Device, U2DeviceProtocol], group_name: str):
        return PresetRecorderNodeU2D(u2d, group_name)

    @staticmethod
    def create_static_recorder_node_u2d(u2d: Union[uiautomator2.Device, U2DeviceProtocol], group_name: str):
        return PresetRecorderNodeU2D(u2d, group_name, is_static=True)


class PresetRecorderNode:
    def __init__(self, device_model: str, device_sn: str, group_name: str):
        self.device_model = device_model
        self.device_sn = device_sn
        self.group_name = group_name

    @property
    def is_static(self):
        return self.device_model == 'static'

    def record(self, key: str, msg):
        PresetRecorder.record(self.device_model, self.device_sn, self.group_name, key, msg)

    def record_static(self, key: str, msg):
        PresetRecorder.record_static(self.group_name, key, msg)

    def delete_all_items(self):
        PresetRecorder.delete_records(self.device_model, self.device_sn, self.group_name)

    def delete_static_all_items(self):
        PresetRecorder.delete_static_records(self.group_name)

    def delete_item(self, key: str):
        PresetRecorder.delete_record_item(self.device_model, self.device_sn, self.group_name, key)

    def delete_static_item(self, key: str):
        PresetRecorder.delete_static_record_item(self.group_name, key)


class PresetRecorderNodeU2D(PresetRecorderNode):
    def __init__(self, u2d: Union[uiautomator2.Device, U2DeviceProtocol], group_name: str, is_static=False):
        if is_static:
            super().__init__('static', group_name, group_name)
        else:
            super().__init__(adb.device_model_simple(u2d.serial), u2d.serial, group_name)
        self.u2d = u2d

    def record_control_pos(self, control_key: str, u2o: Union[
        uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                           offset=(0.0, 0.0),
                           center_relative_offset=(0.5, 0.5)):
        PresetRecorder.record_control_pos_u2o(self.u2d, self.group_name, control_key, u2o, offset,
                                              center_relative_offset, self.is_static)

    def record_static_control_pos(self, control_key: str, u2o: Union[
        uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                                  offset=(0.0, 0.0),
                                  center_relative_offset=(0.5, 0.5)):
        PresetRecorder.record_control_pos_u2o(self.u2d, self.group_name, control_key, u2o, offset,
                                              center_relative_offset, True)

    def record_pos(self, control_key: str, point: Tuple[float, float]):
        PresetRecorder.record_pos_u2d(self.u2d, self.group_name, control_key, point, self.is_static)

    def record_static_pos(self, control_key: str, point: Tuple[float, float]):
        PresetRecorder.record_pos_u2d(self.u2d, self.group_name, control_key, point, True)

    def record_control_pic(self, control_key: str, u2o: Union[
        uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                           pos_offset=(0.0, 0.0), size_offset=(0.0, 0.0)):
        PresetRecorder.record_control_pic_u2o(self.u2d, self.group_name, control_key, u2o, pos_offset, size_offset,
                                              self.is_static)

    def record_static_control_pic(self, control_key: str, u2o: Union[
        uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                                  pos_offset=(0.0, 0.0), size_offset=(0.0, 0.0)):
        PresetRecorder.record_control_pic_u2o(self.u2d, self.group_name, control_key, u2o, pos_offset, size_offset,
                                              True)

    def record_pic(self, control_key: str, pic_bounds: Tuple[float, float, float, float]):
        PresetRecorder.record_pic_u2d(self.u2d, self.group_name, control_key, pic_bounds, self.is_static)

    def record_static_pic(self, control_key: str, pic_bounds: Tuple[float, float, float, float]):
        PresetRecorder.record_pic_u2d(self.u2d, self.group_name, control_key, pic_bounds, True)
