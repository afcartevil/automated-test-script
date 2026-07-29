#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@Project ：dz_auto_env 
@File    ：aw_app_googleplay
@Author  ：xingzhi.chen
@Date    ：2025/8/21 10:57 
"""
import time
from typing import Union

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase
from tpytest_extends.scheme.apps_static_info import AppsStaticInfo


class GooglePlayLocator(U2SelectorLocator):
    search_btn = U2Selector().xpath('//android.widget.TextView[@text="Search"]').bind()
    install_item = U2Selector().xpath('//android.widget.TextView[@text="Install"]').bind()
    cancel_item = U2Selector().xpath('//android.widget.TextView[@text="Cancel"]').bind()
    play_item = U2Selector().xpath('//*[@content-desc="Play"]').bind()
    open_item = U2Selector().xpath('//*[@content-desc="Open"]').bind()
    got_it_item = U2Selector().text_contains('Got it').bind()
    send_feedback_item = U2Selector().text_contains('Send feedback').bind()


class AwAppGooglePlay(GooglePlayLocator, AwAppBase):
    aw_name = 'GooglePlay'
    default_app_package = 'com.google.android.gms'

    def playstore_install_app(self, app_name: Union[str, AppsStaticInfo]):
        """
        通过应用商店 安装app
        安装前检查wifi是否连接
        """
        self.u2d_helper.screen_on_and_unlock()
        self.ensure_wifi_connection()

        if isinstance(app_name, AppsStaticInfo):
            app_info = app_name
        elif isinstance(app_name, str):
            app_info = AppsStaticInfo.get_app_info_no_raise(app_name)
        else:
            raise TypeError(f"app_name 必须是 str 或 AppsStaticInfo，实际类型: {type(app_name)}")

        if app_info is None:
            t_log.warning(f'[安装app时未找到app:{app_name}]', ext_event=True)
            return
        if self.u2d_helper.is_app_installed(app_info.package):
            t_log.info(f'[执行安装前，发现app已安装，跳过安装:{app_name}]', ext_event=True)
            return

        with self.u2_apply_watchers(tags_any=['playstore']):
            if not self.u2d_helper.is_app_installed(app_info.package):
                t_log.info(f'[安装app:{app_name}]', ext_event=True)
                self.u2d_helper.open_playstore_page(app_info.package)
                time.sleep(10)
                if self.install_item.wait(timeout=20):
                    t_log.info(f'[点击安装按钮:{app_name}]', ext_event=True)
                    self.install_item.click()
                    time.sleep(5)
                    if self.u2d.xpath('//*[@text="When Wi-Fi is available"]').exists:
                        self.u2d.xpath('//*[@text="When Wi-Fi is available"]').click()
                        self.u2d.xpath('//*[@text="OK"]').click_exists(timeout=5)
                        self.u2d.xpath('//*[@text="Download"]').click_exists(timeout=3)
                    time.sleep(3)
                elif self.cancel_item.wait(timeout=5):
                    t_log.info(f'[应用正在安装:{app_name}]', ext_event=True)
                    return
                elif self.play_item.wait(timeout=5):
                    t_log.info(f'[应用已经安装:{app_name}]', ext_event=True)
                    return
                elif self.open_item.wait(timeout=5):
                    t_log.info(f'[应用已经安装:{app_name}]', ext_event=True)
                    return
                elif self.got_it_item.exists and self.send_feedback_item.exists:
                    t_log.info(f'[触发google play 检测安装机制:{app_name}]', ext_event=True)
                    self.got_it_item.click_gone(interval=5)
                    return
                else:
                    t_log.error(f'[未找到安装按钮:{app_name}]', ext_event=True)
                    raise Exception(f"{app_name}应用不能安装")
            else:
                return

    def ensure_wifi_connection(self, timeout=300):
        """
        确保WiFi连接正常，超时时间为5分钟（默认300秒）
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            for attempt in range(3):  # 尝试三次
                try:
                    self.u2d_helper.check_wifi_network_connection()
                    t_log.info('[WiFi连接成功]', ext_event=True)
                    return  # 成功连接后直接返回
                except Exception as e:
                    t_log.warning(f'[WiFi连接尝试失败: 第{attempt + 1}次]', ext_event=True)
                    time.sleep(5)  # 每次尝试间隔2秒
            # 如果三次尝试失败，则开启关闭WiFi
            t_log.info('[尝试开启关闭WiFi以恢复连接]', ext_event=True)
            self.u2d_helper.open_close_wifi(False)
            time.sleep(4)
            self.u2d_helper.open_close_wifi(True)
            time.sleep(10)
        # 超时处理
        raise TimeoutError('[WiFi连接失败: 超过5分钟]')
