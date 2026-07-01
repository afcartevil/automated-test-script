import serial
import serial.tools.list_ports
import time
import threading
import signal
import sys
import logging
import colorlog
from typing import Callable, Optional, Dict

# Command definitions
CMD_GET_CHANNEL_POWER_STATUS = 0x00
CMD_SET_CHANNEL_POWER = 0x01

CMD_GET_CHANNEL_VOLTAGE = 0x03
CMD_GET_CHANNEL_CURRENT = 0x04

CMD_SET_CHANNEL_DATALINE = 0x05
CMD_GET_CHANNEL_DATALINE_STATUS = 0x08

CMD_SET_BUTTON_CONTROL = 0x09
CMD_GET_BUTTON_CONTROL_STATUS = 0x0A

CMD_SET_DEFAULT_POWER_STATUS = 0x0B
CMD_GET_DEFAULT_POWER_STATUS = 0x0C

CMD_SET_DEFAULT_DATALINE_STATUS = 0x0D
CMD_GET_DEFAULT_DATALINE_STATUS = 0x0E


# Channel value definitions
CHANNEL_1 = 0x01
CHANNEL_2 = 0x02
CHANNEL_3 = 0x04
CHANNEL_4 = 0x08

OPERATE_MODE_NORMAL = 0
OPERATE_MODE_INTERLOCK = 1

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

ch = colorlog.StreamHandler()

console_formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
    datefmt=None,
    reset=True,
    log_colors={
        "DEBUG": "white",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red,bg_white",
    },
)
ch.setFormatter(console_formatter)
logger.addHandler(ch)


class SmartUSBHub:
    hub = None

    def __init__(self, port):
        self.port = port
        self.ser = serial.Serial(port, 115200, timeout=0.5)
        self.com_timeout = 0.1
        logger.info(f"SmartUSBHub initialized on port {self.port}")

        self.ack_events = {
            CMD_SET_CHANNEL_POWER: threading.Event(),
            CMD_GET_CHANNEL_POWER_STATUS: threading.Event(),
        }
        self.callbacks: Dict[int, Optional[Callable[..., None]]] = {cmd: None for cmd in self.ack_events.keys()}
        self.channel_power_status = {}
        self._start()

    @classmethod
    def scan_available_ports(cls):
        ports = serial.tools.list_ports.comports()
        port_list = []

        for port in ports:
            if port.vid == 0x1A86 and port.pid == 0xfe0c:
                port_list.append(port.device)

        return port_list

    @classmethod
    def scan_and_connect(cls):
        for port_info in serial.tools.list_ports.comports():
            port_name = port_info.device
            logger.debug(f"Trying to connect to port {port_name}")
            if port_info.vid == 0x1A86 and port_info.pid == 0xfe0c:
                cls.hub = cls(port_name)
                port_suffix = port_name.split("/")[-1]
                cls.hub.name = f"smarthub_id:{port_suffix}"
                return cls.hub
        raise Exception("No SmartUSBHub found")

    def _start(self):
        self.stop_event = threading.Event()
        signal.signal(signal.SIGINT, self._signal_handler)
        self.uart_recv_thread = threading.Thread(target=self._uart_recv_task)
        self.uart_recv_thread.start()

    def _signal_handler(self, sig, frame):
        self.stop_event.set()
        self.uart_recv_thread.join(timeout=1)
        if self.ser and self.ser.is_open:
            self.ser.flush()
            self.ser.close()
        sys.exit(0)

    def _parse_protocol_frame(self, data):
        if len(data) < 6:
            return None

        if data[0] != 0x55 or data[1] != 0x5A:
            return None

        cmd = data[2]
        channel = data[3]

        if cmd in [CMD_GET_CHANNEL_VOLTAGE,
                   CMD_GET_CHANNEL_CURRENT,
                   CMD_SET_DEFAULT_POWER_STATUS,
                   CMD_SET_DEFAULT_DATALINE_STATUS,
                   CMD_GET_DEFAULT_POWER_STATUS,
                   CMD_GET_DEFAULT_DATALINE_STATUS]:

            logger.debug(f"Received protocol_v2 data for channel {self._convert_channel(channel)}")
            if len(data) < 7:
                return None
            value_0 = data[4]
            value_1 = data[5]
            checksum = data[6]
            cal_sum = (cmd + channel + value_0 + value_1) & 0xFF
            if cal_sum != checksum:
                logger.debug(
                    f"Invalid checksum for protocol_v2 data for channel {channel},cal:{cal_sum},recv:{checksum}")
                return None
            # Combine two bytes into a single value
            return (cmd, channel, [value_0, value_1], 7)
        else:
            value = data[4]
            checksum = data[5]
            if ((cmd + channel + value) & 0xFF) != checksum:
                return None
            return (cmd, channel, value, 6)

    def _uart_recv_task(self):
        buffer = bytearray()
        while not self.stop_event.is_set():
            if self.ser.in_waiting > 0:
                buffer.extend(self.ser.read(self.ser.in_waiting))
                logger.debug(f"rx data: {buffer.hex()}")
                while len(buffer) >= 6:
                    result = self._parse_protocol_frame(buffer)
                    if result is not None:
                        cmd, channel, value, length = result

                        logger.debug(f"Parsed CMD: {cmd:#04x}, Channel: {channel:#04x}, Value: {value}")

                        if cmd == CMD_SET_CHANNEL_POWER:
                            self._handle_set_channel_power_status()
                        elif cmd == CMD_GET_CHANNEL_POWER_STATUS:
                            self._handle_get_channel_power_status(channel, value)
                        if cmd in self.ack_events:
                            self._invoke_callback(cmd,channel,value)
                            self.ack_events[cmd].set()

                        del buffer[:length]
                    else:
                        buffer.pop(0)
            time.sleep(0.01)

    def _invoke_callback(self, cmd, *args, **kwargs):
        if cmd in self.callbacks and self.callbacks[cmd]:
            try:
                self.callbacks[cmd](*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in callback for command {cmd:#04x}: {e}")

    def _handle_set_channel_power_status(self):
        logger.debug("_handle_set_channel_power_status ACK")
        self.ack_events[CMD_SET_CHANNEL_POWER].set()

    def _handle_get_channel_power_status(self, channel, value):
        logger.debug("_handle_get_channel_power_status ACK")
        channels = self._convert_channel(channel)
        for ch in channels:
            self.channel_power_status[ch] = value
            logger.info(f"CMD_GET_CHANNEL_POWER_STATUS acked: ch{ch} = {value}")

    def _convert_channel(self, channel_mask):
        channels = []
        if channel_mask & CHANNEL_1:
            channels.append(1)
        if channel_mask & CHANNEL_2:
            channels.append(2)
        if channel_mask & CHANNEL_3:
            channels.append(3)
        if channel_mask & CHANNEL_4:
            channels.append(4)
        return channels

    def _send_packet(self, cmd, channels, data=None):
        if channels is None:
            channel_mask = 0
        else:
            channel_mask = sum([1 << (ch - 1) for ch in channels])

        if data is None:
            data = [0x00]
        elif not isinstance(data, list):
            data = [data]

        payload = [channel_mask] + data
        packet = bytearray([0x55, 0x5A, cmd])
        packet.extend(payload)

        checksum = (cmd + sum(payload)) & 0xFF
        packet.append(checksum)

        if self.ser and self.ser.is_open:
            self.ser.write(packet)

        logger.debug(f"Sent command: {packet.hex()}")

        return packet

    def set_channel_power(self, *channels, state):
        self._send_packet(CMD_SET_CHANNEL_POWER, list(channels), [state])
        ack_event = self.ack_events[CMD_SET_CHANNEL_POWER]
        ack_event.clear()
        if ack_event.wait(self.com_timeout):
            logger.debug("set_channel_power ACK")
            return True
        else:
            logger.error("set_channel_power No ACK!")
            return False

    def set_channel_state(self, channel, state):
        if self.hub is None:
            raise Exception("No SmartUSBHub found")
        try:
            current_state = -1
            for attempt in range(1, 4):
                self.hub.set_channel_power(channel, state=state)  # 尝试设置通道电源状态
                time.sleep(5)
                current_state = self.hub.get_channel_power_status(channel)
                if current_state == state:
                    print(f"Attempt {attempt}: Successfully set channel {channel} to state {state}")
                    return
                else:
                    print(f"Attempt {attempt}: Failed to set channel {channel} to state {state}. Current state: {current_state}")
            raise Exception(f"Failed to set channel {channel} to state {state}. Current state: {current_state}")
        finally:
            self.stop_event.set()
            self.uart_recv_thread.join(timeout=1)
            if self.ser and self.ser.is_open:
                self.ser.flush()
                self.ser.close()

    def get_channel_power_status(self, *channels):
        self._send_packet(CMD_GET_CHANNEL_POWER_STATUS, list(channels))
        ack_event = self.ack_events[CMD_GET_CHANNEL_POWER_STATUS]
        ack_event.clear()
        if ack_event.wait(self.com_timeout):
            logger.debug("get_channel_power_status ACK")

            if len(channels) == 1:
                return self.channel_power_status.get(channels[0], None)
            logger.debug(f"get_channel_power_status: {self.channel_power_status}")
            return self.channel_power_status
        else:
            logger.error("get_channel_power_status No ACK!")
            return None