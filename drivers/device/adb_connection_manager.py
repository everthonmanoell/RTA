"""
ADB Connection Manager: Gerencia conexão eficiente com dispositivo via ADB.

Implementa:
- Connection pooling (mantém conexões ativas)
- Caching de resultados
- Heartbeat para detectar desconexões
- Exponential backoff para retries
"""

import logging
import subprocess
import time
import threading
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class CachedMetric:
    """Métrica cacheada com timestamp de expiração."""
    value: str
    cached_at: datetime
    ttl_seconds: int = 30  # Time-to-live padrão

    def is_expired(self) -> bool:
        return datetime.now() - self.cached_at > timedelta(seconds=self.ttl_seconds)


class ADBConnectionManager:
    """
    Gerenciador de conexão ADB com otimizações:
    - Mantém daemon ADB vivo sem reiniciar constantemente
    - Caching de métricas comuns
    - Heartbeat para monitorar conexão
    - Exponential backoff para fallback
    """

    def __init__(self, device_serial: Optional[str] = None):
        """
        Initialize ADB Connection Manager.

        Args:
            device_serial: Serial do dispositivo (se None, usa qualquer dispositivo conectado)
        """
        self.device_serial = device_serial
        self.logger = logging.getLogger(__name__)
        self._cache: Dict[str, CachedMetric] = {}
        self._lock = threading.Lock()
        self._connected = False
        self._last_heartbeat = None
        self._heartbeat_thread = None

    def is_connected(self) -> bool:
        """Verifica se dispositivo está conectado (com retry simples)."""
        for attempt in range(2):  # Tenta até 2 vezes
            try:
                cmd = ["adb", "get-state"]
                if self.device_serial:
                    cmd = ["adb", "-s", self.device_serial, "get-state"]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=2.0
                )
                self._connected = result.returncode == 0 and "device" in result.stdout.lower()
                self._last_heartbeat = datetime.now()
                return self._connected
            except Exception as e:
                if attempt < 1:
                    time.sleep(0.1)  # Pequeno delay antes de retry
                    continue
                self.logger.debug(f"Heartbeat check falhou: {e}")
                self._connected = False
                return False
        return False

    def auto_reconnect(self, max_wait_seconds: float = 15.0) -> bool:
        """
        Tenta reconectar automaticamente ao ADB se desconectado.

        Estratégia:
        1. Verifica se já está conectado
        2. Se não, tenta kill-server + start-server
        3. Aguarda device ficar online (com timeout)

        Args:
            max_wait_seconds: Tempo máximo para aguardar reconexão

        Returns:
            True se conexão estabelecida, False se falhou
        """
        # Se já conectado, retorna rápido
        if self.is_connected():
            self.logger.info("✓ Device já conectado")
            return True

        self.logger.info("Device não detectado. Tentando reconectar ADB...")

        try:
            # 1. Kill server (limpa conexões travadas)
            self.logger.info("  [1/4] Matando daemon ADB...")
            subprocess.run(["adb", "kill-server"], check=False, timeout=10)
            time.sleep(1.0)

            # 2. Start server (reinicia limpo)
            self.logger.info("  [2/4] Iniciando daemon ADB...")
            subprocess.run(["adb", "start-server"], check=False, timeout=10)
            time.sleep(1.0)

            # 2b. Force device discovery with adb devices
            self.logger.info("  [2b] Forçando descoberta de devices...")
            subprocess.run(["adb", "devices"], check=False, timeout=5)
            time.sleep(0.5)

            # 3. Aguarda device ficar online
            self.logger.info("  [3/4] Aguardando device ficar online...")
            start_time = time.time()

            while time.time() - start_time < max_wait_seconds:
                try:
                    # Tenta listar devices
                    result = subprocess.run(
                        ["adb", "devices"],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )

                    # Se houver device online, sucesso!
                    for line in result.stdout.splitlines():
                        if "device" in line and not line.startswith("List"):
                            self.logger.info("  [4/4] Device detectado!")
                            time.sleep(1.0)  # Aguarda estabilização

                            # Valida conexão final
                            if self.is_connected():
                                self.logger.info("✓ Reconexão bem-sucedida!")
                                return True

                    # Aguarda antes de próxima tentativa
                    time.sleep(1.0)

                except Exception as e:
                    self.logger.debug(f"Erro ao listar devices: {e}")
                    time.sleep(1.0)

            self.logger.warning(
                "✗ Timeout ao aguardar device (máximo: %ds)", max_wait_seconds)
            return False

        except Exception as e:
            self.logger.error(f"✗ Erro ao reconectar: {e}")
            return False

    def execute_shell_command(
        self,
        cmd: str,
        timeout: float = 1.5,
        retries: int = 2,
        cache_key: Optional[str] = None,
        cache_ttl: int = 30
    ) -> str:
        """
        Executa comando shell no dispositivo com retry e cache otimizados.

        Args:
            cmd: Comando shell a executar
            timeout: Timeout em segundos
            retries: Número de tentativas
            cache_key: Chave para cache (se None, não cacheia)
            cache_ttl: Tempo de vida do cache em segundos

        Returns:
            Output do comando ou string vazia se falhar
        """
        # Verifica cache antes de executar
        if cache_key and cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired():
                self.logger.debug(f"Cache hit: {cache_key}")
                return cached.value

        # Retry com exponential backoff
        backoff_times = [0.05, 0.1, 0.2]
        output = ""

        for attempt in range(retries):
            try:
                adb_cmd = ["adb"]
                if self.device_serial:
                    adb_cmd = ["adb", "-s", self.device_serial]

                adb_cmd.extend(["shell", cmd])

                result = subprocess.run(
                    adb_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )

                if result.returncode == 0:
                    output = result.stdout.strip()
                    # Cache resultado se sucesso
                    if cache_key and output:
                        with self._lock:
                            self._cache[cache_key] = CachedMetric(
                                value=output,
                                cached_at=datetime.now(),
                                ttl_seconds=cache_ttl
                            )
                    return output

                # Falha, mas pode tentar novamente
                if attempt < retries - 1:
                    backoff = backoff_times[min(
                        attempt, len(backoff_times) - 1)]
                    time.sleep(backoff)

            except subprocess.TimeoutExpired:
                if attempt < retries - 1:
                    time.sleep(
                        backoff_times[min(attempt, len(backoff_times) - 1)])
                continue
            except Exception as e:
                self.logger.debug(f"Command falhou: {e}")
                if attempt < retries - 1:
                    time.sleep(
                        backoff_times[min(attempt, len(backoff_times) - 1)])
                continue

        return output

    def get_device_property(self, prop: str, cache_ttl: int = 300) -> str:
        """
        Obtém propriedade do device com cache.

        Args:
            prop: Nome da propriedade (ex: ro.product.model)
            cache_ttl: Tempo de vida do cache em segundos (padrão 5 min)

        Returns:
            Valor da propriedade ou string vazia se falhar
        """
        cache_key = f"property_{prop}"
        return self.execute_shell_command(
            f"getprop {prop}",
            cache_key=cache_key,
            cache_ttl=cache_ttl
        )

    def ensure_connection(self, max_wait_seconds: float = 3.0) -> bool:
        """
        Garante que a conexão está ativa com retry otimizado.

        Args:
            max_wait_seconds: Tempo máximo de espera

        Returns:
            True se conexão estabelecida ou mantida
        """
        start_time = time.time()

        # Primeira tentativa rápida
        if self.is_connected():
            return True

        # Retry com backoff crescente
        backoff_times = [0.1, 0.2, 0.4, 0.8]
        for i, backoff in enumerate(backoff_times):
            if time.time() - start_time > max_wait_seconds:
                break

            time.sleep(backoff)
            if self.is_connected():
                return True

        # Last resort: limpa daemon (sem full restart)
        self.logger.warning(
            "ADB connection lost. Clearing stale connections...")
        try:
            subprocess.run(["adb", "disconnect"], check=False, timeout=1)
            time.sleep(0.5)
            return self.is_connected()
        except Exception:
            return False

    def clear_cache(self, pattern: Optional[str] = None):
        """Limpa cache."""
        with self._lock:
            if pattern is None:
                self._cache.clear()
            else:
                keys_to_delete = [
                    k for k in self._cache.keys() if pattern in k]
                for k in keys_to_delete:
                    del self._cache[k]

    def start_heartbeat(self, interval_seconds: float = 5.0):
        """
        Inicia thread de heartbeat para manter conexão ativa.

        Args:
            interval_seconds: Intervalo entre heartbeats
        """
        def _heartbeat_loop():
            while self._heartbeat_thread is not None:
                try:
                    self.is_connected()
                    time.sleep(interval_seconds)
                except Exception:
                    time.sleep(1)

        if self._heartbeat_thread is None:
            self._heartbeat_thread = threading.Thread(
                target=_heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()
            self.logger.info("ADB heartbeat started")

    def stop_heartbeat(self):
        """Para thread de heartbeat."""
        self._heartbeat_thread = None
        self.logger.info("ADB heartbeat stopped")


# Singleton global para reutilizar conexão
_global_adb_manager: Optional[ADBConnectionManager] = None


def get_adb_manager(device_serial: Optional[str] = None) -> ADBConnectionManager:
    """Retorna instância global do ADB Connection Manager."""
    global _global_adb_manager
    if _global_adb_manager is None:
        _global_adb_manager = ADBConnectionManager(device_serial)
        _global_adb_manager.start_heartbeat()
    return _global_adb_manager
