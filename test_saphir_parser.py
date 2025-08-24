import re
import json
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

# -----------------------
# Regex utilitaires
# -----------------------
DATE_RE = r"(?:0?[1-9]|[12][0-9]|3[01])/(?:0?[1-9]|1[0-2])/(?:\d{2}|\d{4})"
LINE_RE = re.compile(rf"^\s*({DATE_RE})\s+({DATE_RE})\s+(.+)$")
AMOUNT_RE = re.compile(r"\d{1,3}(?:[ \u00A0]\d{3})*(?:[.,]\d{2})?|\d+")

def _norm_num(txt: str) -> str:
    return txt.replace("\u00A0", " ").replace(" ", "").replace(",", ".")

def _to_float(txt: str):
    try:
        return float(_norm_num(txt))
    except:
        return None

# -----------------------
# Parsing ligne SAFIR
# -----------------------
def _parse_saphir_row(line: str):
    m = LINE_RE.match(line)
    if not m:
        return None
    date, date_valeur, tail = m.groups()

    numbers = list(AMOUNT_RE.finditer(tail))
    if not numbers:
        return None

    solde_txt = numbers[-1].group()
    solde = _to_float(solde_txt)

    montant = None
    if len(numbers) >= 2:
        montant_txt = numbers[-2].group()
        montant = _to_float(montant_txt)

    desc_end = numbers[-2].start() if len(numbers) >= 2 else numbers[-1].start()
    description = tail[:desc_end].strip()

    sens = None
    low = description.lower()
    if "virement" in low or "versement" in low or "remboursement" in low:
        sens = "Cr"
    elif "frais" in low or "commission" in low or "taxe" in low or "intérêt" in low or "interet" in low:
        sens = "Dr"
    else:
        sens = "Dr"

    return {
        "date": date,
        "date_valeur": date_valeur,
        "description": description,
        "montant": montant,
        "solde": solde,
        "sens": sens,
    }

# -----------------------
# Fonction principale
# -----------------------
def extract_saphir_bank_statement_data(ocr_text: str):
    transactions = []
    for raw in ocr_text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        tx = _parse_saphir_row(raw)
        if tx:
            transactions.append(tx)

    return {
        "banque": "AFRILAND FIRST BANK",
        "compte": None,
        "titulaire": None,
        "periode": None,
        "transactions": transactions,
        "_debug": {"tx_count": len(transactions)},
    }

# -----------------------
# OCR + Test
# -----------------------
def ocr_file(filepath: str) -> str:
    if filepath.lower().endswith(".pdf"):
        pages = convert_from_path(filepath, dpi=200)
        text = "\n".join(pytesseract.image_to_string(p, lang="eng") for p in pages)
    else:
        text = pytesseract.image_to_string(Image.open(filepath), lang="eng")
    return text

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python test_saphir_parser.py fichier.pdf|image")
        sys.exit(1)

    file = sys.argv[1]
    ocr_text = ocr_file(file)
    result = extract_saphir_bank_statement_data(ocr_text)

    print(json.dumps(result, indent=2, ensure_ascii=False))
