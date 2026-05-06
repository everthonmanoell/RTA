import cv2

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) # Substitua 0 pelo ID da sua Brio

print(f"Foco Auto: {cap.get(cv2.CAP_PROP_AUTOFOCUS)}")
print(f"Foco Fixo: {cap.get(cv2.CAP_PROP_FOCUS)}")
print(f"Exposição Auto: {cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)}")
print(f"Exposição Fixa: {cap.get(cv2.CAP_PROP_EXPOSURE)}")
print(f"Balanço de Branco Auto: {cap.get(cv2.CAP_PROP_AUTO_WB)}")
print(f"Temperatura WB: {cap.get(cv2.CAP_PROP_WB_TEMPERATURE)}")

cap.release()