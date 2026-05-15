"""
Exemplo prático: Como usar a otimização de conexão ADB

Mostra diferentes cenários e como a nova solução reduz tempo de fallback.
"""

import time
from drivers.device.adb_connection_manager import get_adb_manager
from utils.adb_device_metrics import get_device_metrics_via_adb


def example_1_quick_metrics():
    """Exemplo 1: Obter métricas do device (agora 2x mais rápido)."""
    print("\n=== Exemplo 1: Quick Device Metrics ===")
    start = time.time()

    metrics = get_device_metrics_via_adb(device_type="flat")

    elapsed = time.time() - start
    print(f"✓ Tempo: {elapsed:.2f}s")
    print(
        f"  Screen: {metrics.get('screen_width_px', 0):.0f}x{metrics.get('screen_height_px', 0):.0f}")
    print(f"  DPI: {metrics.get('density_dpi', 0)}")


def example_2_with_connection_manager():
    """Exemplo 2: Usar Connection Manager com cache automático."""
    print("\n=== Exemplo 2: Connection Manager with Caching ===")

    manager = get_adb_manager()

    # Primeira chamada (sem cache)
    start = time.time()
    model_1 = manager.get_device_property("ro.product.model")
    time_1 = time.time() - start
    print(f"✓ Primeira chamada: {time_1:.3f}s → {model_1}")

    # Segunda chamada (COM cache - muito mais rápida!)
    start = time.time()
    model_2 = manager.get_device_property("ro.product.model")
    time_2 = time.time() - start
    print(f"✓ Segunda chamada: {time_2:.3f}s → {model_2} (CACHED)")
    print(f"  Speedup: {time_1 / time_2:.1f}x mais rápido")


def example_3_shell_command_with_retry():
    """Exemplo 3: Executar comando shell com retry automático."""
    print("\n=== Exemplo 3: Shell Command with Auto-Retry ===")

    manager = get_adb_manager()

    start = time.time()
    result = manager.execute_shell_command(
        "getprop ro.vendor.extension_library",
        cache_key="vendor_info",
        cache_ttl=60
    )
    elapsed = time.time() - start

    print(f"✓ Tempo: {elapsed:.3f}s")
    print(f"  Resultado: {result or '(não encontrado)'}")


def example_4_ensure_connection():
    """Exemplo 4: Garantir que conexão está ativa."""
    print("\n=== Exemplo 4: Ensure Connection ===")

    manager = get_adb_manager()

    start = time.time()
    if manager.ensure_connection(max_wait_seconds=2.0):
        elapsed = time.time() - start
        print(f"✓ Conexão OK em {elapsed:.3f}s")
    else:
        print("✗ Falha ao conectar após 2 segundos")


def example_5_clear_cache():
    """Exemplo 5: Limpar cache quando necessário."""
    print("\n=== Exemplo 5: Cache Management ===")

    manager = get_adb_manager()

    # Obter valor (cacheado)
    val1 = manager.get_device_property("ro.product.model")
    print(f"✓ Valor cacheado: {val1}")

    # Limpar cache de propriedades
    manager.clear_cache("property_")

    # Próxima chamada será sem cache
    val2 = manager.get_device_property("ro.product.model")
    print(f"✓ Valor após clear: {val2} (re-fetched)")


def example_6_multiple_operations_optimized():
    """Exemplo 6: Múltiplas operações (otimizado vs não-otimizado)."""
    print("\n=== Exemplo 6: Multiple Operations Comparison ===")

    # Com Connection Manager + cache
    start = time.time()
    manager = get_adb_manager()

    # Todas as chamadas usam cache automaticamente
    model = manager.get_device_property("ro.product.model")
    marker = manager.get_device_property("ro.product.marketname")
    vendor = manager.get_device_property("ro.product.vendor.model")

    elapsed_optimized = time.time() - start

    print(f"✓ Com otimizações: {elapsed_optimized:.2f}s")
    print(f"  Model: {model}")
    print(f"  Market: {marker}")
    print(f"  Vendor: {vendor}")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("ADB Connection Optimization Examples")
    print("=" * 60)

    try:
        example_1_quick_metrics()
        example_2_with_connection_manager()
        example_3_shell_command_with_retry()
        example_4_ensure_connection()
        example_5_clear_cache()
        example_6_multiple_operations_optimized()

        print("\n" + "=" * 60)
        print("✓ Todos os exemplos executados com sucesso!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Erro: {e}")
        import traceback
        traceback.print_exc()
