from utils.calibration_map import CalibrationMap


class CoordinateTransformer:
    def __init__(self, calibration_map: CalibrationMap):
        self.useful_rect_px = calibration_map.useful_rect_px

    def transform(self, px_x: float, px_y: float) -> tuple:
        """ To transform a pixel coordinate (px_x, px_y) to physical coordinates based on the calibration map's useful rectangle. """
        dif_x = self.useful_rect_px[2] - self.useful_rect_px[0]
        dif_y = self.useful_rect_px[3] - self.useful_rect_px[1]

        x = (dif_x * px_x) + self.useful_rect_px[0]
        y = (dif_y * px_y) + self.useful_rect_px[1]

        return round(x), round(y)

    def get_transformed_coordinates(self, key_dict: dict) -> dict:
        """ To transform a dictionary of pixel coordinates to physical coordinates. """
        transformed_dict = {}
        for key, (px_x, px_y) in key_dict.items():
            transformed_dict[key] = self.transform(px_x / 100, px_y / 100)
        return transformed_dict
