import asyncio
import subprocess
import sys
import os
import socket
import argparse
import json
import threading
import time

VERSION = "1.0.0"
DEFAULT_PORT = 41463
DISPATCH_TIMEOUT = 3 * 3600

if getattr(sys, 'frozen', False):
    PROJ_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
else:
    PROJ_DIR = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
    if not os.path.exists(os.path.join(PROJ_DIR, 'assets')):
        PROJ_DIR = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', '..'))

if os.name == 'nt':
    ADB_EXE = os.path.join(PROJ_DIR, 'assets', 'res_core', 'adb', 'adb.exe')
else:
    ADB_EXE = os.path.join(PROJ_DIR, 'assets', 'res_core', 'adb', 'adb_linux')
if not os.path.exists(ADB_EXE):
    ADB_EXE = 'adb'


class SingletonSocket:
    def __init__(self, port):
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._bind_or_upgrade()

    def _bind_or_upgrade(self):
        try:
            self.sock.bind(('127.0.0.1', self.port))
            print(f"[INFO] Bound dispatcher to port {self.port}")
        except OSError:
            print(f"[WARN] Port {self.port} in use, checking existing dispatcher")
            try:
                with socket.create_connection(('127.0.0.1', self.port), timeout=1) as conn:
                    conn.sendall(json.dumps({'cmd': 'version'}).encode() + b"\n")
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = conn.recv(1024)
                        if not chunk:
                            break
                        data += chunk
                    resp = json.loads(data.decode())
                    remote = resp.get('version', '0.0.0')
                    print(f"[INFO] Existing dispatcher version {remote}")
                    if tuple(map(int, VERSION.split('.'))) > tuple(map(int, remote.split('.'))):
                        print(f"[INFO] Shutting down old dispatcher v{remote} to upgrade to v{VERSION}")
                        conn.sendall(json.dumps({'cmd': 'shutdown_server'}).encode() + b"\n")
                        time.sleep(1)
                        self._bind_or_upgrade()
                    else:
                        print(f"[ERROR] Dispatcher v{remote} is newer or same; exiting")
                        sys.exit(0)
            except Exception as e:
                print(f"[ERROR] Failed upgrade: {e}")
                sys.exit(1)

    def listen(self):
        self.sock.listen()
        print(f"[INFO] Dispatcher listening on port {self.port}")
        return self.sock


class DeviceState:
    def __init__(self, sn):
        self.sn = sn
        self.in_use = False
        self.queue = []
        self._lock = asyncio.Lock()

    async def acquire(self, wait, timeout):
        async with self._lock:
            if not await self.is_online():
                return None, 'not_online'
            if not self.in_use:
                self.in_use = True
                return self.sn, 'ok'
            if not wait:
                return None, 'busy'
            fut = asyncio.get_event_loop().create_future()
            self.queue.append(fut)
        try:
            sn = await asyncio.wait_for(fut, timeout)
            return sn, 'ok'
        except asyncio.TimeoutError:
            async with self._lock:
                if fut in self.queue:
                    self.queue.remove(fut)
            return None, 'timeout'

    async def release(self):
        async with self._lock:
            if self.queue:
                fut = self.queue.pop(0)
                if not fut.done(): fut.set_result(self.sn)
            else:
                self.in_use = False

    async def force_release_all(self, reason):
        async with self._lock:
            for fut in self.queue:
                if not fut.done(): fut.set_exception(Exception(reason))
            self.queue.clear()
            self.in_use = False

    async def is_online(self):
        proc = await asyncio.create_subprocess_exec(ADB_EXE, 'devices', stdout=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        return self.sn.encode() in out


class DeviceManager:
    def __init__(self):
        self._devices = {}  # sn -> DeviceState
        self._lock = asyncio.Lock()

    async def _get_online(self):
        proc = await asyncio.create_subprocess_exec(ADB_EXE, 'devices', stdout=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        lines = out.splitlines()[1:]
        return {line.split()[0].decode() for line in lines if line}

    async def register(self, sns):
        results = {}
        online = await self._get_online()
        async with self._lock:
            for sn in sns:
                ok = sn in online
                if ok and sn not in self._devices:
                    self._devices[sn] = DeviceState(sn)
                    print(f"[REGISTER] Device {sn} registered")
                results[sn] = ok
                if not ok:
                    print(f"[REGISTER] Device {sn} offline; cannot register")
        return results

    async def cleanup_offline(self):
        online = await self._get_online()
        async with self._lock:
            for sn, dev in list(self._devices.items()):
                if sn not in online:
                    print(f"[CLEANUP] Device {sn} offline; unregistering and releasing")
                    await dev.force_release_all('Device offline')
                    del self._devices[sn]

    async def request(self, sn, wait=False, timeout=None, register_if_needed=True):
        # Auto-register outside lock
        if sn not in self._devices:
            if register_if_needed:
                results = await self.register([sn])
                if not results.get(sn):
                    return None, 'not_online'
            else:
                return None, 'not_registered'
        async with self._lock:
            dev = self._devices.get(sn)
        if not dev:
            return None, 'not_registered'
        sn_granted, status = await dev.acquire(wait, timeout)
        if status == 'ok':
            print(f"[LEASE] Device {sn_granted} leased (specific)")
        return sn_granted, status

    async def request_any(self, wait=False, timeout=None):
        async with self._lock:
            for dev in self._devices.values():
                if not dev.in_use and await dev.is_online():
                    sn_granted, status = await dev.acquire(False, None)
                    print(f"[LEASE] Device {sn_granted} leased (any)")
                    return sn_granted, status
            if not wait:
                return None, 'busy'
            fut = asyncio.get_event_loop().create_future()
            for dev in self._devices.values():
                dev.queue.append(fut)
        try:
            sn_granted = await asyncio.wait_for(fut, timeout)
            print(f"[LEASE] Device {sn_granted} leased from queue (any)")
            return sn_granted, 'ok'
        except asyncio.TimeoutError:
            async with self._lock:
                for dev in self._devices.values():
                    if fut in dev.queue:
                        dev.queue.remove(fut)
            return None, 'timeout'

    async def release(self, sn):
        async with self._lock:
            if sn in self._devices:
                await self._devices[sn].release()
                print(f"[RELEASE] Device {sn} released")

    def status_snapshot(self):
        # Returns list of (sn, in_use) tuples
        return [(sn, dev.in_use) for sn, dev in self._devices.items()]


class PhoneDispatcherServer:
    def __init__(self, port=DEFAULT_PORT):
        self.port = port
        self.manager = DeviceManager()
        self.server = None

    def _print_status(self):
        snapshot = self.manager.status_snapshot()
        print("[STATUS] Devices:")
        for sn, in_use in snapshot:
            print(f"  - {sn}: {'BUSY' if in_use else 'FREE'}")

    async def _client_handler(self, reader, writer):
        addr = writer.get_extra_info('peername')
        leased = set()
        print(f"[CONNECT] Client {addr} connected")
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break
                try:
                    req = json.loads(data.decode())
                except json.JSONDecodeError:
                    continue
                res = await self._dispatch(req, leased)
                writer.write(json.dumps(res).encode() + b"\n")
                await writer.drain()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[ERROR] Client {addr} handler error: {e}")
        finally:
            for sn in leased:
                await self.manager.release(sn)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            print(f"[DISCONNECT] Client {addr} disconnected")

    async def _dispatch(self, req, leased):
        cmd = req.get('cmd')
        if cmd == 'version':
            return {'version': VERSION}
        if cmd == 'shutdown_server':
            print(f"[INFO] Received shutdown_server command, shutting down...")
            _ = asyncio.create_task(self._shutdown())
            return {'status': 'shutting_down'}
        if cmd == 'register':
            sns = req.get('sns', [])
            print(f"[CMD] register SNS={sns}")
            return {'result': await self.manager.register(sns)}
        if cmd == 'request':
            sn = req.get('sn')
            wait = req.get('wait', False)
            timeout = req.get('timeout')
            reg_if = req.get('register_if_needed', True)
            print(f"[CMD] request SN={sn}, wait={wait}, timeout={timeout}, register_if_needed={reg_if}")
            sn_granted, status = await self.manager.request(sn, wait, timeout, reg_if)
            if status == 'ok':
                leased.add(sn_granted)
            return {'sn': sn_granted, 'status': status}
        if cmd == 'request_any':
            wait = req.get('wait', False)
            timeout = req.get('timeout')
            print(f"[CMD] request_any wait={wait}, timeout={timeout}")
            sn_granted, status = await self.manager.request_any(wait, timeout)
            if status == 'ok':
                leased.add(sn_granted)
            return {'sn': sn_granted, 'status': status}
        if cmd == 'release':
            sn = req.get('sn')
            print(f"[CMD] release SN={sn}")
            if sn in leased:
                leased.remove(sn)
                await self.manager.release(sn)
            return {'status': 'ok'}
        if cmd == 'cleanup':
            print(f"[CMD] cleanup")
            await self.manager.cleanup_offline()
            return {'status': 'ok'}
        if cmd == 'status':
            snapshot = self.manager.status_snapshot()
            return {'status_snapshot': snapshot}
        return {'error': 'unknown cmd'}

    async def _shutdown(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            print("[INFO] Server socket closed")
        loop = asyncio.get_event_loop()
        current = asyncio.current_task(loop)
        tasks = [t for t in asyncio.all_tasks(loop) if t is not current]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        print("[INFO] All client handler tasks cancelled")
        print("[INFO] Stopping event loop")
        loop.stop()

    def start(self):
        sock = SingletonSocket(self.port).listen()
        loop = asyncio.get_event_loop()
        # Setup key listener for status ('L' key)
        try:
            # On Unix, can use add_reader
            loop.add_reader(sys.stdin, lambda: self._print_status())
        except NotImplementedError:
            # On Windows, spawn thread
            def key_listener():
                import msvcrt
                while True:
                    ch = msvcrt.getwch()
                    if ch.upper() == 'L':
                        loop.call_soon_threadsafe(self._print_status)

            t = threading.Thread(target=key_listener, daemon=True)
            t.start()
        # Start server
        self.server = loop.run_until_complete(asyncio.start_server(self._client_handler, sock=sock))
        print(f"[INFO] Serving on 127.0.0.1:{self.port}")
        try:
            loop.run_forever()
        finally:
            if self.server:
                self.server.close()
                loop.run_until_complete(self.server.wait_closed())
            loop.close()


class PhoneDispatcherClient:
    def __init__(self, port=DEFAULT_PORT, timeout=DISPATCH_TIMEOUT):
        self.port = port
        self.timeout = timeout
        self.reader = None
        self.writer = None

    async def connect(self, wait_srv=True):
        try:
            self.reader, self.writer = await asyncio.open_connection('127.0.0.1', self.port)
            print(f"[CLIENT] Connected to dispatcher on port {self.port}")
        except Exception:
            if wait_srv:
                print("[CLIENT] Dispatcher not running; starting...")
                self._lazy_start()
                await asyncio.sleep(2)
                return await self.connect(False)
            raise
        return True

    def _lazy_start(self):
        if os.name == 'nt':
            _args = ['start', f'Phone Rent Center v{VERSION} (测试辅助机派发服务-请勿关闭-DO NOT CLOSE)', sys.executable, __file__, '--serve', '--port', str(self.port)]
            subprocess.Popen(_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                             shell=True)
        else:
            _args = [sys.executable, __file__, '--serve', '--port', str(self.port)]
            subprocess.Popen(_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)

    async def register(self, sns):
        resp = await self._send({'cmd': 'register', 'sns': sns})
        return resp.get('result', {})

    async def request(self, sn, wait=False, timeout=None, register_if_needed=True):
        resp = await self._send({'cmd': 'request', 'sn': sn, 'wait': wait, 'timeout': timeout or self.timeout,
                                 'register_if_needed': register_if_needed})
        return resp.get('sn'), resp.get('status')

    async def request_any(self, wait=False, timeout=None):
        resp = await self._send({'cmd': 'request_any', 'wait': wait, 'timeout': timeout or self.timeout})
        return resp.get('sn'), resp.get('status')

    async def release(self, sn):
        return await self._send({'cmd': 'release', 'sn': sn})

    async def cleanup(self):
        return await self._send({'cmd': 'cleanup'})

    async def status(self):
        resp = await self._send({'cmd': 'status'})
        return resp.get('status_snapshot', [])

    def disconnect(self):
        if self.writer:
            self.writer.close()

    async def _send(self, payload):
        self.writer.write(json.dumps(payload).encode() + b"\n")
        await self.writer.drain()
        data = await self.reader.readline()
        return json.loads(data.decode())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if args.serve:
        PhoneDispatcherServer(port=args.port).start()
    else:
        print('See below client demo')
        # async def demo():
        #     client = DispatcherClient()
        #     await client.connect()
        #     print(await client.request('UNKNOWN_SN', register_if_needed=False))
        #     print(await client.request('UNKNOWN_SN', register_if_needed=True))
        #     print(await client.status())
        #     client.disconnect()
        #
        # asyncio.run(demo())
