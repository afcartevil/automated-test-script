import codecs
import os
import shutil
from pathlib import Path
from typing import Optional, Union

_UTF8_BOM = b"\xEF\xBB\xBF"


def move_dir_and_rename(
        src: Union[str, Path],
        dst_parent: Union[str, Path],
        new_name: Optional[str] = None,
        *,
        overwrite: bool = False
) -> Path:
    """
    Move directory `src` into `dst_parent` and rename it to `new_name` (or keep original name if None).
    If a target exists and overwrite==True, the target will be removed first (shutil.rmtree).
    Returns the final Path to the moved directory.

    Raises:
      FileNotFoundError: if src does not exist
      NotADirectoryError: if src is not a directory
      FileExistsError: if target exists and overwrite is False
      ValueError: if dst_parent is inside src (moving into own subtree)
      Exception: underlying errors from os/shutil operations
    """
    src = Path(src)
    dst_parent = Path(dst_parent)

    if not src.exists():
        raise FileNotFoundError(f"Source directory not found: {src}")
    if not src.is_dir():
        raise NotADirectoryError(f"Source is not a directory: {src}")

    # default new_name
    if not new_name:
        new_name = src.name

    # resolve absolute paths for checks
    src_res = src.resolve()
    dst_parent_res = dst_parent.resolve()

    # Prevent moving into its own subtree (e.g., moving C:/a to C:/a/b)
    try:
        # Python 3.9+: Path.is_relative_to available
        if dst_parent_res.is_relative_to(src_res):
            raise ValueError(f"Destination parent {dst_parent_res} is inside source {src_res} — aborting.")
    except AttributeError:
        # fallback for older Python: string prefix check
        src_s = str(src_res)
        dst_s = str(dst_parent_res)
        # add separator guard to avoid partial match
        sep = os.sep
        if dst_s == src_s or dst_s.startswith(src_s + sep):
            raise ValueError(f"Destination parent {dst_parent_res} is inside source {src_res} — aborting.")

    # Ensure destination parent exists
    dst_parent_res.mkdir(parents=True, exist_ok=True)
    target = dst_parent_res / new_name

    # If target exists
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"Target already exists: {target}")
        # attempt to remove target (be careful with permissions)
        if target.is_file() or target.is_symlink():
            target.unlink()
        else:
            # directory: remove tree
            shutil.rmtree(target)

    # Try atomic rename first (fast on same filesystem)
    try:
        # os.replace works to atomically replace a target if it exists on many platforms
        os.replace(str(src_res), str(target))
        # success
        return target
    except OSError:
        # likely cross-device link or other issue: fallback to shutil.move
        try:
            moved = shutil.move(str(src_res), str(target))
            return Path(moved)
        except Exception:
            # re-raise with context
            raise


def file_startswith_utf8(path: Union[str, Path], prefix: str) -> bool:
    """
    Efficiently check whether a UTF-8 encoded text file starts with the given `prefix` (string).
    Only reads as few bytes from disk as needed; suitable for very large files.

    Args:
        path: path to the file (UTF-8 encoded).
        prefix: the Unicode prefix to check (may contain multi-byte characters).

    Returns:
        True if the file (after skipping optional UTF-8 BOM) begins with prefix, False otherwise.

    Notes:
      - The function assumes the file is encoded in UTF-8 (may contain BOM). If file contains
        invalid UTF-8 sequences in the very beginning, a UnicodeDecodeError may be raised.
      - This reads small binary chunks until enough complete characters are decoded to compare
        against prefix; it never reads the entire file for long prefixes.
    """
    if prefix == "":
        return True

    pref_len_chars = len(prefix)
    pref_bytes = prefix.encode("utf-8")

    # Conservative upper bound for initial bytes to read: encoded length + a few extra bytes
    # but algorithm will request more only if needed (due to partial multibyte sequences).
    max_initial = max(len(pref_bytes) + 8, 32)

    decoder = codecs.getincrementaldecoder("utf-8")()

    p = Path(path)
    with p.open("rb") as f:
        # handle optional BOM: if present, skip it (we don't want BOM to count towards characters)
        start = f.read(3)
        if start.startswith(_UTF8_BOM):
            # BOM present; continue reading from after BOM
            # leave decoder as-is: BOM bytes are consumed and we don't feed them to decoder
            pass
        else:
            # no BOM; rewind to start
            f.seek(0)

        decoded = ""  # decoded string available so far
        total_bytes_read = 0

        # read loop: fetch min bytes required, decode incrementally, stop once we have enough chars
        # or hit EOF; cap to a small safe maximum to avoid pathological behavior
        SAFE_CAP = max(4096, len(pref_bytes) * 4 + 64)

        # initial read
        chunk = f.read(max_initial)
        total_bytes_read += len(chunk)
        if chunk:
            decoded += decoder.decode(chunk, final=False)

        # if we still don't have enough characters, read more (small increments)
        while len(decoded) < pref_len_chars and total_bytes_read < SAFE_CAP:
            # read a small next chunk — typically a few bytes is enough to finish a multi-byte char
            next_chunk = f.read(16)
            if not next_chunk:
                break
            total_bytes_read += len(next_chunk)
            decoded += decoder.decode(next_chunk, final=False)

        # Try to finalize decoder a little (but do not force EOF state)
        # We decode with final=False so incomplete sequences remain buffered (we don't want to error)
        # but to be safe attempt to decode any remaining buffer:
        try:
            decoded += decoder.decode(b"", final=False)
        except UnicodeDecodeError:
            # shouldn't normally happen; treat as mismatch
            return False

        # Now compare only up to prefix length
        return decoded[:pref_len_chars] == prefix


def read_all_text(file_path, encoding='utf-8'):
    """
    读取指定文件的全部内容。

    :param file_path: 文件路径。
    :param encoding: 文件编码格式，默认utf-8。
    :return: 文件内容的字符串表示。
    """
    with open(file_path, 'r', encoding=encoding) as file:
        content = file.read()
    return content


def read_lines(file_path, encoding='utf-8'):
    """
    读取指定文件的全部内容。

    :param file_path: 文件路径。
    :param encoding: 文件编码格式，默认utf-8。
    :return: 文件内容的字符串表示。
    """
    with open(file_path, 'r', encoding=encoding) as file:
        content = file.readlines()
    return content


def write_all_text(file_path, content: str, encoding='utf-8'):
    """
    将指定的字符串写入到文件中。如果文件不存在则创建它，如果文件已经存在则覆盖它。

    :param file_path: 文件路径。
    :param content: 要写入文件的字符串。
    :param encoding: 文件编码，默认为utf-8。
    """
    with open(file_path, 'w', encoding=encoding) as file:
        file.write(content)
