from typing import List, Optional

from powertrde.utils import string_utils, algorithm_utils


class TextFilter:
    default_split_patterns = ['\n', ';', ',', '，']

    def __init__(self):
        self.allow_pattern_list: List[str] = []
        self.disallow_pattern_list: List[str] = []

    def parse_patterns_from_str(self, allow_pattern_string: Optional[str], disallow_pattern_string: Optional[str],
                                split_patterns: Optional[str] = None):
        if not split_patterns:
            split_patterns = self.default_split_patterns
        self.allow_pattern_list.clear()
        if allow_pattern_string:
            splits = string_utils.split_text_by_symbols(allow_pattern_string, split_patterns, True, True)
            self.allow_pattern_list.extend(splits)

        self.disallow_pattern_list.clear()
        if disallow_pattern_string:
            splits = string_utils.split_text_by_symbols(disallow_pattern_string, split_patterns, True, True)
            self.disallow_pattern_list.extend(splits)

    def is_text_allowed(self, text: str) -> bool:
        is_allowed = False
        if not self.allow_pattern_list:
            is_allowed = True
        else:
            for pattern in self.allow_pattern_list:
                if algorithm_utils.simple_line_match(text, pattern):
                    is_allowed = True
                    break
        if not is_allowed:
            return False
        if self.disallow_pattern_list:
            for pattern in self.disallow_pattern_list:
                if algorithm_utils.simple_line_match(text, pattern):
                    return False
        return is_allowed

    def is_all_texts_allowed(self, texts: List[str]) -> bool:
        for text in texts:
            if not self.is_text_allowed(text):
                return False
        return True

    def to_dict(self):
        return {
            "allow_pattern_list": self.allow_pattern_list,
            "disallow_pattern_list": self.disallow_pattern_list
        }
