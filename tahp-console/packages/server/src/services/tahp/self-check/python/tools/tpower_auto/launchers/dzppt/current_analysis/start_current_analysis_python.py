import sys
import os
import io

# 设置无缓冲的标准输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, 
                             encoding='utf-8',
                             line_buffering=True)  # 添加行缓冲

def add_path_to_python_env():
    if getattr(sys, 'frozen', False):
        return
    root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    #plugins_path = os.path.join(root_path, 'plugins')
    #if os.path.exists(plugins_path):
    #    sys.path.insert(0, plugins_path)

if __name__ == '__main__':
    add_path_to_python_env()
    from powertrde.env import PROJ_DIR
    os.chdir(PROJ_DIR)
    import threading
    from tests.current_analysis.task_proc import task_proc_thread
    thread = threading.Thread(target=task_proc_thread)
    thread.daemon = True
    thread.start()
    try:
        print("Press (Ctrl+C)/(q+Enter) to exit")
        while True:
            if input("").strip().lower() == "q":  # 添加strip()和lower()处理
                print("Exit current analysis by user input")
                break
    except KeyboardInterrupt:  # 添加Ctrl+C退出支持 
        print("Exit current analysis by Ctrl+C")
    
    """
    # 读取本地excel
    from powertrde.utils.excel_utils import read_xlsx_rows

    file_path = "./assets/current_analysis/task_current_annalysis.xlsx"
    result_dict = read_xlsx_rows(file_path, 2)
    print(result_dict)
    """
    """
    # 读取yaml
    from powertrde.utils.yaml_utils import read_yaml

    result_dict = read_yaml("./config/current_analysis/base_config.yaml")
    print(result_dict)
    """
    #watchdog_entry.main()