"""
Servidor de recepção de metadados de marcadores via socket TCP.

O app Android envia um JSON com DisplayMetrics quando a UI fica pronta.
Este receiver aguarda a conexão, valida o payload e retorna ACK "OK".

Fallback: Se timeout, tenta carregar um cache de último payload válido.
Se cache também falhar/expirar, deixa config.py usar fallback via ADB.

Uso:
    from utils.receive_marker_params import receive_marker_params
    
    params = receive_marker_params(timeout_seconds=15.0)
    print(params)
"""

import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Configurações do servidor
HOST = "0.0.0.0"
PORT = int(os.getenv("RTA_MARKER_PARAMS_PORT", "50605"))

_CACHE_PATH = os.getenv("RTA_MARKER_PARAMS_CACHE")
if _CACHE_PATH:
    CACHE_FILE = Path(_CACHE_PATH)
else:
    CACHE_FILE = Path(__file__).resolve().parent.parent / "tags" / "last_marker_params.json"

CACHE_MAX_AGE_SECONDS = float(os.getenv("RTA_MARKER_PARAMS_CACHE_MAX_AGE_SECONDS", "86400"))

# Parâmetros padrão (fallback final se tudo falhar)
DEFAULT_PARAMS = {
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
    "orientation": "unknown",
    "rotation": 0,
    "inset_left_px": 0.0,
    "inset_top_px": 0.0,
    "inset_right_px": 0.0,
    "inset_bottom_px": 0.0,
    "timestamp_ms": 0.0,
    "elapsed_realtime_ms": 0.0,
}


def _to_float(data: dict, key: str, fallback: float) -> float:
    """Converte pra float com fallback seguro."""
    try:
        return float(data.get(key, fallback))
    except (TypeError, ValueError):
        return float(fallback)


def _to_int(data: dict, key: str, fallback: int) -> int:
    """Converte pra int com fallback seguro."""
    try:
        return int(data.get(key, fallback))
    except (TypeError, ValueError):
        return int(fallback)


def _parse_and_validate_payload(raw_json: dict) -> Optional[dict]:
    """
    Parse um payload JSON bruto e valida/normaliza.
    
    Retorna None se os dados essenciais (screen_width_px, etc.) forem inválidos.
    """
    if not isinstance(raw_json, dict):
        logger.debug("Payload is not a dict")
        return None

    # Extrai e normaliza cada campo
    width_mm = _to_float(raw_json, "MARKER_REAL_WIDTH_MM", DEFAULT_PARAMS["MARKER_REAL_WIDTH_MM"])
    height_mm = _to_float(raw_json, "MARKER_REAL_HEIGHT_MM", DEFAULT_PARAMS["MARKER_REAL_HEIGHT_MM"])
    x_distance_mm = _to_float(raw_json, "MARKER_X_DISTANCE_MM", DEFAULT_PARAMS["MARKER_X_DISTANCE_MM"])
    marker_margin_px = _to_float(raw_json, "margin_px", DEFAULT_PARAMS["MARKER_MARGIN_PX"])
    tag_size_px = _to_float(raw_json, "tag_size_px", DEFAULT_PARAMS["tag_size_px"])
    density = _to_float(raw_json, "density", DEFAULT_PARAMS["density"])
    density_dpi = _to_float(raw_json, "density_dpi", DEFAULT_PARAMS["density_dpi"])
    xdpi = _to_float(raw_json, "xdpi", DEFAULT_PARAMS["xdpi"])
    ydpi = _to_float(raw_json, "ydpi", DEFAULT_PARAMS["ydpi"])
    screen_width_px = _to_float(raw_json, "screen_width_px", DEFAULT_PARAMS["screen_width_px"])
    screen_height_px = _to_float(raw_json, "screen_height_px", DEFAULT_PARAMS["screen_height_px"])
    orientation = str(raw_json.get("orientation", DEFAULT_PARAMS["orientation"]))
    rotation = _to_int(raw_json, "rotation", DEFAULT_PARAMS["rotation"])
    inset_left_px = _to_float(raw_json, "inset_left_px", DEFAULT_PARAMS["inset_left_px"])
    inset_top_px = _to_float(raw_json, "inset_top_px", DEFAULT_PARAMS["inset_top_px"])
    inset_right_px = _to_float(raw_json, "inset_right_px", DEFAULT_PARAMS["inset_right_px"])
    inset_bottom_px = _to_float(raw_json, "inset_bottom_px", DEFAULT_PARAMS["inset_bottom_px"])
    timestamp_ms = _to_float(raw_json, "timestamp_ms", DEFAULT_PARAMS["timestamp_ms"])
    elapsed_realtime_ms = _to_float(raw_json, "elapsed_realtime_ms", DEFAULT_PARAMS["elapsed_realtime_ms"])

    # Fallback opcional: se não tem tamanho real, derivar de tag_size_px + DPI
    if (width_mm <= 0 or height_mm <= 0) and tag_size_px > 0:
        if width_mm <= 0 and xdpi > 0:
            width_mm = tag_size_px / xdpi * 25.4
        if height_mm <= 0 and ydpi > 0:
            height_mm = tag_size_px / ydpi * 25.4

    parsed = {
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
        "orientation": orientation,
        "rotation": rotation,
        "inset_left_px": inset_left_px,
        "inset_top_px": inset_top_px,
        "inset_right_px": inset_right_px,
        "inset_bottom_px": inset_bottom_px,
        "timestamp_ms": timestamp_ms,
        "elapsed_realtime_ms": elapsed_realtime_ms,
    }

    # Validação mínima: rejeita se screen_width/height estão zerados
    if parsed["screen_width_px"] <= 0 or parsed["screen_height_px"] <= 0:
        logger.debug(f"Parsed payload has invalid screen dimensions: {parsed['screen_width_px']}x{parsed['screen_height_px']}")
        return None

    return parsed


def _send_ack(conn: socket.socket) -> bool:
    """Envia ACK "OK" e retorna True se sucesso."""
    try:
        conn.sendall(b"OK")
        return True
    except Exception as exc:
        logger.debug(f"Failed to send ACK: {exc}")
        return False


def _save_cached_params(parsed: dict) -> None:
    """Salva payload em cache para fallback futuro."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "saved_at_epoch_s": time.time(),
            "params": parsed,
        }
        CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        logger.debug(f"Cached marker params to {CACHE_FILE}")
    except Exception as exc:
        logger.warning(f"Failed to save cached params: {exc}")


def _load_cached_params() -> Optional[dict]:
    """Carrega payload em cache se válido e não expirado."""
    try:
        if not CACHE_FILE.exists():
            logger.debug(f"Cache file does not exist: {CACHE_FILE}")
            return None

        raw = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        saved_at = float(raw.get("saved_at_epoch_s", 0.0))
        params = raw.get("params", {})

        if not isinstance(params, dict):
            logger.debug("Cache payload is not a dict")
            return None

        age_s = max(0.0, time.time() - saved_at)
        if age_s > CACHE_MAX_AGE_SECONDS:
            logger.info(
                f"Cached params expired ({age_s:.1f}s > {CACHE_MAX_AGE_SECONDS:.1f}s). "
                "Falling back to ADB metrics."
            )
            return None

        # Valida que o cache em si é válido
        validated = _parse_and_validate_payload(params)
        if validated is None:
            logger.debug("Cached params failed validation")
            return None

        logger.info(
            f"Using cached marker params ({CACHE_FILE}, age={age_s:.1f}s)"
        )
        return validated
    except Exception as exc:
        logger.warning(f"Failed to load cached params: {exc}")
        return None


def receive_marker_params(timeout_seconds: float = 15.0) -> dict:
    """
    Aguarda e recebe metadados de marcadores via socket TCP.
    
    Estratégia:
    1. Cria servidor TCP em HOST:PORT e aguarda conexão do app.
    2. Tenta parsear JSON durante a recepção (parse incremental).
    3. Se conseguir, envia ACK e retorna; salva em cache.
    4. Se timeout, tenta carregar último payload válido em cache.
    5. Se cache falhar/expirar, deixa config.py usar fallback via ADB.
    
    Args:
        timeout_seconds: Tempo máximo em segundos para aguardar payload válido.
    
    Returns:
        Dict com DisplayMetrics e informações de marcador.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((HOST, PORT))
        server.listen(4)
        logger.info(
            f"Listening for marker params from app at {HOST}:{PORT} "
            f"(timeout={timeout_seconds}s)..."
        )

        deadline = time.monotonic() + timeout_seconds

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.info("Timeout waiting for marker params. Trying cache...")
                break

            server.settimeout(remaining)
            try:
                conn, addr = server.accept()
            except socket.timeout:
                logger.info("Socket timeout on accept. Trying cache...")
                break

            with conn:
                logger.debug(f"Connection from {addr}")
                conn.settimeout(max(0.5, deadline - time.monotonic()))
                chunks: list[bytes] = []

                # Recebe e tenta parsear incrementalmente
                while True:
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        logger.debug("Socket timeout during recv")
                        break

                    if not chunk:
                        logger.debug("Received empty chunk (connection closed)")
                        break

                    chunks.append(chunk)
                    joined = b"".join(chunks)

                    # Tenta parsear como JSON completo
                    try:
                        raw_json = json.loads(joined.decode("utf-8"))
                        parsed = _parse_and_validate_payload(raw_json)
                        if parsed is not None:
                            logger.info(f"Marker params received from {addr}: screen={parsed['screen_width_px']:.0f}x{parsed['screen_height_px']:.0f}")
                            _send_ack(conn)
                            _save_cached_params(parsed)
                            return parsed
                    except json.JSONDecodeError:
                        # JSON ainda incompleto, continua recebendo
                        continue
                    except Exception as exc:
                        logger.debug(f"Error during incremental parse: {exc}")
                        continue

                # Chegou aqui: ou timeout, ou conexão fechou, ou JSON inválido
                data = b"".join(chunks)
                if not data:
                    logger.info("Received empty payload. Waiting for next connection...")
                    continue

                # Tenta última vez com dados completos
                try:
                    raw_json = json.loads(data.decode("utf-8"))
                    parsed = _parse_and_validate_payload(raw_json)
                    if parsed is not None:
                        logger.info(f"Marker params received (final parse) from {addr}: screen={parsed['screen_width_px']:.0f}x{parsed['screen_height_px']:.0f}")
                        _send_ack(conn)
                        _save_cached_params(parsed)
                        return parsed
                except Exception as exc:
                    logger.debug(f"Failed to parse final data: {exc}")
                    continue

        # Chegou aqui com timeout; tenta cache
        cached = _load_cached_params()
        if cached is not None:
            return cached

        logger.warning(
            "No valid marker params received and no valid cache. "
            "Returning defaults (screen_width_px=0). config.py will use ADB fallback."
        )
        return DEFAULT_PARAMS.copy()

    finally:
        server.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    params = receive_marker_params()
    print("Final params:", json.dumps(params, indent=2))
