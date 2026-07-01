
from time import sleep
from powertrde.utils.trde import adb
from tests.current_analysis.phoneconfig import PhoneConfig
from tests.current_analysis.test_cases.C01_sleep import C01_Sleep

def C02_ComplexStandby_Init(phone : PhoneConfig):
    phone.pre_phone_check_wifi_connection()
    phone.pre_app_google_play_update()
    phone.loginfo(f"复杂待机环境初始化")
    try:
        phone.standby_monkey()
        for i in range(12):
            phone.loginfo(f"执行monkey剩余 {(12 - i) * 10} 分钟")
            if phone.debug:
                sleep(6)
            else:
                sleep(600)
        phone.u2d_helper.kill_monkey_process()
        phone.u2d_helper.press_home_key()
        sleep(0.2)
        phone.u2d_helper.press_home_key()
        sleep(2)
        phone.stop_pip_apps()
        phone.stop_music_or_video_playing_apps()
    except:
        raise Exception("复杂待机环境初始化失败")
    finally:
        adb.poweron_screen_and_unlock(phone.serial)
        phone.pre_phone_copilot_switch_language_en()
        phone.loginfo(f"pre_phone_copilot_restore_control_center_status")
        phone.pre_phone_copilot_restore_control_center_status()
        phone.loginfo(f"pre_phone_switch_keyboard_default")
        phone.pre_phone_switch_keyboard_default()
        phone.loginfo(f"pre_phone_switch_navi_mode_3_buttons")
        phone.pre_phone_switch_navi_mode_3_buttons()
        phone.loginfo(f"pre_phone_close_non_disturb_mode")
        phone.pre_phone_close_non_disturb_mode()
        phone.loginfo(f"pre_phone_close_clock")
        phone.pre_phone_close_clock()
        phone.loginfo(f"pre_phone_copilot_switch_dialer_default")
        phone.pre_phone_copilot_switch_dialer_default()
        phone.loginfo(f"pre_phone_close_sidebar")
        phone.pre_phone_close_sidebar()
        phone.loginfo(f"pre_phone_copilot_close_google_protect")
        phone.pre_phone_copilot_close_google_protect()
        phone.loginfo(f"pre_phone_check_wifi_connection")
        phone.pre_phone_check_wifi_connection()
        phone.loginfo(f"pre_phone_close_auto_update")
        phone.pre_phone_close_auto_update()


def C02_ComplexStandby(phone : PhoneConfig):
    pkg = phone.global_config.table_apps["Roblox"]['package']
    phone.u2d_helper.start_app(pkg)
    sleep(10)
    if phone.debug:
        result = C01_Sleep(phone, 120, 60)
    else:
        result = C01_Sleep(phone, 8 * 3600, 3600)
    
    return result

