import asyncio
import struct

from powertrde.framework.logs_protocol import logs_p
from powertrde.framework.simple_response_message import SimpleResponseMessage


class SimpleTcpServer:
    def __init__(self, port, on_message_received_callback=None):
        self.port = port
        self.on_message_received_callback = on_message_received_callback
        self.clients = set()

    async def handle_client(self, reader, writer):
        self.clients.add(writer)
        logs_p().log_debug(f"Client connected: {reader}")
        try:
            while True:
                length_bytes = await reader.readexactly(4)
                length = struct.unpack('>I', length_bytes)[0]
                message_bytes = await reader.readexactly(length)
                logs_p().log_debug(f"Client message received: {message_bytes.decode('utf-8')}")
                self.on_message_received(message_bytes)
        except asyncio.IncompleteReadError:
            logs_p().log_debug("Client disconnected")
        finally:
            self.clients.remove(writer)
            writer.close()
            await writer.wait_closed()

    def on_message_received(self, message_bytes):
        if self.on_message_received_callback:
            self.on_message_received_callback(SimpleResponseMessage(message_bytes))

    async def send_message(self, message):
        length_bytes = struct.pack('>I', len(message))
        for writer in self.clients:
            writer.write(length_bytes + message)
            await writer.drain()

    async def send_text_message(self, text_message):
        await self.send_message(text_message.encode('utf-8'))

    async def start_server(self):
        server = await asyncio.start_server(self.handle_client, '0.0.0.0', self.port)
        logs_p().log_debug(f"Server started on port {self.port}")
        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    async def main():
        def message_callback(message: SimpleResponseMessage):
            print(f"Callback received: {message.text}")

        server = SimpleTcpServer(51515, message_callback)
        await server.start_server()


    asyncio.run(main())
