from gui_templates.default.gui_options import GuiOptions
from pretests.dzppt.therm.therm_gui.therm_gui_constants import ThermGuiConstants
from pretests.dzppt.therm.therm_sub_entry import ThermSubEntry


class ThermGuiOptions(GuiOptions):
    case_scheme_sub_entry_class = ThermSubEntry
    gui_constants_class = ThermGuiConstants
