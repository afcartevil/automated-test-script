"""用户可以删除手机联系人和SIM卡联系人。"""

from typing import Optional

from utils.tdd.apk.contact import add_contact, delete_contact, query_contact, update_contact
from utils.tdd.device_sim import get_sim_by_slot, resolve_aux, resolve_dut, sim_phone_number
from test.step_runner import StepRunner

AUX_CONTACT_NAME = "辅测机"
DUT_SIM1_CONTACT_NAME = "测试机卡1"

STORAGE_LABELS = (
    ("phone", "手机"),
    ("sim1", "卡1"),
    ("sim2", "卡2"),
)


def _contact_crud_flow(
    steps: StepRunner,
    dut_id: str,
    storage: str,
    label: str,
    aux_name: str,
    aux_number: str,
    target_name: str,
    target_number: str,
) -> Optional[str]:
    steps.begin(f"{label}存储联系人(名称:{aux_name},号码:{aux_number})")
    if not add_contact(dut_id, storage, aux_name, aux_number):
        steps.fail()
        return f"{label}存储联系人失败"
    steps.ok()

    steps.begin(f"{label}查询联系人(名称:{aux_name},号码:{aux_number})，应能查到")
    if not query_contact(dut_id, storage, aux_name, aux_number):
        steps.fail()
        return f"{label}存储后查询联系人失败"
    steps.ok()

    steps.begin(
        f"{label}修改联系人(名称:{aux_name},号码:{aux_number}"
        f"→名称:{target_name},号码:{target_number})"
    )
    if not update_contact(
        dut_id,
        storage,
        aux_name,
        aux_number,
        new_contact_name=target_name,
        new_contact_number=target_number,
    ):
        steps.fail()
        return f"{label}修改联系人失败"
    steps.ok()

    steps.begin(f"{label}查询联系人(名称:{aux_name},号码:{aux_number})，应不能查到")
    if query_contact(dut_id, storage, aux_name, aux_number):
        steps.fail()
        return f"{label}修改后旧联系人仍能查到"
    steps.ok()

    steps.begin(f"{label}查询联系人(名称:{target_name},号码:{target_number})，应能查到")
    if not query_contact(dut_id, storage, target_name, target_number):
        steps.fail()
        return f"{label}修改后新联系人查询失败"
    steps.ok()

    steps.begin(f"{label}删除联系人(名称:{target_name},号码:{target_number})")
    if not delete_contact(
        dut_id, storage, target_number, contact_name=target_name
    ):
        steps.fail()
        return f"{label}删除联系人失败"
    steps.ok()

    steps.begin(f"{label}查询联系人(名称:{target_name},号码:{target_number})，应不能查到")
    if query_contact(dut_id, storage, target_name, target_number):
        steps.fail()
        return f"{label}删除后联系人仍能查到"
    steps.ok()

    return None


def run(category=None, case_index=None, device_info=None, **context):
    step_update = context.get("step_update")
    device_info = device_info or context.get("device_info") or {}
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return {"status": "fail", "message": dut_id}

    _, aux_number, _, aux_err = resolve_aux(device_info)
    if aux_err:
        return {"status": "fail", "message": aux_err}

    sim_cards = dut.get("sim_cards") or []
    sim1 = get_sim_by_slot(sim_cards, 0)
    sim2 = get_sim_by_slot(sim_cards, 1)
    sim1_number = sim_phone_number(sim1)
    if not sim1_number:
        return {"status": "fail", "message": "测试机卡1无可用号码"}
    if not sim2:
        return {"status": "fail", "message": "测试机非双卡，无法执行卡1/卡2联系人用例"}

    steps = StepRunner(step_update)
    for storage, label in STORAGE_LABELS:
        err = _contact_crud_flow(
            steps,
            dut_id,
            storage,
            label,
            AUX_CONTACT_NAME,
            aux_number,
            DUT_SIM1_CONTACT_NAME,
            sim1_number,
        )
        if err:
            return {"status": "fail", "message": err}

    return {
        "status": "pass",
        "message": "手机、卡1、卡2联系人增改删查流程通过",
    }
