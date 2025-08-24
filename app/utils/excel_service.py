import xlsxwriter
import os

def save_to_excel(data: dict, output_path: str):
    """
    Sauvegarde les données extraites (banque, compte, titulaire, période, transactions) dans un fichier Excel.
    Ajoute un logo en haut.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    workbook = xlsxwriter.Workbook(output_path)
    worksheet = workbook.add_worksheet("Relevé")

        # Définir les largeurs de colonnes
    worksheet.set_column(0, 0, 12)   # Colonne A (Date) → largeur 12
    worksheet.set_column(1, 1, 50)   # Colonne B (Description) → largeur 50
    worksheet.set_column(2, 2, 15)   # Colonne C (Montant) → largeur 15
    worksheet.set_column(3, 3, 10)   # Colonne D (Sens) → largeur 10


    # -------------------
    # Ajouter le logo
    # -------------------
    logo_path = os.path.join(os.path.dirname(__file__), "LOGO SAFIR.png")
    if os.path.exists(logo_path):
        worksheet.insert_image("A1", logo_path, {
            "x_scale": 0.4,
            "y_scale": 0.2
        })

    # -------------------
    # Infos générales (décalées pour ne pas écraser le logo)
    # -------------------
    worksheet.write("A8", "Banque")
    worksheet.write("B8", data.get("banque", ""))

    worksheet.write("A9", "Compte")
    worksheet.write("B9", data.get("compte", ""))

    worksheet.write("A10", "Titulaire")
    worksheet.write("B10", data.get("titulaire", ""))

    worksheet.write("A11", "Période")
    worksheet.write("B11", data.get("periode", ""))

    # -------------------
    # En-têtes transactions
    # -------------------
    headers = ["Date", "Description", "Montant", "Sens"]
    for col, header in enumerate(headers):
        worksheet.write(13, col, header)  # ligne 12

    # -------------------
    # Transactions
    # -------------------
    for row_idx, tx in enumerate(data.get("transactions", []), start=14):
        worksheet.write(row_idx, 0, tx.get("date", ""))
        worksheet.write(row_idx, 1, tx.get("description", ""))
        worksheet.write(row_idx, 2, tx.get("montant", ""))
        worksheet.write(row_idx, 3, tx.get("sens", ""))

    workbook.close()
