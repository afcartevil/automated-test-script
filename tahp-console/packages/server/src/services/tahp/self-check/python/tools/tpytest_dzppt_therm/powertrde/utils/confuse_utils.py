import base64
import hashlib
import hmac
import os
import secrets
import binascii
import shutil
import tempfile
from pathlib import Path
from typing import Mapping, Dict, Any, Union

PathLike = Union[str, Path]

# ----- Configuration constants -----
_MARKER = "_EC$$"  # 代表本算法的标记前缀（可自定义，但必须保持一致）
_PASSPHRASE = "_$E$C"  # 默认的混淆密钥
_VERSION = 1  # 内部协议版本（1 byte）
_SALT_LEN = 16  # pbkdf2 salt bytes
_NONCE_LEN = 16  # nonce for keystream
_TAG_LEN = 32  # HMAC-SHA256 length
_PBKDF2_ITERS = 200_000  # PBKDF2 iterations (可根据性能与安全权衡调整)
_DERIVED_KEY_LEN = 32  # 派生密钥长度 (bytes)


# ---------------- utils ----------------
def _to_bytes(x: Union[str, bytes]) -> bytes:
    return x.encode("utf-8") if isinstance(x, str) else x


def _derive_key(passphrase: Union[str, bytes], salt: bytes, iterations: int = _PBKDF2_ITERS) -> bytes:
    """从口令和 salt 派生对称 key（使用 PBKDF2-HMAC-SHA256）"""
    pw = _to_bytes(passphrase)
    return hashlib.pbkdf2_hmac("sha256", pw, salt, iterations, dklen=_DERIVED_KEY_LEN)


def _keystream_xor(key: bytes, nonce: bytes, data: bytes) -> bytes:
    """
    使用 HMAC-SHA256(key, nonce||counter) 作为伪随机流生成器，得到 keystream，然后与 data 做 XOR。
    返回异或后的 bytes。
    """
    out = bytearray(len(data))
    block_index = 1
    generated = 0
    while generated < len(data):
        ctr = block_index.to_bytes(4, "big")
        digest = hmac.new(key, nonce + ctr, hashlib.sha256).digest()
        take = min(len(digest), len(data) - generated)
        for i in range(take):
            out[generated + i] = data[generated + i] ^ digest[i]
        generated += take
        block_index += 1
    return bytes(out)


def _hmac_tag(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    """对 (nonce || ciphertext) 做 HMAC-SHA256 作为认证标签"""
    return hmac.new(key, b"TAG" + nonce + ciphertext, hashlib.sha256).digest()


# ---------------- public API ----------------
def confuse_string(plaintext: str, *, passphrase: str = _PASSPHRASE, marker: str = _MARKER) -> str:
    """
    加密 plaintext（str），返回带标记的字符串（marker + base64(payload)）。
    - 若输入 already starts with marker，则直接返回输入（避免二次加密）。
    - passphrase: 用于派生密钥的口令（必须传）。
    """
    if plaintext is None:
        raise ValueError("plaintext must be a string")
    if not isinstance(plaintext, str):
        raise TypeError("plaintext must be str")

    if plaintext.startswith(marker):
        # 已有标记 -> 认为已加密，直接返回（避免二次加密）
        return plaintext

    salt = secrets.token_bytes(_SALT_LEN)
    nonce = secrets.token_bytes(_NONCE_LEN)
    key = _derive_key(passphrase, salt)

    data = plaintext.encode("utf-8")  # 将字符串转为 UTF-8 bytes
    ciphertext = _keystream_xor(key, nonce, data)
    tag = _hmac_tag(key, nonce, ciphertext)

    # payload: version(1) | salt | nonce | ciphertext | tag
    payload = bytes([_VERSION]) + salt + nonce + ciphertext + tag
    b64 = base64.urlsafe_b64encode(payload).decode("ascii")
    return marker + b64


def defuse_string(value: str, *, passphrase: str = _PASSPHRASE, marker: str = _MARKER, strict: bool = True) -> str:
    """
    若 value 以 marker 开头，尝试解密并返回明文字符串；否则直接返回 value（视为明文）。

    - strict=False（默认）：如果带 marker 但 payload 不是合法/base64 或格式不对，则视为未加密，直接返回原值（容错）。
    - strict=True：在遇到无效 base64 或格式错误时会抛出 ValueError（更严格的行为）。

    注意：若验证 HMAC 失败或版本不支持，这里在 strict=False 情况也会抛出 ValueError（因为这通常表示篡改或口令错误）。
    """
    if value is None:
        raise ValueError("value must be a string")
    if not isinstance(value, str):
        raise TypeError("value must be str")

    if not value.startswith(marker):
        # 没有标记 -> 认为是用户明文，直接返回
        return value

    b64 = value[len(marker):]
    try:
        payload = base64.urlsafe_b64decode(b64)
    except (binascii.Error, ValueError):
        # 非法 base64：若 strict 则抛错，否则容错返回原始字符串
        if strict:
            raise ValueError("invalid base64 encrypted payload")
        else:
            # 容错：把原始带标记字符串当作明文返回
            return value

    # minimal length check: version + salt + nonce + tag
    min_len = 1 + _SALT_LEN + _NONCE_LEN + _TAG_LEN
    if len(payload) < min_len:
        if strict:
            raise ValueError("encrypted payload too short or corrupt")
        else:
            return value

    ver = payload[0]
    if ver != _VERSION:
        if strict:
            raise ValueError(f"unsupported encrypted payload version: {ver}")
        else:
            return value

    pos = 1
    salt = payload[pos: pos + _SALT_LEN]
    pos += _SALT_LEN
    nonce = payload[pos: pos + _NONCE_LEN]
    pos += _NONCE_LEN
    # ciphertext goes until last TAG_LEN bytes
    ciphertext = payload[pos: len(payload) - _TAG_LEN]
    tag = payload[len(payload) - _TAG_LEN:]

    key = _derive_key(passphrase, salt)
    # verify tag
    expected_tag = _hmac_tag(key, nonce, ciphertext)
    if not hmac.compare_digest(expected_tag, tag):
        # authentication failure -> very likely tampering or wrong passphrase
        raise ValueError("encrypted payload authentication failed (bad passphrase or tampered)")

    plain_bytes = _keystream_xor(key, nonce, ciphertext)
    try:
        return plain_bytes.decode("utf-8")
    except Exception:
        # 如果因为某些原因无法用 utf-8 解码（理论上不应发生，因为加密时用 utf-8 编码）
        return plain_bytes.decode("utf-8", errors="surrogatepass")


def confuse_data(obj: Any, *, passphrase: str = _PASSPHRASE, marker: str = _MARKER) -> Any:
    """
    对任意基础容器或字符串进行“深度加密”：
      - 如果 obj 是 str -> 使用 confuse_string(str, passphrase=passphrase, marker=marker) 并返回结果字符串
      - 如果 obj 是 Mapping -> 返回新的 dict（或同类型 mapping），只对 values 递归加密（keys 保留原样）
      - 如果 obj 是 list/tuple -> 返回相同类型，元素递归加密
      - 如果 obj 是 set/frozenset -> 返回相同类型，元素递归加密（注意：元素的哈希可能改变）
      - 其它类型原样返回（不做处理）

    返回值是新的对象（不在原地修改输入）。
    循环引用有基本的 memo 避免无限递归（保持结构拓扑，但对完全相同 identity 的循环会尽量保留关系）。
    """
    memo: Dict[int, Any] = {}

    def _enc(v: Any) -> Any:
        vid = id(v)
        if vid in memo:
            return memo[vid]

        # 字符串：直接调用 encrypt_string（内部会处理已加密标记）
        if isinstance(v, str):
            return confuse_string(v, passphrase=passphrase, marker=marker)

        # Mapping (dict-like)
        if isinstance(v, Mapping):
            # 尝试保留原 mapping 类型（若构造失败回退为 dict）
            try:
                out = v.__class__()  # e.g., OrderedDict()
            except Exception:
                out = {}
            memo[vid] = out  # 先登记以防循环引用
            for k, val in v.items():
                out[k] = _enc(val)
            return out

        # list
        if isinstance(v, list):
            out_list = []
            memo[vid] = out_list
            for item in v:
                out_list.append(_enc(item))
            return out_list

        # tuple
        if isinstance(v, tuple):
            # tuples immutable: build tuple normally; store to memo after create
            out_tuple = tuple(_enc(item) for item in v)
            memo[vid] = out_tuple
            return out_tuple

        # set
        if isinstance(v, set):
            out_set = set()
            memo[vid] = out_set
            for item in v:
                out_set.add(_enc(item))
            return out_set

        # frozenset
        if isinstance(v, frozenset):
            out_f = frozenset(_enc(item) for item in v)
            memo[vid] = out_f
            return out_f

        # bytes/bytearray 等二进制数据不处理；其它任意对象也不处理
        return v

    return _enc(obj)


def defuse_data(obj: Any, *, passphrase: str = _PASSPHRASE, marker: str = _MARKER, strict: bool = True) -> Any:
    """
    defuse_data 的行为与 confuse_data 对应：
      - 如果 obj 是 str -> 调用 defuse_string(str, passphrase, marker=marker, strict=strict)
        defuse_string 在没有标记时会直接返回原文（默认 strict=False 为容错）
      - 支持 Mapping / list / tuple / set / frozenset 的深度解密（仅处理字符串值）
      - 其它类型保持不变

    strict: 传递给 defuse_string 的 strict，控制当字符串带标记但格式非法时是否抛异常（True 则抛错）。
    """
    memo: Dict[int, Any] = {}

    def _dec(v: Any) -> Any:
        vid = id(v)
        if vid in memo:
            return memo[vid]

        if isinstance(v, str):
            return defuse_string(v, passphrase=passphrase, marker=marker, strict=strict)

        if isinstance(v, Mapping):
            try:
                out = v.__class__()  # try to keep same mapping type
            except Exception:
                out = {}
            memo[vid] = out
            for k, val in v.items():
                out[k] = _dec(val)
            return out

        if isinstance(v, list):
            out_list = []
            memo[vid] = out_list
            for item in v:
                out_list.append(_dec(item))
            return out_list

        if isinstance(v, tuple):
            out_tuple = tuple(_dec(item) for item in v)
            memo[vid] = out_tuple
            return out_tuple

        if isinstance(v, set):
            out_set = set()
            memo[vid] = out_set
            for item in v:
                out_set.add(_dec(item))
            return out_set

        if isinstance(v, frozenset):
            out_f = frozenset(_dec(item) for item in v)
            memo[vid] = out_f
            return out_f

        return v

    return _dec(obj)


def confuse_file(
    path: PathLike,
    *,
    passphrase: str = _PASSPHRASE,
    marker: str = _MARKER,
    encoding: str = "utf-8",
    errors: str = "strict",
    backup: bool = False,
    atomic: bool = True,
) -> Path:
    """
    对指定文本文件做“混淆”（使用 confuse_string），原地替换文件内容（默认原子替换）。
    - 若文件开头已发现 marker，则视为已混淆，函数直接返回不做二次加密。
    - 返回被写入的目标 Path（Path 对象）。
    参数:
      path: 文件路径（字符串或 Path）
      passphrase/marker: 传递给 confuse_string 的参数
      encoding/errors: 文件文本编码与错误处理（读取/写入时使用）
      backup: 若 True，在覆盖前会生成一个同目录的 `.bak` 备份（源文件名 + ".bak"）
      atomic: 若 True 使用临时文件并 os.replace 以实现原子写入；否则直接覆写。
    异常:
      - 若文件不存在则抛出 FileNotFoundError
      - 其它 I/O 错误会被向上抛出
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file not found: {p!s}")
    if not p.is_file():
        raise IsADirectoryError(f"not a file: {p!s}")

    # 先快速检查开头是否已有 marker（避免完整读取+二次加密）
    # 使用文本读取以便支持常见 BOM/编码情形（confuse_string 输出为 ascii-safe marker + base64）
    with p.open("r", encoding=encoding, errors=errors) as f:
        start = f.read(len(marker))
        if start == marker:
            # 已经带标记 -> 不做二次加密
            return p
        # 回到文件开头，完整读取内容进行加密
        f.seek(0)
        plaintext = f.read()

    # 生成混淆结果（confuse_string 会自己处理已带标记的情形）
    encrypted = confuse_string(plaintext, passphrase=passphrase, marker=marker)

    # 备份原文件（可选）
    if backup:
        bak = p.with_name(p.name + ".bak")
        # 使用 copy2 保留元信息
        shutil.copy2(p, bak)

    # 写入（原子替换或直接写）
    if atomic:
        tmp_dir = str(p.parent) if p.parent.exists() else None
        # 使用 NamedTemporaryFile 在同一目录下创建临时文件以便于原子替换
        with tempfile.NamedTemporaryFile("w", delete=False, dir=tmp_dir, encoding=encoding, errors=errors) as tf:
            tf.write(encrypted)
            tmp_name = tf.name
        # 原子替换
        os.replace(tmp_name, str(p))
    else:
        with p.open("w", encoding=encoding, errors=errors) as f:
            f.write(encrypted)

    return p


def defuse_file(
    path: PathLike,
    *,
    passphrase: str = _PASSPHRASE,
    marker: str = _MARKER,
    encoding: str = "utf-8",
    errors: str = "strict",
    strict: bool = True,
    backup: bool = False,
    atomic: bool = True,
) -> Path:
    """
    对指定文本文件做“解混淆”（如果文件以 marker 开头则尝试 defuse_string），并原地替换为明文。
    - 若文件不以 marker 开头，函数直接返回（不作修改）。
    - strict 控制当文件带 marker 但 payload 无效时是否抛出异常（True 会抛出 ValueError）。
    - 返回被写入的目标 Path（Path 对象）。
    参数:
      path: 文件路径（字符串或 Path）
      passphrase/marker: 传递给 defuse_string 的参数
      encoding/errors: 文件文本编码与错误处理（读取/写入时使用）
      strict: 传递给 defuse_string 的 strict 参数
      backup: 若 True，在覆盖前会生成一个同目录的 `.bak` 备份（源文件名 + ".bak"）
      atomic: 若 True 使用临时文件并 os.replace 以实现原子写入；否则直接覆写。
    异常:
      - 若文件不存在则抛出 FileNotFoundError
      - 若 strict=True 且 payload 非法/鉴定失败则抛出 ValueError
      - 其它 I/O 错误会被向上抛出
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"file not found: {p!s}")
    if not p.is_file():
        raise IsADirectoryError(f"not a file: {p!s}")

    with p.open("r", encoding=encoding, errors=errors) as f:
        start = f.read(len(marker))
        if start != marker:
            # 没有 marker -> 认为是明文，直接返回
            return p
        # 否则读取整个带标记的文本
        f.seek(0)
        enc_text = f.read()

    # 尝试解密（defuse_string 内会根据 strict 行为决定是否抛异常或容错返回原始字符串）
    try:
        plaintext = defuse_string(enc_text, passphrase=passphrase, marker=marker, strict=strict)
    except ValueError:
        # 若 strict=False 的话，defuse_string 已在内部容错并返回原值；但如果 strict=True 抛出，这里按原样传递异常
        raise

    # 如果 defuse_string 在容错模式下返回原始带标记字符串（表示无法解析），则我们不改写文件
    if plaintext == enc_text:
        # 解密失败但非 strict（容错） => 不做任何替换
        return p

    # 备份原文件（可选）
    if backup:
        bak = p.with_name(p.name + ".bak")
        shutil.copy2(p, bak)

    # 写入明文（原子或非原子）
    if atomic:
        tmp_dir = str(p.parent) if p.parent.exists() else None
        with tempfile.NamedTemporaryFile("w", delete=False, dir=tmp_dir, encoding=encoding, errors=errors) as tf:
            tf.write(plaintext)
            tmp_name = tf.name
        os.replace(tmp_name, str(p))
    else:
        with p.open("w", encoding=encoding, errors=errors) as f:
            f.write(plaintext)

    return p


# ---------------- quick demo / tests ----------------
if __name__ == "__main__":
    examples = [
        "hello world",
        "密码含中文",
        "",  # 空字符串
        _MARKER + "already-encrypted"  # 模拟带标记但不是本算法输出的输入
    ]
    print("Demo: marker =", _MARKER)
    for plain in examples:
        enc = confuse_string(plain)
        try:
            dec = defuse_string(enc)  # 宽容模式：不会对无效 base64 抛异常
        except Exception as e:
            dec = f"<ERROR: {e}>"
        print("plain:", repr(plain))
        print("enc  :", enc)
        print("dec  :", repr(dec))
        print("ok   :", dec == plain)
        print("-" * 40)

    # 测试：对已带标记的输入，不发生二次加密
    already = _MARKER + "xxx"
    assert confuse_string(already) == already
    # 对明文直接 decrypt 返回相同字符串
    assert defuse_string("no-mark") == "no-mark"

    # 如果你想要严格行为（遇到带标记但格式不对时抛错），可以：
    try:
        defuse_string(_MARKER + "not-base64!!", strict=True)
    except ValueError as e:
        print("strict mode raises on invalid payload:", e)

    data = {
        "a": "plain1",
        "b": 42,
        "c": ["x", "y", {"inner": "秘密"}],
        "d": ("t1", "t2"),
        "e": {"setval", "s2"},
    }

    enc = confuse_data(data)
    print(enc)  # 所有字符串值会被加密（带标记），非字符串类型不变

    dec = defuse_data(enc)
    assert dec == data

    # 也可以直接传入列表或字符串
    s = "hello"
    enc_s = confuse_data(s)
    dec_s = defuse_data(enc_s)
    assert dec_s == s
