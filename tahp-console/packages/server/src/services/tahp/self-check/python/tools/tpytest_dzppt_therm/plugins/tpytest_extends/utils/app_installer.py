import asyncio
import json
import logging
import os
import subprocess
import uiautomator2

from powertrde import env
from powertrde.env import ADB_EXE
from powertrde.framework.app_installer import AppInstaller
from powertrde.utils.trde import adb
from powertrde.utils import misc_utils
from powertrde.utils.misc_utils import run_as_async
from powertrde.utils.u2_extends.u2d_test_helper_factory import U2DTestHelperFactory
from tpytest.resource_provider import BaseResourceProvider, ResourceProviderFactory
from tpytest_extends.scheme.apps_static_info import AppsStaticInfo

APP_DOWNLOAD_CACHE_DIR = env.get_framework_shared_cache_dir(False, 'app_res')


class AppInstallerForProvider(AppInstaller):
    def __init__(self, res_provider: BaseResourceProvider, device, app_search_name: str, app_package_name: str):
        super().__init__(device, app_search_name, app_package_name)
        self.local_meta_path = None
        self.res_provider: BaseResourceProvider = res_provider

    def read_suffix(self):
        with open(self.local_meta_path, 'r') as file:
            meta = file.read()
        meta_dict = json.loads(meta)
        suffix = meta_dict['suffix']
        return suffix

    async def install(self):
        os.makedirs(APP_DOWNLOAD_CACHE_DIR, exist_ok=True)
        self.local_meta_path = os.path.join(APP_DOWNLOAD_CACHE_DIR,
                                            f'{self.app_search_name}_{self.app_package_name}.meta')

        try:
            with open(self.local_meta_path, 'r', encoding="utf-8") as fp:
                meta = json.load(fp)
                local_version = meta['version']
                local_suffix = meta['suffix']
            temp_local_meta_path = os.path.join(env.get_proj_temp_dir(True), 'apk_res', 'remote_temp.meta')
            await run_as_async(self.res_provider.download,
                               f'apk_res/{self.app_search_name}_{self.app_package_name}.meta', temp_local_meta_path,
                               True)
            with open(temp_local_meta_path, 'r', encoding="utf-8") as fp:
                remote_version = json.load(fp)['version']
            if misc_utils.compare_versions(local_version, remote_version) < 0:
                os.remove(self.local_meta_path)
                os.remove(self.local_meta_path[:-4] + local_suffix)
        except:
            pass

        if not os.path.exists(self.local_meta_path) or not (os.path.exists(
                os.path.join(APP_DOWNLOAD_CACHE_DIR,
                             f'{self.app_search_name}_{self.app_package_name}.apk')) or os.path.exists(
            os.path.join(APP_DOWNLOAD_CACHE_DIR, f'{self.app_search_name}_{self.app_package_name}.xapk'))):
            await run_as_async(self.res_provider.download,
                               f'apk_res/{self.app_search_name}_{self.app_package_name}.meta', self.local_meta_path,
                               True)
            suffix = self.read_suffix()
            local_apk_xapk_path = os.path.join(APP_DOWNLOAD_CACHE_DIR,
                                               f'{self.app_search_name}_{self.app_package_name}.{suffix}')
            await run_as_async(self.res_provider.download,
                               f'apk_res/{self.app_search_name}_{self.app_package_name}.{suffix}', local_apk_xapk_path,
                               True)

        if not os.path.exists(self.local_meta_path):
            logging.info(f"nas和本地都无该app的meta： {self.app_search_name}")
            return False  # 没有复制成功

        suffix = self.read_suffix()
        local_apk_xapk_path = os.path.join(APP_DOWNLOAD_CACHE_DIR,
                                           f'{self.app_search_name}_{self.app_package_name}.{suffix}')
        if not os.path.exists(local_apk_xapk_path):
            logging.info(f"nas和本地都无该app： {self.app_search_name}")
            return False  # 没有复制成功
        try:
            helper = U2DTestHelperFactory.get_instance().get_or_create(self.device)
            install_result = helper.install_app(apk_or_xapk_filepath=local_apk_xapk_path)
            if not install_result:
                install_result = helper.install_app(apk_or_xapk_filepath=local_apk_xapk_path, flags=('-r', '-t'))
            return install_result
        except Exception as e:
            if local_apk_xapk_path.endswith('xapk'):
                return adb.install_xapk(self.device, local_apk_xapk_path)
            else:
                return adb.install_apk(self.device, local_apk_xapk_path)



async def async_function(sn):
    # self.res_provider.list_contents('apk_res')  # [('apks/Facebook_com.facebook.apk', False)]
    rp = ResourceProviderFactory.create('smb://10.205.101.200/nas2/resource/ppt_test_resources', username='monkeytest',
                                        password='Monkey123')

    with open("temp_today1.txt", encoding='utf-8') as f:
        a = f.readlines()

    need_install_list = []  # 替换为你需要安装的关键字列表
    for i in a:
        temp = i.strip()
        need_install_list.append(temp)

    # 获取已安装包列表
    installed_list = subprocess.check_output([ADB_EXE, "-s", sn, 'shell', 'pm', 'list', 'packages'])
    installed_list = installed_list.decode('utf-8').splitlines()
    installed_list = [pkg.split(':')[1] for pkg in installed_list]

    cant_find = {}
    # 遍历需要安装的列表
    for app_name in need_install_list:
        pkg = AppsStaticInfo.get_app_package_by_name(app_name)
        if pkg in installed_list:
            continue
        # aifp = AppInstallerForProvider(rp, u2d, "Telegram", "org.telegram.messenger")
        aifp = AppInstallerForProvider(rp, sn, app_name, pkg)
        res = await aifp.install()
        if not res:
            cant_find[app_name] = pkg
    print(cant_find)


if __name__ == '__main__':
    asyncio.run(async_function("1207125414000521"))

    # nas = ResourceProviderFactory.create('smb://10.205.101.200/nas2/resource/ppt_test_resources', username='monkeytest',
    #                                      password='Monkey123')
    # # print(nas.list_contents('tools'))
    # # nas.download('tools', 'D:\\hehe2')
    #
    # # BaseResourceProvider.local_adb_push(adb.first_device(), 'D:\\tmp\\haha\\hehe2.txt', '/sdcard/Documents/', True)
    # # 查看apk版本号
    # misc_utils.get_apk_file_version(...)
    #
    # # 取得已安装的版本号
    # adb.get_installed_package_version(..., ...)
    #
    # a = Version('1.0.1')
    # b = Version('1.0.14')
    # if a < b:
    #     ...
    # pkg = AppsStaticInfo.get_app_package_by_name(app_name)
    #         if not pkg:
    #             return False
