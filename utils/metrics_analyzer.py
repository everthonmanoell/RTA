import json
import numpy as np
from typing import List, Dict

class TCCMetricsAnalyzer:
    def __init__(self, json_filepaths: List[str]):
        """
        Carrega as execuções de um modelo específico para análise comparativa.
        """
        self.executions = []
        for path in json_filepaths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.executions.append(json.load(f))
            except Exception as e:
                print(f"Erro ao carregar {path}: {e}")

    def calculate_spatial_repeatability(self) -> Dict:
        """
        MÉTRICA 1: Calcula o desvio padrão de X, Y e Z para cada quina da tela útil.
        """
        # Dicionário para acumular coordenadas de todas as rodadas
        # Estrutura: quina -> eixo -> lista de valores
        history = {
            corner: {axis: [] for axis in ['x', 'y', 'z']}
            for corner in ["top_left", "top_right", "bottom_left", "bottom_right"]
        }

        for run in self.executions:
            corners = run.get("physical_screen_corners_mm", {})
            for name, coords in corners.items():
                if name in history:
                    history[name]['x'].append(coords['x'])
                    history[name]['y'].append(coords['y'])
                    history[name]['z'].append(coords['z'])

        results = {}
        for name, axes in history.items():
            if not axes['x']: continue
            results[name] = {
                "std_mm": {
                    "x": round(float(np.std(axes['x'])), 4),
                    "y": round(float(np.std(axes['y'])), 4),
                    "z": round(float(np.std(axes['z'])), 4)
                },
                "max_error_mm": {
                    "x": round(float(np.ptp(axes['x'])), 4), # Peak-to-peak (Max - Min)
                    "y": round(float(np.ptp(axes['y'])), 4),
                    "z": round(float(np.ptp(axes['z'])), 4)
                }
            }
        return results
    
    # =========================================================================
    # MÉTRICA 2: PLANARIDADE E INCLINAÇÃO (TILT Z)
    # =========================================================================
    def calculate_planar_tilt(self) -> Dict[str, float]:
        """
        Calcula o desnível (Tilt) da tela na bancada.
        Mede a diferença entre o ponto Z mais alto e o mais baixo da tela.
        Prova que o sistema de visão compensou a inclinação física do aparelho.
        """
        tilts_por_execucao = []
        
        for run in self.executions:
            corners = run.get("physical_screen_corners_mm", {})
            if not corners:
                continue
            
            # Coleta os valores de Z das 4 quinas nesta execução
            z_values = [
                coords["z"] for coords in corners.values() if "z" in coords
            ]
            
            if len(z_values) == 4:
                # O "Tilt" é a diferença entre a quina mais alta e a mais baixa
                tilt_mm = max(z_values) - min(z_values)
                tilts_por_execucao.append(tilt_mm)
                
        if not tilts_por_execucao:
            return {"media_tilt_mm": 0.0, "max_tilt_mm": 0.0}
            
        return {
            "media_tilt_mm": round(float(np.mean(tilts_por_execucao)), 4),
            "max_tilt_mm": round(float(np.max(tilts_por_execucao)), 4)
        }
    
    # =========================================================================
    # MÉTRICAS 3 E 4: QUALIDADE DO SINAL DE TOQUE E AMOSTRAGEM
    # =========================================================================
    def calculate_touch_quality(self) -> dict:
        drop_rates = []
        polling_rates = []
        
        for run in self.executions:
            interaction = run.get("device_touch_interaction")
            if not interaction:
                continue
            
            # Métrica 3: Drop Rate (Eventos DOWN extras)
            # O esperado num teste de swipe contínuo são 5 downs (4 arucos + 1 inicio de swipe)
            expected_downs = 5 
            actual_downs = interaction.get("down_count", 0)
            drops = max(0, actual_downs - expected_downs)
            drop_rates.append(drops)
            
            # Métrica 4: Polling Rate (Hz) -> Pontos lidos por segundo
            duration = interaction.get("duration_s", 0)
            points = interaction.get("total_points", 0)
            if duration > 0:
                polling_rates.append(points / duration)
                
        return {
            "media_drops_extras_por_execucao": round(float(np.mean(drop_rates)), 2) if drop_rates else 0.0,
            "media_polling_rate_hz": round(float(np.mean(polling_rates)), 2) if polling_rates else 0.0
        }
    
    # =========================================================================
    # MÉTRICA 4: TAXA DE AMOSTRAGEM DO DISPLAY (POLLING RATE)
    # =========================================================================
    def calculate_polling_rate(self) -> dict:
        """
        Calcula a frequência (Hz) com que o ecrã regista os toques.
        Prova a diferença de sensibilidade/hardware entre os aparelhos testados.
        """
        polling_rates = []
        
        for run in self.executions:
            interaction = run.get("device_touch_interaction")
            if not interaction:
                continue
            
            duration = interaction.get("duration_s", 0)
            points = interaction.get("total_points", 0)
            
            # Evita divisão por zero
            if duration > 0:
                hz = points / duration
                polling_rates.append(hz)
                
        if not polling_rates:
            return {"media_hz": 0.0, "max_hz": 0.0, "min_hz": 0.0}
            
        return {
            "media_hz": round(float(np.mean(polling_rates)), 2),
            "max_hz": round(float(np.max(polling_rates)), 2),
            "min_hz": round(float(np.min(polling_rates)), 2)
        }
    
    # =========================================================================
    # MÉTRICA 5: ÁREA DE CONTACTO (DEFORMAÇÃO DA FERRAMENTA / TOUCH MAJOR)
    # =========================================================================
    def calculate_touch_contact_area(self) -> dict:
        """
        Calcula as estatísticas da área de contacto capacitivo (touch_major).
        Como a pressão física costuma ser 0 no Android, o touch_major é a métrica 
        padrão para medir a deformação/força aplicada pela ferramenta do robô.
        """
        todas_as_areas = []
        
        for run in self.executions:
            interaction = run.get("device_touch_interaction")
            if not interaction:
                continue
            
            points = interaction.get("points", [])
            
            # Percorre todos os milissegundos gravados
            for pt in points:
                # Pegamos apenas eventos onde houve efetivamente um toque registrado
                tm = pt.get("touch_major", 0)
                if tm > 0:
                    todas_as_areas.append(tm)
                    
        if not todas_as_areas:
            return {
                "media_area": 0.0, 
                "desvio_padrao_area": 0.0, 
                "max_area": 0, 
                "min_area": 0
            }
            
        return {
            "media_area": round(float(np.mean(todas_as_areas)), 2),
            "desvio_padrao_area": round(float(np.std(todas_as_areas)), 2), # O mais importante para estabilidade
            "max_area": int(np.max(todas_as_areas)),
            "min_area": int(np.min(todas_as_areas))
        }
    
    # =========================================================================
    # MÉTRICA 6: EFICIÊNCIA DO SISTEMA (OVERHEAD VS. MOVIMENTO)
    # =========================================================================
    def calculate_system_efficiency(self) -> dict:
        """
        Calcula a proporção de tempo gasto em cálculos (Overhead de software/visão)
        vs. o tempo gasto na execução mecânica real do swipe.
        """
        tempos_totais = []
        tempos_mecanicos = []
        tempos_overhead = []
        
        for run in self.executions:
            total_time = run.get("execution_duration_s", 0)
            interaction = run.get("device_touch_interaction")
            
            if not interaction or total_time <= 0:
                continue
                
            mech_time = interaction.get("duration_s", 0)
            
            # O Overhead é tudo o que não foi tempo de toque
            overhead_time = max(0, total_time - mech_time)
            
            tempos_totais.append(total_time)
            tempos_mecanicos.append(mech_time)
            tempos_overhead.append(overhead_time)
            
        if not tempos_totais:
            return {"media_total_s": 0, "media_overhead_s": 0, "overhead_percentual": 0.0}
            
        media_total = np.mean(tempos_totais)
        media_overhead = np.mean(tempos_overhead)
        media_mecanico = np.mean(tempos_mecanicos)
        
        # Calcula a percentagem do tempo que foi gasta a "pensar" (Overhead)
        overhead_pct = (media_overhead / media_total) * 100 if media_total > 0 else 0
        mecanico_pct = (media_mecanico / media_total) * 100 if media_total > 0 else 0
        
        return {
            "media_tempo_total_s": round(float(media_total), 2),
            "media_tempo_mecanico_s": round(float(media_mecanico), 2),
            "media_tempo_overhead_s": round(float(media_overhead), 2),
            "percentual_mecanico": round(float(mecanico_pct), 2),
            "percentual_overhead": round(float(overhead_pct), 2)
        }
    
    # =========================================================================
    # MÉTRICA 7: TAXA DE SUCESSO DA CALIBRAÇÃO (RELIABILITY)
    # =========================================================================
    def calculate_success_rate(self) -> dict:
        """
        Calcula a proporção de testes que passaram na calibração com sucesso
        (calibration_succeed == True). Mede a robustez do sistema para cada modelo.
        """
        total_runs = len(self.executions)
        if total_runs == 0:
            return {"total_execucoes": 0, "sucessos": 0, "falhas": 0, "taxa_sucesso_percentual": 0.0}

        sucessos = 0
        for run in self.executions:
            # Usa o .get() com False por padrão, caso a chave não exista numa execução falhada
            if run.get("calibration_succeed", False) is True:
                sucessos += 1

        falhas = total_runs - sucessos
        taxa_sucesso = (sucessos / total_runs) * 100.0

        return {
            "total_execucoes": total_runs,
            "sucessos": sucessos,
            "falhas": falhas,
            "taxa_sucesso_percentual": round(float(taxa_sucesso), 2)
        }