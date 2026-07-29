import threading
import asyncio
import time
from phone_dispatcher.phone_dispatcher_center import PhoneDispatcherClient, DEFAULT_PORT, DISPATCH_TIMEOUT


class SyncPhoneDispatcherClient:
    def __init__(self, port=DEFAULT_PORT, timeout=DISPATCH_TIMEOUT):
        self._port = port
        self._timeout = timeout
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._start_loop, daemon=True)
        self._thread.start()
        self._client = None
        # 等待事件循环真正就绪
        time.sleep(0.1)

    def _start_loop(self):
        """后台线程中的事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro):
        """提交协程到后台loop，并等待结果"""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def connect(self, wait_srv=True):
        """同步 connect"""

        async def _c():
            client = PhoneDispatcherClient(port=self._port, timeout=self._timeout)
            await client.connect(wait_srv=wait_srv)
            return client

        self._client = self._run(_c())
        return True

    def register(self, sns):
        """同步 register"""
        return self._run(self._client.register(sns))

    def request(self, sn, wait=False, timeout=None, register_if_needed=True):
        """同步 request"""
        return self._run(
            self._client.request(sn, wait=wait, timeout=timeout, register_if_needed=register_if_needed)
        )

    def request_any(self, wait=False, timeout=None):
        """同步 request_any"""
        return self._run(self._client.request_any(wait=wait, timeout=timeout))

    def release(self, sn):
        """同步 release"""
        return self._run(self._client.release(sn))

    def cleanup(self):
        """同步 cleanup"""
        return self._run(self._client.cleanup())

    def status(self):
        """同步 status"""
        return self._run(self._client.status())

    def disconnect(self):
        """同步 disconnect"""
        self._client.disconnect()

    def shutdown_loop(self):
        """退出后台事件循环（可选）"""
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()


# 使用示例
if __name__ == '__main__':
    cli = SyncPhoneDispatcherClient(port=9000)
    cli.connect()
    print(cli.register(['DEVICE_SN1', 'DEVICE_SN2']))
    sn, status = cli.request('DEVICE_SN1', wait=True)
    print('Leased:', sn, status)
    print('Current snapshot:', cli.status())
    cli.release(sn)
    cli.disconnect()
    cli.shutdown_loop()
