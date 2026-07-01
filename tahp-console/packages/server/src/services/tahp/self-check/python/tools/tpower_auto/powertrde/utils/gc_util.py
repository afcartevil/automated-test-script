import subprocess
import threading
import queue

from powertrde.env import ADB_EXE


def logcat_monitor(result_queue, timeout_event, device_id):
    subprocess.call([ADB_EXE, '-s', f'{device_id}', 'logcat', '-c'])
    process = subprocess.Popen([ADB_EXE, '-s', f'{device_id}', 'logcat'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    while timeout_event.is_set():
        output = process.stdout.readline()
        if output:
            line = output.decode('utf-8').strip()
            # print(f"Logcat Output: {line}")
            if "idle maintenance completed" in line:
                print("检测到：idle maintenance completed")
                result_queue.put("completed")
                break
            elif "gctimeout" in line:
                print("GC超时： timeout detected.")
                result_queue.put("timeout")
                break
            elif "idle maintenance stopped" in line:
                print("检测到：idle maintenance stopped")
                result_queue.put("stopped")
                break

def run_gc_maintenance(device_id):
    result_queue = queue.Queue()
    timeout = 3
    for i in range(3):
        # 创建并启动B线程来监控logcat输出
        timeout_event_completed = threading.Event()
        timeout_event_completed.set()
        monitor_thread = threading.Thread(target=logcat_monitor, args=(result_queue, timeout_event_completed, device_id))
        monitor_thread.start()

        # 主线程执行 sm idle-maint run
        subprocess.call([ADB_EXE, '-s', f'{device_id}', 'shell', 'sm', 'idle-maint', 'run'])
        # 等待B线程的输出结果
        monitor_thread.join(timeout=timeout)
        timeout_event_completed.clear() #清除标记，内部循环停止

        if result_queue.empty():
            print("队列为空，本次循环结束")
            continue
        result = result_queue.get(timeout=3)  # 从队列中获取结果
        if result == "completed":
            timeout_event_stop = threading.Event()
            timeout_event_stop.set()
            # 再次等待检测到idle maintenance stopped
            monitor_thread = threading.Thread(target=logcat_monitor, args=(result_queue, timeout_event_stop, device_id))
            monitor_thread.start()
            # 执行sm idle-maint abort
            subprocess.call([ADB_EXE, '-s', f'{device_id}', 'shell', 'sm', 'idle-maint', 'abort'])

            monitor_thread.join(timeout=timeout)
            timeout_event_stop.clear()  # 清除事件标志以便重新使用
            if result_queue.empty():
                print("队列为空，本次循环结束")
                continue
            stopped_result = result_queue.get(timeout=3)

            if stopped_result == "stopped":
                print("Idle maintenance stopped successfully.")
                return True
        elif result == "timeout":
            print("Retrying due to GC timeout...")

    return False


if __name__ == "__main__":
    res = run_gc_maintenance("1207125414000521")
    print(res)
