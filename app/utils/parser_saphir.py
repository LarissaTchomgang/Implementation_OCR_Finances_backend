# app/utils/parser_saphir.py
# -------------------------------------------------------------
# Parser spécialisé pour les relevés Afriland / SAFIR Consulting
# -------------------------------------------------------------
import re
from typing import List, Dict, Optional, Tuple

# -----------------------
#  REGEX & Normalisation
# -----------------------

# Dates : 02/01/2025 ou 31/12/24 (tolère 2 ou 4 chiffres d'année)
DATE_RE = r"(?:0?[1-9]|[12][0-9]|3[01])/(?:0?[1-9]|1[0-2])/(?:\d{2}|\d{4})"
DATE_LINE_RE = re.compile(rf"^\s*({DATE_RE})\s+({DATE_RE})\s+(.+)$")

# Montants forts (espaces de milliers OU >= 5 chiffres) + décimales éventuelles
AMOUNT_STRONG_RE = re.compile(
    r"(?<!\d)(?:\d{1,3}(?:[ \u00A0]\d{3})+|\d{5,})(?:[.,]\d{2})?(?!\d)"
)

# Mots-clés (filet de sécurité si on ne peut pas déduire le sens par le solde)
DEBIT_KW = ("frais", "commission", "comm.", "tx", "taxe", "découvert", "decouvert",
            "intérêts", "interets", "dbt", "débit", "debit")
CREDIT_KW = ("virement", "versement", "remboursement", "remb", "cime", "salaire",
             "crédit", "credit")

def _norm_spaces(s: str) -> str:
    return s.replace("\u00A0", " ").strip()

def _norm_amount_txt(txt: str) -> str:
    """ '1 257 225' -> '1257225' ; '5,40' -> '5.40' """
    return _norm_spaces(txt).replace(" ", "").replace(",", ".")

def _to_number(txt: str) -> Optional[float]:
    try:
        return float(_norm_amount_txt(txt))
    except Exception:
        return None

def _has_kw(s: str, kws: Tuple[str, ...]) -> bool:
    s = s.lower()
    return any(k in s for k in kws)

# -----------------------
#  Détection SAFIR
# -----------------------

def is_saphir_statement(text_or_lines) -> bool:
    """Heuristique robuste pour repérer le format Afriland / SAFIR."""
    if isinstance(text_or_lines, str):
        joined = text_or_lines.lower()
    else:
        joined = " ".join([str(x) for x in text_or_lines]).lower()
    return (
        "extrait de compte" in joined
        and ("afriland" in joined or "afriland first bank" in joined)
    ) or ("safir consulting cameroun" in joined)

# -----------------------
#  Extraction en-tête
# -----------------------

def _extract_header(lines: List[str]) -> Dict[str, Optional[str]]:
    banque = "AFRILAND FIRST BANK"  # format connu
    titulaire = None
    compte = None
    solde_initial = None

    # captures possibles :
    # "Nom du client : Societe SAFIR CONSULTING CAMEROUN"
    # "Libellé du compte : SAFIR CONSULTING CAMEROUN"
    # "Numéro de compte : 00002-08237521001-09 XAF"
    # "Solde initial (XAF) : 1 823 518"
    for raw in lines:
        l = _norm_spaces(raw)

        # titulaire
        if "nom du client" in l.lower():
            # après le ':'
            parts = l.split(":", 1)
            if len(parts) == 2:
                titulaire = parts[1].strip()
        if (not titulaire) and "libellé du compte" in l.lower():
            parts = l.split(":", 1)
            if len(parts) == 2:
                titulaire = parts[1].strip()

        # compte
        if "numéro de compte" in l.lower() or "numero de compte" in l.lower():
            parts = l.split(":", 1)
            if len(parts) == 2:
                compte = parts[1].strip()
                # nettoie éventuel "XAF"
                compte = re.sub(r"\bXAF\b", "", compte, flags=re.I).strip()

        # solde initial
        if "solde initial" in l.lower():
            m = AMOUNT_STRONG_RE.search(l)
            if m:
                solde_initial = _norm_amount_txt(m.group())

    return {
        "banque": banque,
        "titulaire": titulaire,
        "compte": compte,
        "solde_initial": solde_initial,
    }

# -----------------------
#  Préparation des lignes du tableau
# -----------------------

def _collect_table_rows(all_lines: List[str]) -> List[str]:
    """
    Concatène les lignes de description qui sont *cassées* par l'OCR.
    On ouvre une ligne quand elle **commence par** 'date date_valeur ...'.
    Les lignes suivantes sans date-value sont rattachées à la description.
    """
    rows: List[str] = []
    current: Optional[str] = None

    # Où commence le tableau ? repère la ligne d'en-tête
    # ex: "Date  Date de valeur  Opération  Débit (XAF)  Crédit (XAF)  Solde (XAF)"
    start_idx = 0
    for i, raw in enumerate(all_lines):
        low = raw.lower()
        if "opération" in low or "operation" in low:
            if "date" in low and "solde" in low:
                start_idx = i + 1
                break

    for raw in all_lines[start_idx:]:
        line = _norm_spaces(raw)
        if not line:
            continue

        m = re.match(rf"^\s*{DATE_RE}\s+{DATE_RE}\b", line)
        if m:
            # nouvelle ligne
            if current:
                rows.append(current)
            current = line
        else:
            # continuation de la description (si une ligne est en cours)
            if current:
                current = (current + " " + line).strip()
            else:
                # encore avant le tableau -> on ignore
                continue

    if current:
        rows.append(current)

    return rows

# -----------------------
#  Parsing de chaque ligne
# -----------------------

def _parse_saphir_row(
    row: str,
    prev_balance: Optional[float]
) -> Optional[Dict]:
    """
    row: "02/01/2025 31/12/2024 PRELV ALIOS FINANCE 1224 566 293 1 257 225"
    Retourne dict {date, description, montant, sens, solde}
    Utilise prev_balance (solde précédent) pour déduire le sens quand possible.
    """
    m = DATE_LINE_RE.match(row)
    if not m:
        return None

    date, _date_val, tail = m.groups()
    tail = _norm_spaces(tail)

    # Tous les montants "forts" dans la partie après les dates
    tokens = list(AMOUNT_STRONG_RE.finditer(tail))
    if len(tokens) < 1:
        # pas de solde → ligne inutilisable
        return None

    # Le dernier token est (presque toujours) le SOLDE
    solde_txt = tail[tokens[-1].start():tokens[-1].end()]
    solde = _to_number(solde_txt)
    if solde is None:
        return None

    # Le montant mouvement = token juste avant le solde (quand présent)
    amount = None
    amount_span = None
    if len(tokens) >= 2:
        # Attention : la description peut contenir de petits nombres (ex: "1224")
        # AMOUNT_STRONG_RE exclut la plupart de ces cas, mais on reste prudent.
        amount_txt = tail[tokens[-2].start():tokens[-2].end()]
        amount = _to_number(amount_txt)
        amount_span = (tokens[-2].start(), tokens[-2].end())

    # Déduction du sens (Dr/Cr)
    sens = None
    if amount is not None and prev_balance is not None:
        # Si le nouveau solde = ancien - montant  => Débit
        # Si le nouveau solde = ancien + montant  => Crédit
        if abs((prev_balance - amount) - solde) < 0.51:
            sens = "Dr"
        elif abs((prev_balance + amount) - solde) < 0.51:
            sens = "Cr"

    # Filet de sécurité par mots-clés si sens encore inconnu
    if sens is None:
        if amount is not None:
            if _has_kw(tail, CREDIT_KW):
                sens = "Cr"
            elif _has_kw(tail, DEBIT_KW):
                sens = "Dr"

    # Nettoyage de la description : on enlève le(s) montant(s) et le solde
    # On supprime d'abord le solde
    desc = tail[:tokens[-1].start()] + " " + tail[tokens[-1].end():]
    # Puis, si on a un amount, on retire uniquement ce span précis
    if amount_span:
        s, e = amount_span
        # recalage d'indices après 1er retrait (on recompute dans la desc courante)
        tmp = AMOUNT_STRONG_RE.finditer(desc)
        spans_now = [(m.start(), m.end()) for m in tmp]
        # on enlève le token dont le texte normalisé == amount_txt
        # (plus robuste que de compter les positions strictes)
        # on cherche le meilleur match par distance d'indices
        best_idx = None
        best_dist = 10**9
        for (s2, e2) in spans_now:
            cand = desc[s2:e2]
            if _norm_amount_txt(cand) == _norm_amount_txt(tail[s:e]):
                d = abs(s - s2) + abs(e - e2)
                if d < best_dist:
                    best_dist = d
                    best_idx = (s2, e2)
        if best_idx:
            s2, e2 = best_idx
            desc = (desc[:s2] + " " + desc[e2:]).strip()

    desc = re.sub(r"\s+", " ", desc).strip()

    # Sortie
    out = {
        "date": date,
        "description": desc,
        "montant": _norm_amount_txt(str(int(amount))) if amount is not None and amount.is_integer() else (_norm_amount_txt(str(amount)) if amount is not None else None),
        "sens": sens,
        "solde": _norm_amount_txt(str(int(solde))) if solde.is_integer() else _norm_amount_txt(str(solde)),
    }
    return out

# -----------------------
#  Parsing du tableau complet
# -----------------------

def parse_saphir_transactions(lines: List[str], solde_initial_txt: Optional[str]) -> List[Dict]:
    """
    Construit la liste des transactions *dans l'ordre d'apparition*.
    Utilise le solde initial (si fourni) pour fiabiliser le sens.
    """
    rows = _collect_table_rows(lines)
    txs: List[Dict] = []

    prev_balance: Optional[float] = _to_number(solde_initial_txt) if solde_initial_txt else None

    for r in rows:
        parsed = _parse_saphir_row(r, prev_balance)
        if not parsed:
            continue

        # Mise à jour du solde courant si possible
        if parsed.get("solde") is not None:
            try:
                prev_balance = float(parsed["solde"])
            except Exception:
                pass

        tx = {
            "date": parsed["date"],
            "description": parsed["description"],
            "montant": parsed["montant"],
            "sens": parsed["sens"],
        }
        txs.append(tx)

    return txs

# -----------------------
#  Période (min/max dates)
# -----------------------

def _extract_period_from_txs(transactions: List[Dict]) -> Optional[str]:
    # format attendu "dd/mm/yyyy - dd/mm/yyyy"
    dates = []
    for t in transactions:
        d = t.get("date")
        if d and re.match(DATE_RE, d):
            # normalise années à 4 chiffres si besoin (25 -> 2025 en heuristique simple)
            parts = d.split("/")
            if len(parts[-1]) == 2:
                yy = int(parts[-1])
                parts[-1] = f"20{yy:02d}"  # hypothèse 20xx
            dates.append("/".join(parts))
    if not dates:
        return None
    try:
        # On garde l'ordre d'entrée (déjà chrono sur le relevé)
        start = dates[0]
        end = dates[-1]
        return f"{start} - {end}"
    except Exception:
        return None

# -----------------------
#  Extraction complète
# -----------------------

def extract_saphir_bank_statement_data(ocr_text: str) -> Dict:
    """
    Fonction **indépendante** qui parse un OCR de relevé SAFIR (Afriland) et
    renvoie un dict cohérent avec le reste de ton app :
      { banque, compte, titulaire, periode, transactions }
    """
    # Découpe lignes propres
    lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]

    # Si ce n'est pas un SAFIR, on renvoie une structure vide => tu décideras côté appelant
    if not is_saphir_statement(lines):
        return {
            "banque": None,
            "compte": None,
            "titulaire": None,
            "periode": None,
            "transactions": [],
            "_debug": {"reason": "not_saphir"},
        }

    header = _extract_header(lines)
    txs = parse_saphir_transactions(lines, header.get("solde_initial"))
    periode = _extract_period_from_txs(txs)

    # sortie finale
    out = {
        "banque": header.get("banque"),
        "compte": header.get("compte"),
        "titulaire": header.get("titulaire"),
        "periode": periode,
        "transactions": txs,
        "_debug": {
            "solde_initial": header.get("solde_initial"),
            "tx_count": len(txs),
        },
    }
    return out
