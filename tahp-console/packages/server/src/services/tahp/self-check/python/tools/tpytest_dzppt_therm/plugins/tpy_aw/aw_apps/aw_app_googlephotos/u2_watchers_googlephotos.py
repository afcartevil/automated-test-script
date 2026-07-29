from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersGooglePhotos(U2WatcherRegister):
    google_photos_ads_dismiss = U2WatcherDef(
        xpaths=['//*[@content-desc="Dismiss"]'],
        action="click",
        tags=["googlePhotos", "permission"],
        priority=100,
        description="googlePhotos弹窗"
    )

    google_photos_backup = U2WatcherDef(
        xpaths=['//*[@text="Let’s go"]'],
        action="click",
        tags=["googlePhotos", "permission"],
        priority=100,
        description="googlePhotos弹窗"
    )
