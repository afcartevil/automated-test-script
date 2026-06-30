import json


def load_json(json_file):
    try:
        with open(json_file, "r", encoding="UTF-8") as pmsf:
            pmsf_info = json.load(pmsf)
    except FileNotFoundError:
        print(f"File '{json_file}' not found.")
        return None
    return pmsf_info
