import cv2
import numpy as np

# 1. Carregar a imagem
image_path = 'setup_.jpeg'  # Garanta que a imagem esteja na mesma pasta do script
image = cv2.imread(image_path)

if image is None:
    print("Erro: Não foi possível encontrar a imagem. Verifique o nome ou o caminho.")
else:
    # 2. Definir o ponto de origem (Base do robô DENSO)
    # Calculei baseado na proporção da sua imagem, mas você pode alterar aqui se quiser mover
    height, width = image.shape[:2]
    origin_x = int(width * 0.75)  # Metade da imagem (centro horizontal)
    origin_y = int(height * 0.50)  # Um pouco abaixo do meio (base do robô)
    origin = (origin_x, origin_y)

    # 3. Configurações visuais das setas
    axis_length = 150  # Tamanho da linha em pixels
    thickness = 6      # Espessura da linha
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.2
    font_thickness = 3

    # 4. Desenhar Eixo Y (Positivo para a direita)
    # Cores no OpenCV são BGR (Blue, Green, Red). Verde = (0, 255, 0)
    y_end = (origin_x + axis_length, origin_y)
    cv2.arrowedLine(image, origin, y_end, (0, 255, 0),
                    thickness, tipLength=0.15)
    cv2.putText(image, 'Y+', (y_end[0] + 10, y_end[1] + 10),
                font, font_scale, (0, 255, 0), font_thickness)

    # 5. Desenhar Eixo Z (Negativo para baixo -> Positivo para cima)
    # Azul = (255, 0, 0)
    z_end = (origin_x, origin_y - axis_length)
    cv2.arrowedLine(image, origin, z_end, (255, 0, 0),
                    thickness, tipLength=0.15)
    cv2.putText(image, 'Z+', (z_end[0] - 25, z_end[1] - 20),
                font, font_scale, (255, 0, 0), font_thickness)

    # 6. Desenhar Eixo X (Negativo pro robô -> Positivo "saindo" da tela/esquerda)
    # Para dar a perspectiva 3D, desenhamos em diagonal para baixo e esquerda
    # Vermelho = (0, 0, 255)
    x_offset = int(axis_length * 0.7)
    x_end = (origin_x - x_offset, origin_y + x_offset)
    cv2.arrowedLine(image, origin, x_end, (0, 0, 255),
                    thickness, tipLength=0.15)
    cv2.putText(image, 'X+', (x_end[0] - 40, x_end[1] + 30),
                font, font_scale, (0, 0, 255), font_thickness)

    # 7. Desenhar um ponto na origem
    cv2.circle(image, origin, 8, (0, 0, 0), -1)  # Ponto preto na base

    # 8. Salvar a imagem final
    output_name = 'setup_com_eixos.jpeg'
    cv2.imwrite(output_name, image)
    print(f"Sucesso! Imagem gerada e salva como '{output_name}'")
