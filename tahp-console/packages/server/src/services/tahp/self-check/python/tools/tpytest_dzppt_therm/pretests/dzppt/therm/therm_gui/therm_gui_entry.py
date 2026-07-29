from gui_templates.default.default_gui_entry import DefaultGuiEntry
from gui_templates.default.gui_options import GuiOptions
from pretests.dzppt.therm.therm_gui.therm_gui_options import ThermGuiOptions

GuiOptions.instance = ThermGuiOptions()


def main():
    DefaultGuiEntry().main()


if __name__ == '__main__':
    main()
