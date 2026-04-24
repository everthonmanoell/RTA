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
    Executa comando ADB e imprime o debug no terminal para diagnosticarmos o problema.
    """
    try:
        # print(f"\n[DEBUG] Executando: adb {' '.join(cmd)}")
        result = subprocess.run(
            ["adb"] + cmd,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        # print(f"[DEBUG] Retorno (código {result.returncode}):")
        # if result.stdout:
        #     print(f"   STDOUT: {result.stdout.strip()}")
        # if result.stderr:
        #     print(f"   STDERR: {result.stderr.strip()}")
            
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception as exc:
        print(f"[DEBUG] Falha fatal ao tentar executar o ADB no Windows: {exc}")
        return ""


def _parse_display_metrics() -> Optional[dict]:
    """
    Extrai DisplayMetrics via `adb shell dumpsys display`.
    
    Busca a resolução e os valores físicos reais de DPI (xdpi, ydpi) 
    para garantir cálculos milimétricos precisos no robô.
    
    Returns:
        Dict com screen_width_px, screen_height_px, density_dpi, xdpi, ydpi.
        None se falhar.
    """
    # Lemos direto do dumpsys display, pois é o único lugar onde 
    # o Android expõe os PPI físicos (xdpi e ydpi) com decimais.
    output = _run_adb_command(["shell", "dumpsys", "display"])
    if not output:
        return None

    # 1. Extração da Resolução em Pixels
    # Cobrir múltiplos formatos comuns em diferentes versões de Android/OEM:
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

    # 2. Extração da Densidade Lógica e Física (PPI)
    # Padrão alvo para pegar tudo exato: "density 400 (393.5 x 394.2) dpi"
    physical_dpi_pattern = r"density\s+(\d+)\s*\(\s*([\d.]+)\s*x\s*([\d.]+)\s*\)\s*dpi"
    match_physical = re.search(physical_dpi_pattern, output)
    
    density_dpi: Optional[int] = None
    xdpi: Optional[float] = None
    ydpi: Optional[float] = None

    if match_physical:
        # Sucesso! Achamos os valores com precisão decimal
        density_dpi = int(match_physical.group(1))
        xdpi = float(match_physical.group(2))
        ydpi = float(match_physical.group(3))
    else:
        # Fallback de segurança: se o celular/emulador não tiver o xdpi exposto,
        # voltamos a usar o DPI lógico como aproximação.
        fallback_patterns = [
            r"densityDpi\s*=?\s*(\d+)",
            r"density\s*:?\s*(\d+)\s*dpi",
            r"density\s+(\d+)\s*\("
        ]
        for pattern in fallback_patterns:
            match_fallback = re.search(pattern, output)
            if match_fallback:
                density_dpi = int(match_fallback.group(1))
                xdpi = float(density_dpi)
                ydpi = float(density_dpi)
                break

    # Se faltar algum dado vital, aborta para o plano de fallback seguro do script
    if width_px is None or height_px is None or density_dpi is None:
        return None

    return {
        "screen_width_px": width_px,
        "screen_height_px": height_px,
        "density_dpi": density_dpi,
        "xdpi": xdpi,
        "ydpi": ydpi,
    }


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
    """
    metrics = _parse_display_metrics()
    
    # Fator de correção do ArUco (Área preta vs Borda branca)
    # Baseado na calibração física com paquímetro (~15mm / ~19.16mm)
    ARUCO_FILL_RATIO = 0.782

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
        
        total_width_mm = tag_size_px / xdpi * 25.4 if xdpi > 0 else 0.0
        total_height_mm = tag_size_px / ydpi * 25.4 if ydpi > 0 else 0.0
        
        marker_real_width_mm = total_width_mm * ARUCO_FILL_RATIO
        marker_real_height_mm = total_height_mm * ARUCO_FILL_RATIO
        marker_x_distance_mm = (width_px - 2 * margin_px - tag_size_px) / xdpi * 25.4 if xdpi > 0 else 0.0
        
        return {
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

    # Parse bem-sucedido; derivar campos restantes
    width_px = metrics["screen_width_px"]
    height_px = metrics["screen_height_px"]
    density_dpi = metrics["density_dpi"]
    xdpi = metrics["xdpi"]
    ydpi = metrics["ydpi"]
    density = density_dpi / 160.0

    # Padrão para todos os devices (dp -> px)
    tag_size_dp = 120.0
    margin_dp = 16.0
    tag_size_px = tag_size_dp * density
    margin_px = margin_dp * density

    # Tamanho total da imagem gerada pelo Android
    total_width_mm = tag_size_px / xdpi * 25.4 if xdpi > 0 else 0.0
    total_height_mm = tag_size_px / ydpi * 25.4 if ydpi > 0 else 0.0

    # Aplicando o fator de correção para extrair apenas a área preta do ArUco
    marker_real_width_mm = total_width_mm * ARUCO_FILL_RATIO
    marker_real_height_mm = total_height_mm * ARUCO_FILL_RATIO
    
    # A distância X usa o total da imagem, pois a borda branca ocupa espaço físico na tela
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

    logger.info(
        f"ADB device metrics loaded successfully: "
        f"{width_px:.0f}x{height_px:.0f} @ {density_dpi} dpi (density={density:.2f})"
    )
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    metrics = get_device_metrics_via_adb(device_type="flat")
    print(json.dumps(metrics, indent=2))
