import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Style settings for more academic and beautiful charts
sns.set_theme(style="whitegrid")
plt.rcParams.update({'font.size': 12, 'figure.autolayout': True})

def load_data(json_path="relatorio_final_tcc.json"):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)

def plot_system_efficiency(df, output_dir):
    """GRAPH 1: System Efficiency (100% Stacked Bars)"""
    plt.figure(figsize=(10, 6))
    
    # Sort by most efficient (higher % mechanical)
    df_sorted = df.sort_values(by="percentual_mecanico", ascending=True)
    
    # Bar plot
    bars_mec = plt.barh(df_sorted["Modelo"], df_sorted["percentual_mecanico"], color="#2ca02c", label="Mechanical Action Time (%)")
    bars_over = plt.barh(df_sorted["Modelo"], df_sorted["percentual_overhead"], left=df_sorted["percentual_mecanico"], color="#d62728", label="Computational Overhead (%)")
    
    plt.title("Proportion of Time: Mechanical Action vs Computational Overhead", fontsize=14, fontweight="bold")
    plt.xlabel("Percentage (%)")
    plt.ylabel("Smartphone Models")
    plt.legend(loc="upper right")
    plt.xlim(0, 100)
    
    plt.savefig(output_dir / "grafico_1_eficiencia.png", dpi=300, bbox_inches="tight")
    plt.close()

def plot_planar_tilt(df, output_dir):
    """GRAPH 2: Bench Tilt/Planarity (Tilt)"""
    plt.figure(figsize=(10, 6))
    
    df_sorted = df.sort_values(by="tilt_medio_mm", ascending=False)
    
    ax = sns.barplot(x="tilt_medio_mm", y="Modelo", data=df_sorted, palette="Blues_r")
    
    plt.title("Bench Tilt (Average Tilt Z in millimeters)", fontsize=14, fontweight="bold")
    plt.xlabel("Average Tilt (mm)")
    plt.ylabel("Smartphone Models")
    
    # Adicionar os números no final de cada barra
    for i, v in enumerate(df_sorted["tilt_medio_mm"]):
        ax.text(v + 0.1, i, f"{v:.2f} mm", color='black', va='center')
        
    plt.savefig(output_dir / "grafico_2_tilt_z.png", dpi=300, bbox_inches="tight")
    plt.close()

def plot_polling_rate(df, output_dir):
    """GRAPH 3: Screen Sampling Rate (Polling Rate)"""
    plt.figure(figsize=(10, 6))
    
    df_sorted = df.sort_values(by="polling_rate_hz", ascending=False)
    
    ax = sns.barplot(x="polling_rate_hz", y="Modelo", data=df_sorted, palette="viridis")
    
    plt.title("Capacitive Sampling Rate (Polling Rate)", fontsize=14, fontweight="bold")
    plt.xlabel("Reading Frequency (Hz)")
    plt.ylabel("Smartphone Models")
    
    for i, v in enumerate(df_sorted["polling_rate_hz"]):
        ax.text(v + 0.5, i, f"{v:.1f} Hz", color='black', va='center')
        
    plt.savefig(output_dir / "grafico_3_polling_rate.png", dpi=300, bbox_inches="tight")
    plt.close()

def plot_repeatability_error(df, output_dir):
    """GRAPH 4: Repeatability (Average Spatial Standard Deviation)"""
    plt.figure(figsize=(10, 6))
    
    df_sorted = df.sort_values(by="erro_std_medio_mm", ascending=True)
    
    ax = sns.barplot(x="erro_std_medio_mm", y="Modelo", data=df_sorted, palette="Reds")
    
    plt.title("Robotic Repeatability (Average Standard Deviation X, Y, Z)", fontsize=14, fontweight="bold")
    plt.xlabel("Average Variation (mm) - Lower is more accurate")
    plt.ylabel("Smartphone Models")
    
    for i, v in enumerate(df_sorted["erro_std_medio_mm"]):
        ax.text(v + 0.01, i, f"{v:.3f} mm", color='black', va='center')
        
    plt.savefig(output_dir / "grafico_4_repetibilidade.png", dpi=300, bbox_inches="tight")
    plt.close()

def plot_success_rate(df, output_dir):
    """GRAPH 5: Calibration Success Rate (%)"""
    plt.figure(figsize=(10, 6))
    
    # Sort by most successful
    df_sorted = df.sort_values(by="taxa_sucesso_percentual", ascending=True)
    
    ax = sns.barplot(x="taxa_sucesso_percentual", y="Modelo", data=df_sorted, palette="YlGnBu")
    
    plt.title("Calibration Success Rate (%)", fontsize=14, fontweight="bold")
    plt.xlabel("Success (%)")
    plt.ylabel("Smartphone Models")
    plt.xlim(0, 105) # Para dar um espaço extra ao texto dos 100%
    
    for i, v in enumerate(df_sorted["taxa_sucesso_percentual"]):
        ax.text(v + 1, i, f"{v:.1f}%", color='black', va='center')
        
    plt.savefig(output_dir / "grafico_5_taxa_sucesso.png", dpi=300, bbox_inches="tight")
    plt.close()

def main():
    print("Starting chart generation...")
    data = load_data()
    
    # Extract data from JSON into tabular format (Pandas DataFrame)
    linhas = []
    for modelo, metricas in data.items():
            # Safe extraction
            eff = metricas.get("metric_6_system_efficiency", {})
            tilt = metricas.get("metric_2_planar_tilt", {})
            poll = metricas.get("metric_4_polling_rate", {})
            
            # Load metric 7 block
            suc = metricas.get("metric_7_success_rate", {}) 
            
            rep = metricas.get("metric_1_repeatability", {})
            std_list = []
            for corner in rep.values():
                if "std_mm" in corner:
                    std_list.extend([corner["std_mm"]["x"], corner["std_mm"]["y"], corner["std_mm"]["z"]])
            media_std = sum(std_list) / len(std_list) if std_list else 0
            
            # Dual search strategy for success rate
            taxa = metricas.get("taxa_sucesso_percentual", suc.get("taxa_sucesso_percentual", 0))
            
            linhas.append({
                "Modelo": modelo,
                "taxa_sucesso_percentual": taxa,
                "erro_std_medio_mm": media_std,
                "tilt_medio_mm": tilt.get("media_tilt_mm", 0),
                "polling_rate_hz": poll.get("media_hz", 0),
                "percentual_mecanico": eff.get("percentual_mecanico", 0),
                "percentual_overhead": eff.get("percentual_overhead", 0),
                "tempo_medio_s": eff.get("media_tempo_total_s", 0)
            })
        
    df = pd.DataFrame(linhas)
    
    # Create folder to save charts and tables
    out_dir = Path("graficos_tcc")
    out_dir.mkdir(exist_ok=True)
    
    # =========================================================================
    # EXPORTAÇÃO DA TABELA (Modelos nas Colunas, Métricas nas Linhas)
    # =========================================================================
    # 1. Define o 'Modelo' como índice e transpõe a matriz (.T)
    df_tabela = df.set_index("Modelo").T
    
    # 2. Renomeia as linhas para um formato amigável para o texto do TCC
    df_tabela.index.name = "Métricas Analisadas"
    df_tabela.rename(index={
        "taxa_sucesso_percentual": "Sucesso da Calibração (%)",
        "erro_std_medio_mm": "Erro de Repetibilidade (mm)",
        "tilt_medio_mm": "Desnível na Bancada - Tilt (mm)",
        "polling_rate_hz": "Taxa de Amostragem (Hz)",
        "tempo_medio_s": "Tempo Total de Execução (s)",
        "percentual_mecanico": "Tempo de Ação Mecânica (%)",
        "percentual_overhead": "Tempo de Overhead (%)"
    }, inplace=True)
    
    # 3. Salva em CSV (para abrir no Excel e formatar para o Word)
    caminho_csv = out_dir / "tabela_metricas_tcc.csv"
    df_tabela.to_csv(caminho_csv, sep=";", decimal=",") # Formato PT-BR (ponto e vírgula)
    
    # 4. Imprime no terminal em formato Markdown (fácil de visualizar)
    print("\n" + "="*80)
    print("📊 TABELA DE DADOS CONSOLIDADOS")
    print("="*80)
    print(df_tabela.to_markdown())
    print("="*80 + "\n")
    # =========================================================================

    # Generate charts
    plot_system_efficiency(df, out_dir)
    plot_planar_tilt(df, out_dir)
    plot_polling_rate(df, out_dir)
    plot_repeatability_error(df, out_dir)
    plot_success_rate(df, out_dir)
    
    print(f"✅ 5 Charts and 1 Data Table generated successfully in folder: '{out_dir.absolute()}'")

if __name__ == "__main__":
    main()

# def main():
#     print("Starting chart generation...")
#     data = load_data()
    
#     # Extract data from JSON into tabular format (Pandas DataFrame)
#     linhas = []
#     for modelo, metricas in data.items():
#             # Safe extraction
#             eff = metricas.get("metric_6_system_efficiency", {})
#             tilt = metricas.get("metric_2_planar_tilt", {})
#             poll = metricas.get("metric_4_polling_rate", {})
            
#             # Load metric 7 block
#             suc = metricas.get("metric_7_success_rate", {}) 
            
#             rep = metricas.get("metric_1_repeatability", {})
#             std_list = []
#             for corner in rep.values():
#                 if "std_mm" in corner:
#                     std_list.extend([corner["std_mm"]["x"], corner["std_mm"]["y"], corner["std_mm"]["z"]])
#             media_std = sum(std_list) / len(std_list) if std_list else 0
            
#             # Dual search strategy for success rate
#             # Search at root first; if not found, search within metric_7_success_rate
#             taxa = metricas.get("taxa_sucesso_percentual", suc.get("taxa_sucesso_percentual", 0))
            
#             linhas.append({
#                 "Modelo": modelo,
#                 "percentual_mecanico": eff.get("percentual_mecanico", 0),
#                 "percentual_overhead": eff.get("percentual_overhead", 0),
#                 "tilt_medio_mm": tilt.get("media_tilt_mm", 0),
#                 "polling_rate_hz": poll.get("media_hz", 0),
#                 "erro_std_medio_mm": media_std,
#                 "taxa_sucesso_percentual": taxa  # <-- Now it finds the value either way!
#             })
        
#     df = pd.DataFrame(linhas)
    
#     # Create folder to save charts
#     out_dir = Path("graficos_tcc")
#     out_dir.mkdir(exist_ok=True)
    
#     # Generate charts
#     plot_system_efficiency(df, out_dir)
#     plot_planar_tilt(df, out_dir)
#     plot_polling_rate(df, out_dir)
#     plot_repeatability_error(df, out_dir)
#     plot_success_rate(df, out_dir) # <-- NEW CHART CALL HERE
    
#     print(f"✅ 5 Charts generated successfully in folder: '{out_dir.absolute()}'")

# if __name__ == "__main__":
#     main()