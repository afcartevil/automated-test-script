import datetime
import os
import queue
import threading
import time

import serial

CSV_DATA_SHIFT = 2


class _AdcData:
    def __init__(self):
        self.header = [4, ]
        self.header_txt = [4, ]
        self.vbus = [4, ]
        self.ibus = [4, ]
        self.vbus_avg = [4, ]
        self.ibus_avg = [4, ]
        self.vbus_ori_avg = [4, ]
        self.ibus_ori_avg = [4, ]
        self.temp = [2, ]
        self.vcc1 = [2, ]
        self.vcc2 = [2, ]
        self.vdp = [2, ]
        self.vdm = [2, ]
        self.vdd = [2, ]
        self.rate = [1, ]
        self.n3 = [3, ]

    @staticmethod
    def data_title() -> list:
        return ['header', 'header_txt', 'vbus', 'ibus',
                'vbus_avg', 'ibus_avg', 'vbus_ori_avg', 'ibus_ori_avg',
                'temp', 'vcc1', 'vcc2', 'vdp',
                'vdm', 'vdd', 'rate', 'n3']

    def data(self):
        return [self.header, self.header_txt, self.vbus, self.ibus,
                self.vbus_avg, self.ibus_avg, self.vbus_ori_avg, self.ibus_ori_avg,
                self.temp, self.vcc1, self.vcc2, self.vdp,
                self.vdm, self.vdd, self.rate, self.n3]


class _SaveData:
    def __init__(self, output_csv):
        self._queue = queue.Queue()
        self.save_ts = 0
        self._output_csv = output_csv
        self._stop_flag = False
        self._save_thread = threading.Thread(target=self._thread_cb)
        self._save_thread.setDaemon(True)
        self._save_thread.start()

    def _thread_cb(self):
        while True:
            if self._stop_flag:
                break
            datas = self._queue.get()
            if datas:
                from . import trde_utils
                # print(f'save {self._output_csv}')
                trde_utils.append_csv(datas, self._output_csv)

    def save(self, datas):
        self._queue.put(datas)
        self.save_ts = int(time.time())

    def finish(self):
        self._stop_flag = True

    def join(self):
        self._save_thread.join()


class _ReadData:
    def __init__(self, s, max_time_sec, sd: _SaveData):
        self._serial = s
        self._max_time_sec = max_time_sec
        d = ['timestamp'] + _AdcData.data_title()[CSV_DATA_SHIFT:]
        self._datas = [list(d)]
        self._start_ts = int(time.time())
        self._sd: _SaveData = sd
        self._stopped = False
        self._read_thread = threading.Thread(target=self._read_thread_cb)
        self._read_thread.setDaemon(True)
        # self._read_thread.start()

    def start(self):
        self._read_thread.start()
        return self

    def finish(self):
        self._stopped = True

    def join(self):
        self._read_thread.join()

    def average_ibus(self):
        ibus_list = []
        for i in range(50):
            adc = self._read_one_data()
            ibus = adc.ibus[1]
            ibus_list.append(ibus)
            time.sleep(0.01)
        return int(sum(ibus_list) / len(ibus_list))

    def _save_data(self):
        self._sd.save(self._datas.copy())
        self._datas = []

    def _read_one_data(self) -> _AdcData:
        s = self._serial
        s.reset_output_buffer()
        s.write(b'\x0C\x00\x02\x00')
        line = s.read(52)
        if not line:
            return None
        adc = _AdcData()
        v = line
        for d in adc.data():
            sz = d[0]
            bts = v[:sz]
            d.append(int.from_bytes(bts, byteorder='little', signed=True))
            d.append(bts)
            v = v[sz:]
        # print(f'time: {time.time()}, vbus: {adc.vbus[1] / 1000000: .2f}v, ibus: {int(adc.ibus[1] * (-1) / 1000)}mA, ')
        return adc

    def _read_thread_cb(self):
        while True:
            ts = time.time()
            if int(ts) - self._sd.save_ts > 60:
                self._save_data()

            if int(ts) - self._start_ts > self._max_time_sec or self._stopped:
                break
            adc = self._read_one_data()

            data = [ts] + [d[1] for d in adc.data()[CSV_DATA_SHIFT:]]
            self._datas.append(data)

            time.sleep(0.01)

        self._save_data()
        self._sd.finish()


class PowerZ:
    def __init__(self, p):
        self._serial = serial.Serial(port=p.device, baudrate=9600, timeout=2.0)
        self._rd = None
        self._sd = None

    @staticmethod
    def is_power_z(p):
        if p.manufacturer in ['Microsoft']:
            return True
        return False

    def is_charging(self):
        rd = _ReadData(self._serial, 10 * 60, None)
        ibus = rd.average_ibus()
        if abs(ibus) < 100:
            return False
        else:
            return True

    def start(self, output_dir, max_time_sec=3 * 60 * 60):
        self.stop()
        dt_s = time.strftime('%m%d_%H%M%S_', time.localtime(time.time())) + str(time.time())[-4:]
        output_csv = os.path.join(output_dir, f'power_z_info_{dt_s}.csv')
        self._sd = _SaveData(output_csv)
        self._rd = _ReadData(self._serial, max_time_sec, self._sd).start()
        return output_csv

    def stop(self):
        if self._rd:
            self._rd.finish()
            self._rd.join()
            self._sd.join()
            self._rd = None
            self._sd = None


def _test():
    import serial.tools.list_ports
    port_list = list(serial.tools.list_ports.comports())
    pz_list = [PowerZ(p) for p in port_list if PowerZ.is_power_z(p)]

    for p in pz_list:
        p.start(r'D:\tmp\powerz')

    time.sleep(3 * 60 * 60)

    for p in pz_list:
        p.stop()


if __name__ == '__main__':
    _test()
