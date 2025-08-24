# Image de base Python slim
FROM python:3.11-slim

# Évite les prompts interactifs
ENV DEBIAN_FRONTEND=noninteractive

# --- Dépendances système ---
# - tesseract-ocr + langues (fra, eng)
# - poppler-utils : pdf2image
# - libglib2.0-0, libgl1, libsm6, libxext6 : nécessaires pour OpenCV
# - ffmpeg : requis par Ultralytics/torchvision
# - libstdc++6 : support C++
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-eng \
    poppler-utils \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    ffmpeg \
    libstdc++6 \
 && rm -rf /var/lib/apt/lists/*

# Répertoire de travail
WORKDIR /app

# Installer d’abord les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste du code
COPY . .

# Vérifier que le modèle YOLO est bien copié
# Mets bien ton fichier avant de builder : runs/detect/train5/weights/best.pt
COPY runs/detect/train5/weights/best.pt .

# Exposer le port
EXPOSE 8001

# Variable d’environnement pour FastAPI
ENV PORT=8001

# Lancer le serveur en mode debug (logs plus clairs)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "debug"]
