from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from PIL import Image
import pytesseract
import os
import shutil
from fastapi import Body
from datetime import datetime
from pdf2image import convert_from_path

from app.utils.parser import extract_bank_statement_data
from app.utils.excel_service import save_to_excel

router = APIRouter()

@router.post("/extract")
async def extract_fields(file: UploadFile = File(...)):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        text = ""

        if file.filename.lower().endswith(".pdf"):
            # ✅ Convertir les pages PDF en images
            images = convert_from_path(temp_path)
            for img in images:
                text += pytesseract.image_to_string(img)
        else:
            # ✅ Traitement standard pour les images
            image = Image.open(temp_path)
            text = pytesseract.image_to_string(image)

        # 🔍 Extraction des données à partir du texte OCR
        data = extract_bank_statement_data(text)

        os.makedirs("exports", exist_ok=True)
        output_path = f"exports/{file.filename.split('.')[0]}.xlsx"

        save_to_excel(data, output_path)

        return JSONResponse(content={
            "message": "Extraction et export réussis",
            "extracted_data": data,
            "excel_file": output_path
        })

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/export-excel-from-json")
async def export_excel_from_json(data: dict = Body(...)):
    """
    Reçoit les données corrigées depuis le frontend (au format JSON)
    et génère un fichier Excel.
    """
    os.makedirs("exports", exist_ok=True)

    # 📛 Utilise le nom d'origine s'il est fourni
    filename = data.get("original_filename")
    if filename:
        filename = filename.replace(" ", "_") + ".xlsx"
    else:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"extracted_{timestamp}.xlsx"

    output_path = os.path.join("exports", filename)

    try:
        save_to_excel(data, output_path)
        return {
            "message": "Export Excel réussi",
            "excel_file": output_path
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
