import re

def extract_bank_statement_data(ocr_text):
    lines = ocr_text.split('\n')
    data = {
        "banque": None,
        "compte": None,
        "titulaire": None,
        "periode": None,
        "transactions": []
    }

    # 1. Recherche Banque
    for line in lines:
        if "bank" in line.lower():
            data["banque"] = line.strip()
            break

    # 2. Compte
    for line in lines:
        if "account" in line.lower() or "compte" in line.lower():
            account_numbers = re.findall(r"\d{6,}", line)
            if account_numbers:
                data["compte"] = account_numbers[0]
                break

    # 3. Titulaire
    for line in lines:
        if "mr" in line.lower() or "ms" in line.lower():
            data["titulaire"] = line.strip()
            break

    # 4. Période
    for line in lines:
        if re.search(r"\d{2}/\d{2}/\d{4}", line):
            dates = re.findall(r"\d{2}/\d{2}/\d{4}", line)
            if len(dates) >= 2:
                data["periode"] = f"{dates[0]} - {dates[1]}"
                break

    # 5. Transactions (meilleure version avec lignes OCR)
    transaction_lines = lines[90:111]  # Ajuste si besoin
    data["transactions"] = extract_transactions_from_lines(lines)

    return data



def extract_transactions_from_lines(lines):
    transactions = []
    for line in lines:
        if re.search(r"\d{2}/\d{2}/\d{4}", line) and re.search(r"\d+\.\d{2}", line):
            date_match = re.search(r"\d{2}/\d{2}/\d{4}", line)
            date = date_match.group()

            # Récupère tous les montants
            amounts = re.findall(r"\d+\.\d{2}", line)
            if len(amounts) >= 1:
                montant = amounts[0]  # On prend le premier montant
                description = line.replace(date, "").replace(montant, "").strip()
                sens = "Cr" if "credit" in line.lower() or "payment" in line.lower() else "Dr"

                transactions.append({
                    "date": date,
                    "description": description,
                    "montant": montant,
                    "sens": sens
                })

                
    return transactions

