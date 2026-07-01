import json
from typing import Optional


class SimpleResponseMessage:
    def __init__(self, data: bytes):
        self._data = data
        self._cached_json_dict: Optional[dict] = None
        self._cached_text: Optional[str] = None

    @property
    def data(self) -> bytes:
        return self._data

    @data.setter
    def data(self, data: bytes):
        self._data = data
        self._cached_json_dict = None
        self._cached_text = None

    @property
    def text(self) -> str:
        if self._cached_text is None:
            self._cached_text = self._data.decode("utf-8")
        return self._cached_text

    @property
    def json_dict(self) -> dict:
        if self._cached_json_dict is None:
            self._cached_json_dict = json.loads(self.text)
        return self._cached_json_dict
