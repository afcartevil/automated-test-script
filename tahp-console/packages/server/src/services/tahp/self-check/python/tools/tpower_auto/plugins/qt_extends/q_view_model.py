from PyQt6.QtCore import QObject

from powertrde.framework.viewmodel.view_model import ViewModel


class QViewModel(ViewModel, QObject):
    pass
