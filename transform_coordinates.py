class TransformCoordinates:
    def __init__(self, useful_rect_px):
        self.useful_rect_px = useful_rect_px

    def transform(self, px_x, px_y):
        dif_x = self.useful_rect_px[2] - self.useful_rect_px[0]
        dif_y = self.useful_rect_px[3] - self.useful_rect_px[1]

        x = (dif_x * px_x) + self.useful_rect_px[0]
        y = (dif_y * px_y) + self.useful_rect_px[1]
        
        return round(x), round(y)

    def get_dict_key_coordinates(self, key_dict):
        for k, v in key_dict.items():
            px_x, px_y = self.transform(v[0]/100, v[1]/100)
            key_dict[k] = [px_x, px_y]
        return key_dict
