#!/usr/bin/env python3
"""
ADB Auto-Reconnect: Reconecta automaticamente ao device.

Execute este script se o device não estiver sendo detectado.
"""

import sys
import time
from drivers.device.adb_connection_manager import get_adb_manager


def main():
    print("=" * 70)
    print("ADB Auto-Reconnect")
    print("=" * 70)

    manager = get_adb_manager()

    print("\n[1] Verificando conexão atual...")
    if manager.is_connected():
        print("✓ Device já está conectado!")
        return 0

    print("✗ Device não detectado\n")
    print("[2] Iniciando reconexão automática...")
    print("    (Certifique-se que o device está conectado via USB)\n")

    if manager.auto_reconnect(max_wait_seconds=20.0):
        print("\n✓ Reconexão bem-sucedida!")
        print("\nAgora você pode rodar:")
        print("  python test_adb_optimization.py")
        print("  python state_machine/run_rta_fsm.py")
        return 0
    else:
        print("\n✗ Falha ao reconectar")
        print("\nDicas para resolver:")
        print("  1. Conecte o device via USB (cabo de boa qualidade)")
        print("  2. Habilite USB Debugging:")
        print("     Settings → Developer Options → USB Debugging")
        print("  3. Autorize a conexão no device")
        print("  4. Tente novamente: python adb_auto_reconnect.py")
        print("\nOu tente manualmente:")
        print("  adb kill-server && adb start-server")
        print("  adb devices")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n✗ Interrompido pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Erro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
