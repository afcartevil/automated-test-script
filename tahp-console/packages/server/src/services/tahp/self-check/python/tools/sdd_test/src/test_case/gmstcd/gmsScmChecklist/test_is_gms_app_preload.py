# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    get_feature,
    get_dumpsys_package,
)


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_non_go_device()
def test_nongo_gms_app_preload(device_serial):
    # Non-GO GMS mandatory app 检查
    mIsVelvet_preload = get_dumpsys_package(device_serial, "com.google.android.googlequicksearchbox" , "versionName")
    logging.info(f"get_mIsVelvet_preload : {mIsVelvet_preload} ")

    mIsMaps_preload = get_dumpsys_package(device_serial, "com.google.android.apps.maps" , "versionName" ,)
    logging.info(f"get_mIsMaps_preload : {mIsMaps_preload} ")

    mIsYoutube_preload = get_dumpsys_package(device_serial,"com.google.android.youtube" , "versionName")
    logging.info(f"get_mIsYoutube_preload : {mIsYoutube_preload} ")

    mIsDrive_preload = get_dumpsys_package(device_serial,"com.google.android.apps.docs" , "versionName")
    logging.info(f"get_mIsDrive_preload : {mIsDrive_preload} ")

    mIsYTmusic_preload = get_dumpsys_package(device_serial,"com.google.android.apps.youtube.music" , "versionName")
    logging.info(f"get_mIsYTmusic_preload : {mIsYTmusic_preload} ")

    mIsVideos_preload = get_dumpsys_package(device_serial,"com.google.android.videos" , "versionName")
    logging.info(f"get_mIsVideos_preload : {mIsVideos_preload} ")

    mIsMeet_preload = get_dumpsys_package(device_serial,"com.google.android.apps.tachyon" , "versionName")
    logging.info(f"get_mIsMeet_preload : {mIsMeet_preload} ")

    mIsGoogleFilse_preload = get_dumpsys_package(device_serial,"com.google.android.apps.nbu.files" , "versionName")
    logging.info(f"get_mIsGoogleFilse_preload : {mIsGoogleFilse_preload} ")

    mIsGmail2_preload = get_dumpsys_package(device_serial,"com.google.android.gm" , "versionName")
    logging.info(f"get_mIsGmail2_preload : {mIsGmail2_preload} ")

    mIsChrome_preload = get_dumpsys_package(device_serial,"com.android.chrome" , "versionName")
    logging.info(f"get_mIsChrome_preload : {mIsChrome_preload} ")

    mIsPhotos_preload = get_dumpsys_package(device_serial,"com.google.android.apps.photos" , "versionName")
    logging.info(f"get_mIsPhotos_preload : {mIsPhotos_preload} ")

    if mIsVelvet_preload is None \
            or mIsChrome_preload is None \
            or mIsGmail2_preload is None \
            or mIsMaps_preload is None \
            or mIsYoutube_preload is None \
            or mIsDrive_preload is None \
            or mIsYTmusic_preload is None \
            or mIsVideos_preload is None \
            or mIsMeet_preload is None \
            or mIsPhotos_preload is None \
            or mIsGoogleFilse_preload is None:
        pytest.fail("GMS mandatory app NOT install")


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_go_device()
def test_go_gms_app_preload(device_serial):
    # GO GMS mandatory app 检查
    mIsAssistantGo_preload = get_dumpsys_package(device_serial, "com.google.android.apps.assistant" , "versionName")
    logging.info(f"get_mIsAssistantGo_preload : {mIsAssistantGo_preload} ")

    mIsMaps_preload = get_dumpsys_package(device_serial, "com.google.android.apps.maps" , "versionName" ,)
    logging.info(f"get_mIsMaps_preload : {mIsMaps_preload} ")

    mIsYoutube_preload = get_dumpsys_package(device_serial,"com.google.android.youtube" , "versionName")
    logging.info(f"get_mIsYoutube_preload : {mIsYoutube_preload} ")

    mIsDrive_preload = get_dumpsys_package(device_serial,"com.google.android.apps.docs" , "versionName")
    logging.info(f"get_mIsDrive_preload : {mIsDrive_preload} ")

    mIsYTmusic_preload = get_dumpsys_package(device_serial,"com.google.android.apps.youtube.music" , "versionName")
    logging.info(f"get_mIsYTmusic_preload : {mIsYTmusic_preload} ")

    mIsVideos_preload = get_dumpsys_package(device_serial,"com.google.android.videos" , "versionName")
    logging.info(f"get_mIsVideos_preload : {mIsVideos_preload} ")

    mIsMeetGo_preload = get_dumpsys_package(device_serial,"com.google.android.apps.tachyon" , "versionName")
    logging.info(f"get_mIsMeetGo_preload : {mIsMeetGo_preload} ")

    mIsGoogleFilse_preload = get_dumpsys_package(device_serial,"com.google.android.apps.nbu.files" , "versionName")
    logging.info(f"get_mIsGoogleFilse_preload : {mIsGoogleFilse_preload} ")

    mIsGmail2_preload = get_dumpsys_package(device_serial,"com.google.android.gm" , "versionName")
    logging.info(f"get_mIsGmail2_preload : {mIsGmail2_preload} ")

    mIsChrome_preload = get_dumpsys_package(device_serial,"com.android.chrome" , "versionName")
    logging.info(f"get_mIsChrome_preload : {mIsChrome_preload} ")

    mIsGoogleSearchGo_preload = get_dumpsys_package(device_serial,"com.google.android.apps.searchlite" , "versionName")
    logging.info(f"get_mIsGoogleSearchGo_preload : {mIsGoogleSearchGo_preload} ")

    mIsGallery_preload = get_dumpsys_package(device_serial,"com.google.android.apps.photosgo" , "versionName")
    logging.info(f"get_mIsGallery_preload : {mIsGallery_preload} ")


    if mIsAssistantGo_preload is None \
            or mIsGmail2_preload is None \
            or mIsMaps_preload is None \
            or mIsYoutube_preload is None \
            or mIsDrive_preload is None \
            or mIsYTmusic_preload is None \
            or mIsVideos_preload is None \
            or mIsGoogleSearchGo_preload is None \
            or mIsMeetGo_preload is None \
            or mIsChrome_preload is None \
            or mIsGallery_preload is None \
            or mIsGoogleFilse_preload is None:
        pytest.fail("GMS mandatory app NOT install")



