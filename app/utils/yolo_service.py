# app/utils/yolo_service.py
import os
from typing import Dict, List, Tuple, Optional
import cv2
import numpy as np
from ultralytics import YOLO
import pytesseract

# ⚙️ CONFIG — mets ici ton chemin vers best.pt si tu veux forcer en dur
YOLO_WEIGHTS = os.getenv(
    "YOLO_WEIGHTS",
    r"C:\Users\Moi\Desktop\doc polytech\doc niveau 4 - AIA 4\Stage_Saphir\projet_comptabilité\implémentation_ocr_finance\backend\modele_yolo\runs\detect\train7\weights\best.pt"
)

# Noms EXACTS des classes telles que dans ton dataset YOLO
CLASS_NAMES = {
    0: "lignes_transactions",
    1: "nom_banque",
    2: "numero_compte",
    3: "periode",
    4: "titulaire",
}

_model: Optional[YOLO] = None

def get_model() -> YOLO:
    global _model
    if _model is None:
        if not os.path.isfile(YOLO_WEIGHTS):
            raise FileNotFoundError(f"YOLO_WEIGHTS introuvable : {YOLO_WEIGHTS}")
        _model = YOLO(YOLO_WEIGHTS)
    return _model

# ------------ Utils image / OCR --------------

def clamp_bbox(xyxy: Tuple[int,int,int,int], w: int, h: int, pad: int = 0) -> Tuple[int,int,int,int]:
    x1, y1, x2, y2 = xyxy
    x1 = max(0, x1 - pad); y1 = max(0, y1 - pad)
    x2 = min(w - 1, x2 + pad); y2 = min(h - 1, y2 + pad)
    return x1, y1, x2, y2

def crop(image_path: str, xyxy: Tuple[int,int,int,int], pad_px: int = 8) -> np.ndarray:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Impossible de charger l'image: {image_path}")
    h, w = img.shape[:2]
    x1, y1, x2, y2 = clamp_bbox(xyxy, w, h, pad=pad_px)
    return img[y1:y2, x1:x2].copy()

def preprocess_for_ocr(img: np.ndarray) -> np.ndarray:
    # Grayscale + Otsu + légère ouverture pour “éclaircir” le texte
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    kernel = np.ones((1, 1), np.uint8)
    proc = cv2.morphologyEx(thr, cv2.MORPH_OPEN, kernel, iterations=1)
    return proc

def ocr_text(img: np.ndarray, psm: int = 6, lang: str = "eng+fra") -> str:
    cfg = f"--oem 3 --psm {psm}"
    return pytesseract.image_to_string(img, lang=lang, config=cfg)

def ocr_lines(img: np.ndarray, psm: int = 6, lang: str = "eng+fra") -> List[str]:
    from pytesseract import image_to_data, Output
    cfg = f"--oem 3 --psm {psm}"
    data = image_to_data(img, lang=lang, config=cfg, output_type=Output.DICT)
    lines = {}
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        lines.setdefault(key, []).append(text)
    out = [" ".join(v) for v in lines.values()]
    return out

# ------------ Détection YOLO ------------------

def detect_blocks(image_path: str, conf: float = 0.25, iou: float = 0.5) -> Dict[str, List[Tuple[int,int,int,int]]]:
    """
    Retourne un dict {class_name: [ (x1,y1,x2,y2), ... ] } en pixels.
    """
    model = get_model()
    results = model.predict(image_path, conf=conf, iou=iou, verbose=False)
    boxes_by_class: Dict[str, List[Tuple[int,int,int,int]]] = {v: [] for v in CLASS_NAMES.values()}
    if not results:
        return boxes_by_class

    r = results[0]
    if r.boxes is None or r.boxes.xyxy is None:
        return boxes_by_class

    for b in r.boxes:
        cls = int(b.cls.item())
        name = CLASS_NAMES.get(cls, None)
        if not name:
            continue
        x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
        boxes_by_class[name].append((x1, y1, x2, y2))

    return boxes_by_class

# ------------ Orchestrateur: YOLO + Fallback regex --------------

def extract_with_yolo_and_rules(
    image_path: str,
    regex_fallback_fn,         # callable(ocr_full_text) -> dict (tes règles parser)
    parse_transactions_fn      # callable(list_of_lines) -> list[dict]
) -> Dict:
    """
    1) YOLO pour localiser zones
    2) OCR sur zones
    3) Fallback regex si nécessaire
    4) OCR zones 'lignes_transactions' -> parse lignes
    """
    # 0) OCR global pour fallback éventuel (et pour aider au debug)
    img_full = cv2.imread(image_path)
    if img_full is None:
        raise ValueError(f"Impossible de lire {image_path}")
    ocr_full = ocr_text(preprocess_for_ocr(img_full), psm=6)

    detections = detect_blocks(image_path)

    # --- Champs généraux via YOLO ---
    def ocr_first_box(class_name: str, psm_hint: int = 7) -> Optional[str]:
        boxes = detections.get(class_name, []) or []
        if not boxes:
            return None
        # on prend la meilleure (la première suffit souvent)
        crop_img = crop(image_path, boxes[0], pad_px=8)
        txt = ocr_text(preprocess_for_ocr(crop_img), psm=psm_hint)
        txt = (txt or "").strip()
        return txt if txt else None

    nom_banque = ocr_first_box("nom_banque", psm_hint=7)
    numero_compte = ocr_first_box("numero_compte", psm_hint=7)
    periode = ocr_first_box("periode", psm_hint=7)
    titulaire = ocr_first_box("titulaire", psm_hint=7)

    # --- Transactions via YOLO ---
    transactions: List[dict] = []
    tx_boxes = detections.get("lignes_transactions", []) or []
    for bb in tx_boxes:
        tx_img = crop(image_path, bb, pad_px=12)
        tx_proc = preprocess_for_ocr(tx_img)
        # psm=6 -> Assume a uniform block of text; psm=11 -> sparse text; selon tes données essaye 6/11
        tx_lines = ocr_lines(tx_proc, psm=6)
        if not tx_lines:
            # tente un autre psm si vide
            tx_lines = ocr_lines(tx_proc, psm=11)
        if tx_lines:
            parsed = parse_transactions_fn(tx_lines)
            if parsed:
                transactions.extend(parsed)

    # --- Fallback sur tes règles (si vide) ---
    fallback = {}
    try:
        fallback = regex_fallback_fn(ocr_full) or {}
    except Exception:
        fallback = {}

    def pick(primary: Optional[str], fb_key: str) -> Optional[str]:
        if primary and primary.strip():
            return primary.strip()
        return (fallback.get(fb_key) or None)

    data = {
        "banque":        pick(nom_banque, "banque"),
        "compte":        pick(numero_compte, "compte"),
        "titulaire":     pick(titulaire, "titulaire"),
        "periode":       pick(periode, "periode"),
        "transactions":  transactions if transactions else (fallback.get("transactions") or []),
        # optionnel: debug
        "_debug": {
            "yolo_found": {k: len(v) for k, v in detections.items()},
            "ocr_full_len": len(ocr_full or ""),
        }
    }
    return data
