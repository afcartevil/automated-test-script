import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
raw_key = "skJGIWEUHVGrbvkfdnvk;civkjdfb,ovSIDVQ\\]wvg=w234654rekgvb"
key = hashlib.sha256(raw_key.encode('utf-8')).digest()  # bytes 类型，长度 32


def md5_encrypt(text: str) -> str:
    """生成文本的 MD5 哈希"""
    m = hashlib.md5()
    m.update(text.encode('utf-8'))
    return m.hexdigest()


def encrypt(plaintext: str) -> str:
    cipher = AES.new(key, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(plaintext.encode('utf-8'), AES.block_size))
    iv = base64.b64encode(cipher.iv).decode('utf-8')
    ct = base64.b64encode(ct_bytes).decode('utf-8')
    return f"{iv}:{ct}"


def decrypt(ciphertext: str) -> str:
    iv_str, ct_str = ciphertext.split(":")
    iv = base64.b64decode(iv_str)
    ct = base64.b64decode(ct_str)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    pt = unpad(cipher.decrypt(ct), AES.block_size)
    return pt.decode('utf-8')
