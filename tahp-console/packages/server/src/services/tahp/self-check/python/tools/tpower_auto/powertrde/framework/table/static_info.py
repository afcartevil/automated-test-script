
class StaticInfo:
    # 默认加载的表格文件
    default_load_file = ''
    # 默认的表格加载器或其工厂
    default_table_loader_or_factory = None
    # 自动将Table的键转为小写
    convert_to_lower_key = False

    @classmethod
    def get_default_table(cls):
        from powertrde.framework.table.table_manager import TableManager
        return TableManager.get_instance().get_or_load_table_with_default(cls)

    def __init__(self):
        self._i = 0
        self.id = ""
        self._ori_id = ""
        self.user_args = {}

    @property
    def ori_id(self):
        return self._ori_id

    def assign_fields(self, fields_dict: dict):
        for key, value in fields_dict.items():
            if not self._on_assign_field(key, value):
                setattr(self, key, value)
        self._on_assign_fields_finished(fields_dict)

    def _on_assign_field(self, filed_name: str, value) -> bool:
        """
        自定义赋值字段
        如果返回 True 表示已自行接管赋值，框架不再自动赋值
        """
        return False

    def _on_assign_fields_finished(self, origin_fields_dict: dict):
        """
        当所有字段赋值完成后，会回调该方法，请覆写用于额外处理逻辑
        """
        pass
