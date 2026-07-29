from typing import Any, Callable, Optional, Sequence

from powertrde.framework.tran_logger import t_log
from txn_sync.transaction_synchronizer import LocalManagerServer
from txn_sync.transaction_synchronizer import IPCClient
from txn_sync.transaction_synchronizer import TransactionSynchronizer


class TxnServerGUI:
    def __init__(self, team_name: str, scheme_name: str, watch_device_ids: Sequence[str], server_port: int, session_uuid: str, session_title: str, session_desc: str, use_gui: bool, post_callback: Optional[Callable[[Any], None]] = None, top_most=False):
        super().__init__()
        self.team_name = team_name
        self.scheme_name = scheme_name
        self.watch_device_ids = watch_device_ids
        self.use_gui = use_gui
        self.post_callback = post_callback
        self.session_uuid = session_uuid
        self.session_title = session_title
        self.session_desc = session_desc
        self.top_most = top_most
        self.server_port = server_port

    @property
    def watch_device_uuids(self):
        return [f'tpytest_{self.team_name}_{self.scheme_name}_{_id}' for _id in self.watch_device_ids]

    @property
    def watch_device_uuids_with_names(self):
        return [(f'tpytest_{self.team_name}_{self.scheme_name}_{_id}', _id) for _id in self.watch_device_ids]

    def start_and_wait(self, on_server_started: Optional[Callable[[int], None]]):
        server = LocalManagerServer(preferred_port=self.server_port)
        server_address = server.start()
        t_log.info(f"Txn server start at {server_address[1]}:{server_address[2]}")

        ipc_for_sync = IPCClient(server_address, timeout=1.0)
        sync = TransactionSynchronizer(ipc_for_sync, poll_interval=1.0)
        sync.start()

        if callable(on_server_started):
            on_server_started(server_address[2])

        def postproc_callback(sync_obj):
            if callable(self.post_callback):
                self.post_callback(sync_obj)

        if self.use_gui:
            from PyQt6.QtWidgets import QApplication
            from txn_sync.transaction_watcher_gui import SessionMonitorWindow
            app = QApplication([])
            win = SessionMonitorWindow(server_address, sync, session_uuid=self.session_uuid, session_title=self.session_title,
                                       session_description=self.session_desc, initial_uuids=self.watch_device_uuids_with_names,
                                       on_postprocess=postproc_callback, always_on_top=self.top_most)
            win.show()
            app.exec()
        else:
            sync.watch_until_all_complete(self.watch_device_uuids, None)

        # cleanup
        sync.stop()
        server.stop()


if __name__ == '__main__':
    _ins = TxnServerGUI('dzppt', 'pdm', ('10BF1G02LF005MC','153772557A000258'), session_uuid='demo-session-uuid', session_title='tpytest_perf_demo', session_desc='tpytest_perf_demo_desc', use_gui=True, post_callback=lambda x: print('完成了'), top_most=True, server_port=57124)
    _ins.start_and_wait(None)
