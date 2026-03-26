"""
DeviceAppManager: Gerencia a aplicação RTA no dispositivo móvel.

Controla o ciclo de vida do RTA_app, inicia com configurações,
e coordena feedback visual com o sistema de alinhamento.
"""

import logging
import subprocess
import time
from typing import List, Optional


class DeviceAppManager:
    """
    Gerencia a aplicação RTA no dispositivo móvel.
    
    Responsabilidades:
    - Iniciar RTA_app com configuração (device_type)
    - Aguardar renderização dos markers
    - Monitorar estado da tela
    - Capturar feedback do app
    """
    
    # Package name do RTA_app
    APP_PACKAGE = "com.example.rta"
    APP_ACTIVITY = "com.example.rta.MainActivity"
    
    # Tipos de dispositivo suportados
    DEVICE_TYPES = {
        "flat": 4,      # 4 markers nos cantos
        "foldable": 8,  # 8 markers (4 em cada tela)
        "one": 1,
        "two": 2,
        "three": 3,
        "six": 6,
        "seven": 7,
    }
    
    def __init__(self, device_interface=None):
        """
        Initialize DeviceAppManager.
        
        Args:
            device_interface: Interface com o dispositivo (para ADB commands).
        """
        self.device = device_interface
        self.logger = logging.getLogger(__name__)
        self.current_device_type = "flat"
        self.expected_marker_count = self.DEVICE_TYPES["flat"]
    
    def install_app(self) -> bool:
        """
        Instala o RTA_app no dispositivo.
        
        Executa: ./gradlew installDebug (do RTA_app/)
        
        Returns:
            bool: True se instalação bem-sucedida.
        """
        try:
            self.logger.info("Instalando RTA_app...")
            # Assumindo que estamos no diretório raiz do projeto
            result = subprocess.run(
                ["gradlew.bat", "installDebug"],
                cwd="RTA_app",
                capture_output=True,
                timeout=120,
                text=True
            )
            
            if result.returncode == 0:
                self.logger.info("RTA_app instalado com sucesso")
                return True
            else:
                self.logger.error(f"Falha na instalação: {result.stderr}")
                return False
        
        except Exception as e:
            self.logger.error(f"Erro ao instalar: {e}")
            return False
    
    def start_app(self, device_type: str = "flat") -> bool:
        """
        Inicia o RTA_app com configuração especificada.
        
        Args:
            device_type (str): Tipo de dispositivo (flat, foldable, etc.)
            
        Returns:
            bool: True se iniciou com sucesso.
        """
        if device_type not in self.DEVICE_TYPES:
            self.logger.error(f"Device type inválido: {device_type}")
            return False
        
        self.current_device_type = device_type
        self.expected_marker_count = self.DEVICE_TYPES[device_type]
        
        try:
            self.logger.info(f"Iniciando RTA_app com device_type='{device_type}'")
            
            cmd = [
                "adb", "shell", "am", "start",
                "-n", f"{self.APP_PACKAGE}/.MainActivity",
                "--es", "device_type", device_type
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"App iniciado com {self.expected_marker_count} markers")
                # Aguardar renderização
                time.sleep(2)
                return True
            else:
                self.logger.error(f"Falha ao iniciar app: {result.stderr}")
                return False
        
        except Exception as e:
            self.logger.error(f"Erro ao iniciar app: {e}")
            return False
    
    def stop_app(self) -> bool:
        """
        Para a aplicação RTA.
        
        Returns:
            bool: True se parou com sucesso.
        """
        try:
            self.logger.info("Parando RTA_app...")
            cmd = ["adb", "shell", "am", "force-stop", self.APP_PACKAGE]
            result = subprocess.run(cmd, capture_output=True, timeout=5, text=True)
            
            if result.returncode == 0:
                self.logger.info("App parado")
                return True
            else:
                self.logger.error(f"Falha ao parar app: {result.stderr}")
                return False
        
        except Exception as e:
            self.logger.error(f"Erro ao parar app: {e}")
            return False
    
    def get_expected_marker_count(self) -> int:
        """
        Retorna o número esperado de markers para a configuração atual.
        
        Returns:
            int: Número de markers.
        """
        return self.expected_marker_count
    
    def take_screenshot(self, filename: str = "rta_screen.png") -> Optional[str]:
        """
        Captura screenshot da tela atual do dispositivo.
        
        Args:
            filename (str): Nome do arquivo para salvar.
            
        Returns:
            Optional[str]: Path do arquivo salvo ou None se falha.
        """
        try:
            self.logger.debug(f"Capturando screenshot: {filename}")
            
            # Salvar no dispositivo
            device_path = f"/sdcard/{filename}"
            cmd_cap = ["adb", "shell", "screencap", "-p", device_path]
            
            result = subprocess.run(cmd_cap, capture_output=True, timeout=5, text=True)
            if result.returncode != 0:
                self.logger.error("Falha ao capturar screenshot")
                return None
            
            # Trazer para máquina local
            local_path = f"log_images/{filename}"
            cmd_pull = ["adb", "pull", device_path, local_path]
            
            result = subprocess.run(cmd_pull, capture_output=True, timeout=5, text=True)
            if result.returncode == 0:
                self.logger.debug(f"Screenshot salvo: {local_path}")
                return local_path
            else:
                self.logger.error("Falha ao baixar screenshot")
                return None
        
        except Exception as e:
            self.logger.error(f"Erro ao capturar screenshot: {e}")
            return None
    
    def is_app_running(self) -> bool:
        """
        Verifica se RTA_app está em execução.
        
        Returns:
            bool: True se app está rodando.
        """
        try:
            cmd = ["adb", "shell", "pidof", self.APP_PACKAGE]
            result = subprocess.run(cmd, capture_output=True, timeout=5, text=True)
            return result.returncode == 0
        
        except Exception as e:
            self.logger.error(f"Erro ao verificar app: {e}")
            return False
    
    def reset_screen(self) -> bool:
        """
        Reseta a tela de markers (clica no botão RESET do app).
        
        Simula clique no botão RESET para voltar todos os markers visíveis.
        
        Returns:
            bool: True se reset bem-sucedido.
        """
        try:
            self.logger.info("Resetando tela de markers...")
            # O botão RESET está no centro da tela
            # Coordenadas aproximadas para uma tela padrão (1080x2400)
            x, y = 540, 1200
            
            cmd = ["adb", "shell", "input", "tap", str(x), str(y)]
            result = subprocess.run(cmd, capture_output=True, timeout=5, text=True)
            
            time.sleep(1)  # Aguardar redação
            return result.returncode == 0
        
        except Exception as e:
            self.logger.error(f"Erro ao reset: {e}")
            return False
    
    def bring_to_foreground(self) -> bool:
        """
        Traz a aplicação para foreground.
        
        Returns:
            bool: True se bem-sucedido.
        """
        try:
            cmd = [
                "adb", "shell", "am", "start",
                "-n", f"{self.APP_PACKAGE}/.MainActivity"
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=5, text=True)
            return result.returncode == 0
        
        except Exception as e:
            self.logger.error(f"Erro ao trazer app para foreground: {e}")
            return False
    
    def wait_for_app_ready(self, timeout: int = 10) -> bool:
        """
        Aguarda até que o app esteja pronto (renderização completa).
        
        Args:
            timeout (int): Máximo de segundos para aguardar.
            
        Returns:
            bool: True se app ficou pronto.
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.is_app_running():
                self.logger.info("App está pronto")
                return True
            
            time.sleep(0.5)
        
        self.logger.warning("Timeout aguardando app ficar pronto")
        return False
