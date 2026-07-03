from utils.calibration_map import CalibrationMap


DEFAULT_MAP_PATH ="physical_calibration_map.json"
cal_map = CalibrationMap.from_file(DEFAULT_MAP_PATH)

useful_rect_px = cal_map.useful_rect_px

def transform(px_x, px_y):
    dif_x = useful_rect_px[2] - useful_rect_px[0]
    dif_y = useful_rect_px[3] - useful_rect_px[1]

    x = (dif_x * px_x) + useful_rect_px[0]
    y = (dif_y * px_y) + useful_rect_px[1]
    
    return round(x), round(y)

# Isso é o valor em porecentagem do centro de cada botão do teclado.
key_dict = {1: [7.6, 69.5], 2: [16.9, 69.5], 3: [26.3, 69.5], 4: [35.6, 69.5], 5: [45.1, 69.5], 6: [54.5, 69.5], 7: [64.0, 69.5], 8: [73.4, 69.5], 9: [82.9, 69.5], 0: [92.3, 69.5],
 "q": [7.6, 74.9], "w": [16.9, 74.9], "e": [26.3, 74.9], "r": [35.6, 74.9], "t": [45.1, 74.9], "y": [54.5, 74.9], "u": [64.0, 74.9], "i": [73.4, 74.9], "o": [82.9, 74.9], "p": [92.3, 74.9], 
 "a": [12.3, 80.5], "s": [21.7, 80.5], "d": [31.0, 80.5], "f": [40.4, 80.5], "g": [49.8, 80.5], "h": [59.3, 80.5], "j": [68.7, 80.5], "k": [78.1, 80.5], "l": [87.6, 80.5], 
 "z": [21.7, 86.0], "x": [31.0, 86.0], "c": [40.4, 86.0], "v": [49.8, 86.0], "b": [59.3, 86.0], "n": [68.7, 86.0], "m": [78.1, 86.0]}

for k, v in key_dict.items():
    px_x, px_y = transform(v[0]/100, v[1]/100)
    print(f"{k}: [{px_x:.2f}, {px_y:.2f}]")
