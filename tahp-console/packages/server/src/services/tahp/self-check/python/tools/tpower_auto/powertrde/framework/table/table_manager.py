from typing import Dict, Optional, TypeVar, Type

from powertrde.framework.table.base_table_loader import BaseTableLoader
from powertrde.framework.table.static_info import StaticInfo
from powertrde.framework.table.static_table import StaticTable

T = TypeVar('T', bound=StaticInfo)


class TableManager:
    _instance: 'TableManager' = None

    @staticmethod
    def get_instance() -> 'TableManager':
        if not TableManager._instance:
            TableManager._instance = TableManager()
        return TableManager._instance

    def __init__(self):
        self._loaders: Dict[type, BaseTableLoader] = {}
        self._static_tables: Dict[type, StaticTable] = {}

    def get_loader(self, loader_class: type) -> BaseTableLoader:
        exist_loader = self._loaders.get(loader_class)
        if exist_loader:
            return exist_loader
        else:
            exist_loader = loader_class()
            self._loaders[loader_class] = exist_loader
        return exist_loader

    def set_loader(self, loader: BaseTableLoader):
        self._loaders[type(loader)] = loader

    def load_static_table(self, static_info_class: Type[T], table_file_name: str,
                          table_loader: Optional[BaseTableLoader] = None) -> StaticTable[T]:
        table = StaticTable(static_info_class, table_file_name, table_loader)
        self._static_tables[static_info_class] = table
        table.reload()
        return table

    def get_static_table(self, static_info_class: Type[T]) -> StaticTable[T]:
        return self._static_tables[static_info_class]

    def get_or_load_table_with_default(self, static_info_class: Type[T]) -> StaticTable[T]:
        exist_table = self._static_tables.get(static_info_class)
        if not exist_table:
            default_table_loader = static_info_class.default_table_loader_or_factory
            if callable(static_info_class.default_table_loader_or_factory):
                default_table_loader = static_info_class.default_table_loader_or_factory()
            exist_table = self.load_static_table(static_info_class, static_info_class.default_load_file, default_table_loader)
        return exist_table
