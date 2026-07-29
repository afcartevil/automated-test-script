import re
import sys
import traceback

from apkutils2 import APK, apkfile, AXML
from apkutils2.axml.chunk import StringPoolChunk


def _split_attrs_respecting_quotes(s: str):
    """
    将标签体（不含尖括号）分割成 tokens（保留引号内部分）。
    例如: 'android:foo="1" ="34" bar="x y"' -> ['android:foo="1"', '="34"', 'bar="x y"']
    """
    tokens = []
    cur = []
    in_quote = False
    quote_char = None
    i = 0
    while i < len(s):
        ch = s[i]
        if in_quote:
            cur.append(ch)
            if ch == quote_char:
                in_quote = False
                quote_char = None
            i += 1
            continue
        if ch == '"' or ch == "'":
            in_quote = True
            quote_char = ch
            cur.append(ch)
            i += 1
            continue
        # 空白分隔 token（当不在引号内）
        if ch.isspace():
            if cur:
                tokens.append(''.join(cur))
                cur = []
            # 跳过多个空白
            while i < len(s) and s[i].isspace():
                i += 1
            continue
        # 普通字符
        cur.append(ch)
        i += 1
    if cur:
        tokens.append(''.join(cur))
    return tokens


def _is_valid_attr_token(tok: str) -> bool:
    """
    判定 token 是否为合法的属性形式 name="value" 或 name='value' 或 name=value (少见)。
    - 如果 token 以 '=' 开头（比如 '="34"'）则视为非法（缺失属性名），返回 False。
    - 如果 token 中有 '='，则检查 '=' 左侧是否包含至少一个字母或 ':'（如 android:xxx）。
    - 如果 token 中无 '='，则可能是奇怪的单词（尽量保留以免丢信息）。
    """
    if not tok:
        return False
    if tok[0] == '=':
        return False
    if '=' in tok:
        name = tok.split('=', 1)[0]
        # 名称应包含字母或冒号（命名空间）
        if re.search(r'[A-Za-z:]', name):
            return True
        else:
            return False
    # 没有等号的 token（比如 boolean attribute 的简短形式）——保留（以免丢信息）
    return True


def clean_manifest(manifest: str) -> str:
    """
    清洗可能不合规的 AndroidManifest.xml 字符串，使其能被标准 XML 解析器正确解析。
    策略：对每个开始标签进行 token 分割（尊重引号），去掉形如 '="xxx"' 的孤立值片段（等号前无属性名）。
    返回修复后的 manifest 字符串。
    """
    # 统一换行，保留原始文本中的缩进和换行
    text = manifest.replace('\r\n', '\n').replace('\r', '\n')

    # 跳过 XML 声明和处理指令（<? ... ?>），我们不改动它们
    # 使用正则替换每个开标签（但不包括以 </ 开头的闭合标签和 <? ... ?>）
    tag_start_re = re.compile(r'<([A-Za-z0-9_:\-.]+)([^>]*)>', flags=re.DOTALL)

    def repl(match: re.Match) -> str:
        tagname = match.group(1)
        rest = match.group(2)  # 包含 attributes / 可能的 "/" / 新行 等等
        # 如果是 xml declaration <? ... ?> 或 <! ... > 类，直接返回原样
        # 但我们的 regex 已经避开了 <? 和 </
        # 处理 self-closing '/>' 情形 — 如果 rest 以 '/' 结尾，保留尾部 '/':
        is_self_closing = False
        tail_slash = ''
        r = rest
        # trim leading/trailing whitespace for processing but detect trailing '/'
        if r.strip().endswith('/'):
            is_self_closing = True
            # 移除最后的斜杠用于解析属性
            # 但要保留原位置的空格
            # 简单方式：去掉尾部的 '/' 及附近空白
            r = re.sub(r'/\s*$', '', r, flags=re.DOTALL)

        # Tokenize attributes respecting quotes
        tokens = _split_attrs_respecting_quotes(r)
        # Filter tokens: 去掉以 '=' 开头（缺名）或等号左侧不合法的 token
        good_tokens = []
        for t in tokens:
            if _is_valid_attr_token(t):
                good_tokens.append(t)
            else:
                # 不合法 token，丢弃
                # 如果需要调试，可以在此处记录被丢弃的 token
                # print("DROP token:", repr(t))
                pass

        # 重建标签。保持单个空格分隔，尽量不要改变 tagname
        if good_tokens:
            inner = ' ' + ' '.join(good_tokens)
        else:
            inner = ''
        if is_self_closing:
            return f"<{tagname}{inner} />"
        else:
            return f"<{tagname}{inner}>"

    # 逐个替换开标签
    cleaned = tag_start_re.sub(repl, text)

    # 另外：某些 APK manifest 里可能有孤立的 bare '=' 行，例如一个单独一行的 ="xxx"
    # 这些在上面处理后通常已被移除；但为保险，可再次做一轮删除孤立的 ='value' 模式（仅在标签体以外）
    # 我们谨慎移除行中仅包含 ="..."
    cleaned = re.sub(r'^\s*=\s*(".*?"|\'.*?\'|\S+)\s*$', '', cleaned, flags=re.MULTILINE)

    return cleaned


def _patched_decode_bytes(self, data: bytes, encoding: str, str_len: int) -> str:
    """
    Robust replacement for original decode_bytes.
    - data: bytes (expected length == str_len*2)
    - encoding: suggested encoding, e.g. 'utf-16'
    - str_len: expected number of UTF-16 code units (16-bit units)
    返回：Python str，不再因 surrogate pair 而抛 "invalid decoded string length"。
    """
    def utf16_code_unit_count(s: str) -> int:
        # 计算字符串在 UTF-16 中占用的 16-bit 单元数：
        # BMP (<=0xFFFF) 占 1 单元， >0xFFFF 占 2 单元（surrogate pair）
        count = 0
        for ch in s:
            cp = ord(ch)
            count += 1 if cp <= 0xFFFF else 2
        return count

    # 1) 尝试若干解码方式，优先 encoding 本身，然后 utf-16le/utf-16be（避免 BOM 影响）
    tried = []
    candidates = []
    if encoding:
        candidates.append(encoding)
    # 如果 encoding 是 utf-16-ish，加入 LE/BE 备选
    if 'utf-16' in (encoding or '').lower():
        candidates += ['utf-16le', 'utf-16be']
    else:
        # 常见情况仍尝试 utf-16le/be
        candidates += ['utf-16le', 'utf-16be']

    # 去重同时保留顺序
    seen = set()
    uniq_cands = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            uniq_cands.append(c)

    for enc in uniq_cands:
        try:
            s = data.decode(enc, errors='replace')
            tried.append((enc, s))
            if utf16_code_unit_count(s) == str_len:
                return s
        except Exception:
            # 忽略单个编码失败
            traceback.print_exc(file=sys.stderr)

    # 2) 回退：直接按 16-bit 单元解析（先假设 little-endian，再 big-endian）
    #    这段保证严格按 UTF-16 code unit 语义把 bytes 解析成 Python str，
    #    并正确合并 surrogate pair（高位 0xD800-0xDBFF + 低位 0xDC00-0xDFFF）。
    def build_from_units(is_le=True):
        units = []
        L = len(data)
        if L % 2 != 0:
            # 如果长度奇怪，丢掉最后一个字节（或可选择抛异常）
            L = L - 1
        for i in range(0, L, 2):
            lo = data[i]
            hi = data[i+1]
            if is_le:
                unit = (hi << 8) | lo
            else:
                unit = (lo << 8) | hi
            units.append(unit)
        # 将 units 转换为 codepoints（合并 surrogate pair）
        out_chars = []
        i = 0
        while i < len(units):
            u = units[i]
            # 高代理
            if 0xD800 <= u <= 0xDBFF and i + 1 < len(units):
                v = units[i+1]
                if 0xDC00 <= v <= 0xDFFF:
                    # 合并成一个补充平面码点
                    hi = u
                    lo = v
                    codepoint = ((hi - 0xD800) << 10) + (lo - 0xDC00) + 0x10000
                    try:
                        out_chars.append(chr(codepoint))
                    except ValueError:
                        out_chars.append('\uFFFD')
                    i += 2
                    continue
            # 非 surrogate 或不成对情形，直接当作 BMP 单位
            try:
                out_chars.append(chr(u))
            except ValueError:
                out_chars.append('\uFFFD')
            i += 1
        return ''.join(out_chars)

    try:
        s_le = build_from_units(is_le=True)
        if utf16_code_unit_count(s_le) == str_len:
            return s_le
    except Exception:
        traceback.print_exc(file=sys.stderr)

    try:
        s_be = build_from_units(is_le=False)
        if utf16_code_unit_count(s_be) == str_len:
            return s_be
    except Exception:
        traceback.print_exc(file=sys.stderr)

    # 最后兜底：返回尝试过的第一个 decode (或替换模式下的 decode)
    if tried:
        # 找一个最“接近”的解（优先 utf-16le 解）
        for enc, s in tried:
            if 'le' in enc:
                return s
        return tried[0][1]

    # 如果什么都没有（极小概率），直接使用 replace 解码
    try:
        return data.decode('utf-16le', errors='replace')
    except Exception:
        return ''.join(chr(b) for b in data)


def _patched_init_org_manifest(self):
    ANDROID_MANIFEST = "AndroidManifest.xml"
    try:
        with apkfile.ZipFile(self.apk_path, mode="r") as zf:
            if ANDROID_MANIFEST in zf.namelist():
                data = zf.read(ANDROID_MANIFEST)
                try:
                    axml = AXML(data)
                    if axml.is_valid:
                        self.org_manifest = axml.get_xml()
                        self.org_manifest = clean_manifest(self.org_manifest)
                except Exception as e:
                    raise e
    except Exception as e:
        raise e


_patched = False


def patch():
    global _patched
    if _patched:
        return

    APK._init_org_manifest = _patched_init_org_manifest
    StringPoolChunk.decode_bytes = _patched_decode_bytes

    _patched = True
