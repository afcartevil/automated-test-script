import serial
import serial.tools.list_ports


class XinKe:
    def __init__(self, p):
        self.serial = serial.Serial(port=p.name, baudrate=9600)

    @staticmethod
    def is_xinke(p):
        if p.manufacturer in ['Prolific']:
            return True
        return False

    def connect(self, out_index=0):
        cmds = [
            b'\x55\x01\x32\x00\x00\x00\x01\x89',
            b'\x55\x01\x32\x00\x00\x00\x02\x8C',
            b'\x55\x01\x32\x00\x00\x00\x03\x8C',
            b'\x55\x01\x32\x00\x00\x00\x04\x8C'
        ]
        self.serial.write(cmds[out_index])

    def disconnect(self, out_index=0):
        cmds = [
            b'\x55\x01\x31\x00\x00\x00\x01\x88',
            b'\x55\x01\x31\x00\x00\x00\x02\x8B',
            b'\x55\x01\x31\x00\x00\x00\x03\x8B',
            b'\x55\x01\x31\x00\x00\x00\x04\x8B'
        ]
        self.serial.write(cmds[out_index])
