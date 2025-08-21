from ultralytics import YOLO

model = YOLO(r"C:\Users\Moi\Desktop\doc polytech\doc niveau 4 - AIA 4\Stage_Saphir\projet_comptabilité\implémentation_ocr_finance\backend\runs\detect\train6\weights\best.pt")
results = model('releve_vrai.jpg')
results = model('releve_vrai.jpg', save=True)
