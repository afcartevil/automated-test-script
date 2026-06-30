# -*- coding: utf-8 -*-
import os
import pytest
import logging
import pandas as pd

from src.utils.adb.adb_utils import (
    get_feature,
    getprop,
    get_dumpsys_package,
    is_GO_device,
    get_product_name_without_market,
)

XLSX_DIR = os.path.dirname(os.path.abspath(__file__))
GMS_HISTORY_MODIFY_XLSX = os.path.join(XLSX_DIR, "GMS_Package_APK_version_release_history_modify.xlsx")
GMS_HISTORY_RELEASE_XLSX = os.path.join(XLSX_DIR, "GMS_Package_APK_version_release_history.xlsx")


def compare_app_version(str1, str2):

    # pandas 从 Excel 读取纯数字单元格时可能返回 int/float，需强制转为 str
    str1 = str(str1) if str1 is not None else ""
    str2 = str(str2) if str2 is not None else ""

    TEST_OK = "test_OK"
    TEST_FAIL = "test_FAIL"

    if str1 == str2:
        # case 0: same,test_OK
        return TEST_OK
    else:
        if " " in str1 \
                or " " in str2:
            # case 1: contain Spaces
            str1 = str1.split(" ")
            str1 = str1[0]

            str2 = str2.split(" ")
            str2 = str2[0]

        if "-" in str1 \
                and "." in str1:
            # case : contain "."和“-”
            str1 = str1.split("-")
            str1 = str1[0]
            str2 = str2.split("-")
            str2 = str2[0]

        if "." in str1:
            split_value = "."
        elif "-" in str1:
            split_value = "-"
        elif "_" in str1:
            split_value = "_"
        else:
            split_value = "."

        if "." in str2:
            split_value_2 = "."
        elif "-" in str2:
            split_value_2 = "-"
        elif "_" in str2:
            split_value_2 = "_"
        else:
            split_value_2 = "."

        list_str1 = str1.split(split_value)
        list_str2 = str2.split(split_value_2)

        for i in range(len(list_str1)):
            if list_str1[i] == list_str2[i]:
                # case 2
                continue
            else:
                try:
                    int(list_str1[i])
                    int(list_str2[i])
                except:
                    logging.info(f"str1={str1}; str2={str2}")
                    logging.info(f"list_str1 = {list_str1}")
                    logging.info(f"list_str2 = {list_str2}")
                    # return TEST_FAIL      //0.1.453788429 0.1.stub 无法对比
                    return TEST_OK

                if int(list_str1[i]) < int(list_str2[i]):
                    # case 3: App version is updated,return test_OK
                    return TEST_OK
                elif int(list_str1[i]) == int(list_str2[i]):
                    # case 4
                    continue
                else:
                    # case 5: App version is degraded,return test_FAIL
                    logging.info(f"case 5: App version is degraded,return test_FAIL")
                    logging.info(f"list_str1 = {list_str1}")
                    logging.info(f"list_str2 = {list_str2}")
                    return TEST_FAIL

            return TEST_OK

@pytest.mark.require_android_version_min(15)
def test_gms_app_version_check(device_serial):

        is_android_go_support = is_GO_device(device_serial)
        project_name_value = get_product_name_without_market(device_serial)
        special_market_value = (getprop("ro.tran.sw.market", device_serial) or getprop("ro.tr_build.sw_market", device_serial) or "").strip().lower()
        is_gms_express_plus = bool(get_feature(device_serial, "com.google.android.feature.GMSEXPRESS_PLUS_BUILD"))

        ro_build_version_release = getprop('ro.build.version.release' , device_serial)

        mGmsversion_value = getprop('ro.com.google.gmsversion' , device_serial)
        logging.info(f"mGmsversion_value = {mGmsversion_value}")

        # 由于spug上不能填写产品信息，此处和spm沟通需要过滤掉X6725B_tOS16
        # project_name = utilo.pmsinfo['project_name']
        # if project_name == "X6725B_tOS16":
        #     return True


        mtk_branch_value = getprop('ro.mediatek.version.branch' , device_serial)

        if mtk_branch_value == "":
            branch_code_name = "Unisoc"
        else:
            branch_code_name = "MTK"
        logging.info(f"branch_code_name = {branch_code_name}")
        
        """
        MTK/Unisoc: 14_202406  14_202408 pass
        """
        if "14_202406" in mGmsversion_value \
                or "14_202408" in mGmsversion_value:
            return
                
        """
        
        MTK: 14_202311 14_202404 14_202405 14_202406 15_202406 OK
        Unisoc: 14_202405 14_202406 OK
        """
        if branch_code_name == "Unisoc":
            if "14_202310" in mGmsversion_value \
                    or "14_202311" in mGmsversion_value \
                    or "14_202401" in mGmsversion_value \
                    or "14_202403" in mGmsversion_value \
                    or "14_202404" in mGmsversion_value:
                return

        '''
        Android GMS包版本对应的表格名
        '''
        dict_build_version_sheet_name = {"13": "T 13",
                                         "14": "U 14",
                                         "15": "V 15",
                                         "16": "B 16",
                                         "17": "C 17"}

        mSheet_name = dict_build_version_sheet_name.get(ro_build_version_release)
        logging.info(f"mSheet_name = {mSheet_name}")

        if mSheet_name is None:
            return

        df = pd.read_excel(GMS_HISTORY_MODIFY_XLSX, sheet_name=mSheet_name, engine='openpyxl')
        df_google_release = pd.read_excel(GMS_HISTORY_RELEASE_XLSX, sheet_name=mSheet_name, engine='openpyxl')

        #表格中空值以“0”填充
        df_filled = df.fillna(value="0")
        df_google_release_filled = df_google_release.fillna(value="0")

        df_shape = df_filled.shape  # 获取列数，‌df.shape返回一个元组，‌表示行数和列数
        num_row_value = df_shape[0]
        num_columns_value = df_shape[1]
        # logging.info(f"The total number of row is: {num_row_value}")
        # logging.info(f"The total number of columns is: {num_columns_value}")

        """
        GMS_Package_APK_version_release_history.xlsx 修改前后对比
        """
        differences = []
        for row in range(num_row_value):
            len_any_row_list = len(df_filled.values[row])
            if len_any_row_list > 0:
                for i in range(len_any_row_list):
                    if df_filled.values[row][i] != df_google_release_filled.values[row][i]:
                        differences.append((row, df_filled.values[row][2], df_filled.values[row][i], df_google_release_filled.values[row][i]))

        # if len(differences) > 0:
        #     for i in range(len(differences)):
        #         logging.info(f"{differences[i]}")

        """
        GMS_Package_APK_version_release_history.xlsx 表格中应用禁止降级。
        首个应用版本 ConfigUpdater 14_202310 坐标 df.iloc[2,3]
        """

        for row in range(num_row_value):
            for colume in range(num_columns_value - 1):
                if row >= 2 and colume >= 3:
                    base_colume_value = df_filled.iloc[row,colume]
                    update_colume_value = df_filled.iloc[row,colume+1]

                    value_compare =  compare_app_version(base_colume_value,update_colume_value)

                    if value_compare == "test_FAIL":
                        logging.info(f"base_colume_value : {base_colume_value}")
                        logging.info(f"update_colume_value : {update_colume_value}")

                        fail_app_name = df_filled.iloc[row,2]
                        reason = "Gms app " + fail_app_name + " version is degraded"

                        if fail_app_name == "com.google.android.tag":
                            continue

                        pytest.fail(reason)



        mGms_app_preload_package_name_list = ["com.google.android.configupdater",
                                              # "com.google.android.gms.policy_sidecar_aps",    #preload,but dumpsys is null
                                              "com.google.android.gms",   #preload,but versionName is not match
                                              "com.google.android.feedback",
                                              "com.google.android.onetimeinitializer",
                                              "com.google.android.partnersetup",
                                              "com.google.android.apps.restore",
                                              "com.google.android.gsf",
                                              # "com.google.android.gms.location.history",
                                              # "com.google.android.apps.actionsservice",   #not install,gms_eea_type1.mk
                                              "com.android.vending",
                                              "com.google.android.setupwizard",
                                              "com.google.android.apps.setupwizard.searchselector",   #EU/IN install
                                              "com.google.android.googlequicksearchbox",   #preload,Velvet_arm64_CircleToSearch is not match
                                              "com.google.android.projection.gearhead",
                                              "com.google.android.apps.wellbeing",
                                              "com.google.android.as",
                                              "com.google.android.as.oss",
                                              "com.google.android.gms.supervision",
                                              # "com.google.android.ims",   #not install
                                              "com.google.android.dialer",   #COCL install
                                              # "com.google.android.tag",   #not install
                                              # "com.google.android.apps.turbo",   #not install
                                              "com.google.android.apps.safetyhub",
                                              "com.google.android.packageinstaller",
                                              "com.android.chrome",
                                              "com.google.android.apps.docs",
                                              "com.google.android.apps.tachyon",
                                              "com.google.android.gm",
                                              "com.google.android.syncadapters.calendar",
                                              "com.google.android.apps.maps",
                                              "com.google.android.apps.photos",
                                              "com.google.android.videos",
                                              "com.google.android.webview",
                                              "com.google.android.youtube",   #preload,but versionName is not match
                                              "com.google.android.apps.youtube.music",
                                              "com.google.android.tts",
                                              # "com.google.android.calculator",    #not install
                                              "com.google.android.calendar",
                                              # "com.google.ambient.streaming",
                                              # "com.google.android.apps.carrier.carrierwifi",
                                              # "com.google.android.deskclock",
                                              # "com.google.android.accessibility.switchaccess",
                                              "com.google.android.contacts",    #COCL install
                                              # "com.google.android.keep",
                                              # "com.google.android.inputmethod.latin",  #Cl8v not install
                                              "com.google.android.marvin.talkback",
                                              "com.google.android.apps.messaging",
                                              "com.google.android.ext.shared",
                                              "com.google.android.printservice.recommendation",
                                              "com.google.android.apps.assistant",
                                              "com.google.android.apps.photosgo",
                                              "com.google.android.apps.searchlite",
                                              "com.google.android.apps.nbu.files"]

        '''
        U 14_202406:
        'reason': 'com.google.android.gms:24.15.18 (190308-627556096) is not match     versionName=24.15.18 (190400-627556096)\n'}
        'com.google.android.googlequicksearchbox:15.22.32.28 is not match     versionName=15.20.37.28.arm64\n'}
        'reason': 'com.google.android.as.oss:1.0..572577908 is not match     versionName=1.0.release.572577908\n'}
        'reason': 'com.google.android.youtube:19.17.34 is not match     versionName=19.20.33\n'}
        'reason': 'com.google.android.tts:20221111.00_p4.491700629 is not match     versionName=googletts.google-speech-apk_20230206.01_p2.509666633\n
        U GO 14_202406:
        'reason': 'com.google.android.gms:24.15.18 (190400-627556096) is not match     versionName=24.15.18 (200400-627556096)\n'}
        
        V 15_202406:
        'reason': 'com.google.android.gms:24.21.13 (260408-638380824) is not match     versionName=24.26.32 (260408-650348549)\n    versionName=24.21.13 (260400-638380824)\n'}
        'reason': 'com.google.android.inputmethod.latin not install'}],
        '''

        '''
        Android 13 GMS包版本
        '''
        dict_df_gmsversion_13 = {0: "App Name",
                                 1: "Apk Filename",
                                 2: "App Package Name",
                                 3: "13_202208",
                                 4: "13_202209",
                                 5: "13_202211",
                                 6: "13_202301",
                                 7: "13_202304",
                                 8: "13_202310",
                                 9: "13_202401",
                                 10: "13_202406",
                                 11: "13_202411",
                                 12: "13_202503"}
        '''
        Android 14 GMS包版本
        '''
        dict_df_gmsversion_14 = {0: "App Name",
                                 1: "Apk Filename",
                                 2: "App Package Name",
                                 3: "14_202310",
                                 4: "14_202311",
                                 5: "14_202401",
                                 6: "14_202403",
                                 7: "14_202404",
                                 8: "14_202405",
                                 9: "14_202406",
                                 10: "14_202408",
                                 11: "14_202411",
                                 12: "14_202501",
                                 13: "14_202503",
                                 14: "14_202507"}

        '''
        Android 15 GMS包版本
        '''
        dict_df_gmsversion_15 = {0: "App Name",
                                 1: "Apk Filename",
                                 2: "App Package Name",
                                 3: "15_202406",
                                 4: "15_202408",
                                 5: "15_202409",
                                 6: "15_202411",
                                 7: "15_202501",
                                 8: "15_202503",
                                 9: "15_202507",
                                 10: "15_202510",
                                 11: "15_202512",
                                 12: "15_202603"}

        '''
        Android 16 GMS包版本
        '''
        dict_df_gmsversion_16 = {0: "App Name",
                                 1: "Apk Filename",
                                 2: "App Package Name",
                                 3: "16_202504",
                                 4: "16_202505",
                                 5: "16_202506",
                                 6: "16_202507",
                                 7: "16_202508",
                                 8: "16_202509",
                                 9: "16_202510",
                                 10: "16_202512",
                                 11: "16_202603",
                                 12: "16_202605"}

        '''
        Android 17 GMS包版本
        '''
        dict_df_gmsversion_17 = {0: "App Name",
                                 1: "Apk Filename",
                                 2: "App Package Name",
                                 3: "17_202601",
                                 4: "17_202604",
                                 5: "17_202605"}

        dict_df_gmsversion_value = {
            "13":dict_df_gmsversion_13,
            "14":dict_df_gmsversion_14,
            "15":dict_df_gmsversion_15,
            "16":dict_df_gmsversion_16,
            "17":dict_df_gmsversion_17
        }

        '''
        Columns_num 获取当前Android平台 gms所在的列
        '''
        get_dict_df_gmsversion = dict_df_gmsversion_value.get(ro_build_version_release)
        # logging.info(f"Length: {len(get_dict_df_gmsversion)}")

        Columns_num = None
        for i in range(len(get_dict_df_gmsversion)):
            # logging.info(f"{i},{get_dict_df_gmsversion.get(i)}")
            if get_dict_df_gmsversion.get(i) in mGmsversion_value :
                Columns_num = i

        # logging.info(f"Columns_num: {Columns_num}")
        if Columns_num == None:
            reason = "Gms package version not found in GMS_Package_APK_version_release_history.xlsx"
            pytest.fail(reason)

        # logging.info(f"{get_dict_df_gmsversion.get(Columns_num)}")

        current_gms_month = get_dict_df_gmsversion.get(Columns_num).split("_")[-1]
        # logging.info(f"current_gms_month : {current_gms_month}")

        dict_current_gms_data = {}

        for row in range(num_row_value):
            for colume in range(num_columns_value - 1):
                if row >= 2:
                    current_app_packagename = df_filled.iloc[row, 2]
                    current_app_version_value = df_filled.iloc[row, int(Columns_num)]

                    if df_filled.values[row][2] != "0":
                        dict_current_gms_data[current_app_packagename] = current_app_version_value

        # logging.info(f"{dict_current_gms_data}")

        '''
        last_Columns_num 获取上一Android平台 gms所在的列
        '''
        last_build_version =  int(ro_build_version_release) - 1
        # logging.info(f"last_build_version : {last_build_version}")

        get_dict_df_last_gmsversion = dict_df_gmsversion_value.get(str(last_build_version))
        # logging.info(f"get_dict_df_last_gmsversion2 : {get_dict_df_last_gmsversion}")

        last_Columns_num = None
        for i in range(len(get_dict_df_last_gmsversion)-1,0,-1):
            if i > 2:
                # logging.info(f"{i} , {get_dict_df_last_gmsversion.get(i)}")

                last_gms_month = get_dict_df_last_gmsversion.get(i).split("_")[-1]
                # logging.info(f"{i} , {last_gms_month}")

                if int(last_gms_month) < int(current_gms_month):
                    last_Columns_num = i
                    # logging.info(f"last_Columns_num , {last_Columns_num}")
                    break

        if last_Columns_num == None:
            return

        mLastSheet_name = dict_build_version_sheet_name.get(str(last_build_version))
        # logging.info(f"mLastSheet_name : {mLastSheet_name}")

        if mLastSheet_name is None:
            return

        last_df = pd.read_excel(GMS_HISTORY_MODIFY_XLSX, sheet_name=mLastSheet_name,
                           engine='openpyxl')
        #表格中空值以“0”填充
        last_df_filled = last_df.fillna(value="0")

        last_df_shape = last_df_filled.shape  # 获取列数，‌df.shape返回一个元组，‌表示行数和列数
        last_num_row_value = last_df_shape[0]
        last_num_columns_value = last_df_shape[1]

        dict_last_gms_data = {}

        for row in range(last_num_row_value):
            for colume in range(last_num_columns_value - 1):
                if row >= 2:
                    last_app_packagename = last_df_filled.iloc[row, 2]
                    last_app_version_value = last_df_filled.iloc[row, int(last_Columns_num)]

                    if last_df_filled.values[row][2] != "0":
                        dict_last_gms_data[last_app_packagename] = last_app_version_value

        # logging.info(f"{dict_last_gms_data}")

        """"
        同一项目,Android大平台升级后,GMS app version检测
        """
        for app_preload_package_name in mGms_app_preload_package_name_list:
            if dict_current_gms_data.get(app_preload_package_name) != None \
                    and dict_last_gms_data.get(app_preload_package_name) != None:

                """
                issue 1:com.google.android.as
                ValueError: invalid literal for int() with base 10: 'T'
                13_202310 T.29.playstore.oemfull.551304676
                14_202311 551370458

                issue 2: Meet Go,DuoGo
                app_preload_package_name: com.google.android.apps.tachyon
                dict_current_gms_data.get(app_preload_package_name) 198.0.542066333
                dict_last_gms_data.get(app_preload_package_name) 211.0.566141806

                issue 3:
                app_preload_package_name: com.google.android.tts
                dict_current_gms_data.get(app_preload_package_name) 20230206.01_p2.509666633
                dict_last_gms_data.get(app_preload_package_name) 20230904.02_p1.563876699

                issue 4:
                TypeError: argument of type 'int' is not iterable
                U:  'com.google.android.ext.shared': '1'
                T:  'com.google.android.ext.shared': 1,

                issue 5:
                app_preload_package_name: com.google.android.as.oss
                14_202406: dict_current_gms_data.get(app_preload_package_name) 1.0.release.572577908
                13_202406: dict_last_gms_data.get(app_preload_package_name) 1.0.release.588154122

                issue 6:  Message Go
                app_preload_package_name: com.google.android.apps.messaging
                dict_current_gms_data.get(app_preload_package_name) 20231010_01_RC03
                dict_last_gms_data.get(app_preload_package_name) 20231114_01_RC11

                """
                if app_preload_package_name != "com.google.android.as" \
                        and app_preload_package_name != "com.google.android.tts" \
                        and app_preload_package_name != "com.google.android.as.oss" \
                        and (app_preload_package_name != "com.google.android.apps.messaging" and is_android_go_support) \
                        and (app_preload_package_name != "com.google.android.apps.tachyon" and project_name_value == "CK9n-U"):
                    value_compare = compare_app_version(dict_last_gms_data.get(app_preload_package_name), dict_current_gms_data.get(app_preload_package_name))

                    if value_compare == "test_FAIL":
                        logging.info(f"app_preload_package_name: {app_preload_package_name}")
                        logging.info(f"dict_current_gms_data.get(app_preload_package_name), {dict_current_gms_data.get(app_preload_package_name)}")
                        logging.info(f"dict_last_gms_data.get(app_preload_package_name), {dict_last_gms_data.get(app_preload_package_name)}")

                        reason = "Android version update,Gms app version is degraded"
                        pytest.fail(reason)

        """
        判断预置的GMS app version与表格中统计的app version对比是否一致
        """

        gms_app_version_not_match_list = []

        for app_preload_package_name in mGms_app_preload_package_name_list:
            get_app_versionName = get_dumpsys_package(device_serial, app_preload_package_name, "versionName")
            # logging.info(f"App preload: {app_preload_package_name} , {get_app_versionName}")

            if get_app_versionName == "" \
                    or get_app_versionName is None:

                #   SearchSelector.apk
                if app_preload_package_name == "com.google.android.apps.setupwizard.searchselector":
                    logging.info(f"SearchSelector not install!")
                    if special_market_value != "eu" \
                            and special_market_value != "in":
                        continue

                #   Android Go apk
                if is_android_go_support == False:
                    if app_preload_package_name == "com.google.android.apps.assistant" \
                            or app_preload_package_name == "com.google.android.apps.photosgo" \
                            or app_preload_package_name == "com.google.android.apps.searchlite":
                        continue
                else:
                    if app_preload_package_name == "com.google.android.apps.docs" \
                            or app_preload_package_name == "com.google.android.apps.photos" \
                            or app_preload_package_name == "com.google.android.projection.gearhead" \
                            or app_preload_package_name == "com.google.android.as" \
                            or app_preload_package_name == "com.google.android.googlequicksearchbox":
                        continue

                #   GMS Express Plus
                if is_gms_express_plus \
                        or special_market_value == "cocl":
                    if app_preload_package_name == "com.google.android.syncadapters.calendar":
                        continue
                else:
                    if app_preload_package_name == "com.google.android.apps.messaging" \
                            or app_preload_package_name == "com.google.android.calendar":
                        continue


                #   TOCC
                if special_market_value == "tocc":
                    if app_preload_package_name == "com.google.android.syncadapters.calendar" \
                            or app_preload_package_name == "com.google.android.apps.messaging":
                        continue

                #   COCL
                if special_market_value != "cocl":
                    if app_preload_package_name == "com.google.android.dialer" \
                            or app_preload_package_name == "com.google.android.contacts":
                        continue

                mIsCocl_slightly_support = getprop('ro.tran.cocl.slightly.support', device_serial)
                if special_market_value == "cocl" \
                        and "1" == mIsCocl_slightly_support:

                    if app_preload_package_name == "com.google.android.calendar" \
                            or app_preload_package_name == "com.google.android.apps.messaging":
                        continue

                if int(ro_build_version_release) >= 15 and is_android_go_support == True:
                    if app_preload_package_name == "com.google.android.dialer" \
                            or app_preload_package_name == "com.google.android.contacts":
                        continue

                if int(ro_build_version_release) >= 17:
                    if app_preload_package_name == "com.google.android.onetimeinitializer":
                        continue

                reason = app_preload_package_name + " not install"
                pytest.fail(reason)

            df_gms_app_search = df[(df['App Package Name']==app_preload_package_name)]
            df_gms_app_search_list = df_gms_app_search.values[0]

            if is_android_go_support == True \
                    and len(df_gms_app_search) == 2:
                if app_preload_package_name =="com.google.android.apps.messaging":
                    df_gms_app_search_list = df_gms_app_search.values[1]
                    logging.info(f"MessagesGo:df_gms_app_search_list: {df_gms_app_search_list}")

                if app_preload_package_name =="com.google.android.inputmethod.latin":
                    df_gms_app_search_list = df_gms_app_search.values[1]
                    logging.info(f"LatinImeGoogleGo:df_gms_app_search_list: {df_gms_app_search_list}")

            df_gms_app_versionName = str(df_gms_app_search_list[Columns_num] or "")
            # logging.info(f"versionName in df xlsx: {df_gms_app_versionName}")

            if df_gms_app_versionName not in get_app_versionName:
                #   Android Go apk
                if is_android_go_support == True:
                    if app_preload_package_name == "com.google.android.dialer":
                        logging.info(f"GoogleDialerGo.apk is not in the gms package now,skipped the check")
                        continue

                """
                skipped single project gms app update
                """
                if "14_202311" in mGmsversion_value:
                    if project_name_value == "CK9n-U":
                        if (app_preload_package_name == "com.android.chrome" and "126.0.6478.71" in get_app_versionName) \
                                or (app_preload_package_name == "com.google.android.webview" and "126.0.6478.71" in get_app_versionName):
                            logging.info(f"{app_preload_package_name} {get_app_versionName} id skipped the check")
                            continue
                    else:
                        if (app_preload_package_name == "com.google.android.apps.photos" and "6.76.0.616958475" in get_app_versionName) :
                            logging.info(f"{app_preload_package_name} {get_app_versionName} is skipped the check")
                            continue

                """
                IN 市场不能使用14_202401 中的setupwizard 和 searchselector
                """
                if "14_202401" in mGmsversion_value:
                    if special_market_value == "in":
                        if (app_preload_package_name == "com.google.android.setupwizard" and "234.564586043" in get_app_versionName) \
                                or (app_preload_package_name == "com.google.android.apps.setupwizard.searchselector" and "1.33.508543999" in get_app_versionName):
                            logging.info(f"IN : {app_preload_package_name} {get_app_versionName} is skipped the check")
                            continue
                    if project_name_value == "CL6s":
                        if (app_preload_package_name == "com.google.android.apps.messaging" and "20231010_01_RC03" in get_app_versionName):
                            logging.info(f"CL6s ：{app_preload_package_name} {get_app_versionName} is skipped the check")
                            continue

                """
                skipped not same in MTK && Unisoc
                """
                if branch_code_name == "Unisoc":
                    if int(ro_build_version_release) == 14:
                        if app_preload_package_name == "com.google.android.apps.photos":
                            logging.info(f"{app_preload_package_name} {get_app_versionName} is skipped the check")
                            continue
                    if "14_202405" in mGmsversion_value:
                        if (app_preload_package_name == "com.google.android.youtube" and "19.20.33" in get_app_versionName) \
                                or (app_preload_package_name == "com.google.android.apps.messaging" and "20240416_00_RC02" in get_app_versionName):
                            logging.info(f"{app_preload_package_name} {get_app_versionName} is skipped the check")
                            continue

                """
                skipped temp gms app update
                """
                if "14_202406" in mGmsversion_value \
                        or "14_202405" in mGmsversion_value:
                    mCircleToSearch_preload_1 = get_feature(device_serial, 'android.software.contextualsearch')
                    mCircleToSearch_preload_2 = get_feature(device_serial, 'com.google.android.feature.CONTEXTUAL_SEARCH')

                    if mCircleToSearch_preload_1 != "" \
                            and mCircleToSearch_preload_2 != "":
                        if (app_preload_package_name == "com.google.android.googlequicksearchbox" and "15.32.44.28" in get_app_versionName) :
                            logging.info(f"mCircleToSearch: {app_preload_package_name} {get_app_versionName} is skipped the check")
                            continue

                if int(ro_build_version_release) == 15:
                    mCircleToSearch_preload_1 = get_feature(device_serial, 'android.software.contextualsearch')
                    mCircleToSearch_preload_2 = get_feature(device_serial, 'com.google.android.feature.CONTEXTUAL_SEARCH')

                    if mCircleToSearch_preload_1 != "" \
                            and mCircleToSearch_preload_2 != "":
                        if (app_preload_package_name == "com.google.android.googlequicksearchbox") :
                            logging.info(f"mCircleToSearch: {app_preload_package_name} {get_app_versionName} is skipped the check")
                            continue

                if "15_202501" in mGmsversion_value:
                    mIsGeminiFeature_preload = get_feature(device_serial, 'com.google.android.feature.GEMINI_EXPERIENCE')

                    if mIsGeminiFeature_preload != "" :
                        if (app_preload_package_name == "com.google.android.googlequicksearchbox") :
                            logging.info(f"mIsGeminiFeature_preload: {app_preload_package_name} {get_app_versionName} is skipped the check")
                            continue

                if "16_202510" in mGmsversion_value \
                            or "16_202512" in mGmsversion_value:
                    if (app_preload_package_name == "com.google.android.apps.photos"):
                        if "7.64.0.873168826" in get_app_versionName \
                                or "7.65.0.874788995" in get_app_versionName:
                            logging.info(f"{app_preload_package_name} {get_app_versionName} is skipped the check")
                            
                            continue

                    if (app_preload_package_name == "com.google.android.googlequicksearchbox") :
                        if "17.5.42.ve.arm64" in get_app_versionName:
                            logging.info(f"{app_preload_package_name} {get_app_versionName} is skipped the check")
                            continue


                gms_app_version_not_match_list.append(app_preload_package_name + " in .xlsx:" + str(df_gms_app_versionName or "") + " preload:" + str(get_app_versionName or ""))


        logging.info(f"gms_app_version_not_match_list len= {len(gms_app_version_not_match_list)}")

        if len(gms_app_version_not_match_list) != 0:
            logging.info(f"{gms_app_version_not_match_list}")
            reason = "GMS app preload version is not match app version in .xlsx"

            if int(ro_build_version_release) >= 16:
                pytest.fail(reason)
            else:
                #logging.warning(reason)
                pytest.skip(reason)

