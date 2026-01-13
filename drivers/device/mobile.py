from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable, Iterator, Optional


@dataclass(frozen=True)
class GetEvent:
    """Evento básico emitido por `adb shell getevent`.

    O formato típico de linha é: 
    "/dev/input/eventX: TIPO CODIGO VALOR"
    """

    device: str
    tipo: str
    codigo: str
    valor: str

    @property
    def valor_decimal(self) -> Optional[int]:
        """Converte o valor de hexadecimal para inteiro quando possível."""
        try:
            return int(self.valor, 16)
        except ValueError:
            return None

    @property
    def is_axis_x(self) -> bool:
        """Retorna True quando o código representa eixo X (0035 é comum)."""
        return self.codigo.lower() == "0035"

    @property
    def is_touch_up(self) -> bool:
        """Heurística simples para "dedo levantado" (EV_KEY=0001 e valor zero)."""
        return self.tipo.lower() == "0001" and self.valor == "00000000"


def start_getevent_process() -> subprocess.Popen:
    """Inicia o processo `adb shell getevent` em modo texto e leitura linha-a-linha."""
    return subprocess.Popen(
        ["adb", "shell", "getevent"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def parse_getevent_line(line: str) -> Optional[GetEvent]:
    """Converte uma linha crua do getevent em um objeto `GetEvent`.

    Espera algo como: 
      "/dev/input/event3: 0003 0035 00000abc"
    Retorna None se o formato não bater.
    """
    raw = line.strip()
    if not raw:
        return None

    parts = raw.split()
    if len(parts) < 4:
        return None

    device = parts[0].rstrip(":")
    tipo = parts[1]
    codigo = parts[2]
    valor = parts[3]

    return GetEvent(device=device, tipo=tipo, codigo=codigo, valor=valor)


def iter_getevent_lines(proc: subprocess.Popen) -> Iterator[str]:
    """Itera linhas do stdout até o processo encerrar."""
    assert proc.stdout is not None
    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            yield line


class MobileInputListener:
    """Listener modular para eventos do `adb shell getevent`.

    - `device_filter`: filtra pelo caminho do dispositivo (ex: "event3").
    - Métodos principais: `start()`, `stop()`, `iter_events()`, `run_loop()`.
    """

    def __init__(self, device_filter: Optional[str] = "event3") -> None:
        self._device_filter = device_filter
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        if self._proc is None:
            self._proc = start_getevent_process()

    def stop(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
            finally:
                self._proc = None

    def iter_events(self) -> Iterator[GetEvent]:
        if self._proc is None:
            self.start()
        assert self._proc is not None

        for line in iter_getevent_lines(self._proc):
            evt = parse_getevent_line(line)
            if not evt:
                continue
            if self._device_filter and self._device_filter not in evt.device:
                continue
            yield evt

    def run_loop(self, on_event: Callable[[GetEvent], None]) -> None:
        """Executa um loop chamando `on_event` para cada evento filtrado."""
        try:
            for evt in self.iter_events():
                on_event(evt)
        finally:
            self.stop()


# Execução standalone preservando o comportamento original
def _default_on_event(evt: GetEvent) -> None:
    # Exemplo: Detectar coordenada X (0035 é comum para ABS_MT_POSITION_X)
    if evt.is_axis_x and evt.valor_decimal is not None:
        print(f"Movimento no Eixo X detectado! Valor: {evt.valor_decimal}")
    # Exemplo: Detectar "Touch Up" (dedo levantou)
    elif evt.is_touch_up:
        print("--> O dedo foi levantado da tela!")


def main() -> None:
    print("--- Iniciando escuta do ADB (Pressione Ctrl+C para parar) ---")
    listener = MobileInputListener(device_filter="/dev/input/event3")
    try:
        listener.run_loop(_default_on_event)
    except KeyboardInterrupt:
        print("\nParando o listener...")
        listener.stop()


if __name__ == "__main__":
    main()