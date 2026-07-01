import json


def dz_result_to_dict(dz_result: str):
    dz_result = dz_result.replace('\\', '\\\\')
    return json.loads(dz_result)
