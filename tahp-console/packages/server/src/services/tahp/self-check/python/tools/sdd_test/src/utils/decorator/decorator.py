from functools import wraps
import time
import threading


def adb_repeat(max_attempts=3):
    def preserving_decorator(function):
        lock = threading.RLock()

        @wraps(function)
        def wrapped(*args, **kwargs):
            nonlocal lock
            # 检查是否禁用重试
            no_retry = kwargs.pop("no_retry", False)
            if no_retry:
                with lock:
                    return function(*args, **kwargs)

            remain_attempts = max_attempts
            res = None
            while remain_attempts > 0:
                try:
                    with lock:
                        res = function(*args, **kwargs)
                        if res["success"]:
                            return res
                        else:
                            time.sleep(2 ** (max_attempts - remain_attempts))
                            remain_attempts -= 1
                except Exception as e:
                    res["exception_msg"] = "\n".join(str(e))
                    time.sleep(2 ** (max_attempts - remain_attempts))
                    remain_attempts -= 1
            # Handle the case when all attempts fail
            return res

        return wrapped

    return preserving_decorator
