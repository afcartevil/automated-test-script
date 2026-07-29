class TaskSessionConfig:
    def __init__(self):
        super().__init__()
        self.config_dict = {}
        self.override_config_dict = {}
        self.device_id = ''
        self.c_device_id = ''
        self.o_device_id = ''
        self.session_id = ''
        self.user_args = {}

    @property
    def configured_config_dict(self):
        return self.config_dict

    def _fill_fields(self):
        self.device_id = self.config_dict.get('device_id', '')
        self.c_device_id = self.config_dict.get('c_device_id', '')
        self.o_device_id = self.config_dict.get('o_device_id', '')
        self.session_id = self.config_dict.get('session_id', '')
        self.user_args = self.config_dict.get('user_args', {})

    def overwrite_config(self, overwrite_value):
        self.override_config_dict.update(overwrite_value)
        self.config_dict.update(self.override_config_dict)
        self._fill_fields()

    def get_config(self, config_key: str, fallback_value=None):
        return self.configured_config_dict.get(config_key, fallback_value)

    def get_config_or_raise(self, config_key: str):
        return self.configured_config_dict[config_key]
