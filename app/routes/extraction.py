from fastapi import APIRouter, UploadFile, File, Body
from fastapi.responses import JSONResponse, FileResponse
import os
import shutil
import time
import traceback
from pdf2image import convert_from_path

from app.utils.parser import extract_bank_statement_data, detect_transactions
from app.utils.yolo_service import extract_with_yolo_and_rules
from app.utils.parser_saphir import extract_saphir_bank_statement_data  # ✅ parse du texte OCR
from app.utils.excel_service import save_to_excel  # ✅ export excel

import pytesseract
from PIL import Image

router = APIRouter()

# -----------------------
# OCR Helper
# -----------------------
def ocr_to_text(filepath: str) -> str:
    """
    Convertit un fichier (pdf/image) en texte OCR brut (français),
    en limitant les césures/lignes cassées.
    """
    config = "--oem 3 --psm 6"  # bloc de texte uniforme
    if filepath.lower().endswith(".pdf"):
        pages = convert_from_path(filepath, dpi=300)  # 300dpi : moins de “/ 24” cassés
        text = "\n".join(pytesseract.image_to_string(p, lang="fra", config=config) for p in pages)
    else:
        text = pytesseract.image_to_string(Image.open(filepath), lang="fra", config=config)

    # Normalisation douce pour éviter les séparations bizarres
    text = text.replace("\u00A0", " ").replace("\u202F", " ").replace("\u2009", " ")
    return text


# -----------------------
# Détection fichier SAFIR
# -----------------------
def is_saphir_file(filepath: str) -> bool:
    """
    Vérifie rapidement si le fichier correspond à un relevé Saphir Consulting.
    OCR brut + recherche de mots-clés.
    """
    try:
        text = ocr_to_text(filepath).lower()
        return "saphir" in text or "afriland" in text
    except Exception:
        return False


# -----------------------
# Route principale : Extraction
# -----------------------
@router.post("/extract")
async def extract_fields(file: UploadFile = File(...)):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # === Cas spécifique SAFIR ===
        if is_saphir_file(temp_path):
            text = ocr_to_text(temp_path)   # ✅ OCR brut
            final_data = extract_saphir_bank_statement_data(text)  # ✅ on passe le texte

        else:
            # === Cas général YOLO ===
            image_paths = []
            if file.filename.lower().endswith(".pdf"):
                pages = convert_from_path(temp_path)
                for i, img in enumerate(pages):
                    p = f"{temp_path}_p{i+1}.png"
                    img.save(p)
                    image_paths.append(p)
            else:
                image_paths = [temp_path]

            final_data = {
                "banque": None,
                "compte": None,
                "titulaire": None,
                "periode": None,
                "transactions": []
            }

            for ipath in image_paths:
                page_data = extract_with_yolo_and_rules(
                    ipath,
                    regex_fallback_fn=extract_bank_statement_data,
                    parse_transactions_fn=detect_transactions
                )

                for k in ["banque", "compte", "titulaire", "periode"]:
                    if not final_data[k] and page_data.get(k):
                        final_data[k] = page_data[k]

                if page_data.get("transactions"):
                    final_data["transactions"].extend(page_data["transactions"])

        return JSONResponse(content={
            "message": "Extraction réussie",
            "extracted_data": final_data
        })

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        for f in os.listdir():
            if f.startswith(temp_path) and f.endswith(".png"):
                try:
                    os.remove(f)
                except:
                    pass


# -----------------------
# Export Excel (Téléchargement direct)
# -----------------------
@router.post("/export-excel-from-json")
async def export_excel_from_json(data: dict = Body(...)):
    try:
        os.makedirs("exports", exist_ok=True)

        # Nom de base + timestamp pour éviter l'écrasement
        base_name = data.get("filename", "releve")
        if base_name.endswith(".xlsx"):
            base_name = base_name[:-5]
        timestamp = int(time.time())  # ex: 1692627890
        out_name = f"{base_name}_{timestamp}.xlsx"

        out_path = os.path.join("exports", out_name)
        save_to_excel(data, out_path)

        # ✅ Retour direct en téléchargement
        return FileResponse(
            path=out_path,
            filename=out_name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        print("ERREUR EXPORT EXCEL:", traceback.format_exc())
        return JSONResponse(status_code=500, content={"error": str(e)})
