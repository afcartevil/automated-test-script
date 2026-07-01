from typing import Dict

from tpytest.cases_steps import CasesSteps

_case_groups: Dict[type, CasesSteps] = {}


def get_cs(cg_class: type):
    exist_ins = _case_groups.get(cg_class)
    if not exist_ins:
        exist_ins = cg_class()
        _case_groups[cg_class] = exist_ins
    return exist_ins


def set_cs_none(cg_class: type):
    if cg_class in _case_groups:
        del _case_groups[cg_class]


def clear_cg():
    _case_groups.clear()
