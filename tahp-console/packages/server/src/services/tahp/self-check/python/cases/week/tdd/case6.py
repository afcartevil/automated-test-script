from typing import Optional

from utils.tdd.apk.contact import add_contact, delete_contact, query_contact, update_contact
from utils.tdd.device_sim import (
    dut_storage_key,
    resolve_aux,
    resolve_dut_active,
    sim_slot_label,
)
from utils.tdd.ui_sim_pin import reboot_and_unlock
from test.step_runner import StepRunner

CONTACT_NAME = "SIM测试联系人"
CONTACT_NAME_EDITED = "SIM测试联系人改"


def _query_contact(
    steps: StepRunner,
    dut_id: str,
    storage: str,
    slot_label: str,
    contact_name: str,
    contact_number: str,
    *,
    expect_found: bool,
    fail_message: str,
) -> Optional[str]:
    expect_text = "应能查到" if expect_found else "应不能查到"
    steps.begin(
        f"{slot_label}查询联系人(名称:{contact_name},号码:{contact_number})，{expect_text}"
    )
    found = query_contact(dut_id, storage, contact_name, contact_number)
    if found != expect_found:
        steps.fail()
        return fail_message
    steps.ok()
    return None


def _reboot(steps: StepRunner, dut_id: str) -> Optional[str]:
    steps.begin("重启手机")
    if not reboot_and_unlock(dut_id):
        steps.fail()
        return "重启手机失败"
    steps.ok()
    return None


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}

    _, dut_id, _, slot_index, _, sim_err = resolve_dut_active(device_info)
    if sim_err:
        return {"status": "fail", "message": sim_err}

    _, aux_number, _, aux_err = resolve_aux(device_info)
    if aux_err:
        return {"status": "fail", "message": aux_err}

    storage = dut_storage_key(slot_index)
    slot_label = sim_slot_label(slot_index)
    steps = StepRunner(step_update)

    steps.begin(f"{slot_label}新增联系人(名称:{CONTACT_NAME},号码:{aux_number})")
    if not add_contact(dut_id, storage, CONTACT_NAME, aux_number):
        steps.fail()
        return {"status": "fail", "message": f"{slot_label}新增联系人失败"}
    steps.ok()

    err = _query_contact(
        steps,
        dut_id,
        storage,
        slot_label,
        CONTACT_NAME,
        aux_number,
        expect_found=True,
        fail_message=f"{slot_label}应能查到新建联系人",
    )
    if err:
        return {"status": "fail", "message": err}

    steps.begin(
        f"{slot_label}修改联系人(名称:{CONTACT_NAME},号码:{aux_number}"
        f"→名称:{CONTACT_NAME_EDITED},号码:{aux_number})"
    )
    if not update_contact(
        dut_id,
        storage,
        CONTACT_NAME,
        aux_number,
        new_contact_name=CONTACT_NAME_EDITED,
        new_contact_number=aux_number,
    ):
        steps.fail()
        return {"status": "fail", "message": f"{slot_label}修改联系人失败"}
    steps.ok()

    err = _query_contact(
        steps,
        dut_id,
        storage,
        slot_label,
        CONTACT_NAME,
        aux_number,
        expect_found=False,
        fail_message=f"{slot_label}修改后不应再查到旧名称联系人",
    )
    if err:
        return {"status": "fail", "message": err}

    err = _query_contact(
        steps,
        dut_id,
        storage,
        slot_label,
        CONTACT_NAME_EDITED,
        aux_number,
        expect_found=True,
        fail_message=f"{slot_label}修改后应能查到新名称联系人",
    )
    if err:
        return {"status": "fail", "message": err}

    err = _reboot(steps, dut_id)
    if err:
        return {"status": "fail", "message": err}

    err = _query_contact(
        steps,
        dut_id,
        storage,
        slot_label,
        CONTACT_NAME_EDITED,
        aux_number,
        expect_found=True,
        fail_message=f"重启后{slot_label}应能查到联系人",
    )
    if err:
        return {"status": "fail", "message": err}

    steps.begin(f"{slot_label}删除联系人(名称:{CONTACT_NAME_EDITED},号码:{aux_number})")
    if not delete_contact(
        dut_id, storage, aux_number, contact_name=CONTACT_NAME_EDITED
    ):
        steps.fail()
        return {"status": "fail", "message": f"{slot_label}删除联系人失败"}
    steps.ok()

    err = _query_contact(
        steps,
        dut_id,
        storage,
        slot_label,
        CONTACT_NAME_EDITED,
        aux_number,
        expect_found=False,
        fail_message=f"删除后{slot_label}不应查到联系人",
    )
    if err:
        return {"status": "fail", "message": err}

    err = _reboot(steps, dut_id)
    if err:
        return {"status": "fail", "message": err}

    err = _query_contact(
        steps,
        dut_id,
        storage,
        slot_label,
        CONTACT_NAME_EDITED,
        aux_number,
        expect_found=False,
        fail_message=f"二次重启后{slot_label}不应查到已删除联系人",
    )
    if err:
        return {"status": "fail", "message": err}

    return {
        "status": "pass",
        "message": f"单卡 {slot_label} SIM 联系人新增、修改、重启持久化与删除验证通过",
    }
