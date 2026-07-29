from PyQt6.QtCore import QLocale

from powertrde import env

# 建议把映射放到单独模块或常量里，便于维护
ENGLISH_TEXT_BY_ATTR = {
    # 使用 ui 属性名 映射 要设置的 文本/标题/shortcut
    # key 格式： "<attr>.__text" / "<attr>.__title" / "<attr>.__shortcut"
    "DefaultGuiMainWindow.__windowTitle": "MainWindow",
    "textTitle.__text": "Performance Dynamic Model Test Executor",
    "controlBoxGroup.__title": "Execution Control",
    "startTestButton.__text": "Start Test",
    "caseSetLabel.__text": "Case Set",
    "pretestLevelLabel.__text": "Pretest Level",
    "traceParseLabel.__text": "Trace Parse Config",
    "appPretestLabel.__text": "App Pretest",
    "testPhoneLabel.__text": "DUT",
    "copilotPhoneLabel.__text": "AUX",
    "taskIDLabel.__text": "Task ID",
    "fillLastTimeButton.__text": "Fill Last Time",
    "disableButton.__text": "Disable",
    "disableButton.__shortcut": "Ctrl+S",
    "refreshDeviceButton.__text": "Refresh Dev",
    "caseBoxGroup.__title": "Test Case Information",
    "log_group.__title": "Execution Info",
    "test_progress_bar.__format": "%p%",  # progress bar format string
    "test_progress_desc.__text": "60/90, Pass/Fail: 15/1",
    "only_show_error.__text": "Only Show Error",
    "open_log_dir.__text": "Latest report path: none",
    "textStage.__text": "Stopped",
    "textTimer.__text": "12:21:34",

    # 菜单与标题
    "menuOpen.__title": "Open",
    "menuControl.__title": "Control",
    "menuRetest.__title": "Retest",
    "menuAbout.__title": "About",
    "menuFeedback.__title": "Feedback",

    # QAction 文本 (生成的 ui 里通常是 QAction 对象)
    "actionOpenLastReport.__text": "Open Latest Report Directory",
    "actionStopTest.__text": "Stop Test",
    "actionOpenConfigDir.__text": "Open Config Folder",
    "actionOpenLatestRetest.__text": "Run Retest on Latest Report",
    "actionOpenCustomizeRetest.__text": "Select Report for Custom Retest",
    "actionRelease.__text": "Version Info",
    "actionCheckUpdate.__text": "Check for Updates",
    "actionHelp.__text": "About Us",
    "actionResultUpload.__text": "Upload Results",
    "actionSOP.__text": "SOP Document",
    "actionOneClickUpload.__text": "One Click Upload",
}


def apply_embedded_i18n(ui, window, forced_english=False):
    """
    ui: the generated Ui_* instance (the object with attributes like textTitle, startTestButton, ...)
    window: the actual QMainWindow (DefaultGuiMainWindow)
    """
    use_english = forced_english or env.scheme.tool_language == "en"
    if not use_english:
        return  # 默认中文，不做任何改动

    # 遍历映射并应用
    for key, text in ENGLISH_TEXT_BY_ATTR.items():
        try:
            attr, what = key.split(".__", 1)
            if attr == "DefaultGuiMainWindow" and what == "windowTitle":
                window.setWindowTitle(text)
                continue
            widget = getattr(ui, attr, None)
            if widget is None:
                continue
            if what == "text":
                # 普通控件的 setText
                widget.setText(text)
            elif what == "title":
                # QGroupBox.setTitle 等
                widget.setTitle(text)
            elif what == "shortcut":
                # 如果是 QPushButton 或 QAction 之类
                try:
                    widget.setShortcut(text)
                except Exception:
                    # 备用处理：有些按钮可能没有 setShortcut
                    pass
            # 你可以扩展更多属性处理，如 toolTip、placeholderText 等
        except Exception:
            # 忽略任何单条设置失败，保证尽量设置其余项目
            pass
