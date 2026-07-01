import sys
from typing import Optional, Literal, Callable, List, TypeVar, Protocol

_on_output_text: List[Callable[[str], None]] = []
_on_output_error_text: List[Callable[[str], None]] = []

_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsWrite(Protocol[_T_contra]):
    def write(self, __s: _T_contra) -> object:
        pass


def register_output_text_listener(callback: Callable[[str], None]):
    _on_output_text.append(callback)


def unregister_output_text_listener(callback: Callable[[str], None]):
    _on_output_text.remove(callback)


def register_output_error_listener(callback: Callable[[str], None]):
    _on_output_error_text.append(callback)


def unregister_output_error_listener(callback: Callable[[str], None]):
    _on_output_error_text.remove(callback)


def output(*args, sep: Optional[str] = " ", end: Optional[str] = "\n", file: Optional[SupportsWrite[str]] = None,
           flush: Literal[False] = False):
    if _on_output_text:
        text = ("" if sep is None else sep).join(map(str, args))  # + ("" if end is None else end)
        for callback in _on_output_text:
            callback(text)
        print(text, sep=None, end=end, file=file, flush=flush)
    else:
        print(*args, sep=sep, end=end, file=file, flush=flush)


def output_error(*args, sep: Optional[str] = " ", end: Optional[str] = "\n", file: Optional[SupportsWrite[str]] = None,
                 flush: Literal[False] = False):
    if file is None:
        file = sys.stderr
    if _on_output_error_text:
        text = ("" if sep is None else sep).join(map(str, args))  # + ("" if end is None else end)
        for callback in _on_output_error_text:
            callback(text)
        print(text, sep=None, end=end, file=file, flush=flush)
    else:
        print(*args, sep=sep, end=end, file=file, flush=flush)
