class ViewModel:
    def reset(self):
        pass

    def refresh_view(self, **kwargs):
        pass

    def start(self):
        pass

    @classmethod
    def get_instance(cls) -> 'ViewModel':
        from powertrde.framework.viewmodel.view_model_manager import ViewModelManager
        return ViewModelManager.get_instance().get_view_model(cls)
