# -*- coding: utf-8 -*-
# @Time     : 2025/7/3 11:37
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_boomplay.py
import time

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase


class AwAppBoomplay(AwAppBase):
    aw_name = 'Boomplay'
    default_app_package = 'com.afmobi.boomplayer'

    def tt(self, template_key: str, debug_fallback_value=None):
        """
        同 get_typed_template
        从类级别的“模板录制”中获取录制记录
        """
        return self.get_typed_template(template_key, debug_fallback_value)

    def skip_ads(self, xpath_str, try_times=3):
        """
        广告处理
        """
        for _ in range(int(try_times)):
            icon = self.u2d.xpath(xpath_str).wait(timeout=1)
            if not icon:
                time.sleep(3)
                self.u2d_helper.press_back_key(1)
            icon = self.u2d.xpath(xpath_str).wait(timeout=1)
            if not icon:
                time.sleep(3)
                self.u2d_helper.press_back_key(1)
            icon = self.u2d.xpath(xpath_str).wait(timeout=1)
            if not icon:
                ad = self.u2d_helper.und_u2.match_template(self.tt('ads'), target_score=0.8)
                if ad:
                    self.u2d_helper.und_u2.click_tuple(ad.center)
                time.sleep(3)
            icon = self.u2d.xpath(xpath_str).wait(timeout=1)
            if not icon:
                self.u2d.click(0.9, 0.07)
                time.sleep(3)

    def click_playlist(self):
        """
        点击歌单
        """
        albums = self.u2d.xpath('//*[@text="Trending Albums"]').wait(timeout=1)
        trending_playlists = self.u2d.xpath('//*[@text="Trending Playlists"]').wait(timeout=1)
        playlist_hub = self.u2d.xpath('//*[@text="Playlist Hub"]').wait(timeout=1)
        if albums:
            albums_location = self.u2d.xpath('//*[@text="Trending Albums"]')
            x = (albums_location.info['bounds']['left'] + albums_location.info['bounds']['right']) / 2
            y = (albums_location.info['bounds']['top'] + albums_location.info['bounds']['bottom']) / 2
        elif trending_playlists:
            playlists_location = self.u2d.xpath('//*[@text="Trending Playlists"]')
            x = (playlists_location.info['bounds']['left'] + playlists_location.info['bounds']['right']) / 2
            y = (playlists_location.info['bounds']['top'] + playlists_location.info['bounds']['bottom']) / 2
        elif playlist_hub:
            hub_location = self.u2d.xpath('//*[@text="Playlist Hub"]')
            x = (hub_location.info['bounds']['left'] + hub_location.info['bounds']['right']) / 2
            y = (hub_location.info['bounds']['top'] + hub_location.info['bounds']['bottom']) / 2
        else:
            # 前面的都找不到，走到else有可能点到歌曲，不是歌单
            image_location = self.u2d.xpath('com.afmobi.boomplayer:id/imgCover')
            x = (image_location.info['bounds']['left'] + image_location.info['bounds']['right']) / 2
            y = (image_location.info['bounds']['top'] + image_location.info['bounds']['bottom']) / 2
        self.u2d.click(x, y+300)
        time.sleep(1)
        play = self.u2d.xpath('//*[@resource-id="com.afmobi.boomplayer:id/playpage_play"]').wait(timeout=1)
        if play:
            self.u2d.xpath('//*[@resource-id="com.afmobi.boomplayer:id/playpage_play"]').click()
            time.sleep(1)

    def click_library_tab(self):
        """
        点击Library tab
        """
        self.skip_ads('//*[@text="Library"]')
        self.u2d.xpath('//*[@text="Library"]').click(timeout=1)
        time.sleep(2)

    def click_music_tab(self):
        """
        点击Music tab
        """
        self.skip_ads('//*[@text="Music"]')
        self.u2d.xpath('//*[@text="Music"]').click(timeout=1)
        time.sleep(2)
