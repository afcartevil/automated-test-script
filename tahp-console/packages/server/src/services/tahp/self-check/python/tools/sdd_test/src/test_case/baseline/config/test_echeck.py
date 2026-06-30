# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import getprop,get_desktop_widget

def test_searchcheck(device_serial):
    """
    检查ru市场的search bar应该是chrome search而不是google search
    """
    is_ru = getprop("ro.tr_build.sw_market", device_serial).strip() == "ru"
    widgets_list = get_desktop_widget(device_serial)
    if widgets_list == None:
        pytest.error(f"未获取到当前桌面上的widget列表")
    
    chrome_search_widget = "com.android.chrome/org.chromium.chrome.browser.searchwidget.SearchWidgetProvider"
    google_search_widget = "com.google.android.googlequicksearchbox/com.google.android.googlequicksearchbox.SearchWidgetProvider"
    google_search_widget_1 = "com.google.android.googlequicksearchbox/com.google.android.apps.gsa.staticplugins.searchwidget.GoogleSearchWidgetProvider"
    
    cbool = chrome_search_widget in widgets_list
    gbool = google_search_widget in widgets_list or google_search_widget_1 in widgets_list
    
    logging.info(f"chrome search  {cbool}, google search  {gbool}")
    
    if not cbool ^ gbool:  #拦截 都配置 或 都未配置
        pytest.fail(f"search bar 配置错误: 未配置或配置了2个search bar")
    
    if cbool and not is_ru:
        pytest.fail(f"非ru 市场的配置了chrome search widget")
    if gbool and is_ru:
        pytest.fail(f"ru 市场的配置了google search widget")
        
        
