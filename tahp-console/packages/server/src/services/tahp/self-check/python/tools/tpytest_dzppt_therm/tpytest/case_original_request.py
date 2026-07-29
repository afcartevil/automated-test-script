import copy
from dataclasses import dataclass, field
from typing import List, Dict, Set, Any


@dataclass
class CaseOriginalRequest:
    case_id: str = ''
    loop: int = 1
    group_loop: int = 1
    big_loop: int = 1
    retry: int = 0
    timeout: int = 0
    whole_class: bool = False
    is_group: bool = False
    regex: bool = False
    user_args: dict = field(default_factory=dict)

    case_index: int = 1
    dup_index: int = 1
    loop_index: int = 1
    group_loop_index: int = 1
    big_loop_index: int = 1

    overwrite_properties: Set[str] = field(default_factory=set)

    def clone_with_indexes(self, case_index: int, dup_index: int, big_loop_index: int, group_loop_index: int,
                           loop_index: int):
        cloned_ins = copy.copy(self)
        cloned_ins.case_index = case_index
        cloned_ins.dup_index = dup_index
        cloned_ins.big_loop_index = big_loop_index
        cloned_ins.group_loop_index = group_loop_index
        cloned_ins.loop_index = loop_index
        return cloned_ins

    def extract_group(self, request_group_query_pool: Dict[str, List['CaseOriginalRequest']]):
        """解压Group原始用例请求"""
        if self.is_group:
            _cur_group = request_group_query_pool.get(self.case_id)
            assert _cur_group, f'Unable to find a use case group named "{self.case_id}" from Request Group Query Pool.'
            # 递归解压
            _overwrite_property_kv_dict = self._gen_overwrite_property_kv_dict()
            for item in _cur_group:
                _cloned_item = item._try_overwrite_property_clone(_overwrite_property_kv_dict)
                for item2 in _cloned_item._sub_extract_group(request_group_query_pool):
                    yield item2
        else:
            yield self

    def _sub_extract_group(self, request_group_query_pool: Dict[str, List['CaseOriginalRequest']]):
        if self.is_group:
            _cur_group = request_group_query_pool.get(self.case_id)
            assert _cur_group, f'Unable to find a use case group named "{self.case_id}" from Request Group Query Pool.'
            # 递归解压（并排布group_loop信息）
            _overwrite_property_kv_dict = self._gen_overwrite_property_kv_dict()
            for _g in range(self.group_loop):
                for item in _cur_group:
                    _cloned_item = item._try_overwrite_property_clone(_overwrite_property_kv_dict)
                    for item2 in _cloned_item._sub_extract_group(request_group_query_pool):
                        yield item2
        else:
            yield self

    def _gen_overwrite_property_kv_dict(self):
        ret = {}
        for k in self.overwrite_properties:
            ret[k] = getattr(self, k)
        return ret

    def _try_overwrite_property_clone(self, property_kv_dict: Dict[str, Any]):
        if property_kv_dict:
            _property_kv_dict = property_kv_dict.copy()
            for k in property_kv_dict:
                if k in self.overwrite_properties:
                    del _property_kv_dict[k]

            if _property_kv_dict:
                cloned_ins = copy.copy(self)
                cloned_ins.overwrite_properties = self.overwrite_properties.copy()
                for k, v in _property_kv_dict.items():
                    setattr(cloned_ins, k, v)
                    cloned_ins.overwrite_properties.add(k)
                return cloned_ins
        return self

    @classmethod
    def parse(cls, text_line: str, default_small_loop=1, default_retry=0, default_timeout=0):
        ins = cls()
        ins.parse_from(text_line, default_small_loop, default_retry, default_timeout)
        return ins

    @classmethod
    def parse_lines(cls, text_lines: List[str], default_small_loop=1, default_retry=0, default_timeout=0):
        ret = []
        for line in text_lines:
            ret.append(cls.parse(line, default_small_loop, default_retry, default_timeout))
        return ret

    @property
    def is_available(self):
        return bool(self.case_id)

    def parse_from(self, text_line: str, default_small_loop=1, default_retry=0, default_timeout=0):
        text_line = text_line.strip()
        g_pos = 0
        self.is_group = bool(text_line.startswith('case_group'))
        if text_line and text_line[-1] == ')':
            g_pos = text_line.rfind('(')
        if g_pos > 0:
            self.case_id = text_line[:g_pos].strip()
            self._parse_args(text_line[g_pos + 1:-1], default_small_loop, default_retry, default_timeout)
        else:
            self.case_id = text_line.strip()
            self.loop = max(1, default_small_loop)
            self.group_loop = 1
            self.retry = max(0, default_retry)
            self.timeout = max(0, default_timeout)
            self.whole_class = False
            self.regex = False
            self.user_args.clear()

    def _parse_args(self, args_text: str, default_small_loop, default_retry, default_timeout):
        self.user_args.clear()
        for s in args_text.split(','):
            sub_s = s.split('=', maxsplit=2)
            self.user_args[sub_s[0].strip()] = sub_s[1].strip()
        if 'loop' in self.user_args:
            self.loop = int(self.user_args.pop('loop'))
            self.overwrite_properties.add('loop')
        else:
            self.loop = max(1, default_small_loop)

        if 'retry' in self.user_args:
            self.retry = int(self.user_args.pop('retry'))
            self.overwrite_properties.add('retry')
        else:
            self.retry = max(0, default_retry)

        if 'timeout' in self.user_args:
            self.timeout = int(self.user_args.pop('timeout'))
            self.overwrite_properties.add('timeout')
        else:
            self.timeout = max(0, default_timeout)

        self.group_loop = int(self.user_args.pop('group_loop', 1))
        self.whole_class = bool(self.user_args.pop('class', False))
        self.regex = bool(self.user_args.pop('regex', False))

    def is_overwrite_property(self, property_name: str):
        return property_name in self.overwrite_properties

    @property
    def is_first_small_loop(self):
        return self.loop_index <= 1

    @property
    def is_last_small_loop(self):
        return self.loop_index >= self.loop

    @property
    def is_first_big_loop(self):
        return self.big_loop_index <= 1

    @property
    def is_last_big_loop(self):
        return self.big_loop_index >= self.big_loop

    @property
    def is_first_group_loop(self):
        return self.group_loop_index <= 1

    @property
    def is_last_group_loop(self):
        return self.group_loop_index >= self.group_loop
