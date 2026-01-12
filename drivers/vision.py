import os
from datetime import datetime

import cv2
import numpy as np
from pupil_apriltags import Detector

# ================= CONFIGURAÇÕES =================
# LAYOUT DAS TAGS:
#   Tag 1 (superior esquerda) ------- Tag 0 (superior direita)
#       |                                    |
#       |         SMARTPHONE                 |
#       |                                    |
#   Tag 3 (inferior esquerda) ------ Tag 2 (inferior direita)

# MEÇA ISSO NA VIDA REAL COM UMA RÉGUA!
# Distância horizontal (em cm) entre os cantos internos das tags
DISTANCIA_REAL_LARGURA_CM = 9.62 
# Distância vertical (em cm) entre os cantos internos das tags
DISTANCIA_REAL_ALTURA_CM = 12.53

# Tamanho mínimo da área do celular para evitar detectar ruído (em cm quadrados)
AREA_MINIMA_CELULAR_CM2 = 10.0
# =================================================

# Criar pasta para salvar imagens
OUTPUT_DIR = "detections_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def main():
    cap = cv2.VideoCapture(1)  # Abre a câmera padrão
    
    if not cap.isOpened():
        print("❌ Erro: Não consegui abrir a câmera. Verifique se está conectada.")
        return
    
    # Inicializa o detector (família tag36h11 padrão)
    detector = Detector(families='tag36h11')

    print("\n" + "="*60)
    print("🔍 MEDIDOR DE DIMENSÕES DE SMARTPHONE COM APRILTAGS")
    print("="*60)
    print("\n📋 INSTRUÇÕES:")
    print("  1. Coloque um papel com 4 tags apriltag nos cantos")
    print("  2. Tag 1: Superior ESQUERDA")
    print("  3. Tag 0: Superior DIREITA")
    print("  4. Tag 3: Inferior ESQUERDA")
    print("  5. Tag 2: Inferior DIREITA")
    print("  6. Coloque o smartphone NO CENTRO da área delimitada pelas tags")
    print("  7. Aponte a câmera para a cena")
    print("\n⌨️  Pressione 'q' para sair\n")

    print("--- INICIANDO DETECÇÃO ---\n")
    
    frame_count = 0
    detections_log = {"tags_encontradas": 0, "smartphone_detectado": 0}
    
    while True:
        ret, frame = cap.read()
        if not ret: 
            break

        frame_count += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detections = detector.detect(gray)
        
        # ========== ETAPA 1: DETECTAR AS 4 TAGS ==========
        tag_centers = {}
        tag_corners = {}  # Armazena os 4 cantos de cada tag
        tag_ids_encontradas = []
        
        for detection in detections:
            tag_id = detection.tag_id
            center = tuple(map(int, detection.center))
            tag_centers[tag_id] = center
            # Armazena os 4 cantos da tag
            tag_corners[tag_id] = detection.corners
            tag_ids_encontradas.append(tag_id)
            
            # Desenha círculo na tag com cor e ID
            cor = {0: (0, 0, 255), 1: (255, 0, 0), 2: (0, 255, 0), 3: (255, 255, 0)}.get(tag_id, (128, 128, 128))
            cv2.circle(frame, center, 8, cor, -1)
            cv2.putText(frame, f"Tag{tag_id}", (center[0] + 10, center[1] - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Status das tags encontradas
        status_tags = f"Tags detectadas: {len(tag_ids_encontradas)}/4"
        cv2.putText(frame, status_tags, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Se achar as 4 tags (0, 1, 2, 3)
        if all(tag_id in tag_centers for tag_id in [0, 1, 2, 3]):
            detections_log["tags_encontradas"] += 1
            
            # ========== ETAPA 2: USAR CORNERS DAS TAGS PARA DEFINIR A ÁREA ==========
            # LAYOUT CORRETO:
            # Tag 1 (superior esquerda) ------- Tag 0 (superior direita)
            #   |                                    |
            #   |         SMARTPHONE                 |
            #   |                                    |
            # Tag 3 (inferior esquerda) ------ Tag 2 (inferior direita)
            
            # Extrai o corner correto de cada tag (o mais próximo ao smartphone)
            # Ordem dos corners em apriltag: 0=canto1, 1=canto2, 2=canto3, 3=canto4
            
            # Tag 0 (superior direita) - usa corner mais à esquerda e inferior (que aponta para dentro)
            corner_tag0 = tuple(map(int, tag_corners[0][2]))
            
            # Tag 1 (superior esquerda) - usa corner mais à direita e inferior (que aponta para dentro)
            corner_tag1 = tuple(map(int, tag_corners[1][3]))
            
            # Tag 2 (inferior direita) - usa corner mais à esquerda e superior (que aponta para dentro)
            corner_tag2 = tuple(map(int, tag_corners[2][0]))
            
            # Tag 3 (inferior esquerda) - usa corner mais à direita e superior (que aponta para dentro)
            corner_tag3 = tuple(map(int, tag_corners[3][1]))
            
            # Define os pontos de origem baseado nos corners das tags
            src_pts = np.float32([
                corner_tag1,  # superior esquerda
                corner_tag0,  # superior direita
                corner_tag3,  # inferior esquerda
                corner_tag2   # inferior direita
            ])
            
            # Define o tamanho da imagem corrigida (em pixels)
            # Escala: 10 pixels = 1 cm real
            escala = 10 
            w_pixels = int(DISTANCIA_REAL_LARGURA_CM * escala)
            h_pixels = int(DISTANCIA_REAL_ALTURA_CM * escala)
            
            # Pontos de destino (transformação de perspectiva)
            dst_pts = np.float32([
                [0, 0],                    # superior esquerda
                [w_pixels, 0],             # superior direita
                [0, h_pixels],             # inferior esquerda
                [w_pixels, h_pixels]       # inferior direita
            ])
            
            # Calcula e aplica a transformação de perspectiva
            matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
            warped = cv2.warpPerspective(frame, matrix, (w_pixels, h_pixels))
            
            # ========== ETAPA 3: DETECTAR O SMARTPHONE ==========
            warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(warped_gray, (5, 5), 0)
            
            # Detecção de bordas - técnica sensível
            edges = cv2.Canny(blurred, 25, 80)
            
            # Dilatar as bordas para fechar "buracos"
            kernel = np.ones((5, 5), np.uint8)
            edges_dilated = cv2.dilate(edges, kernel, iterations=2)

            contours, _ = cv2.findContours(edges_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Cria uma cópia colorida para desenhos
            warped_resultado = warped.copy()
            
            celular_encontrado = False
            maior_contorno = None
            maior_area_cm2 = 0

            # ========== ETAPA 4: FILTRAR E MEDIR O SMARTPHONE ==========
            for cnt in contours:
                area_pixels = cv2.contourArea(cnt)
                area_cm2 = area_pixels / (escala ** 2)

                # Filtro de tamanho: Ignora sujeira e backgrounds
                area_maxima = (DISTANCIA_REAL_LARGURA_CM * DISTANCIA_REAL_ALTURA_CM) * 0.90
                
                if area_cm2 > AREA_MINIMA_CELULAR_CM2 and area_cm2 < area_maxima:
                    if area_cm2 > maior_area_cm2:
                        maior_area_cm2 = area_cm2
                        maior_contorno = (cnt, area_cm2)

            # Desenha o maior contorno encontrado (que é presumivelmente o smartphone)
            if maior_contorno is not None:
                cnt, area_cm2 = maior_contorno
                detections_log["smartphone_detectado"] += 1
                
                # Desenha o contorno em verde
                rect = cv2.minAreaRect(cnt)
                box = np.intp(cv2.boxPoints(rect))
                cv2.drawContours(warped_resultado, [box], 0, (0, 255, 0), 3)
                
                # Calcula dimensões
                (w_px, h_px) = rect[1]
                dim1 = w_px / escala
                dim2 = h_px / escala
                
                # Ordena: Menor x Maior
                medidas = sorted([dim1, dim2])
                largura, altura = medidas[0], medidas[1]
                
                # Texto com resultado
                texto = f"{largura:.2f} cm x {altura:.2f} cm"
                
                # Desenha a medição com fundo
                text_size = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0]
                text_x, text_y = 10, 30
                cv2.rectangle(warped_resultado, (text_x - 5, text_y - text_size[1] - 5),
                            (text_x + text_size[0] + 5, text_y + 5), (0, 255, 0), -1)
                cv2.putText(warped_resultado, texto, (text_x, text_y), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
                
                # Imprime no console
                print(f"✅ Smartphone detectado: {texto} (Área: {area_cm2:.1f} cm²)")
                celular_encontrado = True
                
                # ========== SALVAR IMAGENS PARA COMPARAÇÃO ==========
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Salvar imagem binarizada (bordas)
                img_binarizada_path = os.path.join(OUTPUT_DIR, f"binarizada_{timestamp}.png")
                cv2.imwrite(img_binarizada_path, edges_dilated)
                
                # Salvar imagem com o resultado (warped com detecção)
                img_resultado_path = os.path.join(OUTPUT_DIR, f"resultado_{timestamp}.png")
                cv2.imwrite(img_resultado_path, warped_resultado)
                
                # Salvar imagem original transformada
                img_original_path = os.path.join(OUTPUT_DIR, f"original_{timestamp}.png")
                cv2.imwrite(img_original_path, warped)
                
                print(f"💾 Imagens salvas em: {OUTPUT_DIR}/")
                print(f"   - binarizada_{timestamp}.png")
                print(f"   - resultado_{timestamp}.png")
                print(f"   - original_{timestamp}.png")
            else:
                cv2.putText(warped_resultado, "Procurando smartphone...", (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # ========== EXIBIÇÃO DOS RESULTADOS ==========
            # Janela principal com o resultado
            cv2.imshow("Resultado Final - Dimensoes do Smartphone", warped_resultado)
            
            # Janela DEBUG (opcional - mostra as bordas detectadas)
            if frame_count % 10 == 0:  # Mostra a cada 10 frames para não pesar
                edges_display = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
                cv2.imshow("Debug - Bordas Detectadas", edges_display)

        else:
            # Se não achou as 4 tags
            tags_str = ", ".join([f"Tag{i}" for i in range(4) if i not in tag_centers])
            cv2.putText(frame, f"Procurando tags... Faltam: {tags_str}", (10, 80), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        
        # Exibe o feed principal da câmera
        cv2.imshow("Camera - Feed Principal", frame)
        
        # Sair ao pressionar 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'): 
            break

    # Resumo final
    cap.release()
    cv2.destroyAllWindows()
    
    print("\n" + "="*60)
    print("📊 RESUMO DA EXECUÇÃO:")
    print(f"  • Frames processados: {frame_count}")
    print(f"  • Detecções com 4 tags: {detections_log['tags_encontradas']}")
    print(f"  • Detecções de smartphone: {detections_log['smartphone_detectado']}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()