class AppInstaller:
    """
    封装了手机下载应用的逻辑，便于在其他地方调用下载应用的功能。
    """

    def __init__(self, device, app_search_name: str, app_package_name: str):
        self.device = device
        self.app_search_name = app_search_name
        self.app_package_name = app_package_name

    def install(self):
        raise NotImplementedError()

    @classmethod
    def update_app_repo_index(cls, app_repo_client):
        pass
