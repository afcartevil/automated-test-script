class DzRect:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.width = 0
        self.height = 0

    @staticmethod
    def create_from_seat(dz_seat, percent_x: float, percent_y: float, percent_width: float, percent_height: float):
        x_ratio = dz_seat.to_screen_ratio_x
        y_ratio = dz_seat.to_screen_ratio_y
        ins = DzRect()
        ins.x = percent_x * x_ratio
        ins.y = percent_y * y_ratio
        ins.width = percent_width * x_ratio
        ins.height = percent_height * y_ratio
        return ins

    @staticmethod
    def create(x: float, y: float, width: float, height: float):
        ins = DzRect()
        ins.x = x
        ins.y = y
        ins.width = width
        ins.height = height
        return ins

    def __str__(self):
        return f'{self.x}, {self.y}, {self.width}, {self.height}'

    def to_str(self):
        return f'{self.x},{self.y},{self.width},{self.height}'
