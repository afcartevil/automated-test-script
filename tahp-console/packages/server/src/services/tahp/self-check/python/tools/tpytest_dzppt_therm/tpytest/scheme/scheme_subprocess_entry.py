from powertrde.utils.trde import adb


class SchemeSubprocessEntry:
    option_start_class_path = ''

    @classmethod
    def handle_process_event(cls, process_event):
        # 异步处理事件
        from powertrde.utils.simple_event_center import SimpleEventCenter
        SimpleEventCenter.get_instance().send_event(process_event)

    @classmethod
    def child_process(cls, to_main_queue, to_child_queue, to_child_env_id, scheme_shared_kwargs):
        """子进程发送数据"""

        import os
        import time
        import threading
        from powertrde.utils.simple_event_center import SimpleEventCenter, SimpleEvent

        def _check_child_queue():
            # 异步处理来自to_child_queue的事件
            while True:
                try:
                    if not to_child_queue.empty():
                        process_event = to_child_queue.get()
                        try:
                            cls.handle_process_event(process_event)
                        except Exception as e:
                            from powertrde.framework.tran_logger import t_log
                            t_log.exception(str(e))
                    else:
                        # 如果队列为空，稍微等待以减少CPU占用
                        time.sleep(0.1)
                except:
                    cls.on_subprocess_end(from_forced_interruption=True)
                    os._exit(0)

        check_queue_thread = threading.Thread(target=_check_child_queue)
        check_queue_thread.daemon = True
        check_queue_thread.start()

        def _on_child_dispatch_event(e: SimpleEvent):
            if e.tag == 'cross_process' and e.sender != 'main':
                child_send_event = e.clone_and_reuse('child')
                to_main_queue.put(child_send_event)

        SimpleEventCenter.get_instance().on_dispatch_event = _on_child_dispatch_event
        cls.start_test(to_child_env_id, scheme_shared_kwargs)

    @classmethod
    def start_test(cls, env_id, scheme_shared_kwargs):
        from powertrde import env
        import os

        to_start_class = env.load_class(cls.option_start_class_path)
        assert to_start_class, f'Can not load class path "{cls.option_start_class_path}"!'

        os.chdir(env.PROJ_DIR)
        if env_id:
            env.ENV_ID = env_id
        env.get_scheme_shared_kwargs().update(scheme_shared_kwargs)
        to_start_class.get_instance().start()

    @classmethod
    async def main(cls):
        assert cls.option_start_class_path, 'Class filed "option_start_class_path" must be set in your entry class!'

        from powertrde.utils.simple_event_center import SimpleEventCenter, SimpleEvent
        import multiprocessing
        from multiprocessing import Process
        import asyncio

        from powertrde import env

        # 使用Manager创建一个共享队列
        with multiprocessing.Manager() as manager:
            to_main_queue = manager.Queue()
            to_child_queue = manager.Queue()
            scheme_shared_kwargs = env.get_scheme_shared_kwargs()
            # 不再传递ENV_ID
            to_child_env_id = ''
            # to_child_env_id = env.ENV_ID

            def _on_main_dispatch_event(e: SimpleEvent):
                if e.tag == 'cross_process' and e.sender != 'child':
                    to_child_queue.put(e.clone_and_reuse('main'))

            SimpleEventCenter.get_instance().on_dispatch_event = _on_main_dispatch_event

            # 创建子进程
            process = Process(target=cls.child_process, args=(to_main_queue, to_child_queue, to_child_env_id, scheme_shared_kwargs))
            env.set_user_env_arg('sub_entry_process', process)
            process.daemon = False
            process.start()

            # 异步处理来自to_main_queue的事件
            while process.is_alive() or not to_main_queue.empty():
                if not to_main_queue.empty():
                    process_event = to_main_queue.get()
                    cls.handle_process_event(process_event)
                else:
                    # 如果队列为空，稍微等待以减少CPU占用
                    await asyncio.sleep(0.1)

            process.join()
            await cls.on_subprocess_end_async()

    @classmethod
    async def on_subprocess_end_async(cls):
        # if VideoRecorderHelper.get_instance().is_recording:
        #     with UnclosableWindow('Stopping...', 'Turning off camera recording, please wait...'):
        #         VideoRecorderHelper.get_instance().stop_record(wait_for_stop=True)
        cls.on_subprocess_end(from_forced_interruption=False)

    @classmethod
    def on_subprocess_end(cls, from_forced_interruption: bool):
        from powertrde import env
        adb_devices = adb.adb_devices()
        env_d = env.get_scheme_shared_kwargs_kv('device_id')
        if env_d and env_d != 'none' and env_d in adb_devices:
            adb.set_heads_up_notify_enabled(env_d, True)
            adb.try_stop_exist_detached_perfetto(device_id=env_d)

        try:
            vg = env.load_class('video_recorder.video_recorder_helper.VideoRecorderHelper').get_instance()
            if vg:
                if from_forced_interruption:
                    vg.stop_record(wait_for_stop=False)
                else:
                    from powertrde.utils.window_utils import UnclosableWindow
                    with UnclosableWindow('Stopping...', 'Turning off camera recording, please wait...'):
                        vg.stop_record(wait_for_stop=True)
        except Exception:
            pass
