import asyncio
import os
import sys


def main():
    async def _main():
        from phone_dispatcher.phone_dispatcher_center import PhoneDispatcherClient
        client = PhoneDispatcherClient()
        await client.connect()
        # print(await client.register(['1410925519000179']))
        sn, status = await client.request('1410925519000179', wait=True, register_if_needed=True, timeout=999)
        print(f"Leased {sn}: {status}")
        await asyncio.sleep(10)
        # print(await client.release(sn))
        client.disconnect()

    asyncio.run(_main())


def add_path_to_python_env():
    if getattr(sys, 'frozen', False):
        return
    root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    plugins_path = os.path.join(root_path, 'plugins')
    if os.path.exists(plugins_path):
        sys.path.insert(0, plugins_path)


if __name__ == '__main__':
    add_path_to_python_env()
    main()
