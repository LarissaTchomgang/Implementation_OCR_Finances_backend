from fastapi import APIRouter, UploadFile, File, Body
from fastapi.responses import JSONResponse, FileResponse
import os
import shutil
from pdf2image import convert_from_path

from app.utils.parser import extract_bank_statement_data, detect_transactions
from app.utils.yolo_service import extract_with_yolo_and_rules
from app.utils.parser_saphir import extract_saphir_bank_statement_data  # ✅ parse du texte OCR

import pytesseract
from PIL import Image

router = APIRouter()

# -----------------------
# OCR Helper
# -----------------------
def ocr_to_text(filepath: str) -> str:
    """
    Convertit un fichier (pdf/image) en texte OCR brut (français).
    """
    if filepath.lower().endswith(".pdf"):
        pages = convert_from_path(filepath, dpi=200)
        text = "\n".join(pytesseract.image_to_string(p, lang="fra") for p in pages)
    else:
        text = pytesseract.image_to_string(Image.open(filepath), lang="fra")
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
# Route principale
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

@router.post("/export-excel-from-json")
async def export_excel_from_json(data: dict = Body(...)):
    try:
        from app.utils.excel_service import save_to_excel

        os.makedirs("exports", exist_ok=True)
        out_name = data.get("filename", "releve.xlsx")
        if not out_name.endswith(".xlsx"):
            out_name += ".xlsx"
        out_path = os.path.join("exports", out_name)

        save_to_excel(data, out_path)

        return {"message": "Excel généré avec succès", "excel_file": out_path}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})