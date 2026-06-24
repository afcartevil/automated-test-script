from typing import Optional

from utils.tdd.apk.contact import add_contact, delete_contact, query_contact, update_contact
from utils.tdd.device_sim import get_sim_by_slot, resolve_dut, sim_phone_number
from utils.tdd.ui_sim_pin import reboot_and_unlock
from test.step_runner import StepRunner

SIM1_CONTACT_NAME = "卡1"
SIM2_CONTACT_NAME = "卡2"


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
    dut, dut_id = resolve_dut(device_info)
    if not dut:
        return {"status": "fail", "message": dut_id}

    sim_cards = dut.get("sim_cards") or []
    sim1 = get_sim_by_slot(sim_cards, 0)
    sim2 = get_sim_by_slot(sim_cards, 1)
    if not sim1 or not sim2:
        return {"status": "fail", "message": "测试机非双卡，无法执行 SIM 卡联系人用例"}

    sim1_number = sim_phone_number(sim1)
    sim2_number = sim_phone_number(sim2)
    if not sim1_number or not sim2_number:
        return {"status": "fail", "message": "测试机卡1或卡2无可用号码"}

    steps = StepRunner(step_update)

    steps.begin(f"卡1新增联系人(名称:{SIM2_CONTACT_NAME},号码:{sim2_number})")
    if not add_contact(dut_id, "sim1", SIM2_CONTACT_NAME, sim2_number):
        steps.fail()
        return {"status": "fail", "message": "卡1新增卡2联系人失败"}
    steps.ok()

    steps.begin(f"卡2新增联系人(名称:{SIM1_CONTACT_NAME},号码:{sim1_number})")
    if not add_contact(dut_id, "sim2", SIM1_CONTACT_NAME, sim1_number):
        steps.fail()
        return {"status": "fail", "message": "卡2新增卡1联系人失败"}
    steps.ok()

    for err in (
        _query_contact(
            steps,
            dut_id,
            "sim1",
            "卡1",
            SIM2_CONTACT_NAME,
            sim2_number,
            expect_found=True,
            fail_message="卡1应能查到卡2联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim2",
            "卡2",
            SIM1_CONTACT_NAME,
            sim1_number,
            expect_found=True,
            fail_message="卡2应能查到卡1联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim1",
            "卡1",
            SIM1_CONTACT_NAME,
            sim1_number,
            expect_found=False,
            fail_message="卡1不应查到卡1联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim2",
            "卡2",
            SIM2_CONTACT_NAME,
            sim2_number,
            expect_found=False,
            fail_message="卡2不应查到卡2联系人",
        ),
    ):
        if err:
            return {"status": "fail", "message": err}

    steps.begin(
        f"卡1修改联系人(名称:{SIM2_CONTACT_NAME},号码:{sim2_number}"
        f"→名称:{SIM1_CONTACT_NAME},号码:{sim1_number})"
    )
    if not update_contact(
        dut_id,
        "sim1",
        SIM2_CONTACT_NAME,
        sim2_number,
        new_contact_name=SIM1_CONTACT_NAME,
        new_contact_number=sim1_number,
    ):
        steps.fail()
        return {"status": "fail", "message": "卡1修改联系人失败"}
    steps.ok()

    steps.begin(
        f"卡2修改联系人(名称:{SIM1_CONTACT_NAME},号码:{sim1_number}"
        f"→名称:{SIM2_CONTACT_NAME},号码:{sim2_number})"
    )
    if not update_contact(
        dut_id,
        "sim2",
        SIM1_CONTACT_NAME,
        sim1_number,
        new_contact_name=SIM2_CONTACT_NAME,
        new_contact_number=sim2_number,
    ):
        steps.fail()
        return {"status": "fail", "message": "卡2修改联系人失败"}
    steps.ok()

    for err in (
        _query_contact(
            steps,
            dut_id,
            "sim1",
            "卡1",
            SIM2_CONTACT_NAME,
            sim2_number,
            expect_found=False,
            fail_message="卡1修改后不应再查到卡2联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim2",
            "卡2",
            SIM1_CONTACT_NAME,
            sim1_number,
            expect_found=False,
            fail_message="卡2修改后不应再查到卡1联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim1",
            "卡1",
            SIM1_CONTACT_NAME,
            sim1_number,
            expect_found=True,
            fail_message="卡1修改后应能查到卡1联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim2",
            "卡2",
            SIM2_CONTACT_NAME,
            sim2_number,
            expect_found=True,
            fail_message="卡2修改后应能查到卡2联系人",
        ),
    ):
        if err:
            return {"status": "fail", "message": err}

    err = _reboot(steps, dut_id)
    if err:
        return {"status": "fail", "message": err}

    for err in (
        _query_contact(
            steps,
            dut_id,
            "sim1",
            "卡1",
            SIM2_CONTACT_NAME,
            sim2_number,
            expect_found=False,
            fail_message="重启后卡1不应查到卡2联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim2",
            "卡2",
            SIM1_CONTACT_NAME,
            sim1_number,
            expect_found=False,
            fail_message="重启后卡2不应查到卡1联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim1",
            "卡1",
            SIM1_CONTACT_NAME,
            sim1_number,
            expect_found=True,
            fail_message="重启后卡1应能查到卡1联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim2",
            "卡2",
            SIM2_CONTACT_NAME,
            sim2_number,
            expect_found=True,
            fail_message="重启后卡2应能查到卡2联系人",
        ),
    ):
        if err:
            return {"status": "fail", "message": err}

    steps.begin(f"卡1删除联系人(名称:{SIM1_CONTACT_NAME},号码:{sim1_number})")
    if not delete_contact(
        dut_id, "sim1", sim1_number, contact_name=SIM1_CONTACT_NAME
    ):
        steps.fail()
        return {"status": "fail", "message": "卡1删除联系人失败"}
    steps.ok()

    steps.begin(f"卡2删除联系人(名称:{SIM2_CONTACT_NAME},号码:{sim2_number})")
    if not delete_contact(
        dut_id, "sim2", sim2_number, contact_name=SIM2_CONTACT_NAME
    ):
        steps.fail()
        return {"status": "fail", "message": "卡2删除联系人失败"}
    steps.ok()

    for err in (
        _query_contact(
            steps,
            dut_id,
            "sim1",
            "卡1",
            SIM2_CONTACT_NAME,
            sim2_number,
            expect_found=False,
            fail_message="删除后卡1不应查到卡2联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim2",
            "卡2",
            SIM1_CONTACT_NAME,
            sim1_number,
            expect_found=False,
            fail_message="删除后卡2不应查到卡1联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim1",
            "卡1",
            SIM1_CONTACT_NAME,
            sim1_number,
            expect_found=False,
            fail_message="删除后卡1不应查到卡1联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim2",
            "卡2",
            SIM2_CONTACT_NAME,
            sim2_number,
            expect_found=False,
            fail_message="删除后卡2不应查到卡2联系人",
        ),
    ):
        if err:
            return {"status": "fail", "message": err}

    err = _reboot(steps, dut_id)
    if err:
        return {"status": "fail", "message": err}

    for err in (
        _query_contact(
            steps,
            dut_id,
            "sim1",
            "卡1",
            SIM2_CONTACT_NAME,
            sim2_number,
            expect_found=False,
            fail_message="二次重启后卡1不应查到卡2联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim2",
            "卡2",
            SIM1_CONTACT_NAME,
            sim1_number,
            expect_found=False,
            fail_message="二次重启后卡2不应查到卡1联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim1",
            "卡1",
            SIM1_CONTACT_NAME,
            sim1_number,
            expect_found=False,
            fail_message="二次重启后卡1不应查到卡1联系人",
        ),
        _query_contact(
            steps,
            dut_id,
            "sim2",
            "卡2",
            SIM2_CONTACT_NAME,
            sim2_number,
            expect_found=False,
            fail_message="二次重启后卡2不应查到卡2联系人",
        ),
    ):
        if err:
            return {"status": "fail", "message": err}

    return {
        "status": "pass",
        "message": "SIM卡联系人互增、修改、重启持久化与删除验证通过",
    }
