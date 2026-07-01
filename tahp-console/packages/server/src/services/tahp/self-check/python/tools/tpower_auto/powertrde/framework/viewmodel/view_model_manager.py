from typing import Type, Dict

from powertrde.framework.viewmodel.view_model import ViewModel


class ViewModelManager:
    _instance: 'ViewModelManager' = None

    @staticmethod
    def get_instance() -> 'ViewModelManager':
        if not ViewModelManager._instance:
            ViewModelManager._instance = ViewModelManager()
        return ViewModelManager._instance

    def __init__(self):
        self._view_models: Dict[Type, ViewModel] = {}

    def get_view_model(self, view_model_type: Type):
        if view_model_type not in self._view_models:
            self._view_models[view_model_type] = view_model_type()
        return self._view_models[view_model_type]
