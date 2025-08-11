import cv2
import numpy as np
from PIL import Image
import pytesseract
import io
from pdf2image import convert_from_bytes
import re
from typing import List, Dict, Union
import logging
import os

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TableExtractor:
    def __init__(self, debug_mode=False):
        self.debug_mode = debug_mode
        self.min_cell_width = 20
        self.min_cell_height = 10
        self.pdf_dpi = 400  # Augmenté pour meilleure qualité
        self.ocr_config = '--oem 3 --psm 6 -c preserve_interword_spaces=1'
        
    def save_debug_image(self, img_np, step_name):
        """Sauvegarde les images intermédiaires pour debug"""
        if self.debug_mode:
            debug_dir = "debug_images"
            os.makedirs(debug_dir, exist_ok=True)
            cv2.imwrite(f"{debug_dir}/{step_name}.png", img_np)

    def preprocess_image(self, img_np):
        """Prétraitement amélioré de l'image"""
        # Conversion en niveaux de gris si nécessaire
        if len(img_np.shape) == 3:
            img_np = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
        
        # Dénosage et amélioration du contraste
        img_np = cv2.fastNlMeansDenoising(img_np, None, 30, 7, 21)
        img_np = cv2.equalizeHist(img_np)
        
        # Binarisation adaptative
        img_np = cv2.adaptiveThreshold(
            img_np, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        self.save_debug_image(img_np, "1_preprocessed")
        return img_np

    def detect_table_contours(self, img_np):
        """Détection améliorée des contours de tableau"""
        # Détection des lignes
        kernel_length = max(5, img_np.shape[1] // 100)
        
        # Kernel horizontal
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_length, 1))
        horizontal = cv2.morphologyEx(img_np, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        
        # Kernel vertical
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_length))
        vertical = cv2.morphologyEx(img_np, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        
        # Combinaison
        table_structure = cv2.addWeighted(horizontal, 0.5, vertical, 0.5, 0.0)
        table_structure = cv2.dilate(table_structure, np.ones((3,3), np.uint8), iterations=2)
        
        self.save_debug_image(table_structure, "2_table_structure")
        return table_structure

    def extract_table_data(self, img_np, table_mask):
        """Extraction des données du tableau"""
        contours, _ = cv2.findContours(table_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            logger.warning("Aucun contour détecté")
            return []
        
        # Tri des contours de gauche à droite et de haut en bas
        contours = sorted(contours, key=lambda c: (cv2.boundingRect(c)[1], cv2.boundingRect(c)[0]))
        
        extracted_data = []
        for i, contour in enumerate(contours):
            x, y, w, h = cv2.boundingRect(contour)
            
            if w < self.min_cell_width or h < self.min_cell_height:
                continue
                
            roi = img_np[y:y+h, x:x+w]
            self.save_debug_image(roi, f"3_cell_{i}")
            
            # OCR avec configuration optimisée
            text = pytesseract.image_to_string(
                Image.fromarray(roi),
                config=self.ocr_config,
                lang='fra+eng'  # Français + Anglais
            ).strip()
            
            if text:
                logger.info(f"Cellule {i} détectée - Position: {x},{y} - Taille: {w}x{h} - Texte: '{text}'")
                extracted_data.append(text)
        
        return extracted_data

    def extract_from_image(self, pil_img):
        """Traitement d'une seule image"""
        img_np = np.array(pil_img)
        original_img = img_np.copy()
        
        # Pré-traitement
        processed_img = self.preprocess_image(img_np)
        
        # Détection tableau
        table_mask = self.detect_table_contours(processed_img)
        
        # Extraction données
        table_data = self.extract_table_data(255 - processed_img, table_mask)  # Inversion pour OCR
        
        # Si échec détection tableau, essayer extraction brute
        if not table_data:
            logger.warning("Aucun tableau détecté - Tentative d'extraction brute")
            text = pytesseract.image_to_string(pil_img, config=self.ocr_config)
            table_data = [line for line in text.split('\n') if line.strip()]
        
        return table_data

    def extract_table_lines(self, file_bytes: bytes, filename: str = "") -> List[Union[Dict[str, str], str]]:
        """Fonction principale d'extraction"""
        try:
            logger.info(f"Début traitement du fichier: {filename}")
            
            # Conversion PDF si nécessaire
            if filename.lower().endswith(".pdf"):
                images = convert_from_bytes(file_bytes, dpi=self.pdf_dpi, fmt='png')
                logger.info(f"{len(images)} pages détectées dans le PDF")
            else:
                images = [Image.open(io.BytesIO(file_bytes))]
            
            all_data = []
            for i, img in enumerate(images):
                logger.info(f"Traitement page/image {i+1}")
                page_data = self.extract_from_image(img)
                all_data.extend(page_data)
                
                # Log toutes les données extraites
                logger.info(f"Données extraites (page {i+1}):\n{'-'*40}")
                for j, data in enumerate(page_data):
                    logger.info(f"{j+1}: {data}")
                logger.info("-"*40)
            
            if not all_data:
                logger.error("Aucune donnée extraite de l'image/PDF")
                return []
            
            # Tentative de structuration automatique
            try:
                structured_data = self.auto_structure_data(all_data)
                return structured_data
            except Exception as e:
                logger.warning(f"Échec structuration automatique: {str(e)} - Retour données brutes")
                return all_data
                
        except Exception as e:
            logger.error(f"Erreur lors de l'extraction: {str(e)}", exc_info=True)
            raise

    def auto_structure_data(self, lines: List[str]) -> List[Dict[str, str]]:
        """Tente de structurer automatiquement les données"""
        # Détection des colonnes par alignement
        split_lines = [re.split(r'\s{2,}', line.strip()) for line in lines if line.strip()]
        
        if not split_lines:
            return []
        
        # Vérifie si toutes les lignes ont le même nombre de colonnes
        col_counts = [len(parts) for parts in split_lines]
        if len(set(col_counts)) != 1:
            logger.warning("Nombre de colonnes incohérent - retour données brutes")
            return lines
            
        # Création des en-têtes
        num_cols = col_counts[0]
        headers = [f"Colonne_{i+1}" for i in range(num_cols)]
        
        # Construction des dictionnaires
        structured_data = []
        for parts in split_lines:
            if len(parts) == num_cols:
                structured_data.append(dict(zip(headers, parts)))
            else:
                structured_data.append({"Donnée": " ".join(parts)})
        
        return structured_data