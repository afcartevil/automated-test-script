import asyncio
import ctypes
import json
import logging
import os
import socket
import struct
import sys
import tempfile
import threading
import time
from queue import Queue
from typing import Dict, Optional

import win32api
import win32event
import winerror

TEMP_DIR = os.path.join(tempfile.gettempdir(), "tpytest_service")
TEMP_DATA_SERVER_VERSION_FILE = os.path.join(TEMP_DIR, "server_version.txt")

SERVER_ADDRESS = ('0.0.0.0', 51515)
MUTEX_EVENT_NAME = "Global\\TPyTestCaseServer"

SERVER_VERSION = '1.1'


class DeviceTestResponse:
    def __init__(self, json_response_text: str, device_addr: Optional[str]):
        self.json_dict: dict = json.loads(json_response_text)
        if not device_addr:
            self.device_addr = self.json_dict['device_addr']
        else:
            self.device_addr = device_addr
            self.json_dict['device_addr'] = device_addr
        self.requester_addr: str = self.json_dict['requester_addr']
        self.request_id: str = self.json_dict['request_id']
        self.result: str = self.json_dict['result']
        self.data = self.json_dict['data']
        self.message = self.json_dict['message']

    def to_json_text(self) -> str:
        return json.dumps(self.json_dict)


class ClientConnection:
    def __init__(self, addr: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.addr = addr
        self.reader = reader
        self.writer = writer
        self.task_queue = Queue()


connected_clients: Dict[str, ClientConnection] = dict()
control_request_lock = asyncio.Lock()
device_response_lock = asyncio.Lock()

service_control_id_count: int = 0
in_processing: bool = False

_last_auto_start_watching_cancel_token: Optional[asyncio.Event] = None


async def add_device_response_to_queue(response: DeviceTestResponse):
    async with device_response_lock:
        if response.requester_addr in connected_clients:
            connected_clients[response.requester_addr].task_queue.put(response)
        else:
            logging.error(f'没有在连接列表里找到{response.requester_addr}，无法进行转发！')


def is_server_running() -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(SERVER_ADDRESS)
    sock.close()
    return result == 0


def read_runtime_server_version() -> str:
    if not os.path.exists(TEMP_DATA_SERVER_VERSION_FILE):
        return ""
    try:
        with open(TEMP_DATA_SERVER_VERSION_FILE, 'r') as file:
            content = file.read()
        return content
    except:
        return ""


def write_runtime_server_version():
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR, exist_ok=True)
    with open(TEMP_DATA_SERVER_VERSION_FILE, 'w') as file:
        file.write(SERVER_VERSION)


def is_server_event_exists(check_version: bool) -> bool:
    try:
        server_event = win32event.OpenEvent(win32event.SYNCHRONIZE, False, MUTEX_EVENT_NAME)
    except:
        return False
    if server_event:
        win32api.CloseHandle(server_event)
        if check_version:
            time.sleep(0.1)
            server_version = read_runtime_server_version()
            if server_version != SERVER_VERSION:
                logging.warning(f"服务器已在运行，但其版本是 {server_version} 而并非 {SERVER_VERSION}")
                stop_server()
                time.sleep(0.2)
                return False
        return True
    return False


def start_server() -> bool:
    server_event = None
    try:
        server_event = win32event.OpenEvent(win32event.SYNCHRONIZE, False, MUTEX_EVENT_NAME)
    except:
        pass
    if server_event:
        # 存在服务器，直接结束
        win32api.CloseHandle(server_event)
        logging.debug("服务器正在运行中，不再重复运行！")
        return True

    server_event = win32event.CreateEvent(None, True, False, MUTEX_EVENT_NAME)
    last_error = win32api.GetLastError()
    if last_error == winerror.ERROR_ALREADY_EXISTS:
        if server_event:
            # 存在服务器，直接结束
            win32api.CloseHandle(server_event)
            logging.debug("服务器正在运行中，不再重复运行！")
        return True

    # 设置控制台标题
    ctypes.windll.kernel32.SetConsoleTitleW(f'Tpytest Case Server v{SERVER_VERSION}')

    # 将服务器版本写入临时文件
    write_runtime_server_version()

    event_loop = asyncio.get_event_loop()

    # 在单独的线程中运行事件监听器
    def stop_server_listener():
        while True:
            listen_result = win32event.WaitForSingleObject(server_event, 100)
            if event_loop is None:
                break
            if listen_result == win32event.WAIT_OBJECT_0:
                logging.debug("收到了停止服务器的请求！")
                try:
                    asyncio.run_coroutine_threadsafe(async_stop_server(), event_loop)
                except:
                    pass
                break

    listener_thread = threading.Thread(target=stop_server_listener)
    listener_thread.start()

    # 启动协程式服务
    try:
        event_loop.run_until_complete(_async_start_server())
    except KeyboardInterrupt:
        event_loop.run_until_complete(shutdown_async_tasks(event_loop))
        event_loop = None
        return True
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.exception(e)
        # set_error(‘ERR_CODE_CANNOT_START_SERVER’, str(e))
        return False
    finally:
        if event_loop:
            event_loop.close()
            event_loop = None
        if server_event:
            win32api.CloseHandle(server_event)
        listener_thread.join()
    return True


def stop_server() -> bool:
    try:
        server_event = win32event.OpenEvent(win32event.EVENT_MODIFY_STATE, False, MUTEX_EVENT_NAME)
        win32event.SetEvent(server_event)
        win32api.CloseHandle(server_event)
        logging.debug("发送了停止服务器的请求！")
    except:
        logging.debug("没有服务器需要被停止！")
    return True


async def shutdown_async_tasks(loop, signal=None):
    if signal:
        logging.debug(f"收到了取消信号： {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    logging.debug(f"取消了 {len(tasks)} 个未完成的后台任务！")
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    logging.debug("所有后台任务都取消了！")
    loop.stop()


async def async_stop_server():
    try:
        loop = asyncio.get_running_loop()
        for task in asyncio.all_tasks():
            task.cancel()
        await asyncio.sleep(0.1)
        loop.stop()
    except:
        pass


async def async_listen_and_forward_device_response():
    while True:
        await asyncio.sleep(0.1)
        async with device_response_lock:
            for client_addr, client in connected_clients.items():
                response: Optional[DeviceTestResponse] = None
                try:
                    response = client.task_queue.get_nowait()
                except:
                    pass
                if response:
                    try:
                        message_body = response.to_json_text().encode('utf-8')
                        message_head = struct.pack('!I', len(message_body))
                        client.writer.write(message_head)
                        client.writer.write(message_body)
                        await client.writer.drain()
                        logging.debug(f"转发给{client_addr}")
                    except:
                        logging.error(f"客户端{client_addr}已断开连接，无法转发给它消息.")
                        try:
                            client.writer.close()
                        except:
                            pass


async def async_handle_client(reader, writer):
    # 获取客户端地址
    client_addr_tuple = writer.get_extra_info('peername')
    client_addr = f'{client_addr_tuple[0]}:{client_addr_tuple[1]}'

    async with device_response_lock:
        if client_addr not in connected_clients:
            # 客户端首次连接
            connected_clients[client_addr] = ClientConnection(client_addr, reader, writer)
            logging.debug(f"新客户端 {client_addr} 连接")
        else:
            # 客户端已连接过
            logging.debug(f"已知客户端 {client_addr} 重新连接")

    try:
        while True:
            if reader.at_eof():
                logging.debug(f"客户端 {client_addr} 已经断开连接")
                break

            length_data = await reader.readexactly(4)  # 长度字段占4字节
            if not length_data:
                logging.debug(f"客户端 {client_addr} 已经断开连接")
                break
            length = struct.unpack('!I', length_data)[0]
            data: bytes = await reader.readexactly(length)
            if len(data) != length:
                logging.debug(f"客户端 {client_addr} 已经断开连接")
                break
            response = DeviceTestResponse(data.decode('utf-8'), client_addr)
            logging.debug(f"收到来自设备 {client_addr} 的消息ID：{response.request_id}")
            requester_port = response.requester_addr.split(':')[1]
            response.requester_addr = f'127.0.0.1:{requester_port}'
            await add_device_response_to_queue(response)
    except Exception as e:
        if not str(e).startswith('0 bytes read on a total'):
            logging.error(f"客户端 {client_addr} 连接异常：{e}")
    finally:
        # 客户端断开连接时，移除地址
        async with device_response_lock:
            if client_addr in connected_clients:
                del connected_clients[client_addr]
        try:
            writer.close()
        except:
            pass


async def _async_start_server():
    # 创建服务器，配置客户端连接的协程处理函数为 async_handle_client
    server = await asyncio.start_server(
        async_handle_client, *SERVER_ADDRESS)
    addr = server.sockets[0].getsockname()
    logging.debug(f"tpytest用例服务器启动成功，地址：{addr}")
    # 协程轮巡后台队列任务
    _ = asyncio.create_task(async_listen_and_forward_device_response())
    async with server:
        # 启动服务器的主循环
        await server.serve_forever()


if __name__ == '__main__':
    if len(sys.argv) > 1 and (sys.argv[1] == '-v' or sys.argv[1] == '--version'):
        print(f'Tpytest Case Server V{SERVER_VERSION}')
    else:
        logging.basicConfig(
            level=logging.DEBUG,  # 设置日志级别为DEBUG
            format='%(asctime)s - %(message)s',  # 指定日志格式
            datefmt='%m-%d %H:%M:%S'  # 指定日期时间格式
        )
        start_server()
