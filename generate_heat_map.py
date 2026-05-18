import json
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
from pathlib import Path

def extrair_dados_crus(pasta_resultados: Path):
    x_crus, y_crus, z_crus = [], [], []
    pastas_modelos = [d for d in pasta_resultados.iterdir() if d.is_dir()]
    
    for pasta_modelo in pastas_modelos:
        arquivos_json = list(pasta_modelo.glob("*.json"))
        for arquivo in arquivos_json:
            try:
                with open(arquivo, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                    if "physical_screen_corners_mm" in dados and dados.get("calibration_succeed", False):
                        corners = dados["physical_screen_corners_mm"]
                        for quina, coords in corners.items():
                            if "x" in coords and "y" in coords and "z" in coords:
                                x_crus.append(coords["x"])
                                y_crus.append(coords["y"])
                                z_crus.append(coords["z"])
            except Exception as e:
                print(f"Erro ao ler {arquivo}: {e}")
                
    return np.array(x_crus), np.array(y_crus), np.array(z_crus)

def plot_3d_heatmap_from_raw(x_toques, y_toques, z_toques, output_dir=Path("graficos_tcc")):
    if len(x_toques) == 0:
        print("Erro: Nenhum dado encontrado!")
        return

    output_dir.mkdir(exist_ok=True)
    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection='3d')
    
    # CORREÇÃO: Pegar os limites reais (mínimos e máximos) incluindo negativos
    x_min, x_max = np.min(x_toques) - 20, np.max(x_toques) + 20
    y_min, y_max = np.min(y_toques) - 20, np.max(y_toques) + 20
    z_min, z_max = np.min(z_toques), np.max(z_toques)
    z_floor = z_min - 10 # Chão do mapa de calor
    
    # 1. Plotar os pontos reais (As 4 quinas)
    scatter = ax.scatter(x_toques, y_toques, z_toques, c=z_toques, cmap='Reds', 
                         marker='o', s=40, alpha=0.9, edgecolors='k', linewidth=0.5)
                         
    # 2. Criar o Mapa de Calor corrigido para o espaço real do robô
    x_grid = np.linspace(x_min, x_max, 150)
    y_grid = np.linspace(y_min, y_max, 150)
    X, Y = np.meshgrid(x_grid, y_grid)
    
    pos = np.vstack([X.ravel(), Y.ravel()])
    values = np.vstack([x_toques, y_toques])
    
    try:
        kernel = gaussian_kde(values)
        Z_density = np.reshape(kernel(pos).T, X.shape)
        # Plota o mapa de calor no chão
        ax.contourf(X, Y, Z_density, zdir='z', offset=z_floor, cmap='Reds', alpha=0.7, levels=30)
    except Exception as e:
        print(f"Aviso sobre o Heatmap: {e}")
        
    # 3. Estética
    ax.set_title(f"Análise de Repetibilidade: Distribuição dos Toques (Âncoras)\n(Total de Pontos Reais: {len(x_toques)})", 
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xlabel('Eixo X Cinematográfico (mm)', fontweight='bold')
    ax.set_ylabel('Eixo Y Cinematográfico (mm)', fontweight='bold')
    ax.set_zlabel('Elevação Z (mm)', fontweight='bold')
    
    # Aplicar os limites corrigidos
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_zlim(z_floor, z_max + 5)
    
    cbar = fig.colorbar(scatter, ax=ax, shrink=0.5, pad=0.1)
    cbar.set_label('Altitude do Toque (Z) em mm')
    
    # Ângulo ideal para ver o retângulo perfeito
    ax.view_init(elev=35, azim=-55)
    
    arquivo_saida = output_dir / "grafico_6_heatmap_raw_data.png"
    plt.savefig(arquivo_saida, dpi=300, bbox_inches="tight")
    plt.close()
    print("✅ Heatmap 3D gerado com sucesso!")

def main():
    pasta_raiz = Path("test_results")
    if pasta_raiz.exists():
        x, y, z = extrair_dados_crus(pasta_raiz)
        plot_3d_heatmap_from_raw(x, y, z)

if __name__ == "__main__":
    main()