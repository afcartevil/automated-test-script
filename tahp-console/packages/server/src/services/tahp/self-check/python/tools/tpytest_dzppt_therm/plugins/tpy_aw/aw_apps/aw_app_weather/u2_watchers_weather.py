from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_register import U2WatcherRegister


class U2WatchersWeather(U2WatcherRegister):
    weather_agree = U2WatcherDef(
        xpaths=['//*[@text="Agree"]'],
        action="click",
        tags=["weather"],
        priority=100,
        description="weather Agree"
    )

    weather_change_to_precise_location = U2WatcherDef(
        xpaths=['//*[@text="Change to precise location"]'],
        action="click",
        tags=["weather"],
        priority=100,
        description="weather Change to precise location"
    )
