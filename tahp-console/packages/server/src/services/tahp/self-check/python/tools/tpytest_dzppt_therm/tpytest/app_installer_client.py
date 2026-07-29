from powertrde.framework.app_installer import AppInstaller
from tpytest.app_repo_client_protocol import AppRepoClientProtocol


class AppInstallerForClient(AppInstaller):
    def __init__(self, app_repo_client: AppRepoClientProtocol, device_id: str, app_package_name: str, update_version: bool, install_options: tuple):
        super().__init__(device_id, app_package_name, app_package_name)
        self.app_repo_client = app_repo_client
        self.compare_mode = 'version_code' if update_version else 'existence'
        self.install_options = install_options

    def install(self):
        return self.app_repo_client.install_cached_to_device(self.device, self.app_package_name, compare_mode=self.compare_mode, install_options=self.install_options)

    @classmethod
    def update_app_repo_index(cls, app_repo_client: AppRepoClientProtocol):
        app_repo_client.fetch_global_index()


if __name__ == '__main__':
    ...
