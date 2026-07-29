import os
import shutil
import xml.etree.ElementTree as ET


def setup_idea_directory(project_root):
    """
    检查项目根目录下是否存在 .idea 目录，
    如果不存在则创建，并拷贝模板文件；
    如果存在且存在 tpytest.iml 文件，则进行 XML 检查与修改。
    """
    proj_name = os.path.basename(project_root)
    idea_dir = os.path.join(project_root, ".idea")

    def _process_templates():
        templates_dir = os.path.join(project_root, 'assets', 'res_core', 'tpytest', "templates")
        modules_src = os.path.join(templates_dir, "modules.xml")
        modules_dst = os.path.join(idea_dir, "modules.xml")
        with open(modules_src, 'r', encoding='utf-8') as file:
            content = file.read()
        content = content.replace('tpytest', proj_name)
        with open(modules_dst, 'w', encoding='utf-8') as file:
            file.write(content)
        tpytest_iml_src = os.path.join(templates_dir, "tpytest.iml")
        tpytest_iml_dst = os.path.join(idea_dir, f"{proj_name}.iml")
        shutil.copy(tpytest_iml_src, tpytest_iml_dst)

    if os.path.exists(idea_dir) and os.path.exists(os.path.join(idea_dir, 'modules.xml')):
        print(f"检测到 .idea 目录：{idea_dir}")
        iml_path = ''
        for entry in os.scandir(idea_dir):
            if entry.is_file() and entry.name.endswith('.iml'):
                iml_path = os.path.join(idea_dir, entry.name)
        if iml_path:
            modify_iml_file(iml_path)
        else:
            _process_templates()
    else:
        print(f".idea 目录不存在或modules.xml不存在，正在创建：{idea_dir}")
        os.makedirs(idea_dir, exist_ok=True)
        _process_templates()


def modify_iml_file(iml_path):
    """
    解析 iml 文件，检查 <module>/<component>/<content> 节点下是否已经存在
    <sourceFolder url="file://$MODULE_DIR$/plugins" isTestSource="false" />，
    如果不存在则添加该节点。
    """
    try:
        tree = ET.parse(iml_path)
        root = tree.getroot()
    except Exception as e:
        print(f"解析 {iml_path} 出错：{e}")
        return

    # 找到 <content> 节点，通常路径为 <module> -> <component name="NewModuleRootManager"> -> <content>
    content_elem = None
    for component in root.findall("component"):
        content_elem = component.find("content")
        if content_elem is not None:
            break

    if content_elem is None:
        print("未找到 <content> 节点，无法进行修改。")
        return

    # 检查是否已存在目标 sourceFolder 节点
    target_url = "file://$MODULE_DIR$/plugins"
    exists = False
    for sourceFolder in content_elem.findall("sourceFolder"):
        if sourceFolder.attrib.get("url") == target_url and sourceFolder.attrib.get("isTestSource") == "false":
            exists = True
            break

    if exists:
        print("目标 sourceFolder 节点已存在，无需修改。")
    else:
        # 创建新的 sourceFolder 节点并添加到 <content> 下
        new_elem = ET.Element("sourceFolder", {"url": target_url, "isTestSource": "false"})
        content_elem.append(new_elem)
        # 保存修改，注意写入时添加编码和 XML 声明
        tree.write(iml_path, encoding="utf-8", xml_declaration=True)
        print("已添加新的 sourceFolder 节点，并保存到 iml 文件。")


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    setup_idea_directory(project_root)


if __name__ == "__main__":
    main()
