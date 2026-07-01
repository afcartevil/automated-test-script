import time
from typing import List

import serial.tools.list_ports

CMD_DISCONNECT_ALL = b'\x5a\x24\xff\xaa\x00\x40'
PORT_CMD = [
    b'\x5a\x24\xff\xaa\x01\x40',
    b'\x5a\x24\xff\xaa\x10\x40',
    b'\x5a\x24\xff\xaa\x03\x40',
    b'\x5a\x24\xff\xaa\x04\x40',
    b'\x5a\x24\xff\xaa\x05\x40',
    b'\x5a\x24\xff\xaa\x06\x40',
    b'\x5a\x24\xff\xaa\x07\x40',
    b'\x5a\x24\xff\xaa\x08\x40',
]


# class ctr_data:
#     def __init__(self):
#         # VBUS,IBUS,VD+,VD-,Vcc1,Vcc2
#         self.vbus = ''  # mV
#         self.ibus = ''  # mA
#         self.vd_add = ''
#         self.vd_sub = ''
#         self.vcc1 = ''
#         self.vcc2 = ''
#         self.empty_all()
#
#     def empty_all(self):
#         self.vbus = ''
#         self.ibus = ''
#         self.vd_add = ''
#         self.vd_sub = ''
#         self.vcc1 = ''
#         self.vcc2 = ''


class _Control:
    instance = None

    def __init__(self):
        self.port_list = []
        self._serial_list: List[serial.Serial] = []
        # self._read_thread = threading.Thread(target=self._read_lines)
        # self._read_thread.setDaemon(True)
        # self._last_data = ctr_data()
        # self._new_data_file()

        self._xinke = None  # 新科继电器，用作短接手机开机
        self.power_z_list = []

    def get_serial_list(self):
        return self._serial_list

    def init(self):
        if self._serial_list:
            return len(self._serial_list)

        from powertrde.utils.trde.logs import log
        port_list = list(serial.tools.list_ports.comports())

        port_list = self._select_valid(port_list)
        assert port_list, '没有发现TRDE测试盒!'
        self.port_list = port_list
        for p in port_list:
            # 暂定默认端口描述为 USB-SERIAL CH340 为trde板
            if "CH340" not in p.description:
                log('发现其他端口设备')
                continue
            from powertrde.utils.trde.control_relay_kexin import XinKe
            if XinKe.is_xinke(p):
                log('发现继电器')
                assert not self._xinke, "发现多个新科继电器，只支持同时连接一个新科继电器"
                self._xinke = XinKe(p)
                continue
            from powertrde.utils.trde.ctr_power_z import PowerZ
            if PowerZ.is_power_z(p):
                log('检测到连接了power-z')
                self.power_z_list.append(PowerZ(p))
                continue

            # p = port_list[0]
            s = serial.Serial(port=p.device, baudrate=115200, timeout=2)
            self._serial_list.append(s)
            # self._read_thread.start()
        return len(self._serial_list)

    def _select_valid(self, port_list):
        def _valid(_p):
            if _p.hwid and _p.hwid != 'n/a':
                if _p.description in 'USB Serial':
                    return True
                if _p.description and 'USB' in _p.description.upper() and 'SERIAL' in _p.description.upper():
                    return True
                if _p.description and 'USB' in _p.description.upper() and _p.manufacturer in ['Microsoft']:
                    return True
            return False

        return [p for p in port_list if _valid(p)]

    def connect(self, serial_index, port_index):
        cmd = PORT_CMD[port_index]
        self._serial_list[serial_index].write(cmd)

    def disconnect_all(self, serial_index):
        self._serial_list[serial_index].write(CMD_DISCONNECT_ALL)

    def exit(self, serial_index):
        self._serial_list[serial_index].close()

    # def _read_lines(self):
    #     # b'VBUS=4536 IBUS=470\r\n'
    #     while True:
    #         try:
    #             line_b = self._serial.readline()
    #             line = line_b.decode() if line_b else ""
    #             # print(line)
    #             self._parse_and_save(line)
    #         except BaseException:
    #             time.sleep(1)
    #
    # def _parse_and_save(self, line):
    #     self._last_data.empty_all()
    #     if line and 'VBUS=' in line:
    #         patt = r'.*=(\d*) .*=(\d*)'
    #         srch = re.search(patt, line)
    #         vbus, ibus = srch.groups()
    #         self._last_data.vbus, self._last_data.ibus = vbus, ibus
    #         self._save_file(f'{vbus}    {ibus}\n')
    #
    # def _new_data_file(self):
    #     with open(CONTROL_DATA_FILE, 'w+'):
    #         pass
    #
    # def _save_file(self, line):
    #     with open(CONTROL_DATA_FILE, 'a+') as f:
    #         f.write(f'{str(time.time())}    {line}')
    #
    # def get_last_data(self):
    #     return self._last_data


def _get_control() -> _Control:
    if not _Control.instance:
        _Control.instance = _Control()
    return _Control.instance


def init_ctrs() -> int:  # return controller count
    return _get_control().init()


def exit_ctr(ctr_index):
    _get_control().exit(ctr_index)


def connect(ctr_index, port_index):
    _get_control().disconnect_all(ctr_index)
    time.sleep(1)
    _get_control().connect(ctr_index, port_index)
    time.sleep(3)
    # time.sleep(15)


def disconnect(ctr_index):
    _get_control().disconnect_all(ctr_index)
    time.sleep(1)


def disconnect_fast(ctr_index):
    _get_control().disconnect_all(ctr_index)


def connect_fast(ctr_index, port_index):
    _get_control().connect(ctr_index, port_index)


# def last_data() -> ctr_data:
#     return _get_control().get_last_data()


def long_press_power(press_time=3):
    ctr = _get_control()
    from powertrde.utils.trde.control_relay_kexin import XinKe
    xk: XinKe = ctr._xinke
    if xk:
        xk.connect()
        time.sleep(press_time)
        xk.disconnect()
        time.sleep(1)


def power_z_exist():
    from powertrde.utils.trde.ctr_power_z import PowerZ
    pz_l: List[PowerZ] = _get_control().power_z_list
    return len(pz_l) > 0


def power_z_is_charging(power_z_index):
    from powertrde.utils.trde.ctr_power_z import PowerZ
    pz_l: List[PowerZ] = _get_control().power_z_list
    return pz_l[power_z_index].is_charging()


def power_z_start_record(power_z_index, csv_dir):
    from powertrde.utils.trde.ctr_power_z import PowerZ
    pz_l: List[PowerZ] = _get_control().power_z_list
    csv = pz_l[power_z_index].start(csv_dir)
    return csv


def power_z_stop_record(power_z_index):
    from powertrde.utils.trde.ctr_power_z import PowerZ
    pz_l: List[PowerZ] = _get_control().power_z_list
    pz_l[power_z_index].stop()


def get_serial_list():
    ctr = _get_control()
    return ctr.get_serial_list()


def purge_instance():
    if _Control.instance:
        _Control.instance = None


def _test_tran():
    print('\nEnter "q", then press Enter to exit.')
    n = init_ctrs()

    while True:
        p = input('Please enter the charging port number (0~7):')
        if p not in ['0', '1', '2', '3', '4', '5', '6', '7', 'q', 'Q']:
            print('=> Input error, please try again.')
            continue
        if p == 'q':
            break
        for c in range(n):
            disconnect_fast(c)
            time.sleep(2)
            connect_fast(c, int(p))
            # connect(c, int(p))

    exit_ctr(0)


if __name__ == '__main__':
    # pyinstaller -F -i ..\resource\trde.ico control_tran_soc.py
    try:
        # _test_tran()
        num = _get_control().init()
        print(num)
        _get_control().disconnect_all(0)
        connect(0, 0)
    finally:
        input('Press the Enter key to exit.')
