from powertrde.utils import collection_utils


class BaseTableLoader:
    def on_load_table(self, table_name: str, primary_key_to_lower=False) -> dict:
        pass

    def load_table(self, table_name: str, primary_key_to_lower=False) -> dict:
        ret = self.on_load_table(table_name, primary_key_to_lower)
        ret = self._strip_load_table_dict(ret)
        return ret

    def _strip_load_table_dict(self, loaded_dict: dict):
        return collection_utils.strip_dict(loaded_dict, max_depth=1)
