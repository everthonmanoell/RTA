from pathlib import Path

import cv2
import numpy as np

# Famílias AprilTag disponíveis no OpenCV
FAMILIES = {
    "tag16h5": cv2.aruco.DICT_APRILTAG_16h5,
    "tag25h9": cv2.aruco.DICT_APRILTAG_25h9,
    "tag36h10": cv2.aruco.DICT_APRILTAG_36h10,
    "tag36h11": cv2.aruco.DICT_APRILTAG_36h11,
}


def gerar_apriltag(tag_id: int, family: str = "tag36h11", size: int = 400,
                   output_dir: str | None = None, quiet_zone: bool = True) -> Path:
    """Gera uma imagem PNG de uma AprilTag válida usando cv2.aruco.

    Args:
        tag_id: ID da tag a ser gerada.
        family: Família da tag (tag16h5, tag25h9, tag36h10, tag36h11).
        size: Tamanho em pixels da imagem (sem quiet zone).
        output_dir: Diretório de saída. Se None, usa o diretório atual.
        quiet_zone: Se True, adiciona borda branca ao redor (necessária para detecção).

    Returns:
        Path do arquivo PNG salvo.
    """
    if family not in FAMILIES:
        raise ValueError(
            f"Família '{family}' não suportada. Opções: {list(FAMILIES.keys())}"
        )

    aruco_dict = cv2.aruco.getPredefinedDictionary(FAMILIES[family])

    # Verifica se o ID é válido para a família escolhida
    max_id = aruco_dict.bytesList.shape[0] - 1
    if tag_id < 0 or tag_id > max_id:
        raise ValueError(
            f"ID {tag_id} fora do intervalo para '{family}' (0–{max_id})."
        )

    print(f"Gerando AprilTag ID: {tag_id} (Família: {family})")

    # Gera a imagem da tag
    tag_img = cv2.aruco.generateImageMarker(aruco_dict, tag_id, size)

    # Adiciona quiet zone (borda branca) — essencial para detecção confiável
    if quiet_zone:
        border = size // 8
        tag_img = cv2.copyMakeBorder(
            tag_img,
            top=border, bottom=border, left=border, right=border,
            borderType=cv2.BORDER_CONSTANT,
            value=255,
        )

    # Salva o arquivo
    dest = Path(output_dir) if output_dir else Path.cwd()
    dest.mkdir(parents=True, exist_ok=True)
    filename = dest / f"apriltag_{family}_id{tag_id}.png"
    cv2.imwrite(str(filename), tag_img)

    print(f"Sucesso! Arquivo salvo como: {filename}")
    return filename


# Executar
if __name__ == "__main__":
    ID_DESEJADO = 0        # Altere aqui o ID que você precisa
    FAMILIA = "tag36h11"   # tag16h5 | tag25h9 | tag36h10 | tag36h11
    TAMANHO = 400          # pixels

    for i in range(1,):  # Gerar os primeiros 5 IDs para teste
        gerar_apriltag(tag_id=i, family=FAMILIA, size=TAMANHO)