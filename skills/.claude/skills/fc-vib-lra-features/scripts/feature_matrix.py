"""LRA vibration feature → required getprop matrix.

Keep in sync with SKILL.md「功能-属性矩阵」table.
"""

from __future__ import annotations

FEATURE_MATRIX: list[dict[str, object]] = [
    {
        "feature": "铃声无极振动调节",
        "axis": "X",
        "props": ("ro.tr_vibrate.vibrate30.feature.support",),
    },
    {
        "feature": "铃声无极振动调节",
        "axis": "Z",
        "props": (
            "ro.tr_vibrate.vibrate30_z.feature.support",
            "ro.tr_vibrate.realvib05.feature.support",
        ),
    },
    {
        "feature": "触感反馈无极振动调节",
        "axis": "X",
        "props": ("ro.tr_vibrate.vibrate30.feature.support",),
    },
    {
        "feature": "触感反馈无极振动调节",
        "axis": "Z",
        "props": (
            "ro.tr_vibrate.vibrate30_z.feature.support",
            "ro.tr_vibrate.realvib05.feature.support",
        ),
    },
    {
        "feature": "自研振动 SDK",
        "axis": "X",
        "props": ("ro.tr_vibrate.vibrate30.feature.support",),
    },
    {
        "feature": "自研振动 SDK",
        "axis": "Z",
        "props": ("ro.tr_vibrate.vibrate30_z.feature.support",),
    },
    {
        "feature": "铃声随振",
        "axis": "X",
        "props": (
            "ro.tr_vibrate.notification_lra",
            "ro.tr_vibrate.vibrate30.feature.support",
        ),
    },
    {
        "feature": "铃声随振",
        "axis": "Z",
        "props": (
            "ro.tr_vibrate.vibrate30_z.feature.support",
            "ro.tr_vibrate.notification_lra",
        ),
    },
    {
        "feature": "PUBG/FreeFire 高品质振动",
        "axis": "X",
        "props": (
            "ro.tr_vibrate.vibrate10.feature.support",
            "ro.tr_vibrate.vibrate20.feature.support",
            "ro.tr_vibrate.vibrate30.feature.support",
        ),
    },
    {
        "feature": "PUBG/FreeFire 高品质振动",
        "axis": "Z",
        "props": ("ro.tr_vibrate.vibrate30_z.feature.support",),
    },
    {
        "feature": "交互场景震感（场景振动）",
        "axis": "X",
        "props": (
            "ro.tr_vibrate.vibrate10.feature.support",
            "ro.tr_vibrate.vibrate20.feature.support",
            "ro.tr_vibrate.vibrate30.feature.support",
        ),
    },
    {
        "feature": "交互场景震感（场景振动）",
        "axis": "Z",
        "props": ("ro.tr_vibrate.vibrate30_z.feature.support",),
    },
    {
        "feature": "真实触感",
        "axis": "-",
        "props": ("ro.tr_vibrate.realvib05.feature.support",),
    },
]
