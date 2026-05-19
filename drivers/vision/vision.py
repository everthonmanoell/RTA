"""
Sistema de Medição de Dispositivos com AprilTags
================================================
Este programa usa 4 AprilTags posicionadas nos cantos de uma área para:
1. Corrigir a perspectiva da câmera (transformação top-down)
2. Calibrar a escala real (pixels → cm)
3. Detectar e medir dimensões de smartphones automaticamente

Layout das Tags:
   Tag 1 (sup. esq.) ------- Tag 0 (sup. dir.)
        |                          |
        |      DISPOSITIVO         |
        |                          |
   Tag 3 (inf. esq.) ------- Tag 2 (inf. dir.)
"""

import os
import time
from datetime import datetime

import cv2
import numpy as np
from pupil_apriltags import Detector

# ================= CONFIGURAÇÕES =================

# Distâncias reais entre os corners internos das tags (medidas com régua)
# IMPORTANTE: Essas medidas definem a escala de conversão
# Horizontal: Tag 1 corner[0] até Tag 0 corner[1]
DISTANCIA_REAL_LARGURA_CM = 8.09
# Vertical: Tag 1 corner[0] até Tag 3 corner[3]
DISTANCIA_REAL_ALTURA_CM = 15.13

# Configuração de diretórios
SCRIPT_DIR = os.path.dirname(os.path.abspath(
    __file__))  # Pasta onde está este script
# Pasta para salvar imagens
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "detections_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)  # Cria a pasta se não existir

# Controle de salvamento anti-flood
SAVE_INTERVAL_SECONDS = 2.0  # Intervalo mínimo entre salvamentos automáticos
# True = salva ao pressionar 's' | False = salva automaticamente
SAVE_ON_KEY = True
last_save_time = 0           # Timestamp do último salvamento


def order_points(pts):
    """
    Ordena 4 pontos no sentido horário começando do superior esquerdo.

    Args:
        pts: Array numpy com 4 pontos (x, y)

    Returns:
        Array ordenado: [top-left, top-right, bottom-right, bottom-left]
    """
    rect = np.zeros((4, 2), dtype="float32")

    # Superior esquerdo tem a menor soma de coordenadas (x+y)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]

    # Inferior direito tem a maior soma (x+y)
    rect[2] = pts[np.argmax(s)]

    # Superior direito tem a menor diferença (y-x)
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]

    # Inferior esquerdo tem a maior diferença (y-x)
    rect[3] = pts[np.argmax(diff)]

    return rect


def main():
    """Função principal do sistema de medição"""

    # ========== INICIALIZAÇÃO DA CÂMERA ==========
    # Tenta abrir câmera 1 (câmera externa), se falhar usa câmera 0 (webcam)
    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    # Configura resolução para melhor qualidade
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # ========== INICIALIZAÇÃO DO DETECTOR DE APRILTAGS ==========
    # Família tag36h11 é a mais comum (robusta e confiável)
    detector = Detector(families='tag36h11')

    # ========== MENSAGENS INICIAIS ==========
    print("\n" + "="*60)
    print("📱 APRILTAG MEASUREMENT SYSTEM")
    print("="*60)
    print(f"\n📁 Pasta de salvamento: {OUTPUT_DIR}")
    if SAVE_ON_KEY:
        print("⌨️  Pressione 's' para SALVAR imagens | 'q' para SAIR")
    else:
        print(f"💾 Auto-save every {SAVE_INTERVAL_SECONDS}s")
    print("\n" + "="*60 + "\n")

    # ========== VARIÁVEIS DE CONTROLE ==========
    global last_save_time
    save_requested = False  # Flag para sinalizar quando usuário pressiona 's'

    # ========== LOOP PRINCIPAL ==========
    while True:
        # Captura frame da câmera
        ret, frame = cap.read()
        if not ret:
            break  # Se falhou, encerra o programa

        # ========== ETAPA 1: DETECÇÃO DAS APRILTAGS ==========
        # Converte para escala de cinza (apriltags são detectadas em preto e branco)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detecta todas as tags no frame
        detections = detector.detect(gray)

        # Mapeia ID da tag → seus 4 corners
        # Cada tag tem 4 corners indexados: [0]=sup-esq, [1]=sup-dir, [2]=inf-dir, [3]=inf-esq
        tag_corners_map = {}
        for detection in detections:
            tag_corners_map[detection.tag_id] = detection.corners

            # Desenha círculo vermelho no centro da tag (para visualização)
            center = tuple(map(int, detection.center))
            cv2.circle(frame, center, 4, (0, 0, 255), -1)

        # ========== ETAPA 2: VERIFICA SE AS 4 TAGS ESTÃO PRESENTES ==========
        if all(tid in tag_corners_map for tid in [0, 1, 2, 3]):
            try:
                # ========== ETAPA 3: EXTRAI OS CORNERS INTERNOS DAS TAGS ==========
                # Cada tag contribui com 1 corner que aponta para dentro da área
                # Biblioteca pupil_apriltags retorna corners sempre nesta ordem:
                # [0]=top-left, [1]=top-right, [2]=bottom-right, [3]=bottom-left

                # Tag 1 (superior esquerda) → pega corner inferior direito [3]
                pt_tl = tag_corners_map[1][3]

                # Tag 0 (superior direita) → pega corner inferior esquerdo [2]
                pt_tr = tag_corners_map[0][2]

                # Tag 2 (inferior direita) → pega corner superior esquerdo [1]
                pt_br = tag_corners_map[2][1]

                # Tag 3 (inferior esquerda) → pega corner superior direito [0]
                pt_bl = tag_corners_map[3][0]

                # Desenha bolinhas ROSA nos 4 pontos de ancoragem (visualização)
                for pt in [pt_tl, pt_tr, pt_br, pt_bl]:
                    cv2.circle(frame, tuple(map(int, pt)),
                               6, (255, 0, 255), -1)

            except KeyError:
                # Se alguma tag não foi detectada corretamente, pula este frame
                cv2.imshow("Original", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            # ========== ETAPA 4: TRANSFORMAÇÃO DE PERSPECTIVA ==========
            # Ordena os pontos corretamente (top-left, top-right, bottom-left, bottom-right)
            src_pts = order_points(np.float32([pt_tl, pt_tr, pt_bl, pt_br]))

            # Define a escala: quantos pixels representam 1 cm real
            # Escala maior = imagem warped maior = mais precisão
            escala = 20  # 20 pixels = 1 cm

            # Calcula dimensões da imagem corrigida em pixels
            w_pixels = int(DISTANCIA_REAL_LARGURA_CM * escala)
            h_pixels = int(DISTANCIA_REAL_ALTURA_CM * escala)

            # Define os 4 pontos de destino (retângulo perfeito)
            dst_pts = np.float32([
                [0, 0],                    # top-left
                [w_pixels, 0],             # top-right
                [w_pixels, h_pixels],      # bottom-right
                [0, h_pixels]              # bottom-left
            ])

            # Calcula matriz de transformação de perspectiva
            matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)

            # Aplica a transformação → imagem "top-down" (vista de cima)
            warped = cv2.warpPerspective(frame, matrix, (w_pixels, h_pixels))

            # ========== ETAPA 5: DETECÇÃO E SEGMENTAÇÃO DO DISPOSITIVO ==========
            # Converte para escala de cinza
            warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

            # Aplica blur para reduzir ruído (filtro passa-baixa)
            blurred = cv2.GaussianBlur(warped_gray, (5, 5), 0)

            # Binarização automática (Otsu): converte para preto e branco
            # THRESH_BINARY_INV = objetos escuros ficam brancos
            _, thresh = cv2.threshold(
                blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

            # Operação morfológica OPEN: remove pequenos ruídos brancos
            kernel = np.ones((3, 3), np.uint8)
            thresh = cv2.morphologyEx(
                thresh, cv2.MORPH_OPEN, kernel, iterations=2)

            # Encontra contornos (bordas) dos objetos brancos
            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Cria cópia da imagem warped para desenhar resultados
            warped_display = warped.copy()

            # ========== ETAPA 6: FILTRAGEM E MEDIÇÃO DOS CONTORNOS ==========
            # Percorre todos os contornos encontrados
            for cnt in contours:
                # Calcula área do contorno em cm² (converte de pixels para cm)
                area_cm2 = cv2.contourArea(cnt) / (escala ** 2)

                # Filtro de tamanho: ignora objetos muito pequenos ou muito grandes
                # Muito pequeno < 20 cm² = ruído/sujeira
                # Muito grande > 95% da área total = fundo/folha
                area_maxima = DISTANCIA_REAL_LARGURA_CM * DISTANCIA_REAL_ALTURA_CM * 0.95

                if area_cm2 > 20.0 and area_cm2 < area_maxima:
                    # Calcula retângulo mínimo envolvente (pode estar rotacionado)
                    rect = cv2.minAreaRect(cnt)

                    # Converte para 4 pontos (corners do retângulo)
                    box = np.intp(cv2.boxPoints(rect))

                    # Desenha contorno VERDE ao redor do dispositivo
                    cv2.drawContours(warped_display, [box], 0, (0, 255, 0), 3)

                    # Extrai largura e altura do retângulo (em pixels)
                    (w, h) = rect[1]

                    # Converte para cm e formata texto
                    largura_cm = min(w, h) / escala
                    altura_cm = max(w, h) / escala
                    texto = f"{largura_cm:.2f}cm x {altura_cm:.2f}cm"

                    # Imprime dimensões no console (em tempo real)
                    print(f"📱 Dispositivo: {texto}")

                    # Desenha texto na imagem (acima do retângulo)
                    cv2.putText(warped_display, texto, (box[0][0], box[0][1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # ========== ETAPA 7: LÓGICA DE SALVAMENTO DE IMAGENS ==========
            # (Executada fora do loop de contornos para salvar apenas 1 vez por frame)

            should_save = False
            current_time = time.time()

            # Modo Manual: salva apenas quando 's' for pressionado
            if SAVE_ON_KEY and save_requested:
                should_save = True
                save_requested = False  # Reseta flag

            # Modo Automático: respeita intervalo de tempo (anti-flood)
            elif not SAVE_ON_KEY and (current_time - last_save_time > SAVE_INTERVAL_SECONDS):
                should_save = True

            # Executa salvamento se flag estiver ativa
            if should_save:
                last_save_time = current_time
                ts = datetime.now().strftime("%H%M%S")
                print(f"\n💾 SALVANDO IMAGENS [{ts}]...")

                # Salva 3 imagens:
                # 1. mask = Imagem binarizada (CRÍTICO para debug: dispositivo deve ser branco)
                cv2.imwrite(os.path.join(OUTPUT_DIR, f"mask_{ts}.jpg"), thresh)

                # 2. warp = Vista top-down com medições desenhadas
                cv2.imwrite(os.path.join(
                    OUTPUT_DIR, f"warp_{ts}.jpg"), warped_display)

                # 3. orig = Frame original da câmera (com tags marcadas)
                cv2.imwrite(os.path.join(OUTPUT_DIR, f"orig_{ts}.jpg"), frame)

                print(f"   ✅ Salvo em: {OUTPUT_DIR}")
                print(f"   📄 mask_{ts}.jpg | warp_{ts}.jpg | orig_{ts}.jpg\n")

            # ========== ETAPA 8: EXIBIÇÃO DAS JANELAS ==========
            cv2.imshow("Warped", warped_display)
            cv2.imshow("Mask", thresh)

        else:
            # Se as 4 tags NÃO foram detectadas
            cv2.putText(frame, "Procurando tags... (precisa das 4)", (10, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # Sempre mostra o frame original da câmera
        cv2.imshow("Original", frame)

        # ========== ETAPA 9: CONTROLE DE TECLAS ==========
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            # Sai do programa
            break
        elif key == ord('s'):
            # Sinaliza para salvar no próximo frame válido
            print("\n>> 'S' key pressed. Waiting for valid detection...\n")
            save_requested = True

    # ========== ENCERRAMENTO ==========
    cap.release()  # Libera a câmera
    cv2.destroyAllWindows()  # Fecha todas as janelas


if __name__ == "__main__":
    main()
