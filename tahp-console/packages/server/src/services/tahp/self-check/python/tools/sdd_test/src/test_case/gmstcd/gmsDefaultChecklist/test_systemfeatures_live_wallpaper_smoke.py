# -*- coding: utf-8 -*-
import pytest

from src.utils.adb.adb_utils import adb_shell, get_feature


def _shell_output(device_serial, command):
    result = adb_shell(device_serial, command, no_retry=True)
    return (result.get("output") or result.get("error") or "").strip()


@pytest.mark.require_android_version_min(15)
def test_live_wallpaper_feature_consistency_smoke(device_serial):
    """
    ID:TOS1600-SYSFEATURE-LIVE-WALLPAPER
    DESCRIPTION:[CTS]SystemFeaturesTest#testLiveWallpaperFeature
    FIDELITY:L2 (intent resolvability + feature consistency)
    """
    feature_available = bool(get_feature(device_serial, "android.software.live_wallpaper"))

    resolve_out = _shell_output(
        device_serial,
        "cmd package resolve-activity --brief "
        "-a android.service.wallpaper.LIVE_WALLPAPER_CHOOSER",
    )
    lower_resolve = resolve_out.lower()
    chooser_resolvable = (
        bool(resolve_out)
        and "no activity found" not in lower_resolve
        and "error:" not in lower_resolve
        and "exception" not in lower_resolve
    )

    if chooser_resolvable and not feature_available:
        pytest.fail(
            "LIVE_WALLPAPER_CHOOSER is resolvable but feature "
            "android.software.live_wallpaper is missing"
        )

    if (not chooser_resolvable) and feature_available:
        pytest.fail(
            "feature android.software.live_wallpaper is declared but "
            f"LIVE_WALLPAPER_CHOOSER is not resolvable; raw={resolve_out}"
        )
