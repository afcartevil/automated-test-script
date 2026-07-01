import copy
from dataclasses import dataclass, field
from typing import List


@dataclass
class CaseOriginalRequest:
    case_id: str = ''
    loop: int = 1
    group_loop: int = 1
    big_loop: int = 1
    retry: int = 0
    whole_class: bool = False
    regex: bool = False
    user_args: dict = field(default_factory=dict)

    case_index: int = 1
    dup_index: int = 1
    loop_index: int = 1
    big_loop_index: int = 1

    def clone_with_indexes(self, case_index: int, dup_index: int, big_loop_index: int, loop_index: int):
        cloned_ins = copy.copy(self)
        cloned_ins.case_index = case_index
        cloned_ins.dup_index = dup_index
        cloned_ins.big_loop_index = big_loop_index
        cloned_ins.loop_index = loop_index
        return cloned_ins

    @classmethod
    def parse(cls, text_line: str, default_small_loop=1, default_retry=0):
        ins = cls()
        ins.parse_from(text_line, default_small_loop, default_retry)
        return ins

    @classmethod
    def parse_lines(cls, text_lines: List[str], default_small_loop=1, default_retry=0):
        ret = []
        for line in text_lines:
            ret.append(cls.parse(line, default_small_loop, default_retry))
        return ret

    @property
    def is_available(self):
        return bool(self.case_id)

    def parse_from(self, text_line: str, default_small_loop=1, default_retry=0):
        text_line = text_line.strip()
        g_pos = 0
        if text_line and text_line[-1] == ')':
            g_pos = text_line.rfind('(')
        if g_pos > 0:
            self.case_id = text_line[:g_pos].strip()
            self._parse_args(text_line[g_pos + 1:-1])
        else:
            self.case_id = text_line.strip()
            self.loop = max(1, default_small_loop)
            self.group_loop = 1
            self.retry = max(0, default_retry)
            self.whole_class = False
            self.regex = False
            self.user_args.clear()

    def _parse_args(self, args_text: str, default_small_loop=1, default_retry=0):
        self.user_args.clear()
        for s in args_text.split(','):
            sub_s = s.split('=', maxsplit=2)
            self.user_args[sub_s[0].strip()] = sub_s[1].strip()
        self.loop = int(self.user_args.pop('loop', max(1, default_small_loop)))
        self.group_loop = int(self.user_args.pop('group_loop', 1))
        self.retry = int(self.user_args.pop('retry', max(0, default_retry)))
        self.whole_class = bool(self.user_args.pop('class', False))
        self.regex = bool(self.user_args.pop('regex', False))

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
