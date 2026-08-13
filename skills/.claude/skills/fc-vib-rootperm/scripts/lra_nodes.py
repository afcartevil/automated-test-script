"""LRA init.tp.rc node lists — single (vibrator_single) / dual (vibrator_l, vibrator_r)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

CHOWN_ONLY_DEV = ["/dev/tppolldrv"]

CHOWN_AND_MODE666_DEV = [
    "/dev/aw8697_haptic",
    "/dev/aac_richtap_5f",
]

VIBRATOR_LED_ATTRS = [
    "activate", "activate_mode", "awrw", "brightness", "bullet_nr", "cali",
    "cont", "cont_brk_time", "cont_drv_lvl", "cont_drv_time", "cont_wait_num",
    "duration", "f0", "f0_save", "gain", "gun_type", "haptic_audio",
    "haptic_audio_time", "index", "loop", "lra_resistance", "max_brightness",
    "osc_cali", "osc_save", "prctmode", "ram_num", "ram_update", "ram_vbat_comp",
    "reg", "rtp", "seq", "state", "trig", "trigger", "uevent", "vbat_monitor",
    "vibr_level",
]


@dataclass
class LraScheme:
    type: str  # single | dual | none
    leds: List[str]
    label: str


def get_scheme(leds_listing: str) -> LraScheme:
    has_single = bool(re.search(r"(?<!\w)vibrator_single(?!\w)", leds_listing))
    has_l = bool(re.search(r"(?<!\w)vibrator_l(?!\w)", leds_listing))
    has_r = bool(re.search(r"(?<!\w)vibrator_r(?!\w)", leds_listing))

    if has_l or has_r:
        leds = []
        if has_l:
            leds.append("vibrator_l")
        if has_r:
            leds.append("vibrator_r")
        return LraScheme("dual", leds, "vibrator_l + vibrator_r")

    if has_single:
        return LraScheme("single", ["vibrator_single"], "vibrator_single")

    return LraScheme("none", [], "unknown")


def path_requires_mode666(path: str) -> bool:
    if path in CHOWN_AND_MODE666_DEV:
        return True
    return bool(re.search(r"/sys/class/leds/vibrator_(single|l|r)/rtp$", path))
