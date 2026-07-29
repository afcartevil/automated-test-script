from powertrde import env


class U2DHelperConstants:
    SEARCH_Y_POSITION = {'default': 0.09, '15': 0.09, '16': 0.066}
    SIM_Y_POSTION = {'1':0.16,  "2":0.25}
    SIM_X_POSTION = {'1':0.50}

    PHONE_KEYBOARD_POS_MAP = {'q': (0.054, 0.73), 'w': (0.153, 0.73), 'e': (0.252, 0.73), 'r': (0.351, 0.73),
                              't': (0.45, 0.73),
                              'y': (0.549, 0.73), 'u': (0.648, 0.73), 'i': (0.747, 0.73), 'o': (0.846, 0.73),
                              'p': (0.945, 0.73),
                              'a': (0.100, 0.794), 's': (0.202, 0.794), 'd': (0.301, 0.794),
                              'f': (0.4, 0.794),
                              'g': (0.499, 0.794),
                              'h': (0.598, 0.794), 'j': (0.697, 0.794), 'k': (0.796, 0.794),
                              'l': (0.92, 0.794),
                              'z': (0.202, 0.859), 'x': (0.301, 0.859), 'c': (0.4, 0.859), 'v': (0.499, 0.859),
                              'b': (0.598, 0.859), 'n': (0.697, 0.859), 'm': (0.796, 0.859),
                              '1': (0.054, 0.73), '2': (0.153, 0.73), '3': (0.252, 0.73), '4': (0.351, 0.73),
                              '5': (0.45, 0.73),
                              '6': (0.549, 0.73), '7': (0.648, 0.73), '8': (0.747, 0.73), '9': (0.846, 0.73),
                              '0': (0.945, 0.73),
                              '?': (0.09, 0.92), '_': (0.55, 0.92), '&': (0.89, 0.917),
                              '.': (0.796, 0.924), ' ': (0.55, 0.92), '!': (0.930, 0.859), '/': (0.21, 0.9)}
    # ？数字键盘切换   _和  表示空格  & 表示搜索  . 点  !删除
    PHONE_CALLBOARD_POS_MAP = {'1': (0.18, 0.514), '2': (0.499, 0.514), '3': (0.818, 0.514),
                               '4': (0.18, 0.586), '5': (0.499, 0.586), '6': (0.818, 0.586),
                               '7': (0.179, 0.658), '8': (0.499, 0.658), '9': (0.818, 0.658),
                               '*': (0.18, 0.733), '0': (0.499, 0.74), '#': (0.819, 0.731),
                               'card1': (0.37, 0.826), 'card': (0.50, 0.845), 'card2': (0.592, 0.826)
                               }

    PHONE_KEYBOARD_POS_MAP_CURVED_SCREEN = {'q': (0.092, 0.754), 'w': (0.182, 0.754), 'e': (0.273, 0.754),
                                            'r': (0.364, 0.754),
                                            't': (0.455, 0.754),
                                            'y': (0.545, 0.754), 'u': (0.636, 0.754), 'i': (0.727, 0.754),
                                            'o': (0.818, 0.754),
                                            'p': (0.908, 0.754),
                                            'a': (0.114, 0.811), 's': (0.228, 0.811), 'd': (0.319, 0.811),
                                            'f': (0.409, 0.811),
                                            'g': (0.5, 0.811),
                                            'h': (0.591, 0.811), 'j': (0.681, 0.811), 'k': (0.772, 0.811),
                                            'l': (0.885, 0.811),
                                            'z': (0.228, 0.868), 'x': (0.319, 0.868), 'c': (0.409, 0.868),
                                            'v': (0.5, 0.868),
                                            'b': (0.591, 0.868),
                                            'n': (0.681, 0.868), 'm': (0.772, 0.868),
                                            '1': (0.092, 0.754), '2': (0.182, 0.754), '3': (0.273, 0.754),
                                            '4': (0.364, 0.754),
                                            '5': (0.455, 0.754),
                                            '6': (0.545, 0.754), '7': (0.636, 0.754), '8': (0.727, 0.754),
                                            '9': (0.818, 0.754),
                                            '0': (0.908, 0.754),
                                            '?': (0.114, 0.926), '_': (0.545, 0.92), '&': (0.885, 0.92),
                                            '.': (0.772, 0.926), '!': (0.910, 0.868),
                                            ' ': (0.545, 0.92), '/': (0.21, 0.9)
                                            }

    PHONE_CALLBOARD_POS_MAP_CURVED_SCREEN = {'1': (0.18, 0.521), '2': (0.499, 0.521), '3': (0.818, 0.521),
                                             '4': (0.18, 0.592), '5': (0.499, 0.592), '6': (0.818, 0.592),
                                             '7': (0.18, 0.663), '8': (0.499, 0.663), '9': (0.818, 0.663),
                                             '*': (0.18, 0.733), '0': (0.499, 0.74), '#': (0.819, 0.731),
                                             'card1': (0.37, 0.826), 'card': (0.50, 0.845), 'card2': (0.592, 0.826),
                                             }

    PHONE_MONITOR_APP_PACKAGE = 'com.transsion.emmctest'
    PHONE_MONITOR_APP_MAIN_ACTIVITY = 'com.transsion.emmctest/.MainActivity'


    #contacts
    RAW_CONTACTS_SHELL = "content insert --uri content://com.android.contacts/raw_contacts --bind account_type:s:com.android.localphone --bind account_name:s:Phone"
    QUERY_CONTACTS_SHELL = "content query --uri content://com.android.contacts/raw_contacts --projection _id"
    QUERY_CONTACTS_BY_NAME_SHELL  = "content query --uri content://com.android.contacts/raw_contacts --where \"display_name='{name}'\" --projection _id"
    INSERT_NAME_SHELL = "content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:{raw_contact_id} --bind mimetype:s:vnd.android.cursor.item/name --bind data1:s:{contact_name}"
    INSERT_PHONE_SHELL = "content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:{raw_contact_id} --bind mimetype:s:vnd.android.cursor.item/phone_v2 --bind data1:s:{phone_number} --bind data2:i:2"
    DELETE_ALL_CONTACTS_SHELL = "content delete --uri content://com.android.contacts/raw_contacts"
    DELETE_CONTACTS_BY_ID_SHELL = "content delete --uri content://com.android.contacts/raw_contacts --where \"_id={contact_id}\""
    #call
    DELETE_ALL_CALL_SHELL = "content delete --uri content://call_log/calls"
    INSERT_ALL_CALL_SHELL =  "content insert --uri content://call_log/calls --bind number:s:{phone_number} --bind type:i:{call_type} --bind date:l:{timestamp} --bind duration:i:{duration} --bind new:i:0 --bind name:s:calllog_{index}"
    #messgae
    INSERT_MESSAGE_SHELL = "content insert --uri content://sms/inbox --bind address:s:{number} --bind body:s:'{content}'"
    DELETE_MESSAGE_SHELL = "content delete --uri content://sms"
    @classmethod
    def get_phone_keyboard_pos_map(cls):
        if env.get_user_env_arg('is_curved_screen'):
            return cls.PHONE_KEYBOARD_POS_MAP_CURVED_SCREEN
        else:
            return cls.PHONE_KEYBOARD_POS_MAP

    @classmethod
    def get_phone_callboard_pos_map(cls):
        if env.get_user_env_arg('is_curved_screen'):
            return cls.PHONE_CALLBOARD_POS_MAP_CURVED_SCREEN
        else:
            return cls.PHONE_CALLBOARD_POS_MAP

    @classmethod
    def get_search_postion(cls, os_version='default'):
        y = cls.SEARCH_Y_POSITION.get(str(os_version), None)
        return y

    @classmethod
    def get_sim_postion_y(cls, index):
        y = cls.SIM_Y_POSTION.get(str(index), None)
        return y if y else None

    @classmethod
    def get_sim_postion_x(cls, index):
        x = cls.SIM_X_POSTION.get(str(index), None)
        return x if x else None
