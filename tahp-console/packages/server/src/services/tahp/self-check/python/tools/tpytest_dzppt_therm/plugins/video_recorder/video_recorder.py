import mmap
import sys
import time
import cv2
import os
import win32event
import win32api
import winerror

MUTEX_EVENT_NAME = "Global\\VideoRecorder_V3_20250903"

from datetime import datetime

def convert_value(value):
    """
    根据输入类型转换值：如果是 int，则转为字符串；
    如果是字符串，则转为 int 并在长度小于 7 时在前面补 0。
    """
    if isinstance(value, int):
        # 将整数转换为字符串
        if value>9999999 or value<0:
            value = 9999999
        value = str(value)
        if len(value) < 7:
            value = value.zfill(7)
        return value
    elif isinstance(value, str):
        # 确保输入字符串是数字字符串
        if value.isdigit():
            # 在字符串的前面补0，确保总长度至少为7
            if len(value) < 8:
                value = value.zfill(7)
            else:
                value = 9999999
            return int(value)
        else:
            raise ValueError("Input string must represent a valid integer.")
    else:
        raise ValueError("Input must be either an integer or a string.")


class CameraMonitor:
    def __init__(self, save_path, segment_duration=60*60, close_delay_time=30*60):
        path_len = str(len(save_path.encode("utf-8"))).zfill(3)
        size = 1024  # 定义共享内存的大小
        self.shm = mmap.mmap(-1, size, tagname='transsion_video_shared_memory')
        self.shm.seek(0)
        self.cur_data = f"{str(int(time.time()))}"
        self.shm.write(self.cur_data.encode('utf-8'))

        self.save_path = save_path
        self.segment_duration = segment_duration  # in seconds
        self.cap = None
        self.is_recording = False
        self.current_time_for_delay_close = datetime.now()
        self.close_delay_time = close_delay_time
        self.split_flag_checked = False  # 用于记录是否已经检查过分割标志

    def _get_output_filename(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.save_path, f"recording_{timestamp}.avi")

    def start_recording(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():#没有插入摄像头
            print("未检测到摄像头")
            return
        self.cap.set(cv2.CAP_PROP_EXPOSURE, -15)

        if not os.path.exists(self.save_path):
            os.makedirs(self.save_path)

        # 设置帧率为 5 FPS
        frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = 10
        print(self._get_output_filename())
        out = cv2.VideoWriter(self._get_output_filename(),
                              cv2.VideoWriter_fourcc('X', 'V', 'I', 'D'),
                              fps,  # 设置为 5 FPS
                              (frame_width, frame_height))

        start_time = datetime.now()
        self.is_recording = True
        frame_count = 0

        # 计算每帧的时间间隔（秒）
        frame_interval = 1.0 / fps  # 0.2 秒

        while self.is_recording:
            ret, frame = self.cap.read()
            if not ret:
                break

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # cv2.putText(frame, timestamp, (10, frame_height - 10),
            #             cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, timestamp, (10, frame_height - 30),  # Y坐标上移
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0,  # 字体大小从0.5→1.0
                        (0, 0, 255), 2)  # 白色→红色，线宽1→2

            # 计算当前时间与上一帧的时间差
            current_time = datetime.now()
            elapsed_time = (current_time - start_time).total_seconds()

            # 如果达到帧间隔时间，写入帧
            if elapsed_time >= frame_count * frame_interval:
                out.write(frame)
                frame_count += 1

            # 检查录制时长
            if elapsed_time >= self.segment_duration:
                out.release()
                out = cv2.VideoWriter(self._get_output_filename(),
                                      cv2.VideoWriter_fourcc('X', 'V', 'I', 'D'),
                                      fps,  # 设置为 5 FPS
                                      (frame_width, frame_height))
                start_time = datetime.now()
                frame_count = 0
                print(f"[自动分割] 达到时长限制，已创建新视频文件")

            # 显示帧
            cv2.imshow('Camera Monitor', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            # 添加窗口状态检测,可以右上角叉叉关闭窗口
            if cv2.getWindowProperty('Camera Monitor', cv2.WND_PROP_VISIBLE) < 1:
                self.stop_recording()
                break

            self.shm.seek(0)
            # 读取数据
            data = self.shm.read(10)
            d = data.decode('utf-8').strip() # 格式：1738922982#1234567
            
            # 检查分割标志位（位置 500）
            self.shm.seek(500)
            split_flag_data = self.shm.read(1)
            split_flag = split_flag_data.decode('utf-8').strip()
            
            if split_flag == '1' and not self.split_flag_checked:
                # 检测到分割信号，立即分割视频
                print(f"[主动分割] 收到分割指令，开始分割视频...")
                out.release()
                out = cv2.VideoWriter(self._get_output_filename(),
                                      cv2.VideoWriter_fourcc('X', 'V', 'I', 'D'),
                                      fps,
                                      (frame_width, frame_height))
                start_time = datetime.now()
                frame_count = 0
                
                # 清除分割标志
                self.shm.seek(500)
                self.shm.write(b'0')
                self.split_flag_checked = True
                print(f"[主动分割] 已创建新视频文件")
            elif split_flag != '1':
                # 重置检查标志，以便下次可以再次响应
                self.split_flag_checked = False
            
            if self.cur_data != d: #如果时间有更新
                print(f"当前:d{d},self.cur_data:{self.cur_data}")
                self.current_time_for_delay_close = datetime.now()

                self.shm.seek(11)
                data = self.shm.read(7) #读取新时间
                self.close_delay_time = convert_value(data.decode('utf-8').strip())
                print(self.close_delay_time)

                self.shm.seek(19)
                data = self.shm.read(3) #从19开始，读取三位表示save_path的长度
                save_path_len = int(data.decode('utf-8').strip())
                print(save_path_len)

                self.shm.seek(23)
                data = self.shm.read(save_path_len) #从23开始，读取三位表示save_path的长度
                if self.save_path != data.decode('utf-8').strip(): # 如果路径更改了
                    if data.decode('utf-8').strip() == 'stop':
                        self.stop_recording()
                        break
                    self.save_path = data.decode('utf-8').strip()
                    if not os.path.exists(self.save_path):
                        os.makedirs(self.save_path)
                    out.release()
                    out = cv2.VideoWriter(self._get_output_filename(),
                                          cv2.VideoWriter_fourcc('X', 'V', 'I', 'D'),
                                          fps,  # 设置为 5 FPS
                                          (frame_width, frame_height))
                    start_time = datetime.now()
                    frame_count = 0
                    print(self.save_path)

                # self.cur_data = f"{str(int(time.time()))}"
                self.cur_data = d
            if (datetime.now() - self.current_time_for_delay_close).total_seconds() >= self.close_delay_time:
                self.stop_recording()

        out.release()
        print(f"Total frames written: {frame_count}")
        print(f"Expected frames: {fps * self.segment_duration}")

    def stop_recording(self):
        self.is_recording = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()

def write_data(save_path, close_delay_time):
    path_len = str(len(save_path.encode("utf-8"))).zfill(3)
    size = 1024  # 定义共享内存的大小
    shm = mmap.mmap(-1, size, tagname='transsion_video_shared_memory')
    shm.seek(0)
    new_data = f"{int(time.time())}#{convert_value(close_delay_time)}#{path_len}#{save_path}"
    shm.write(new_data.encode('utf-8'))
    shm.close()


def start_server(save_path, close_delay_time) -> bool:
    server_event = None
    try:
        server_event = win32event.OpenEvent(win32event.SYNCHRONIZE, False, MUTEX_EVENT_NAME)
    except:
        pass
    if server_event:
        # 存在服务器，直接结束
        win32api.CloseHandle(server_event)
        print("服务器正在运行中，不再重复运行！已经更新数据")
        write_data(save_path, close_delay_time)
        return True
    server_event = win32event.CreateEvent(None, True, False, MUTEX_EVENT_NAME)
    last_error = win32api.GetLastError()
    if last_error == winerror.ERROR_ALREADY_EXISTS:
        if server_event:
            # 存在服务器，直接结束
            win32api.CloseHandle(server_event)
            print("服务器正在运行中，不再重复运行！已经更新数据")
            write_data(save_path, close_delay_time)
        return True
    if save_path == 'stop': # 如果程序没有启动，并且传参为stop，则直接结束
        return True
    monitor = CameraMonitor(save_path=save_path, close_delay_time=close_delay_time)
    monitor.start_recording()


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python your_script.py param1 param2")
        sys.exit(1)
    save_path = sys.argv[1]
    close_delay_time = sys.argv[2]
    start_server(save_path, int(close_delay_time))



