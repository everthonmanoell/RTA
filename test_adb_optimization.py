#!/usr/bin/env python3
"""
ADB Auto-Reconnect Test

Testa apenas a reconexão automática ao ADB.
Execute este script para validar se a reconexão está funcionando.
"""

import time
import sys
from drivers.device.adb_connection_manager import get_adb_manager


def test_auto_reconnect():
    """Testa auto-reconnect do ADB."""
    print("\n" + "=" * 70)
    print("ADB Auto-Reconnect Test")
    print("=" * 70)

    manager = get_adb_manager()

    print("\n[1] Verificando conexão atual...")
    is_connected = manager.is_connected()

    if is_connected:
        print("✓ Device já está conectado!")
        return True

    print("✗ Device não está conectado")
    print("\n[2] Iniciando reconexão automática...")
    print("    Aguardando até 15 segundos...\n")

    start_time = time.time()
    success = manager.auto_reconnect(max_wait_seconds=15.0)
    elapsed = time.time() - start_time

    print()
    print("=" * 70)

    if success:
        print(f"✓ SUCESSO! Reconectado em {elapsed:.1f}s")
        print("=" * 70)
        print("\nAgora você pode rodar:")
        print("  python state_machine/run_rta_fsm.py --device_type flat")
        return True
    else:
        print(f"✗ FALHA na reconexão após {elapsed:.1f}s")
        print("=" * 70)
        print("\nDicas para resolver:")
        print("  1. Conecte o device via USB (cabo de boa qualidade)")
        print("  2. Habilite USB Debugging:")
        print("     Settings → Developer Options → USB Debugging")
        print("  3. Autorize a conexão no device")
        print("  4. Tente novamente: python test_adb_optimization.py")
        return False


def main():
    """Executa o teste."""
    try:
        success = test_auto_reconnect()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n✗ Teste interrompido pelo usuário")
        return 1
    except Exception as e:
        print(f"\n✗ Erro: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
