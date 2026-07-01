from utils.gms.tradefed_run import run_gms_subplan

SUBPLAN = "sensor-vts-plan"


def run(device_info=None, step_update=None, **_context):
    return run_gms_subplan(SUBPLAN, device_info, step_update)
