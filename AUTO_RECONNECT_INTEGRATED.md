# Auto-Reconexão Integrada - Quick Guide

## ✅ Agora está automático!

A auto-reconexão já está integrada em 2 lugares:

### 1️⃣ **config.py** (Ao carregar configuração)
```python
# No início de config.py:
from drivers.device.adb_connection_manager import get_adb_manager

# Tenta reconectar (10 segundos timeout)
adb_mgr = get_adb_manager()
if not adb_mgr.is_connected():
    adb_mgr.auto_reconnect(max_wait_seconds=10.0)
```

**Quando**: Ao importar `config` em qualquer script  
**Timeout**: 10 segundos  
**Ação**: Se device offline, mata e reinicia daemon ADB

### 2️⃣ **run_rta_fsm.py** (Antes de começar execução)
```python
# No início de main():
from drivers.device.adb_connection_manager import get_adb_manager

adb_manager = get_adb_manager()

if not adb_manager.is_connected():
    logging.warning("Device não detectado. Tentando reconectar...")
    if adb_manager.auto_reconnect(max_wait_seconds=15.0):
        logging.info("✓ Reconexão bem-sucedida!")
    else:
        logging.error("✗ Falha ao reconectar")
        return 1  # Aborta se falhar
```

**Quando**: Ao executar RTA  
**Timeout**: 15 segundos  
**Ação**: Aborta com erro se falhar (safety)

---

## 🚀 Como Usar

### Cenário 1: Device Conectado
```bash
python state_machine/run_rta_fsm.py --device_type flat
```
✓ Detecta conexão → Prossegue normalmente

### Cenário 2: Device Offline
```bash
python state_machine/run_rta_fsm.py --device_type flat
```
⚠️ Detecta offline → Reconecta automaticamente (15s)  
✓ Sucesso → Prossegue com RTA  
✗ Falha → Aborta com mensagem clara

### Cenário 3: Device Offline, Quer Reconectar Rápido
```bash
python adb_auto_reconnect.py
```
Reconecta independentemente, depois:
```bash
python state_machine/run_rta_fsm.py --device_type flat
```

---

## 📊 Fluxo Automático

```
┌─────────────────────────────────────────┐
│ Executa run_rta_fsm.py                  │
├─────────────────────────────────────────┤
│                                         │
│ [1] Carrega config.py                   │
│     → Auto-reconnect (10s timeout)      │
│     → Se falha, continua                │
│                                         │
│ [2] main() começa                       │
│     → Verifica conexão                  │
│     → Se offline, auto-reconnect (15s)  │
│     → Se falha, aborta                  │
│                                         │
│ [3] RTA executa normalmente             │
│     → Device já está online             │
│                                         │
└─────────────────────────────────────────┘
```

---

## 🔧 Mensagens Esperadas

### Device Online
```
Verificando conexão ADB...
✓ Device já conectado
[RTA prossegue...]
```

### Device Offline (Reconecta com Sucesso)
```
Verificando conexão ADB...
Device não detectado. Tentando reconectar...
  [1/4] Matando daemon ADB...
  [2/4] Iniciando daemon ADB...
  [3/4] Aguardando device ficar online...
  [4/4] Device detectado!
✓ Reconexão bem-sucedida!
[RTA prossegue...]
```

### Device Offline (Falha na Reconexão)
```
Verificando conexão ADB...
Device não detectado. Tentando reconectar...
  [1/4] Matando daemon ADB...
  [2/4] Iniciando daemon ADB...
  [3/4] Aguardando device ficar online...
✗ Falha ao reconectar ao device. Verifique:
   - Device conectado via USB
   - USB Debugging habilitado
   - Autorização concedida no device

[Script aborta - exit code 1]
```

---

## 🎯 Resumo

| Situação | O que Acontece |
|----------|---------------|
| Device online | ✓ Prossegue normalmente |
| Device offline, mas conectável | ✓ Reconecta automaticamente |
| Device offline, não conectável | ✗ Aborta com erro claro |

**Tudo transparente para o usuário!** 🚀

---

## 📝 Para Integrar em Outro Script

Se você tiver outro script que precisa se conectar:

```python
from drivers.device.adb_connection_manager import get_adb_manager

def main():
    adb_manager = get_adb_manager()
    
    # Garante conexão
    if not adb_manager.is_connected():
        if not adb_manager.auto_reconnect(max_wait_seconds=15.0):
            print("✗ Falha ao conectar")
            return 1
    
    # Prossegue com suas operações
    print("✓ Device conectado, iniciando operações...")
    ...
```

Done! ✅
