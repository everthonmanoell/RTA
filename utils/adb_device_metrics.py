"""
Fallback para pegar DisplayMetrics do device via ADB quando socket falha.

Este módulo implementa um fallback robusto que extrai resolução, densidade, DPI
e outras propriedades do device Android diretamente via `adb shell` e ADB commands,
sem depender do payload do socket que pode falhar ou ter corrida de sincronização.

Uso:
    from utils.adb_device_metrics import get_device_metrics_via_adb

    metrics = get_device_metrics_via_adb(device_type="flat")
    if metrics:
        print(f"Resolução: {metrics['screen_width_px']}x{metrics['screen_height_px']}")
        print(f"DPI: {metrics['xdpi']:.1f} / {metrics['ydpi']:.1f}")
"""

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Defaults para quando ADB também falha
FALLBACK_METRICS_FLAT = {
    "screen_width_px": 1080.0,
    "screen_height_px": 2340.0,
    "density_dpi": 420,
    "xdpi": 420.0,
    "ydpi": 420.0,
    "density": 2.625,  # density_dpi / 160
    "tag_size_dp": 120.0,
    "margin_dp": 16.0,
}

FALLBACK_METRICS_FOLDABLE = {
    "screen_width_px": 2152.0,
    "screen_height_px": 1536.0,
    "density_dpi": 408,
    "xdpi": 408.0,
    "ydpi": 408.0,
    "density": 2.55,
    "tag_size_dp": 120.0,
    "margin_dp": 16.0,
}


def _run_adb_command(cmd: list[str]) -> str:
    """
    Executa comando ADB silenciosamente e retorna stdout.
    
    Args:
        cmd: Lista de argumentos para `adb` (ex: ["shell", "getprop", "ro.display.width"])
    
    Returns:
        stdout limpo, ou string vazia se falhar.
    """
    try:
        result = subprocess.run(
            ["adb"] + cmd,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception as exc:
        logger.debug(f"ADB command failed: {exc}")
        return ""


def _parse_display_metrics() -> Optional[dict]:
    """
    Extrai DisplayMetrics via `adb shell dumpsys display`.
    
    Procura por linhas como:
        mBaseDisplayInfo=DisplayInfo{... size 1080x2340 ... densityDpi 420}
    
    Returns:
        Dict com screen_width_px, screen_height_px, density_dpi se conseguir parsear.
        None se falhar.
    """
    # Fonte primária: comandos leves e rápidos, menos sujeitos a timeout.
    wm_size = _run_adb_command(["shell", "wm", "size"])
    wm_density = _run_adb_command(["shell", "wm", "density"])

    wm_match = re.search(r"(\d+)x(\d+)", wm_size)
    wd_match = re.search(r"(\d+)", wm_density)
    if wm_match and wd_match:
        return {
            "screen_width_px": float(wm_match.group(1)),
            "screen_height_px": float(wm_match.group(2)),
            "density_dpi": int(wd_match.group(1)),
        }

    # Fallback secundário: dumpsys display (mais completo, porém mais pesado).
    output = _run_adb_command(["shell", "dumpsys", "display"])
    if not output:
        return None

    # Cobrir múltiplos formatos comuns em diferentes versões de Android/OEM:
    # - "size 1080x2340"
    # - "real 1080 x 2400"
    # - "logicalFrame=Rect(0, 0 - 1080, 2400)"
    size_patterns = [
        r"size\s*=?\s*(\d+)\s*x\s*(\d+)",
        r"real\s+(\d+)\s*x\s*(\d+)",
        r"logicalFrame=Rect\(0,\s*0\s*-\s*(\d+),\s*(\d+)\)",
        r"app\s+(\d+)\s*x\s*(\d+)",
    ]
    width_px: Optional[float] = None
    height_px: Optional[float] = None
    for pattern in size_patterns:
        match = re.search(pattern, output)
        if match:
            width_px = float(match.group(1))
            height_px = float(match.group(2))
            break

    # Densidade em formatos comuns:
    # - "densityDpi 420"
    # - "densityDpi=420"
    # - "density 400 (397.565 x 393.29) dpi"
    density_patterns = [
        r"densityDpi\s*=?\s*(\d+)",
        r"density\s+(\d+)\s*\(",
        r"density\s*:?\s*(\d+)\s*dpi",
    ]
    density_dpi: Optional[int] = None
    for pattern in density_patterns:
        match = re.search(pattern, output)
        if match:
            density_dpi = int(match.group(1))
            break

    if width_px is None or height_px is None or density_dpi is None:
        return None

    return {
        "screen_width_px": width_px,
        "screen_height_px": height_px,
        "density_dpi": density_dpi,
    }


def _get_dpi_values(density_dpi: int) -> tuple[float, float]:
    """
    Estima xdpi/ydpi a partir de density_dpi (simplificação).
    
    Na maioria dos devices, xdpi e ydpi são próximos. Usa density_dpi como proxy.
    
    Args:
        density_dpi: Valor de densityDpi (ex: 420)
    
    Returns:
        Tupla (xdpi, ydpi)
    """
    # Aproximação: assume isotropic (xdpi ≈ ydpi ≈ density_dpi)
    return float(density_dpi), float(density_dpi)


def _get_device_model() -> str:
    """Obtém modelo do device via ADB com retries e múltiplos fallbacks."""
    env_model = os.getenv("RTA_DEVICE_MODEL", "").strip()
    if env_model:
        return env_model

    props = [
        "ro.product.model",
        "ro.product.marketname",
        "ro.product.vendor.model",
        "ro.vendor.product.model",
        "ro.product.system.model",
    ]

    # Repetições pequenas ajudam quando o adb está concorrendo com am start/reverse.
    for _ in range(3):
        for prop in props:
            value = _run_adb_command(["shell", "getprop", prop]).strip()
            if value:
                return value
        time.sleep(0.2)

    # Fallback host-side: adb devices -l inclui token model:<nome>
    devices_output = _run_adb_command(["devices", "-l"])
    if devices_output:
        for line in devices_output.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            if " device " not in f" {line} ":
                continue
            model_match = re.search(r"\bmodel:([^\s]+)", line)
            if model_match:
                return model_match.group(1).replace("_", " ")

    logger.warning("Could not resolve device model via ADB; using 'unknown'.")
    return "unknown"


def get_device_metrics_via_adb(device_type: str = "flat") -> dict:
    """
    Pega DisplayMetrics do device via ADB e retorna dict compatível com
    os payloads do socket.
    
    Esta é a função principal de fallback que tenta:
    1. ADB dumpsys display para pegar resolução + DPI
    2. Se falhar, retorna defaults conhecidos por device_type
    
    Args:
        device_type: "flat" ou "foldable" (usado no fallback)
    
    Returns:
        Dict com:
        - screen_width_px, screen_height_px
        - density_dpi, xdpi, ydpi
        - density (density_dpi / 160)
        - tag_size_dp, margin_dp (valores padrão)
        - Campos adicionais necessários para compatibilidade com config.py
    """
    metrics = _parse_display_metrics()

    if metrics is None:
        # ADB falhou; usar fallback por device_type
        fallback = (
            FALLBACK_METRICS_FOLDABLE if device_type == "foldable"
            else FALLBACK_METRICS_FLAT
        )
        logger.warning(
            f"ADB display metrics parsing failed. Usando fallback para device_type='{device_type}': "
            f"{fallback['screen_width_px']:.0f}x{fallback['screen_height_px']:.0f} @ {fallback['density_dpi']} dpi"
        )
        
        # Calcular campos derivados mesmo no fallback
        width_px = fallback["screen_width_px"]
        height_px = fallback["screen_height_px"]
        density_dpi = fallback["density_dpi"]
        xdpi = fallback["xdpi"]
        ydpi = fallback["ydpi"]
        density = fallback["density"]
        tag_size_dp = fallback["tag_size_dp"]
        margin_dp = fallback["margin_dp"]
        tag_size_px = tag_size_dp * density
        margin_px = margin_dp * density
        
        marker_real_width_mm = tag_size_px / xdpi * 25.4 if xdpi > 0 else 0.0
        marker_real_height_mm = tag_size_px / ydpi * 25.4 if ydpi > 0 else 0.0
        marker_x_distance_mm = (width_px - 2 * margin_px - tag_size_px) / xdpi * 25.4 if xdpi > 0 else 0.0
        
        result = {
            "screen_width_px": width_px,
            "screen_height_px": height_px,
            "density_dpi": density_dpi,
            "xdpi": xdpi,
            "ydpi": ydpi,
            "density": density,
            "tag_size_dp": tag_size_dp,
            "margin_dp": margin_dp,
            "tag_size_px": tag_size_px,
            "margin_px": margin_px,
            "MARKER_REAL_WIDTH_MM": marker_real_width_mm,
            "MARKER_REAL_HEIGHT_MM": marker_real_height_mm,
            "MARKER_X_DISTANCE_MM": marker_x_distance_mm,
            "device_model": _get_device_model(),
            "orientation": "portrait",
            "rotation": 0,
            "inset_left_px": 0.0,
            "inset_top_px": 0.0,
            "inset_right_px": 0.0,
            "inset_bottom_px": 0.0,
            "timestamp_ms": 0.0,
            "elapsed_realtime_ms": 0.0,
        }
        return result

    # Parse bem-sucedido; derivar campos restantes
    width_px = metrics["screen_width_px"]
    height_px = metrics["screen_height_px"]
    density_dpi = metrics["density_dpi"]
    xdpi, ydpi = _get_dpi_values(density_dpi)
    density = density_dpi / 160.0

    # Padrão para todos os devices (dp -> px)
    tag_size_dp = 120.0
    margin_dp = 16.0
    tag_size_px = tag_size_dp * density
    margin_px = margin_dp * density

    # Espera cálculos parecidos aos do app
    marker_real_width_mm = tag_size_px / xdpi * 25.4 if xdpi > 0 else 0.0
    marker_real_height_mm = tag_size_px / ydpi * 25.4 if ydpi > 0 else 0.0
    marker_x_distance_mm = (width_px - 2 * margin_px - tag_size_px) / xdpi * 25.4 if xdpi > 0 else 0.0

    result = {
        "screen_width_px": width_px,
        "screen_height_px": height_px,
        "density_dpi": density_dpi,
        "xdpi": xdpi,
        "ydpi": ydpi,
        "density": density,
        "tag_size_dp": tag_size_dp,
        "margin_dp": margin_dp,
        "tag_size_px": tag_size_px,
        "margin_px": margin_px,
        "MARKER_REAL_WIDTH_MM": marker_real_width_mm,
        "MARKER_REAL_HEIGHT_MM": marker_real_height_mm,
        "MARKER_X_DISTANCE_MM": marker_x_distance_mm,
        "device_model": _get_device_model(),
        # Campos extras para compatibilidade
        "orientation": "portrait",
        "rotation": 0,
        "inset_left_px": 0.0,
        "inset_top_px": 0.0,
        "inset_right_px": 0.0,
        "inset_bottom_px": 0.0,
        "timestamp_ms": 0.0,
        "elapsed_realtime_ms": 0.0,
    }

    logger.info(
        f"ADB device metrics loaded successfully: "
        f"{width_px:.0f}x{height_px:.0f} @ {density_dpi} dpi (density={density:.2f})"
    )
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    metrics = get_device_metrics_via_adb(device_type="flat")
    print(json.dumps(metrics, indent=2))
