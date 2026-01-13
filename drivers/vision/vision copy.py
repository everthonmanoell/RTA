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
DISTANCIA_REAL_LARGURA_CM = 8.09   # Horizontal: Tag 1 corner[0] até Tag 0 corner[1]
DISTANCIA_REAL_ALTURA_CM = 15.13   # Vertical: Tag 1 corner[0] até Tag 3 corner[3]

# Configuração de diretórios
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # Pasta onde está este script
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "detections_output")  # Pasta para salvar imagens
os.makedirs(OUTPUT_DIR, exist_ok=True)  # Cria a pasta se não existir

# Controle de salvamento anti-flood
SAVE_INTERVAL_SECONDS = 2.0  # Intervalo mínimo entre salvamentos automáticos
SAVE_ON_KEY = True           # True = salva ao pressionar 's' | False = salva automaticamente
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


def initialize_camera():
    """Inicializa a câmera com configurações apropriadas"""
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) 
    if not cap.isOpened():
        print("Câmera 1 não encontrada. Tentando câmera 0...")
        cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    return cap


def detect_apriltags(frame, detector):
    """
    Detecta AprilTags no frame e retorna mapa de corners
    
    Args:
        frame: Frame da câmera
        detector: Detector de AprilTags
    
    Returns:
        tuple: (tag_corners_map, frame com visualização)
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detections = detector.detect(gray)
    
    tag_corners_map = {}
    frame_display = frame.copy()
    
    for detection in detections:
        tag_corners_map[detection.tag_id] = detection.corners
        center = tuple(map(int, detection.center))
        cv2.circle(frame_display, center, 4, (0, 0, 255), -1)
    
    return tag_corners_map, frame_display


def extract_inner_corners(tag_corners_map):
    """
    Extrai os corners internos das 4 tags
    
    Args:
        tag_corners_map: Dicionário com corners de cada tag
    
    Returns:
        tuple: (pt_tl, pt_tr, pt_br, pt_bl) ou None se tags não estiverem presentes
    """
    if not all(tid in tag_corners_map for tid in [0, 1, 2, 3]):
        return None
    
    try:
        pt_tl = tag_corners_map[1][3]  # Tag 1 (superior esquerda)
        pt_tr = tag_corners_map[0][2]  # Tag 0 (superior direita)
        pt_br = tag_corners_map[2][1]  # Tag 2 (inferior direita)
        pt_bl = tag_corners_map[3][0]  # Tag 3 (inferior esquerda)
        
        return pt_tl, pt_tr, pt_br, pt_bl
    except KeyError:
        return None


def draw_anchor_points(frame, points):
    """Desenha pontos de ancoragem no frame"""
    for pt in points:
        cv2.circle(frame, tuple(map(int, pt)), 6, (255, 0, 255), -1)


def apply_perspective_transform(frame, src_points, width_cm, height_cm, scale=20):
    """
    Aplica transformação de perspectiva para obter vista top-down
    
    Args:
        frame: Frame original
        src_points: 4 pontos de origem (corners internos das tags)
        width_cm: Largura real em cm
        height_cm: Altura real em cm
        scale: Pixels por cm
    
    Returns:
        tuple: (warped image, transformation matrix)
    """
    src_pts = order_points(np.float32(src_points))
    
    w_pixels = int(width_cm * scale)
    h_pixels = int(height_cm * scale)
    
    dst_pts = np.float32([
        [0, 0],
        [w_pixels, 0],
        [w_pixels, h_pixels],
        [0, h_pixels]
    ])
    
    matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(frame, matrix, (w_pixels, h_pixels))
    
    return warped, matrix


def segment_device(warped):
    """
    Segmenta o dispositivo na imagem warped usando threshold
    
    Args:
        warped: Imagem com perspectiva corrigida
    
    Returns:
        tuple: (thresholded image, contours)
    """
    warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(warped_gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    kernel = np.ones((3, 3), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)
    
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    return thresh, contours


def measure_and_draw_devices(warped, contours, scale, width_cm, height_cm):
    """
    Mede dispositivos detectados e desenha resultados
    
    Args:
        warped: Imagem warped original
        contours: Contornos detectados
        scale: Escala de pixels por cm
        width_cm: Largura da área em cm
        height_cm: Altura da área em cm
    
    Returns:
        Imagem com medições desenhadas
    """
    warped_display = warped.copy()
    area_maxima = width_cm * height_cm * 0.95
    
    for cnt in contours:
        area_cm2 = cv2.contourArea(cnt) / (scale ** 2)
        
        if area_cm2 > 20.0 and area_cm2 < area_maxima:
            rect = cv2.minAreaRect(cnt)
            box = np.intp(cv2.boxPoints(rect))
            cv2.drawContours(warped_display, [box], 0, (0, 255, 0), 3)
            
            (w, h) = rect[1]
            largura_cm = min(w, h) / scale
            altura_cm = max(w, h) / scale
            texto = f"{largura_cm:.2f}cm x {altura_cm:.2f}cm"
            
            print(f"📱 Dispositivo: {texto}")
            
            cv2.putText(warped_display, texto, (box[0][0], box[0][1] - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    
    return warped_display


def save_detection_images(frame, warped_display, thresh):
    """
    Salva as imagens de detecção
    
    Args:
        frame: Frame original
        warped_display: Imagem warped com medições
        thresh: Imagem binarizada
    """
    ts = datetime.now().strftime("%H%M%S")
    print(f"\n💾 SALVANDO IMAGENS [{ts}]...")
    
    cv2.imwrite(os.path.join(OUTPUT_DIR, f"mask_{ts}.jpg"), thresh)
    cv2.imwrite(os.path.join(OUTPUT_DIR, f"warp_{ts}.jpg"), warped_display)
    cv2.imwrite(os.path.join(OUTPUT_DIR, f"orig_{ts}.jpg"), frame)
    
    print(f"   ✅ Salvo em: {OUTPUT_DIR}")
    print(f"   📄 mask_{ts}.jpg | warp_{ts}.jpg | orig_{ts}.jpg\n")


def should_save_images(save_requested, last_save_time):
    """
    Determina se deve salvar imagens baseado no modo e tempo
    
    Args:
        save_requested: Flag de requisição manual
        last_save_time: Timestamp do último salvamento
    
    Returns:
        bool: True se deve salvar
    """
    current_time = time.time()
    
    if SAVE_ON_KEY and save_requested:
        return True
    elif not SAVE_ON_KEY and (current_time - last_save_time > SAVE_INTERVAL_SECONDS):
        return True
    
    return False


def print_startup_messages():
    """Imprime mensagens iniciais do sistema"""
    print("\n" + "="*60)
    print("📱 SISTEMA DE MEDIÇÃO COM APRILTAGS")
    print("="*60)
    print(f"\n📁 Pasta de salvamento: {OUTPUT_DIR}")
    if SAVE_ON_KEY:
        print("⌨️  Pressione 's' para SALVAR imagens | 'q' para SAIR")
    else:
        print(f"💾 Salvamento automático a cada {SAVE_INTERVAL_SECONDS}s")
    print("\n" + "="*60 + "\n")


def main():
    """Função principal do sistema de medição"""
    
    # Inicialização
    cap = initialize_camera()
    detector = Detector(families='tag36h11')
    print_startup_messages()
    
    # Variáveis de controle
    global last_save_time
    save_requested = False
    escala = 20  # 20 pixels = 1 cm

    # Loop principal
    while True:
        ret, frame = cap.read()
        if not ret: 
            break

        # Detecção das AprilTags
        tag_corners_map, frame = detect_apriltags(frame, detector)

        # Verifica se as 4 tags estão presentes
        corners = extract_inner_corners(tag_corners_map)
        
        if corners is not None:
            pt_tl, pt_tr, pt_br, pt_bl = corners
            
            # Desenha pontos de ancoragem
            draw_anchor_points(frame, [pt_tl, pt_tr, pt_br, pt_bl])

            # Transformação de perspectiva
            warped, matrix = apply_perspective_transform(
                frame, 
                [pt_tl, pt_tr, pt_bl, pt_br],
                DISTANCIA_REAL_LARGURA_CM,
                DISTANCIA_REAL_ALTURA_CM,
                escala
            )

            # Segmentação do dispositivo
            thresh, contours = segment_device(warped)
            
            # Medição e desenho dos dispositivos
            warped_display = measure_and_draw_devices(
                warped, 
                contours, 
                escala,
                DISTANCIA_REAL_LARGURA_CM,
                DISTANCIA_REAL_ALTURA_CM
            )

            # Lógica de salvamento de imagens
            if should_save_images(save_requested, last_save_time):
                save_detection_images(frame, warped_display, thresh)
                last_save_time = time.time()
                save_requested = False

            # Exibição das janelas
            cv2.imshow("Warped", warped_display)
            cv2.imshow("Mask", thresh)

        else:
            # Se as 4 tags NÃO foram detectadas
            cv2.putText(frame, "Procurando tags... (precisa das 4)", (10, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        # Sempre mostra o frame original da câmera
        cv2.imshow("Original", frame)

        # Controle de teclas
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'):
            break
        elif key == ord('s'):
            print("\n>> Tecla 'S' pressionada. Aguardando detecção válida...\n")
            save_requested = True

    # Encerramento
    cap.release()
    cv2.destroyAllWindows()
if __name__ == "__main__":
    main()