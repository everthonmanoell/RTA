import cv2

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # Substitua 0 pelo ID da sua Brio

print(f"Foco Auto: {cap.get(cv2.CAP_PROP_AUTOFOCUS)}")
print(f"Foco Fixo: {cap.get(cv2.CAP_PROP_FOCUS)}")
print(f"Auto Exposure: {cap.get(cv2.CAP_PROP_AUTO_EXPOSURE)}")
print(f"Fixed Exposure: {cap.get(cv2.CAP_PROP_EXPOSURE)}")
print(f"Auto White Balance: {cap.get(cv2.CAP_PROP_AUTO_WB)}")
print(f"Temperatura WB: {cap.get(cv2.CAP_PROP_WB_TEMPERATURE)}")

cap.release()
