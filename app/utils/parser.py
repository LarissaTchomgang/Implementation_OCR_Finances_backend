import re
from rapidfuzz import fuzz

# Liste élargie de mots-clés et noms possibles
BANK_KEYWORDS = [
    "bank", "banque", "banco", "banca",
    "bnp", "société générale", "sg", "barclays", "hsbc", "lcl", "credit agricole"
]

ACCOUNT_KEYWORDS = ["account", "compte", "numéro de compte", "acc no", "iban"]

TITLE_KEYWORDS = ["mr", "ms", "mme", "madame", "monsieur"]

DATE_REGEX = r"\d{2}/\d{2}/\d{4}"

# -----------------------
# Extraction principale
# -----------------------

def extract_bank_statement_data(ocr_text):
    lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
    data = {
        "banque": detect_bank(lines),
        "compte": detect_account(lines),
        "titulaire": detect_title_holder(lines),
        "periode": detect_period(lines),
        "transactions": detect_transactions(lines)
    }
    return data

# -----------------------
# Détections simples mais flexibles
# -----------------------

def detect_bank(lines):
    for line in lines:
        for kw in BANK_KEYWORDS:
            if fuzz.partial_ratio(kw.lower(), line.lower()) > 80:
                return line
    return None

def detect_account(lines):
    for line in lines:
        for kw in ACCOUNT_KEYWORDS:
            if fuzz.partial_ratio(kw.lower(), line.lower()) > 80:
                account_numbers = re.findall(r"\d{6,}", line.replace(" ", ""))
                if account_numbers:
                    return account_numbers[0]
    return None

def detect_title_holder(lines):
    for line in lines:
        for kw in TITLE_KEYWORDS:
            if fuzz.partial_ratio(kw.lower(), line.lower()) > 80:
                return line
    return None

def detect_period(lines):
    dates = []
    for line in lines:
        matches = re.findall(DATE_REGEX, line)
        if matches:
            dates.extend(matches)
    if len(dates) >= 2:
        return f"{dates[0]} - {dates[1]}"
    return None

# -----------------------
# Détection dynamique des transactions
# -----------------------

# Formats multiples de date
DATE_PATTERNS = [
    r"\d{2}/\d{2}/\d{4}",   # 03/02/2021
    r"\d{2}/\d{2}",         # 03/02
    r"\d{1,2} \w{3} \d{2,4}" # 14 Feb 13
]
DATE_REGEX_COMBINED = "(" + "|".join(DATE_PATTERNS) + ")"

# Montant : accepte , ou . comme séparateur
AMOUNT_REGEX = r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})"

def detect_transactions(lines):
    transactions = []
    buffer_line = ""

    for line in lines:
        # Fusionner avec ligne précédente si pas de date détectée
        if not re.search(DATE_REGEX_COMBINED, line) and buffer_line:
            buffer_line += " " + line
        else:
            if buffer_line:
                tx = parse_transaction_line(buffer_line)
                if tx:
                    transactions.append(tx)
            buffer_line = line

    # Dernière transaction
    if buffer_line:
        tx = parse_transaction_line(buffer_line)
        if tx:
            transactions.append(tx)

    return transactions

def parse_transaction_line(line):
    date_match = re.search(DATE_REGEX_COMBINED, line)
    if not date_match:
        return None
    date = date_match.group().strip()

    # On récupère tous les montants
    amounts = re.findall(AMOUNT_REGEX, line)
    montant = None

    if amounts:
        # Chercher le premier montant après la date → éviter le solde final
        date_end_index = date_match.end()
        after_date_text = line[date_end_index:]
        after_date_amounts = re.findall(AMOUNT_REGEX, after_date_text)
        
        if after_date_amounts:
            montant = after_date_amounts[0]  # Premier montant après la date
        else:
            montant = amounts[0]  # fallback si rien trouvé

    # Nettoyage de la description
    description = line
    description = re.sub(DATE_REGEX_COMBINED, "", description)
    if montant:
        description = description.replace(montant, "")
    description = re.sub(r"\s+", " ", description).strip()

    # Sens basé sur signes et mots clés
    sens = None
    if montant and montant.strip().startswith("-"):
        sens = "Dr"
        montant = montant.strip().lstrip("-")  # On enlève le signe du montant
    elif "credit" in line.lower() or re.search(r"\bcr\b", line.lower()):
        sens = "Cr"
    elif "debit" in line.lower() or re.search(r"\bdr\b", line.lower()):
        sens = "Dr"
    elif "+" in line:
        sens = "Cr"
    elif "-" in line and not sens:
        sens = "Dr"

    return {
        "date": date,
        "description": description,
        "montant": montant,
        "sens": sens
    }
