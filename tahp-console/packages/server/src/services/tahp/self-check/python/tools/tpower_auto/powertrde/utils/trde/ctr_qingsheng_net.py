import socket
import time
from collections import namedtuple

WARM_BOX_IP = '192.168.1.10'
WARM_BOX_PORT = 4001

wb_status = namedtuple('wb_status', {'status', 'temp_pv', 'temp_sv', 'pgm_name', 'cycle', 'step', 'error'})

_debug_flag = False


def set_debug_flag(flg):
    global _debug_flag
    _debug_flag = flg


def _status_parse(data):
    from .logs import log
    # data = 'STX, 1, 0,A,6,0, 23.71,  0.0,  0.00,  0.0,one-poin.pgm,0,0,0,0,0,END'
    l = data.split(',')
    l = [i.strip() for i in l]
    if len(l) < 17 or ','.join(l[:4]) != 'STX,1,0,A':
        log(f'error !!!!!! 温箱状态：异常，{data}')
        return

    sta = wb_status(status=l[5], temp_pv=l[6], temp_sv=l[8], pgm_name=l[10], cycle=l[11], step=l[12], error=l[15])

    st = {'0': '停机', '1': '运行', '2': '预约'}
    status = st[sta.status]
    temp_pv = f'实际温度{sta.temp_pv}'
    humi_pv = f'实际湿度{l[7]}'
    temp_sv = f'目标温度{sta.temp_sv}'
    humi_sv = f'目标湿度{l[9]}'
    pgm_name = sta.pgm_name
    cycle = f'当前第{sta.cycle}次循环'
    step = f'当前第{sta.step}步'
    hour = f'剩余{l[13]}小时'
    min = f'剩余{l[14]}分钟'
    error = '运行正常' if sta.error == '0' else f'运行错误：{sta.error}'
    log('温箱状态：'+','.join([status, temp_pv, humi_pv, temp_sv, humi_sv, pgm_name, cycle, step, hour, min, error]))
    return sta


def _run_cmd(cmd: str) -> str:
    from .logs import log
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((WARM_BOX_IP, WARM_BOX_PORT))
    s.sendall(cmd.encode())
    datab = s.recv(1024)
    s.close()
    data = datab.strip().strip(b'\x00').decode()
    log(f'warm box command: {cmd}, return: {data}')
    return data


def ctr_start(to_temp, hour, minute):
    from .logs import log
    log(f'ctr_start(), to_temp:{to_temp}, hour:{hour}, minute:{minute}')
    if _debug_flag:
        return True
    cmd = f'STX,0,1,G,{to_temp},0,0,0,{hour},{minute},0,0,0,1,END'
    data = _run_cmd(cmd)  # return "STX, 1, 0,G,END"
    if data.replace(' ', '') == 'STX,1,0,G,END':
        return True
    else:
        from .logs import log
        log(f'error !!!!!! ctr_start(), start warm box failed!!!!!, {data}')
        return False


def ctr_stop():
    from .logs import log
    log('ctr_stop()')
    if _debug_flag:
        return True
    cmd = 'STX,0,1,E,END'
    data = _run_cmd(cmd)  # return "STX, 1, 0,E,END"
    if data.replace(' ', '') == 'STX,1,0,E,END':
        return True
    else:
        from .logs import log
        log(f'error !!!!!! ctr_stop(), stop warm box failed!!!!!!, {data}')
        return False


def ctr_status() -> wb_status:
    from .logs import log
    if _debug_flag:
        log('ctr_status()')
        return wb_status('', '', '', '', '', '', '')
    # STX, 1, 0,A,6,0, 23.71,  0.0,  0.00,  0.0,one-poin.pgm,0,0,0,0,0,END
    data = _run_cmd('STX,0,1,A,END')
    return _status_parse(data)


def _test():
    ctr_status()
    ctr_start(42, 0, 5)
    ctr_status()
    time.sleep(7 * 60)
    ctr_status()
    time.sleep(10)
    ctr_stop()
    ctr_status()
    time.sleep(6)
    ctr_status()


if __name__ == '__main__':
    _test()
