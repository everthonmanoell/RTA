import json
import socket

# Configurações do servidor
HOST = '0.0.0.0'  # Aceita conexões de qualquer IP
PORT = 50505      # Porta para comunicação

# Parâmetros padrão (caso não receba do app)
default_params = {
    "MARKER_REAL_WIDTH_MM": 100.0,
    "MARKER_REAL_HEIGHT_MM": 100.0,
    "MARKER_X_DISTANCE_MM": 500.0
}

# Função para aguardar parâmetros do app Android
def receive_marker_params():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(1)
        print(f"Aguardando conexão do app Android em {HOST}:{PORT}...")
        conn, addr = s.accept()
        with conn:
            print(f"Conectado por {addr}")
            data = conn.recv(1024)
            if not data:
                print("Nenhum dado recebido. Usando parâmetros padrão.")
                return default_params
            try:
                params = json.loads(data.decode())
                print(f"Parâmetros recebidos: {params}")
                return {
                    "MARKER_REAL_WIDTH_MM": float(params.get("MARKER_REAL_WIDTH_MM", default_params["MARKER_REAL_WIDTH_MM"])),
                    "MARKER_REAL_HEIGHT_MM": float(params.get("MARKER_REAL_HEIGHT_MM", default_params["MARKER_REAL_HEIGHT_MM"])),
                    "MARKER_X_DISTANCE_MM": float(params.get("MARKER_X_DISTANCE_MM", default_params["MARKER_X_DISTANCE_MM"]))
                }
            except Exception as e:
                print(f"Erro ao decodificar parâmetros: {e}")
                return default_params

if __name__ == "__main__":
    params = receive_marker_params()
    print("Parâmetros finais:", params)
