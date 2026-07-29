from phone_dispatcher.sync_phone_dispatcher_client import SyncPhoneDispatcherClient


class PhoneDispatcherMixIn:
    def __init__(self):
        super().__init__()
        self._phone_dispatcher_client = None

    @property
    def phone_dispatcher_client(self):
        if self._phone_dispatcher_client is None:
            self._phone_dispatcher_client = SyncPhoneDispatcherClient()
            self._phone_dispatcher_client.connect()
        return self._phone_dispatcher_client

    def lock_use_copilot(self, wait=True):
        assert self.c_device_id, 'Not found copilot phone!'
        return self.phone_dispatcher_client.request(self.c_device_id, wait=wait)

    def unlock_use_copilot(self):
        return self.phone_dispatcher_client.release(self.c_device_id)

    def lock_use_observe(self, wait=True):
        assert self.o_device_id, 'Not found observe phone!'
        return self.phone_dispatcher_client.request(self.o_device_id, wait=wait)

    def unlock_use_observe(self):
        return self.phone_dispatcher_client.release(self.o_device_id)
