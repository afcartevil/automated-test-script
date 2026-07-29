from typing import Callable, Optional, Union

from dz_remote.dz_seat import DzSeat


class DzLazySeat:
    def __init__(self, factory_or_instance: Union[DzSeat, Callable[[], DzSeat]]):
        if isinstance(factory_or_instance, DzSeat):
            self._factory: Optional[Callable[[], DzSeat]] = None
            self._dz_seat: Optional[DzSeat] = factory_or_instance
        else:
            self._factory: Optional[Callable[[], DzSeat]] = factory_or_instance
            self._dz_seat: Optional[DzSeat] = None

    @property
    def dz_seat(self):
        if not self._dz_seat:
            if self._factory is not None:
                self._dz_seat = self._factory()
        return self._dz_seat

    @dz_seat.setter
    def dz_seat(self, value: Optional[DzSeat]):
        self._dz_seat = value
