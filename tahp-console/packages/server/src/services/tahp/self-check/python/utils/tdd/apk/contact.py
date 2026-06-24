import subprocess
import time
from typing import Optional, Union

from utils.tdd.apk.get_result import wait_test_result

PACKAGE = "com.android.transsion.tdd.autotest"
CONTACT_ACTIVITY = f"{PACKAGE}/.contacts.ContactActivity"

OperationInput = Union[str]
StorageInput = Union[str, int]


def _run_adb(device_id: str, args: list[str], timeout: int = 30):
    cmd = ["adb", "-s", device_id, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _normalize_operation(operation: OperationInput) -> Optional[str]:
    """归一化为 ContactActivity 接受的 operation：add / query / update / delete。"""
    if operation is None:
        return None
    value = str(operation).strip().lower()
    mapping = {
        "add": "add",
        "insert": "add",
        "create": "add",
        "新增": "add",
        "添加": "add",
        "query": "query",
        "check": "query",
        "find": "query",
        "查询": "query",
        "查找": "query",
        "update": "update",
        "modify": "update",
        "edit": "update",
        "更新": "update",
        "修改": "update",
        "delete": "delete",
        "remove": "delete",
        "del": "delete",
        "删除": "delete",
    }
    return mapping.get(value)


def _normalize_storage(storage: StorageInput) -> Optional[str]:
    """归一化为 ContactActivity 接受的 storage：phone / sim1 / sim2。"""
    if storage is None:
        return None
    value = str(storage).strip().lower()
    mapping = {
        "phone": "phone",
        "device": "phone",
        "local": "phone",
        "手机": "phone",
        "本机": "phone",
        "0": "phone",
        "sim1": "sim1",
        "card1": "sim1",
        "slot0": "sim1",
        "slot_0": "sim1",
        "卡1": "sim1",
        "sim_1": "sim1",
        "1": "sim1",
        "sim2": "sim2",
        "card2": "sim2",
        "slot1": "sim2",
        "slot_1": "sim2",
        "卡2": "sim2",
        "sim_2": "sim2",
        "2": "sim2",
    }
    return mapping.get(value)


def _validate_contact_args(
    operation: str,
    contact_number: str,
    contact_name: str,
    *,
    new_contact_name: str = "",
    new_contact_number: str = "",
) -> bool:
    if not contact_number:
        return False
    if operation == "delete":
        return True
    if operation == "update":
        if not contact_name:
            return False
        return bool(new_contact_name or new_contact_number)
    return bool(contact_name)


def start_contact_test(
    device_id: str,
    operation: OperationInput,
    storage: StorageInput,
    contact_number: str,
    contact_name: str = "",
    *,
    new_contact_name: str = "",
    new_contact_number: str = "",
) -> bool:
    """
    调起测试 APK 的 ContactActivity，执行联系人 CRUD。

    参数:
        device_id: 设备 adb 序列号
        operation: add / query / update / delete
        storage: phone / sim1 / sim2
        contact_number: 电话号码（匹配/写入用）
        contact_name: 联系人姓名；delete 时可省略
        new_contact_name: update 时的新姓名（可选）
        new_contact_number: update 时的新号码（可选）

    返回:
        界面拉起成功为 True，否则 False。
    """
    if not device_id:
        return False

    op = _normalize_operation(operation)
    loc = _normalize_storage(storage)
    number = str(contact_number or "").strip()
    name = str(contact_name or "").strip()
    new_name = str(new_contact_name or "").strip()
    new_number = str(new_contact_number or "").strip()
    if not op or not loc:
        return False
    if not _validate_contact_args(
        op,
        number,
        name,
        new_contact_name=new_name,
        new_contact_number=new_number,
    ):
        return False

    _run_adb(device_id, ["shell", "am", "force-stop", PACKAGE], timeout=15)
    time.sleep(0.3)

    args = [
        "shell",
        "am",
        "start",
        "-W",
        "-n",
        CONTACT_ACTIVITY,
        "--es",
        "operation",
        op,
        "--es",
        "storage",
        loc,
        "--es",
        "contact_number",
        number,
    ]
    if name:
        args.extend(["--es", "contact_name", name])
    if op == "update":
        if new_name:
            args.extend(["--es", "new_contact_name", new_name])
        if new_number:
            args.extend(["--es", "new_contact_number", new_number])

    result = _run_adb(device_id, args, timeout=30)
    output = f"{result.stdout or ''}\n{result.stderr or ''}"
    if result.returncode != 0 or "Error" in output or "Exception" in output:
        return False
    return True


def run_contact_test(
    device_id: str,
    operation: OperationInput,
    storage: StorageInput,
    contact_number: str,
    contact_name: str = "",
    *,
    new_contact_name: str = "",
    new_contact_number: str = "",
) -> bool:
    """
    调起联系人测试并轮询 Pass/Fail 结果页。

    返回:
        PassActivity 为 True，FailActivity 或拉起失败/超时为 False。
    """
    if not start_contact_test(
        device_id,
        operation,
        storage,
        contact_number,
        contact_name=contact_name,
        new_contact_name=new_contact_name,
        new_contact_number=new_contact_number,
    ):
        return False
    return wait_test_result(device_id)


def add_contact(
    device_id: str,
    storage: StorageInput,
    contact_name: str,
    contact_number: str,
) -> bool:
    """新增联系人并校验是否成功。"""
    return run_contact_test(
        device_id,
        "add",
        storage,
        contact_number,
        contact_name=contact_name,
    )


def query_contact(
    device_id: str,
    storage: StorageInput,
    contact_name: str,
    contact_number: str,
) -> bool:
    """
    查询联系人是否存在（仅反映 APK 查询结果）。

    返回:
        查到（PassActivity）为 True；
        未查到（FailActivity）、拉起失败或超时为 False。
    """
    return run_contact_test(
        device_id,
        "query",
        storage,
        contact_number,
        contact_name=contact_name,
    )


def update_contact(
    device_id: str,
    storage: StorageInput,
    contact_name: str,
    contact_number: str,
    *,
    new_contact_name: str = "",
    new_contact_number: str = "",
) -> bool:
    """
    更新联系人（按姓名+号码匹配；SIM 卡按 recordNumber 更新）。

    new_contact_name / new_contact_number 至少传一个。
    """
    return run_contact_test(
        device_id,
        "update",
        storage,
        contact_number,
        contact_name=contact_name,
        new_contact_name=new_contact_name,
        new_contact_number=new_contact_number,
    )


def delete_contact(
    device_id: str,
    storage: StorageInput,
    contact_number: str,
    contact_name: str = "",
) -> bool:
    """删除指定联系人（按号码+位置；SIM 卡按匹配到的 recordNumber 删除）。"""
    return run_contact_test(
        device_id,
        "delete",
        storage,
        contact_number,
        contact_name=contact_name,
    )
