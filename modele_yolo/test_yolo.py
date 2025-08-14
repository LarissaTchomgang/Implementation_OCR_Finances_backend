from ultralytics import YOLO

model = YOLO('runs/detect/train7/weights/best.pt')
results = model('releve_05.jpg')
results = model('releve_05.jpg', save=True)
