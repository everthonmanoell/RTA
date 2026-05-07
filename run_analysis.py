import json
from pathlib import Path
from utils.metrics_analyzer import TCCMetricsAnalyzer

def run_full_analysis():
    BASE_DIR = Path("test_results")
    final_report = {}

    print("🔍 Iniciando Varredura de Resultados...")

    for model_folder in BASE_DIR.iterdir():
        if model_folder.is_dir():
            model_name = model_folder.name
            json_files = list(model_folder.glob("physical_calibration_map_*.json"))
            
            if len(json_files) < 2:
                print(f"⚠️  {model_name}: Dados insuficientes para análise ({len(json_files)} arquivos).")
                continue

            print(f"📊 Analisando {model_name} ({len(json_files)} execuções)...")
            
            paths = [str(p) for p in json_files]
            analyzer = TCCMetricsAnalyzer(paths)
            
            # Execução das Métricas Modulares
            final_report[model_name] = {
                "sample_size": len(json_files),
                "metric_1_repeatability": analyzer.calculate_spatial_repeatability(),
                "metric_2_planar_tilt": analyzer.calculate_planar_tilt(),
                "metric_3_4_touch_quality": analyzer.calculate_touch_quality(),
                "metric_4_polling_rate": analyzer.calculate_polling_rate(),
                "metric_5_contact_area": analyzer.calculate_touch_contact_area(),
                "metric_6_system_efficiency": analyzer.calculate_system_efficiency()

            }

    with open("relatorio_final_tcc.json", "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=4, ensure_ascii=False)
    
    print("\n✅ Análise concluída! Resultados em 'relatorio_final_tcc.json'.")

if __name__ == "__main__":
    run_full_analysis()