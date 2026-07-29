from tpy_aw.aw_helpers.aw_helper_xiaomi.aw_helper_xiaomi_hyper import AwHelperXiaomiHyper
from tpy_aw.u2d_test_helper import U2DTestHelper


class AwHelperXiaomiHyperR(AwHelperXiaomiHyper):
    variant_key = 'hyper_r'

    def set_all_volume_level(self, level: int):
        return U2DTestHelper.set_all_volume_level(self, level)

    def set_call_volume_level(self, level: int):
        return U2DTestHelper.set_call_volume_level(self, level)

    def set_ring_volume_level(self, level: int):
        return U2DTestHelper.set_ring_volume_level(self, level)

    def set_media_volume_level(self, level: int):
        return U2DTestHelper.set_media_volume_level(self, level)
