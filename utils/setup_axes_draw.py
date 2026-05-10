import matplotlib.pyplot as plt
import matplotlib.image as mpimg

def desenhar_eixos():
    # Carregar a imagem (certifique-se de que o nome do arquivo está correto)
    img = mpimg.imread('log_images/setup.jpg')
    
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.imshow(img)
    
    # 1. Escolher o Ponto de Origem na foto
    # Escolhi um ponto perto da base do robô/bancada para não tapar o celular
    orig_x, orig_y = 650, 750 
    
    L = 200 # Comprimento das setas
    
    # Eixo Z (AZUL) - Cima (+Z)
    # Nota: No matplotlib, o Y=0 é no topo da imagem, então subtrair vai para CIMA
    ax.arrow(orig_x, orig_y, 0, -L, head_width=30, head_length=30, fc='blue', ec='blue', width=8)
    ax.text(orig_x - 10, orig_y - L - 30, '+Z (UP)', color='blue', fontsize=16, weight='bold')

    # Eixo Y (VERDE) - Direita (+Y) conforme o seu prompt
    ax.arrow(orig_x, orig_y, L, 0, head_width=30, head_length=30, fc='green', ec='green', width=8)
    ax.text(orig_x + L + 20, orig_y + 10, '+Y (Right)', color='green', fontsize=16, weight='bold')

    # Eixo X (VERMELHO) - Frente (+X)
    # Desenhado na diagonal para dar noção de perspetiva 3D (saindo da tela)
    ax.arrow(orig_x, orig_y, -L*0.6, L*0.8, head_width=30, head_length=30, fc='red', ec='red', width=8)
    ax.text(orig_x - L*0.6 - 120, orig_y + L*0.8 + 40, '+X (Front)', color='red', fontsize=16, weight='bold')

    # Esconder as bordas do gráfico
    plt.axis('off')
    
    # Salvar em alta resolução para o artigo ACM
    plt.savefig('setup_com_eixos.png', dpi=300, bbox_inches='tight', pad_inches=0)
    print("✅ Imagem 'setup_com_eixos.png' gerada com sucesso!")

if __name__ == "__main__":
    desenhar_eixos()