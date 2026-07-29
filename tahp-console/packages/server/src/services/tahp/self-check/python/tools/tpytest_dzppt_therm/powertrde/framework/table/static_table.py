from typing import Optional, Dict, TypeVar, Generic

from powertrde.framework.table.default_static_table_loader import DefaultStaticTableLoader
from powertrde.framework.table.base_table_loader import BaseTableLoader
from powertrde.framework.table.static_info import StaticInfo


T = TypeVar('T', bound=StaticInfo)


class StaticTable(Generic[T]):
    def __init__(self, static_info_class: type, table_file_name: str, table_loader: Optional[BaseTableLoader] = None):
        self.is_loaded = False
        self.infos: Dict[str, T] = {}
        self.table_loader = table_loader
        if not self.table_loader:
            from powertrde.framework.table.table_manager import TableManager
            self.table_loader = TableManager.get_instance().get_loader(DefaultStaticTableLoader)
        self.static_info_class = static_info_class
        self.table_file_name = table_file_name

    def get_info_with_default(self, key: str, default_value=None) -> Optional[T]:
        if self.static_info_class.convert_to_lower_key:
            key = key.lower()
        return self.infos.get(key, default_value)

    def get_info(self, key: str) -> T:
        if self.static_info_class.convert_to_lower_key:
            key = key.lower()
        return self.infos[key]

    def has_info(self, key: str) -> bool:
        return key in self.infos

    def load_if_needed(self):
        if self.is_loaded:
            return
        self.reload()

    def reload(self):
        self.infos.clear()
        table_dict = self.table_loader.load_table(self.table_file_name, self.static_info_class.convert_to_lower_key)
        for k, v in table_dict.items():
            si: StaticInfo = self.static_info_class()
            si.assign_fields(v)
            self.infos[k] = si
        self.is_loaded = True
