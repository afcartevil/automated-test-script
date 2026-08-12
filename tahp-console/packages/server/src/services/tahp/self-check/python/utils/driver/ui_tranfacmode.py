"""工模自动化：主界面进组、屏幕单项测试、Other 分类单项测试。"""

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from utils.driver.tranfacmode_config import (
    ADAPTER_TITLE_RID_SUFFIX,
    MAIN_MENU_KEYWORDS,
    OTHER_FAIL_TEXT,
    OTHER_GROUP_TAB_RID,
    OTHER_PAGE_MARKERS,
    OTHER_PASS_TEXT,
    OTHER_RESULT_STATUS_RID,
    OTHER_TAB_SWIPE_LEFT_TIMES,
    OTHER_TAB_TEXT,
    SCREEN,
    SCREEN_TOUCH_PANEL_ITEM_KEYWORDS,
    SCREEN_TOUCH_SELF_ITEM_KEYWORDS,
    SENSOR,
    OtherTabItem,
    TranfacGroup,
    VIBRATOR_ITEMS,
)
from utils.driver.tranfacmode_ui import (
    TAP_DELAY,
    adb,
    dump,
    poll_bool,
    poll_value,
    swipe_resource,
    tap_list_item,
    tap_text,
    tap_xml,
    tranfacmode_item_result,
    ui_has_keywords,
)
from utils.tdd.ui_automatic import (
    click_by_match_keywords,
    ensure_screen_on_and_unlocked,
)
from utils.driver.tranfacmode_group_result import FAIL_TEXTS, PASS_TEXTS, get_current_group_results

MAIN_ACTIVITY = (
    "com.transsion.tranfacmode/com.transsion.tranfacmode.entrance.main.MainActivity"
)
PKG = "com.transsion.tranfacmode"
FOREGROUND_CLASS = "foreground.ForegroundActivity"
RID_SEQUENCE_TEST = "com.transsion.tranfacmode:id/sequence_test_btn"
CLICK_KWARGS = {
    "max_scrolls": 2,
    "sleep_after_swipe": 0.35,
    "sleep_after_tap": TAP_DELAY,
    "prefer_cached_ui": True,
}
GROUP_TAB_MAX_SWIPE_ROUNDS = 6
RF_CONFIRM_PARENT_PANEL_RID = "android:id/parentPanel"
RF_CONFIRM_TEXTS = ("确认", "Confirm", "CONFIRM")


def _run_steps(
    on_step: Optional[Callable[[str, bool], None]],
    steps: list[tuple[str, Callable[[], bool], str]],
) -> Optional[dict[str, Any]]:
    for label, action, fail_msg in steps:
        ok = action()
        if on_step:
            on_step(label, ok)
        if not ok:
            return {"status": "fail", "message": fail_msg}
    return None


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _save_result_json(
    result_dir: str | Path | None,
    filename: str,
    data: dict[str, Any],
) -> None:
    if not result_dir:
        return
    try:
        _save_json(Path(result_dir) / filename, data)
    except OSError:
        pass


def go_home(device_id: str) -> bool:
    """返回桌面；防误触场景需连按两次 Home。"""
    for _ in range(3):
        if adb(device_id, "shell", "input", "keyevent", "3").returncode != 0:
            return False
        time.sleep(0.1)
    return True


def close_tranfacmode(device_id: str) -> bool:
    ret = adb(device_id, "shell", "am", "force-stop", PKG)
    if ret.returncode != 0:
        return False
    time.sleep(TAP_DELAY)
    return True


def tranfacmode_prep_steps(
    device_id: str,
) -> list[tuple[str, Callable[[], bool], str]]:
    """工模测试前：亮屏解锁、回桌面并关闭工模应用，避免残留界面影响后续用例。"""
    return [
        (
            "确认屏幕已亮屏并解锁",
            lambda: ensure_screen_on_and_unlocked(device_id),
            "屏幕未亮屏或解锁失败",
        ),
        ("返回桌面", lambda: go_home(device_id), "返回桌面失败"),
        ("关闭工模应用", lambda: close_tranfacmode(device_id), "关闭工模应用失败"),
    ]


def start_main(device_id: str) -> bool:
    out = adb(device_id, "shell", "am", "start", "-n", MAIN_ACTIVITY)
    if out.returncode != 0 or "Error" in f"{out.stdout}{out.stderr}":
        return False

    def ready() -> bool:
        xml = dump(device_id)
        if xml is None:
            return False
        if ui_has_keywords(xml, MAIN_MENU_KEYWORDS):
            return True
        return any(
            "button1" in (n.attrib.get("resource-id") or "")
            for n in ET.parse(xml).getroot().iter("node")
        )

    return poll_bool(ready, 15.0, 0.35)


def _xml_has_resource_id(xml: Path, resource_id: str) -> bool:
    rid_suffix = resource_id.split("/")[-1]
    return any(
        resource_id in (node.attrib.get("resource-id") or "")
        or (node.attrib.get("resource-id") or "").endswith("/" + rid_suffix)
        for node in ET.parse(xml).getroot().iter("node")
    )


def _tap_rf_confirm(device_id: str, xml: Path) -> bool:
    return tap_xml(device_id, xml, text_equals=RF_CONFIRM_TEXTS) or tap_xml(
        device_id, xml, resource_id="android:id/button1"
    )


def skip_rf_calibration(device_id: str) -> bool:
    def step() -> bool:
        xml = dump(device_id)
        if not xml:
            return False

        if _xml_has_resource_id(xml, RF_CONFIRM_PARENT_PANEL_RID):
            if _tap_rf_confirm(device_id, xml):
                time.sleep(TAP_DELAY)
            return False

        if _has_group_tab(xml) or ui_has_keywords(xml, MAIN_MENU_KEYWORDS):
            return True
        return False

    return poll_bool(step, 15.0, 0.35)


def _try_tap_group_tab_labels(
    device_id: str,
    xml: Path,
    labels: tuple[str, ...],
    entry_by: str,
) -> bool:
    primary = (
        {"text_equals": labels} if entry_by == "text" else {"content_desc": labels}
    )
    if tap_xml(device_id, xml, **primary):
        return True
    alternate = (
        {"content_desc": labels} if entry_by == "text" else {"text_equals": labels}
    )
    return tap_xml(device_id, xml, **alternate)


def _find_and_tap_group_tab(
    device_id: str,
    labels: tuple[str, ...],
    entry_by: str = "text",
    *,
    max_swipe_rounds: int = GROUP_TAB_MAX_SWIPE_ROUNDS,
) -> bool:
    """在 group_tab 标签栏横滑查找并点击，不滚动主界面。"""
    if not labels:
        return False
    if not skip_rf_calibration(device_id):
        return False

    def try_tap() -> bool:
        xml = dump(device_id)
        if not xml:
            return False
        return _try_tap_group_tab_labels(device_id, xml, labels, entry_by)

    if try_tap():
        return True

    for _ in range(max_swipe_rounds):
        xml = dump(device_id)
        if not xml:
            return False
        for direction in ("left", "right"):
            if not swipe_resource(
                device_id, xml, OTHER_GROUP_TAB_RID, times=1, direction=direction
            ):
                continue
            time.sleep(TAP_DELAY)
            if try_tap():
                return True
    return False


def tap_group_tab(device_id: str, labels: tuple[str, ...], entry_by: str = "text") -> bool:
    """点击工模 group_tab 标签栏中的分类标签（横滑查找，不滚动主界面）。"""
    return _find_and_tap_group_tab(device_id, labels, entry_by)


def enter_group(device_id: str, group: TranfacGroup) -> bool:
    """在 group_tab 标签栏横滑查找并点击测试组入口，不滚动主界面。"""
    if not group.entry_keywords:
        return False
    return _find_and_tap_group_tab(
        device_id, group.entry_keywords, group.entry_by
    )


def _is_other_tab_page(xml: Path) -> bool:
    return ui_has_keywords(xml, OTHER_PAGE_MARKERS)


def _has_group_tab(xml: Path) -> bool:
    suffix = OTHER_GROUP_TAB_RID.rsplit("/", 1)[-1]
    return any(
        suffix in (node.attrib.get("resource-id") or "")
        for node in ET.parse(xml).getroot().iter("node")
    )


def _ensure_group_tab_visible(device_id: str) -> bool:
    """Other 标签在测试组内顶部栏；主界面需先进入 Sensor 组。"""
    xml = dump(device_id)
    if not xml or _has_group_tab(xml):
        return bool(xml)
    if not enter_group(device_id, SENSOR):
        return False
    time.sleep(TAP_DELAY)
    return poll_bool(
        lambda: (x := dump(device_id)) is not None and _has_group_tab(x),
        5.0,
        0.3,
    )


def _tap_other_tab_label(device_id: str) -> bool:
    """只在顶部标签栏查找并点击「其他/Other」，不触发主界面上下滚动。"""
    xml = dump(device_id)
    if not xml:
        return False
    if tap_xml(device_id, xml, text_equals=OTHER_TAB_TEXT):
        return True
    if tap_xml(device_id, xml, content_desc=OTHER_TAB_TEXT):
        return True
    return tap_group_tab(device_id, OTHER_TAB_TEXT, entry_by="text")


def open_other_tab(device_id: str) -> bool:
    xml = dump(device_id)
    if not xml:
        return False
    if _is_other_tab_page(xml):
        return True
    if not _ensure_group_tab_visible(device_id):
        return False

    if _tap_other_tab_label(device_id):
        time.sleep(TAP_DELAY)
        xml = dump(device_id)
        if xml and _is_other_tab_page(xml):
            return True

    xml = dump(device_id)
    if xml and swipe_resource(
        device_id, xml, OTHER_GROUP_TAB_RID, times=OTHER_TAB_SWIPE_LEFT_TIMES, direction="left"
    ):
        time.sleep(TAP_DELAY)
        if _tap_other_tab_label(device_id):
            time.sleep(TAP_DELAY)
            xml = dump(device_id)
            if xml and _is_other_tab_page(xml):
                return True

    return False


def tap_other_list_item(device_id: str, texts: tuple[str, ...]) -> bool:
    if tap_list_item(device_id, texts, rid_suffix=ADAPTER_TITLE_RID_SUFFIX):
        return True
    return click_by_match_keywords(
        device_id,
        texts,
        max_scrolls=5,
        prefer_cached_ui=False,
    )


def is_foreground_activity_active(device_id: str) -> bool:
    activity = adb(device_id, "shell", "dumpsys", "activity", "activities").stdout or ""
    for line in activity.splitlines():
        if PKG in line and FOREGROUND_CLASS in line and any(
            k in line for k in ("topResumed", "mResumed", "mFocused", "state=RESUMED")
        ):
            return True
    window = adb(device_id, "shell", "dumpsys", "window").stdout or ""
    return PKG in window and FOREGROUND_CLASS in window and "mCurrentFocus" in window


def _group_result_ready(result: dict, group: TranfacGroup) -> bool:
    name = (result.get("group") or "").strip()
    if not any(k in name for k in group.result_keywords):
        return False
    items = result.get("items") or []
    terminal = PASS_TEXTS | FAIL_TEXTS
    return bool(items) and all((i.get("state") or "").strip() in terminal for i in items)


def evaluate_group_results(data: dict[str, Any]) -> tuple[str, str]:
    group = (data.get("group") or "").strip()
    items = data.get("items") or []
    if not items:
        return "fail", f"测试组「{group}」无子项结果"
    if data.get("all_pass"):
        names = "、".join(i.get("name", "") for i in items if i.get("name"))
        return "pass", f"测试组「{group}」全部通过（{len(items)}项）: {names}"
    failed = [i for i in items if (i.get("state") or "").strip() in FAIL_TEXTS]
    if failed:
        detail = "; ".join(f"{i.get('name', '?')}({i.get('state', '')})" for i in failed)
        return "fail", f"测试组「{group}」{len(failed)}项失败: {detail}"
    return "fail", f"测试组「{group}」存在未完成项"


def _item_name_matches(name: str, keywords: tuple[str, ...]) -> bool:
    text = (name or "").strip()
    if not text:
        return False
    lower = text.lower()
    collapsed = lower.replace(" ", "")
    for keyword in keywords:
        kw = (keyword or "").strip().lower()
        if not kw:
            continue
        if kw in lower or kw.replace(" ", "") in collapsed:
            return True
    return False


def _build_group_entry_steps(
    device_id: str,
    group: TranfacGroup,
    page_ready: Callable[[], bool],
) -> list[tuple[str, Callable[[], bool], str]]:
    steps: list[tuple[str, Callable[[], bool], str]] = [
        *tranfacmode_prep_steps(device_id),
        ("启动工模主界面", lambda: start_main(device_id), "启动工模 MainActivity 失败"),
        ("跳过射频参数校准", lambda: skip_rf_calibration(device_id), "跳过射频参数校准失败"),
    ]
    if group.tabs_before_sequence:
        for tab_labels in group.tabs_before_sequence:
            name = tab_labels[0] if tab_labels else "标签"
            steps.append(
                (
                    f"点击{name}标签",
                    lambda labels=tab_labels: tap_group_tab(
                        device_id, labels, group.entry_by
                    ),
                    f"未找到标签: {tab_labels}",
                )
            )
    else:
        steps.append(
            (
                f"进入{group.key}测试组",
                lambda: enter_group(device_id, group),
                f"未找到测试组入口: {group.entry_keywords}",
            )
        )
    steps.append(
        (
            "校验测试组界面",
            lambda: poll_bool(page_ready, 8.0, 0.35),
            f"未进入测试组界面: {group.page_keywords}",
        )
    )
    return steps


def _build_group_sequence_steps(
    device_id: str, group: TranfacGroup
) -> list[tuple[str, Callable[[], bool], str]]:
    steps = _build_group_entry_steps(
        device_id,
        group,
        lambda: (x := dump(device_id)) is not None
        and ui_has_keywords(x, group.page_keywords),
    )
    steps.extend(
        [
            (
                "点击顺序执行",
                lambda: (x := dump(device_id)) is not None
                and tap_xml(device_id, x, resource_id=RID_SEQUENCE_TEST),
                "点击顺序执行失败",
            ),
            (
                "等待 ForegroundActivity",
                lambda: poll_bool(
                    lambda: is_foreground_activity_active(device_id), 120.0, 1.0
                ),
                "超时未进入 ForegroundActivity",
            ),
        ]
    )
    return steps


def _build_enter_group_steps(
    device_id: str, group: TranfacGroup
) -> list[tuple[str, Callable[[], bool], str]]:
    return _build_group_entry_steps(
        device_id,
        group,
        lambda: _group_page_ready(device_id, group),
    )


def run_group_sequence(
    device_id: str,
    group: TranfacGroup,
    *,
    result_dir: str | Path | None = None,
    on_step: Optional[Callable[[str, bool], None]] = None,
    evaluate_fn: Optional[Callable[[dict[str, Any]], tuple[str, str]]] = None,
    result_json_suffix: str = "",
) -> dict[str, Any]:
    if err := _run_steps(on_step, _build_group_sequence_steps(device_id, group)):
        return err

    deadline = time.time() + 300.0
    group_result = None
    while time.time() < deadline:
        result = get_current_group_results(device_id)
        if result and _group_result_ready(result, group):
            group_result = result
            break
        time.sleep(2.0)

    if on_step:
        on_step("等待并解析测试组结果", group_result is not None)
    if group_result is None:
        return {"status": "fail", "message": "超时未获取测试组结果"}

    suffix = result_json_suffix or ""
    _save_result_json(
        result_dir,
        f"tranfacmode_{group.key}{suffix}_group.json",
        group_result,
    )

    evaluate = evaluate_fn or evaluate_group_results
    status, message = evaluate(group_result)
    if on_step:
        on_step("校验测试组通过状态", status == "pass")
    return {"status": status, "message": message, "group_result": group_result}


def _confirm_item_result(device_id: str, status: str) -> bool:
    xml = dump(device_id)
    if not xml:
        return False
    if status == "pass":
        return tap_xml(
            device_id,
            xml,
            resource_id="com.transsion.tranfacmode:id/result_btn_pass",
        ) or tap_xml(device_id, xml, text_equals=tuple(PASS_TEXTS))
    if status == "fail":
        return tap_xml(
            device_id,
            xml,
            resource_id="com.transsion.tranfacmode:id/result_btn_fail",
        ) or tap_xml(device_id, xml, text_equals=tuple(FAIL_TEXTS))
    return False


def _apply_item_result_confirm(
    device_id: str,
    item_status: str | None,
    item_label: str,
    *,
    on_step: Optional[Callable[[str, bool], None]] = None,
    page_ready: Optional[Callable[[], bool]] = None,
) -> Optional[dict[str, Any]]:
    """根据测试结果点击工模 pass/fail 按钮；已回到列表页则跳过。"""
    if item_status not in ("pass", "fail"):
        return None

    confirmed = _confirm_item_result(device_id, item_status)
    if on_step:
        label = "通过" if item_status == "pass" else "失败"
        on_step(f"点击{item_label}{label}按钮", confirmed)
    if confirmed:
        return None

    check_page = page_ready or (lambda: _screen_group_page_ready(device_id))
    if check_page():
        return None
    return {"status": "fail", "message": f"{item_label}结果确认按钮点击失败"}


def _tap_screen_item(
    device_id: str,
    keywords: tuple[str, ...],
) -> bool:
    return _tap_group_item(device_id, keywords)


def _screen_group_page_ready(device_id: str) -> bool:
    return _group_page_ready(device_id, SCREEN)


def _group_page_ready(device_id: str, group: TranfacGroup) -> bool:
    xml = dump(device_id)
    if not xml or not ui_has_keywords(xml, group.page_keywords):
        return False
    return any(
        ADAPTER_TITLE_RID_SUFFIX in (node.attrib.get("resource-id") or "")
        for node in ET.parse(xml).getroot().iter("node")
    )


def _enter_screen_group_for_items(
    device_id: str,
    on_step: Optional[Callable[[str, bool], None]],
) -> Optional[dict[str, Any]]:
    return _run_steps(
        on_step,
        [
            *tranfacmode_prep_steps(device_id),
            ("启动工模主界面", lambda: start_main(device_id), "启动工模 MainActivity 失败"),
            ("跳过射频参数校准", lambda: skip_rf_calibration(device_id), "跳过射频参数校准失败"),
            ("进入screen测试组", lambda: enter_group(device_id, SCREEN), "未找到屏幕测试组入口"),
            (
                "校验屏幕测试组界面",
                lambda: poll_bool(lambda: _screen_group_page_ready(device_id), 8.0, 0.35),
                f"未进入屏幕测试组界面: {SCREEN.page_keywords}",
            ),
        ],
    )


def _collect_screen_item_names(
    device_id: str,
    keywords: tuple[str, ...],
    *,
    exclude_keywords: tuple[str, ...] = (),
) -> list[str]:
    return _collect_group_item_names(
        device_id,
        keywords,
        exclude_keywords=exclude_keywords,
    )


def _collect_group_item_names(
    device_id: str,
    keywords: tuple[str, ...],
    *,
    exclude_keywords: tuple[str, ...] = (),
) -> list[str]:
    xml = dump(device_id)
    if not xml:
        return []
    names: list[str] = []
    for node in ET.parse(xml).getroot().iter("node"):
        rid = node.attrib.get("resource-id") or ""
        if ADAPTER_TITLE_RID_SUFFIX not in rid:
            continue
        text = (node.attrib.get("text") or "").strip()
        if not text or not _item_name_matches(text, keywords):
            continue
        if exclude_keywords and _item_name_matches(text, exclude_keywords):
            continue
        if text not in names:
            names.append(text)
    return names


def _tap_screen_item_name(device_id: str, item_name: str) -> bool:
    return _tap_group_item_name(device_id, item_name)


def _tap_group_item(
    device_id: str,
    keywords: tuple[str, ...],
    *,
    exclude_keywords: tuple[str, ...] = (),
) -> bool:
    exact_names = _collect_group_item_names(
        device_id,
        keywords,
        exclude_keywords=exclude_keywords,
    )
    if exact_names and tap_list_item(
        device_id, tuple(exact_names), rid_suffix=ADAPTER_TITLE_RID_SUFFIX
    ):
        return True
    if exclude_keywords:
        return False
    return click_by_match_keywords(device_id, keywords, **CLICK_KWARGS)


def _tap_group_item_name(device_id: str, item_name: str) -> bool:
    if tap_list_item(device_id, (item_name,), rid_suffix=ADAPTER_TITLE_RID_SUFFIX):
        return True
    return click_by_match_keywords(device_id, (item_name,), **CLICK_KWARGS)


def _wait_screen_item_result(device_id: str) -> str | None:
    return poll_value(
        lambda: (x := dump(device_id))
        and tranfacmode_item_result(
            x,
            tuple(PASS_TEXTS),
            tuple(FAIL_TEXTS),
            status_rid=OTHER_RESULT_STATUS_RID,
        ),
        120.0,
        0.6,
    )


def _run_selected_screen_item(
    device_id: str,
    item_label: str,
    tap_item: Callable[[], bool],
    keywords: tuple[str, ...],
    *,
    on_step: Optional[Callable[[str, bool], None]],
    item_name: str = "",
    manual_confirm: Optional[Callable[..., str]] = None,
    page_ready: Optional[Callable[[], bool]] = None,
    after_tap: Optional[Callable[[str], bool]] = None,
) -> dict[str, Any]:
    item_tapped = tap_item()
    if on_step:
        on_step(f"选择{item_label}测试项", item_tapped)
    if not item_tapped:
        return {"status": "fail", "message": f"未找到{item_label}测试项"}

    if callable(after_tap) and not after_tap(device_id):
        return {"status": "fail", "message": f"{item_label}进入后操作失败"}

    if callable(manual_confirm):
        if on_step:
            on_step(f"{item_label}需人工判断", True)
        item_status = manual_confirm(f"请根据设备工模现象判断{item_label}测试结果")
        if item_status == "pass":
            return {
                "status": "pass",
                "message": f"{item_label}人工判断通过",
                "test_result": item_status,
            }
        if item_status == "fail":
            return {
                "status": "fail",
                "message": f"{item_label}人工判断失败",
                "test_result": item_status,
            }
        return {
            "status": item_status or "pending",
            "message": f"{item_label}人工判断{item_status or 'pending'}",
            "test_result": item_status,
        }

    item_status = _wait_screen_item_result(device_id)
    if on_step:
        on_step(f"判断{item_label}测试结果", item_status is not None)

    if err := _apply_item_result_confirm(
        device_id,
        item_status,
        item_label,
        on_step=on_step,
        page_ready=page_ready,
    ):
        return err

    if item_status == "pass":
        status, message = "pass", f"{item_label}工模测试成功"
    elif item_status == "fail":
        status, message = "fail", f"{item_label}工模测试失败"
    else:
        status, message = "fail", f"超时未获取{item_label}测试结果"

    return {"status": status, "message": message, "test_result": item_status}


def _save_screen_item_result(
    result_dir: str | Path | None,
    item_label: str,
    result: dict[str, Any],
) -> None:
    _save_result_json(
        result_dir,
        f"tranfacmode_screen_{item_label}_result.json",
        {
            "result": result.get("test_result"),
            "status": result.get("status"),
            "message": result.get("message"),
        },
    )


def _save_group_item_result(
    result_dir: str | Path | None,
    group: TranfacGroup,
    item_label: str,
    result: dict[str, Any],
) -> None:
    _save_result_json(
        result_dir,
        f"tranfacmode_{group.key}_{item_label}_result.json",
        {
            "result": result.get("test_result"),
            "status": result.get("status"),
            "message": result.get("message"),
            "group": group.key,
        },
    )


def _save_group_items_result(
    result_dir: str | Path | None,
    group: TranfacGroup,
    group_label: str,
    result: dict[str, Any],
) -> None:
    _save_result_json(
        result_dir,
        f"tranfacmode_{group.key}_{group_label}_items_result.json",
        result,
    )


def run_screen_group_item_test(
    device_id: str,
    keywords: tuple[str, ...],
    *,
    item_label: str,
    result_dir: str | Path | None = None,
    on_step: Optional[Callable[[str, bool], None]] = None,
    manual_confirm: Optional[Callable[..., str]] = None,
) -> dict[str, Any]:
    """进入屏幕工模页，只执行指定屏幕子项（触摸/色彩/背光等）。"""
    if err := _enter_screen_group_for_items(device_id, on_step):
        return err

    item_names = _collect_screen_item_names(device_id, keywords)
    item_name = item_names[0] if item_names else ""
    result = _run_selected_screen_item(
        device_id,
        item_label,
        lambda: _tap_screen_item_name(device_id, item_name)
        if item_name
        else _tap_screen_item(device_id, keywords),
        keywords,
        on_step=on_step,
        item_name=item_name,
        manual_confirm=manual_confirm,
    )
    _save_screen_item_result(result_dir, item_label, result)
    return result


def _parse_group_item_spec(
    item_spec: tuple[Any, ...],
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    item_label = item_spec[0]
    keywords = item_spec[1]
    exclude_keywords = item_spec[2] if len(item_spec) > 2 else ()
    return item_label, keywords, exclude_keywords


def run_tranfacmode_group_items_test(
    device_id: str,
    group: TranfacGroup,
    item_specs: Sequence[tuple[Any, ...]],
    *,
    group_label: str = "",
    result_dir: str | Path | None = None,
    on_step: Optional[Callable[[str, bool], None]] = None,
    manual_confirm: Optional[Callable[..., str]] = None,
    before_items: Optional[Callable[[], Optional[dict[str, Any]]]] = None,
    after_item_tap: Optional[dict[str, Callable[[str], bool]]] = None,
    stop_on_fail: bool = True,
) -> dict[str, Any]:
    """进入指定工模测试组，按传入配置执行一个或多个子项。

    item_specs 格式: [("标准充电", ("标准充电", "Standard Charge")), ...]
    可选第三个元素为排除关键字: ("光感", LIGHT_SENSOR_ITEM_KEYWORDS, ("校准", "Cali"))
    after_item_tap: 进入子项后的额外操作，如 {"光感数据采集": fn(device_id) -> bool}
    """
    if err := _run_steps(on_step, _build_enter_group_steps(device_id, group)):
        return err

    if callable(before_items):
        if result := before_items():
            return result

    specs = list(item_specs)
    if not specs:
        return {"status": "fail", "message": f"{group.key}测试组未配置测试子项"}

    item_results: list[dict[str, Any]] = []
    for index, item_spec in enumerate(specs):
        item_label, keywords, exclude_keywords = _parse_group_item_spec(item_spec)
        item_names = _collect_group_item_names(
            device_id,
            keywords,
            exclude_keywords=exclude_keywords,
        )
        item_name = item_names[0] if item_names else ""
        result = _run_selected_screen_item(
            device_id,
            item_label,
            lambda name=item_name, kws=keywords, excludes=exclude_keywords: _tap_group_item_name(device_id, name)
            if name
            else _tap_group_item(device_id, kws, exclude_keywords=excludes),
            keywords,
            on_step=on_step,
            item_name=item_name,
            manual_confirm=manual_confirm,
            page_ready=lambda: _group_page_ready(device_id, group),
            after_tap=(after_item_tap or {}).get(item_label),
        )
        item_result = {
            "label": item_label,
            "matched_name": item_name,
            **result,
        }
        item_results.append(item_result)
        _save_group_item_result(result_dir, group, item_label, result)

        if result.get("status") != "pass" and stop_on_fail:
            final_result = {
                "status": result.get("status", "fail"),
                "message": result.get("message", f"{item_label}工模测试失败"),
                "items": item_results,
                "group": group.key,
            }
            _save_group_items_result(
                result_dir, group, group_label or group.key, final_result
            )
            return final_result

        if index < len(specs) - 1 and result.get("test_result") in ("pass", "fail"):
            ready = poll_bool(lambda: _group_page_ready(device_id, group), 8.0, 0.35)
            if on_step:
                on_step(f"{item_label}测试后返回测试组界面", ready)
            if not ready:
                final_result = {
                    "status": "fail",
                    "message": f"{item_label}测试后未返回{group.key}测试组界面",
                    "items": item_results,
                    "group": group.key,
                }
                _save_group_items_result(
                    result_dir, group, group_label or group.key, final_result
                )
                return final_result

    failed_items = [item for item in item_results if item.get("status") != "pass"]
    if failed_items:
        labels = "、".join(item.get("label", "?") for item in failed_items)
        status, message = "fail", f"{group.key}测试组子项失败: {labels}"
    else:
        labels = "、".join(item.get("label", "?") for item in item_results)
        status, message = "pass", f"{group.key}测试组子项全部通过: {labels}"

    final_result = {
        "status": status,
        "message": message,
        "items": item_results,
        "group": group.key,
    }
    _save_group_items_result(result_dir, group, group_label or group.key, final_result)
    return final_result


def run_screen_touch_items_test(
    device_id: str,
    *,
    result_dir: str | Path | None = None,
    on_step: Optional[Callable[[str, bool], None]] = None,
) -> dict[str, Any]:
    """触摸屏自检：依次执行两个 TouchSelf 项，再执行 TouchPanel 项。"""
    if err := _enter_screen_group_for_items(device_id, on_step):
        return err

    touch_self_names = _collect_screen_item_names(
        device_id, SCREEN_TOUCH_SELF_ITEM_KEYWORDS
    )
    if on_step:
        on_step("识别触摸屏自检项", len(touch_self_names) >= 2)
    if len(touch_self_names) < 2:
        found = "、".join(touch_self_names) if touch_self_names else "无"
        return {
            "status": "fail",
            "message": f"未找到两个触摸屏自检项（已找到: {found}）",
        }

    item_results: list[dict[str, Any]] = []
    for index, item_name in enumerate(touch_self_names[:2], start=1):
        label = f"触摸屏自检{index}({item_name})"
        result = _run_selected_screen_item(
            device_id,
            label,
            lambda name=item_name: _tap_screen_item_name(device_id, name),
            SCREEN_TOUCH_SELF_ITEM_KEYWORDS,
            on_step=on_step,
            item_name=item_name,
        )
        item_results.append({"item": item_name, **result})
        if result.get("test_result") not in ("pass", "fail"):
            _save_screen_item_result(result_dir, "触摸屏", result)
            return {"status": result["status"], "message": result["message"]}
        if not poll_bool(lambda: _screen_group_page_ready(device_id), 8.0, 0.35):
            return {"status": "fail", "message": "触摸屏自检后未返回屏幕测试列表"}

    touch_panel_names = _collect_screen_item_names(
        device_id,
        SCREEN_TOUCH_PANEL_ITEM_KEYWORDS,
        exclude_keywords=SCREEN_TOUCH_SELF_ITEM_KEYWORDS,
    )
    if on_step:
        on_step("识别触摸屏测试项", bool(touch_panel_names))
    if not touch_panel_names:
        return {"status": "fail", "message": "未找到触摸屏测试项"}

    panel_name = touch_panel_names[0]
    panel_result = _run_selected_screen_item(
        device_id,
        f"触摸屏测试({panel_name})",
        lambda: _tap_screen_item_name(device_id, panel_name),
        SCREEN_TOUCH_PANEL_ITEM_KEYWORDS,
        on_step=on_step,
        item_name=panel_name,
    )
    item_results.append({"item": panel_name, **panel_result})
    if panel_result.get("test_result") not in ("pass", "fail"):
        _save_screen_item_result(result_dir, "触摸屏", panel_result)
        return {"status": panel_result["status"], "message": panel_result["message"]}

    failed_items = [
        item
        for item in item_results
        if item.get("test_result") == "fail" or item.get("status") != "pass"
    ]
    if failed_items:
        detail = "、".join(item.get("item", "?") for item in failed_items)
        result = {
            "status": "fail",
            "message": f"触摸屏子项失败: {detail}",
            "items": item_results,
        }
        _save_screen_item_result(result_dir, "触摸屏", result)
        return result

    result = {
        "status": "pass",
        "message": "触摸屏自检项和触摸屏测试项全部通过",
        "items": item_results,
    }
    _save_screen_item_result(result_dir, "触摸屏", result)
    return result


def pick_other_tab_item(
    xml: Path, items: tuple[OtherTabItem, ...]
) -> Optional[OtherTabItem]:
    """在 Other 分类页中识别首个匹配的测试项（按 items 顺序优先）。"""
    for item in items:
        for el in ET.parse(xml).getroot().iter("node"):
            rid = el.attrib.get("resource-id") or ""
            if ADAPTER_TITLE_RID_SUFFIX not in rid:
                continue
            label = (el.attrib.get("text") or "").strip()
            if label in item.item_text:
                return item
    return None


def _finish_other_tab_item_test(
    device_id: str,
    item: OtherTabItem,
    *,
    result_dir: str | Path | None,
    on_step: Optional[Callable[[str, bool], None]],
) -> dict[str, Any]:
    test_status = poll_value(
        lambda: (x := dump(device_id))
        and tranfacmode_item_result(
            x, OTHER_PASS_TEXT, OTHER_FAIL_TEXT, status_rid=OTHER_RESULT_STATUS_RID
        ),
        120.0,
        0.5,
    )
    if on_step:
        on_step(f"判断{item.label}测试结果", test_status is not None)

    if err := _apply_item_result_confirm(device_id, test_status, item.label, on_step=on_step):
        return err

    if test_status == "pass":
        status, message = "pass", f"{item.label}工模测试成功"
    elif test_status == "fail":
        status, message = "fail", f"{item.label}工模测试失败"
    else:
        status, message = "fail", f"超时未获取{item.label}测试结果（无成功/失败 TextView）"

    _save_result_json(
        result_dir,
        f"tranfacmode_{item.key}_result.json",
        {"result": test_status, "status": status, "message": message, "item": item.key},
    )

    return {"status": status, "message": message, "test_result": test_status, "item": item.key}


def run_other_tab_item_test(
    device_id: str,
    item: OtherTabItem,
    *,
    result_dir: str | Path | None = None,
    on_step: Optional[Callable[[str, bool], None]] = None,
) -> dict[str, Any]:
    if err := _run_steps(
        on_step,
        [
            *tranfacmode_prep_steps(device_id),
            ("启动工模主界面", lambda: start_main(device_id), "启动工模 MainActivity 失败"),
            ("跳过射频参数校准", lambda: skip_rf_calibration(device_id), "跳过射频参数校准失败"),
            ("进入 Other 分类", lambda: open_other_tab(device_id), "进入 Other/其他 分类失败"),
            (
                f"选择{item.label}测试项",
                lambda: tap_other_list_item(device_id, item.item_text),
                f"未找到{item.label}测试项",
            ),
        ],
    ):
        return err
    return _finish_other_tab_item_test(
        device_id, item, result_dir=result_dir, on_step=on_step
    )


def run_vibrator_test(
    device_id: str,
    *,
    result_dir: str | Path | None = None,
    on_step: Optional[Callable[[str, bool], None]] = None,
) -> dict[str, Any]:
    """马达工模：Other 页自动识别转子(Vibrator)或线性(LinearVibrator)后执行测试。"""
    if err := _run_steps(
        on_step,
        [
            *tranfacmode_prep_steps(device_id),
            ("启动工模主界面", lambda: start_main(device_id), "启动工模 MainActivity 失败"),
            ("跳过射频参数校准", lambda: skip_rf_calibration(device_id), "跳过射频参数校准失败"),
            ("进入 Other 分类", lambda: open_other_tab(device_id), "进入 Other/其他 分类失败"),
        ],
    ):
        return err

    xml = dump(device_id)
    item = pick_other_tab_item(xml, VIBRATOR_ITEMS) if xml else None
    if on_step:
        on_step("识别马达类型", item is not None)
    if item is None:
        return {
            "status": "fail",
            "message": "未找到转子马达(Vibrator/马达)或线性马达(LinearVibrator/线性马达)测试项",
        }

    if on_step:
        on_step(f"识别为{item.label}", True)
    ok = tap_other_list_item(device_id, item.item_text)
    if on_step:
        on_step(f"选择{item.label}测试项", ok)
    if not ok:
        return {"status": "fail", "message": f"未找到 {item.item_text} 测试项"}

    return _finish_other_tab_item_test(
        device_id, item, result_dir=result_dir, on_step=on_step
    )
