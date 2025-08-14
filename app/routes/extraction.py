from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
import os
import shutil
from pdf2image import convert_from_path

from app.utils.parser import extract_bank_statement_data, detect_transactions
from app.utils.yolo_service import extract_with_yolo_and_rules

router = APIRouter()


@router.post("/extract")
async def extract_fields(file: UploadFile = File(...)):
    temp_path = f"temp_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
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

        os.makedirs("exports", exist_ok=True)
        out_name = os.path.splitext(os.path.basename(file.filename))[0] + ".xlsx"
        out_path = os.path.join("exports", out_name)

        from app.utils.excel_service import save_to_excel
        save_to_excel(final_data, out_path)

        return JSONResponse(content={
            "message": "Extraction et export réussis",
            "extracted_data": final_data,
            "excel_file": out_path
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
