import xlsxwriter
import os

def save_to_excel(data: dict, output_path: str):
    """
    Sauvegarde les données extraites (banque, compte, titulaire, période, transactions) dans un fichier Excel.
    """
    # Créer le dossier s'il n'existe pas
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    workbook = xlsxwriter.Workbook(output_path)
    worksheet = workbook.add_worksheet("Relevé")

    # Écrire les infos générales
    worksheet.write("A1", "Banque")
    worksheet.write("B1", data.get("banque", ""))

    worksheet.write("A2", "Compte")
    worksheet.write("B2", data.get("compte", ""))

    worksheet.write("A3", "Titulaire")
    worksheet.write("B3", data.get("titulaire", ""))

    worksheet.write("A4", "Période")
    worksheet.write("B4", data.get("periode", ""))

    # Écrire les en-têtes du tableau de transactions
    headers = ["Date", "Description", "Montant", "Sens"]
    for col, header in enumerate(headers):
        worksheet.write(6, col, header)  # Commence à la ligne 7 (index 6)

    # Écrire les transactions
    for row_idx, tx in enumerate(data.get("transactions", []), start=7):
        worksheet.write(row_idx, 0, tx.get("date", ""))
        worksheet.write(row_idx, 1, tx.get("description", ""))
        worksheet.write(row_idx, 2, tx.get("montant", ""))
        worksheet.write(row_idx, 3, tx.get("sens", ""))

    workbook.close()
