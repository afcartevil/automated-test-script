from utils.gms.tradefed_run import run_gms_subplan

SUITE = "vts"
SUBPLAN = "sensor-vts-plan"


def run(device_info=None, step_update=None, **_context):
    return run_gms_subplan(SUITE, SUBPLAN, device_info, step_update)
