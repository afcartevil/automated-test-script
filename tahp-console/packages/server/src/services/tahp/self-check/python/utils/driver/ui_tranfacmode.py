"""工模自动化：主界面进组顺序测试 / Other 分类单项测试。"""

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Optional

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
    SCREEN_BACKLIGHT_ITEM_KEYWORDS,
    SCREEN_COLOR_ITEM_KEYWORDS,
    SCREEN_TOUCH_ITEM_KEYWORDS,
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
    click_by_match,
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


def go_home(device_id: str) -> bool:
    return adb(device_id, "shell", "input", "keyevent", "3").returncode == 0


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


def is_screen_touch_item(name: str) -> bool:
    text = (name or "").strip()
    if not text:
        return False
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in SCREEN_TOUCH_ITEM_KEYWORDS)


def _screen_item_category(name: str) -> str:
    if _item_name_matches(name, SCREEN_COLOR_ITEM_KEYWORDS):
        return "色彩"
    if _item_name_matches(name, SCREEN_BACKLIGHT_ITEM_KEYWORDS):
        return "背光"
    if is_screen_touch_item(name):
        return "触摸"
    return ""


def filter_screen_touch_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if is_screen_touch_item(item.get("name", ""))]


def filter_screen_case5_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """case5 关注子项：触摸、色彩、背光。"""
    return [item for item in items if _screen_item_category(item.get("name", ""))]


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


def evaluate_screen_touch_group_results(data: dict[str, Any]) -> tuple[str, str]:
    """校验屏幕顺序测试中触摸、色彩、背光子项是否全部通过。"""
    group = (data.get("group") or "").strip()
    all_items = data.get("items") or []
    items = filter_screen_case5_items(all_items)
    if not items:
        all_names = "、".join(i.get("name", "") for i in all_items if i.get("name"))
        return (
            "fail",
            f"测试组「{group}」未找到触摸/色彩/背光子项"
            + (f"（共{len(all_items)}项: {all_names}）" if all_names else ""),
        )

    def _item_summary(item: dict[str, Any]) -> str:
        name = item.get("name", "?")
        category = _screen_item_category(name) or "未知"
        state = (item.get("state") or "").strip()
        return f"{category}({name}/{state})"

    if all((item.get("state") or "").strip() in PASS_TEXTS for item in items):
        names = "、".join(_item_summary(item) for item in items)
        return "pass", f"触摸/色彩/背光全部通过（{len(items)}项）: {names}"

    failed = [
        item for item in items if (item.get("state") or "").strip() in FAIL_TEXTS
    ]
    if failed:
        detail = "; ".join(_item_summary(item) for item in failed)
        return "fail", f"失败项: {detail}"

    pending = [
        item
        for item in items
        if (item.get("state") or "").strip() not in PASS_TEXTS
    ]
    detail = "; ".join(_item_summary(item) for item in pending)
    return "fail", f"未完成项: {detail}"


SCREEN_TOUCH_GROUP_JSON = "tranfacmode_screen_touch_group.json"
SOURCE_SCREEN_TOUCH_CASE_INDEX = 5
USB_GROUP_JSON = "tranfacmode_usb_group.json"
SOURCE_USB_CASE_INDEX = 14
SENSOR_ITEMS_JSON = "tranfacmode_sensor_items.json"
SOURCE_SENSOR_ITEMS_CASE_INDEX = 22


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


def _load_tranfacmode_group_json(
    result_dir: str | Path | None, filename: str
) -> dict[str, Any] | None:
    if not result_dir:
        return None
    path = Path(result_dir).resolve() / filename
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_screen_touch_group_result(result_dir: str | Path | None) -> dict[str, Any] | None:
    return _load_tranfacmode_group_json(result_dir, SCREEN_TOUCH_GROUP_JSON)


def load_usb_group_result(result_dir: str | Path | None) -> dict[str, Any] | None:
    return _load_tranfacmode_group_json(result_dir, USB_GROUP_JSON)


def load_sensor_items_result(result_dir: str | Path | None) -> dict[str, Any] | None:
    from utils.driver.sensor_items_result import load_sensor_items_result as _load

    return _load(result_dir)


def save_sensor_items_result(
    result_dir: str | Path | None,
    items: list[dict[str, str]],
    **kwargs: Any,
) -> None:
    from utils.driver.sensor_items_result import save_sensor_items_result as _save

    _save(result_dir, items, **kwargs)


def evaluate_reused_group_item(
    data: dict[str, Any],
    keywords: tuple[str, ...],
    item_label: str,
    *,
    result_source_label: str,
) -> tuple[str, str]:
    items = data.get("items") or []
    matched = [
        item
        for item in items
        if isinstance(item, dict) and _item_name_matches(item.get("name", ""), keywords)
    ]
    if not matched:
        all_names = "、".join(item.get("name", "") for item in items if isinstance(item, dict))
        suffix = f"（已有: {all_names}）" if all_names else ""
        return "fail", f"未在{result_source_label}结果中找到{item_label}子项{suffix}"

    failed = [
        item
        for item in matched
        if (item.get("state") or "").strip() in FAIL_TEXTS
    ]
    if failed:
        detail = "; ".join(
            f"{item.get('name', '?')}({item.get('state', '')})" for item in failed
        )
        return "fail", f"复用{result_source_label}结果: {detail}"

    pending = [
        item
        for item in matched
        if (item.get("state") or "").strip() not in PASS_TEXTS
    ]
    if pending:
        detail = "; ".join(
            f"{item.get('name', '?')}({item.get('state', '')})" for item in pending
        )
        return "fail", f"复用{result_source_label}结果: {item_label}未完成({detail})"

    names = "、".join(item.get("name", "") for item in matched if item.get("name"))
    return "pass", f"复用{result_source_label}结果: {names} 通过"


def evaluate_reused_screen_item(
    data: dict[str, Any],
    keywords: tuple[str, ...],
    item_label: str,
) -> tuple[str, str]:
    return evaluate_reused_group_item(
        data,
        keywords,
        item_label,
        result_source_label=f"case{SOURCE_SCREEN_TOUCH_CASE_INDEX} 屏幕顺序测试",
    )


def _run_reuse_tranfacmode_group_item(
    context: dict[str, Any],
    keywords: tuple[str, ...],
    *,
    item_label: str,
    load_result: Callable[[str | Path | None], dict[str, Any] | None],
    step_update: Callable[[str], None] | None = None,
    source_case_index: int,
    source_case_hint: str,
    result_type_label: str,
) -> dict[str, str]:
    sub_steps = ""

    def update(steps: str) -> None:
        if callable(step_update):
            step_update(steps)

    sub_steps += (
        f"\n复用 case{source_case_index} {result_type_label}结果({item_label})"
    )
    update(sub_steps)

    data = load_result(context.get("result_dir"))
    if not data:
        sub_steps += f"-跳过(未找到 case{source_case_index} 结果文件)"
        update(sub_steps)
        return {
            "status": "skip",
            "message": source_case_hint,
        }

    result_source_label = f"case{source_case_index} {result_type_label}"
    status, message = evaluate_reused_group_item(
        data,
        keywords,
        item_label,
        result_source_label=result_source_label,
    )
    sub_steps += "-成功" if status == "pass" else "-失败"
    update(sub_steps)
    return {"status": status, "message": message}


def run_reuse_screen_touch_group_item(
    context: dict[str, Any],
    keywords: tuple[str, ...],
    *,
    item_label: str,
    step_update: Callable[[str], None] | None = None,
    source_case_index: int = SOURCE_SCREEN_TOUCH_CASE_INDEX,
) -> dict[str, str]:
    return _run_reuse_tranfacmode_group_item(
        context,
        keywords,
        item_label=item_label,
        load_result=load_screen_touch_group_result,
        step_update=step_update,
        source_case_index=source_case_index,
        source_case_hint=f"请先执行 case{source_case_index} 开机工模触摸屏",
        result_type_label="屏幕顺序测试",
    )


def run_reuse_usb_group_item(
    context: dict[str, Any],
    keywords: tuple[str, ...],
    *,
    item_label: str,
    step_update: Callable[[str], None] | None = None,
    source_case_index: int = SOURCE_USB_CASE_INDEX,
) -> dict[str, str]:
    return _run_reuse_tranfacmode_group_item(
        context,
        keywords,
        item_label=item_label,
        load_result=load_usb_group_result,
        step_update=step_update,
        source_case_index=source_case_index,
        source_case_hint=f"请先执行 case{source_case_index} USB功能正常充电",
        result_type_label="USB工模测试",
    )


def run_reuse_sensor_items_item(
    context: dict[str, Any],
    keywords: tuple[str, ...],
    *,
    item_label: str,
    step_update: Callable[[str], None] | None = None,
    source_case_index: int = SOURCE_SENSOR_ITEMS_CASE_INDEX,
) -> dict[str, str]:
    from utils.driver.sensor_items_result import run_reuse_sensor_items_item as _run

    return _run(
        context,
        keywords,
        item_label=item_label,
        step_update=step_update,
        source_case_index=source_case_index,
    )


def _build_group_sequence_steps(
    device_id: str, group: TranfacGroup
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
            lambda: poll_bool(
                lambda: (x := dump(device_id)) is not None
                and ui_has_keywords(x, group.page_keywords),
                8.0,
                0.35,
            ),
            f"未进入测试组界面: {group.page_keywords}",
        )
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
    if result_dir:
        try:
            _save_json(
                Path(result_dir) / f"tranfacmode_{group.key}{suffix}_group.json",
                group_result,
            )
        except OSError:
            pass

    evaluate = evaluate_fn or evaluate_group_results
    status, message = evaluate(group_result)
    if on_step:
        on_step("校验测试组通过状态", status == "pass")
    return {"status": status, "message": message, "group_result": group_result}


def run_screen_touch_group_sequence(
    device_id: str,
    *,
    result_dir: str | Path | None = None,
    on_step: Optional[Callable[[str, bool], None]] = None,
) -> dict[str, Any]:
    """执行屏幕顺序测试，校验触摸、色彩、背光子项结果。"""
    return run_group_sequence(
        device_id,
        SCREEN,
        result_dir=result_dir,
        on_step=on_step,
        evaluate_fn=evaluate_screen_touch_group_results,
        result_json_suffix="_touch",
    )


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

    if test_status == "pass":
        status, message = "pass", f"{item.label}工模测试成功"
    elif test_status == "fail":
        status, message = "fail", f"{item.label}工模测试失败"
    else:
        status, message = "fail", f"超时未获取{item.label}测试结果（无成功/失败 TextView）"

    if result_dir:
        try:
            _save_json(
                Path(result_dir) / f"tranfacmode_{item.key}_result.json",
                {"result": test_status, "status": status, "message": message, "item": item.key},
            )
        except OSError:
            pass

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
                f"未找到 {item.item_text} 测试项",
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
