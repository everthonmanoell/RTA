import json
import socket

# Configurações do servidor
HOST = '0.0.0.0'  # Aceita conexões de qualquer IP
PORT = 50505      # Porta para comunicação

# Parâmetros padrão (caso não receba do app)
default_params = {
    "MARKER_REAL_WIDTH_MM": 100.0,
    "MARKER_REAL_HEIGHT_MM": 100.0,
    "MARKER_X_DISTANCE_MM": 500.0,
    "MARKER_MARGIN_PX": 30.0,
    "tag_size_px": 0.0,
    "margin_px": 30.0,
    "density": 0.0,
    "density_dpi": 0.0,
    "xdpi": 0.0,
    "ydpi": 0.0,
    "screen_width_px": 0.0,
    "screen_height_px": 0.0,
}

# Função para aguardar parâmetros do app Android
def receive_marker_params(timeout_seconds: float = 15.0):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.settimeout(timeout_seconds)
        s.bind((HOST, PORT))
        s.listen(1)
        print(f"Aguardando conexão do app Android em {HOST}:{PORT} (timeout={timeout_seconds}s)...")

        try:
            conn, addr = s.accept()
        except socket.timeout:
            print("Timeout ao aguardar app Android. Usando parâmetros padrão.")
            return default_params

        with conn:
            print(f"Conectado por {addr}")
            data = conn.recv(1024)
            if not data:
                print("Nenhum dado recebido. Usando parâmetros padrão.")
                return default_params
            try:
                params = json.loads(data.decode())
                print(f"Parâmetros recebidos: {params}")
                width_mm = float(params.get("MARKER_REAL_WIDTH_MM", default_params["MARKER_REAL_WIDTH_MM"]))
                height_mm = float(params.get("MARKER_REAL_HEIGHT_MM", default_params["MARKER_REAL_HEIGHT_MM"]))
                x_distance_mm = float(params.get("MARKER_X_DISTANCE_MM", default_params["MARKER_X_DISTANCE_MM"]))
                marker_margin_px = float(params.get("margin_px", default_params["MARKER_MARGIN_PX"]))
                tag_size_px = float(params.get("tag_size_px", default_params["tag_size_px"]))
                density = float(params.get("density", default_params["density"]))
                density_dpi = float(params.get("density_dpi", default_params["density_dpi"]))
                xdpi = float(params.get("xdpi", default_params["xdpi"]))
                ydpi = float(params.get("ydpi", default_params["ydpi"]))
                screen_width_px = float(params.get("screen_width_px", default_params["screen_width_px"]))
                screen_height_px = float(params.get("screen_height_px", default_params["screen_height_px"]))

                # Optional fallback: derive marker size from tag_size_px and display DPI.
                if (width_mm <= 0 or height_mm <= 0) and "tag_size_px" in params:
                    tag_size_px = float(params.get("tag_size_px", 0))
                    xdpi = float(params.get("xdpi", 0))
                    ydpi = float(params.get("ydpi", 0))

                    if width_mm <= 0 and xdpi > 0 and tag_size_px > 0:
                        width_mm = tag_size_px / xdpi * 25.4
                    if height_mm <= 0 and ydpi > 0 and tag_size_px > 0:
                        height_mm = tag_size_px / ydpi * 25.4

                return {
                    "MARKER_REAL_WIDTH_MM": width_mm,
                    "MARKER_REAL_HEIGHT_MM": height_mm,
                    "MARKER_X_DISTANCE_MM": x_distance_mm,
                    "MARKER_MARGIN_PX": marker_margin_px,
                    "tag_size_px": tag_size_px,
                    "density": density,
                    "density_dpi": density_dpi,
                    "xdpi": xdpi,
                    "ydpi": ydpi,
                    "screen_width_px": screen_width_px,
                    "screen_height_px": screen_height_px,
                }
            except Exception as e:
                print(f"Erro ao decodificar parâmetros: {e}")
                return default_params

if __name__ == "__main__":
    params = receive_marker_params()
    print("Parâmetros finais:", params)
