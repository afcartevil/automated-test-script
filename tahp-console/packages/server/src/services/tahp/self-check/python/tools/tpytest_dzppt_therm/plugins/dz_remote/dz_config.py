import os
from lxml import etree
import shutil

### DONGZHOU CONFIG
# ========== SMC 配置参数 ==========
smc_updates = {
    # 各轴的运行速度
    'x.speed.nomal': '300',
    'y.speed.nomal': '300',
    'z.speed.nomal': '200',
    'a.speed.nomal': '50',
    'b.speed.nomal': '100',
    'normal.speed': '100',

    # 各轴回零速度
    'x.speed.zero': '120',
    'y.speed.zero': '120',
    'z.speed.zero': '120',
    'a.speed.zero': '0',
    'b.speed.zero': '0',
    'speed.zero': '100',

    # 各轴加速时间
    'speed.tacc.x': '0.1',
    'speed.tacc.y': '0.1',
    'speed.tacc.z': '0.01',
    'speed.tacc.a': '0.1',
    'speed.tacc.b': '0.1',
    'speed.tacc.c': '0.1',

    # 各轴减速时间
    'speed.tdec.x': '0.1',
    'speed.tdec.y': '0.1',
    'speed.tdec.z': '0.01',
    'speed.tdec.a': '0.1',
    'speed.tdec.b': '0.1',
    'speed.tdec.c': '0.1',
}
# ========== 曝光参数配置 ==========
camera_updates = {
    "exposure.time.auto": "On",
    "gray.intensity.max": "50",
    "exposure.time.max": "50000",
    "gray.intensity.middle": "90",
    "exposure.time.middle": "30000",
    "gray.intensity.min": "130",
    "exposure.time.min": "20000",
}


def find_config_paths(base_path):
    # 固定子路径
    SMC_CONFIG_PATH = r'Release\Configs\SMC_Config.xml'
    CAMERA_CONFIG_PATH = r'Release\Configs\Camera1_Config.xml'

    # 查找"_RELEASE"并截断
    release_index = base_path.find('_RELEASE')
    if release_index == -1:
        print("没找到路径")
        return None
    else:
        return (os.path.join(base_path[:release_index + len('_RELEASE')], SMC_CONFIG_PATH),
                os.path.join(base_path[:release_index + len('_RELEASE')], CAMERA_CONFIG_PATH))


def update_config(config_path, updates_dict):
    """
    更新 XML 配置文件。
    """
    hehe = 1
    # 检查配置文件是否存在
    if not os.path.isfile(config_path):
        print(f"配置文件不存在：{config_path}")
        return

    # 解析 XML 文件（保留注释）
    parser = etree.XMLParser(remove_blank_text=False)  # 保留格式
    tree = etree.parse(config_path, parser)
    root = tree.getroot()
    modified = False

    # 遍历并更新配置
    for elem in root.findall(".//add"):
        key = elem.get("key")
        if key in updates_dict and elem.get("value") != updates_dict[key]:
            print(f"🛠️ 更新 {key}：{elem.get('value')} → {updates_dict[key]}")
            elem.set("value", updates_dict[key])
            modified = True

    # 写回文件
    if modified:
        # 创建备份文件
        backup_path = config_path + ".bak"
        shutil.copy(config_path, backup_path)
        print(f"已备份原文件到：{backup_path}")

        # 写入更新后的 XML
        tree.write(config_path, encoding='utf-8', xml_declaration=True)
        print(f"配置文件已更新：{config_path}")
    else:
        print("配置文件无需修改")


if __name__ == "__main__":
    print("请输入正在使用的东舟软件路径（例如：D:\DZSOFT\exe\V2.2025.325.1968_RELEASE)")
    user_input = input("路径：").strip('"').strip()
    config_path = 1

    smc_path, cam_path = find_config_paths(user_input)

    if smc_path:
        print(f"\n开始更新 SMC_Config.xml ...")
        update_config(smc_path, smc_updates)

    if cam_path:
        print(f"\n开始更新 Camera1_Config.xml ...")
        update_config(cam_path, camera_updates)