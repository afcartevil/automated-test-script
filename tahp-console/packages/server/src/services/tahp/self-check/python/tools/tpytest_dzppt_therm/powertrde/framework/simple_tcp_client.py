import asyncio
import json
from asyncio import StreamReader, StreamWriter
from typing import Optional, Callable

from powertrde.framework.defines import HostPort
from powertrde.framework.simple_response_message import SimpleResponseMessage
from powertrde.framework.tran_logger import t_log


class SimpleTcpClient:
    def __init__(self, address: HostPort, on_received_callback: Optional[Callable[[SimpleResponseMessage], None]]):
        self._address: HostPort = address
        self._tcp_reader: Optional[StreamReader] = None
        self._tcp_writer: Optional[StreamWriter] = None
        self._write_lock: asyncio.Lock = asyncio.Lock()
        self._is_connected: bool = False
        self.on_received_callback: Optional[Callable[[SimpleResponseMessage], None]] = on_received_callback
        self.on_disconnected_callback: Optional[Callable[[], None]] = None

    @property
    def is_connected(self):
        return self._is_connected

    async def send(self, content_bytes: bytes, throw_if_error: bool = True):
        async with self._write_lock:
            try:
                if not self._is_connected:
                    if throw_if_error:
                        raise RuntimeError("Connection is not open.")
                    else:
                        return
                self._tcp_writer.write(len(content_bytes).to_bytes(4, byteorder="big"))
                self._tcp_writer.write(content_bytes)
                await self._tcp_writer.drain()
            except:
                self.disconnect()
                if throw_if_error:
                    raise

    async def send_text(self, content_text: str):
        await self.send(content_text.encode("utf-8"))

    async def send_json(self, content_json: dict):
        await self.send_text(json.dumps(content_json))

    async def _background_read(self):
        try:
            while True:
                head_bytes = await self._tcp_reader.readexactly(4)
                data_len = int.from_bytes(head_bytes, byteorder="big")
                if data_len > 0:
                    body_bytes = await self._tcp_reader.readexactly(data_len)
                    if self.on_received_callback:
                        self.on_received_callback(SimpleResponseMessage(body_bytes))
        except:
            self.disconnect()

    async def connect(self):
        if self._is_connected:
            return
        t_log.info("链接")
        reader, writer = await asyncio.open_connection(self._address.host, self._address.port)
        client_ip, client_port = writer.get_extra_info('sockname')
        self._tcp_reader = reader
        self._tcp_writer = writer
        self._is_connected = True
        _ = asyncio.create_task(self._background_read())
        return client_ip, client_port

    def disconnect(self):
        if self._is_connected:
            self._is_connected = False
            try:
                self._tcp_writer.close()
            except:
                pass
            self._tcp_reader = None
            self._tcp_writer = None
            if self.on_disconnected_callback:
                self.on_disconnected_callback()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


async def main():
    def message_callback(message: SimpleResponseMessage):
        print(f"Callback received: {message.json_dict}")

    client = SimpleTcpClient(HostPort('127.0.0.1', 51615), message_callback)
    # client = SimpleTcpClient(HostPort('192.168.45.81', 51515), message_callback)
    await client.connect()
    while client.is_connected:
        await asyncio.sleep(5)
        await client.send_json({'requester_addr': "('127.0.0.1', 56062)", 'request_id': 'hehe', 'case_name': 'MockTest', 'test_result': 'pass', 'message': 'xixi'})


if __name__ == "__main__":
    asyncio.run(main())

