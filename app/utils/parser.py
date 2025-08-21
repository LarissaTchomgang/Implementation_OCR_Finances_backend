import re
from rapidfuzz import fuzz

# =========================
# Mots-clés génériques
# =========================
BANK_KEYWORDS = [
    "bank", "banque", "banco", "banca",
    "bnp", "société générale", "sg", "barclays", "hsbc", "lcl", "credit agricole"
]

ACCOUNT_KEYWORDS = ["account", "compte", "numéro de compte", "acc no", "iban"]
TITLE_KEYWORDS = ["mr", "ms", "mme", "madame", "monsieur"]

DATE_REGEX = r"\d{2}/\d{2}/\d{4}"

# =========================
# Extraction principale
# =========================
def extract_bank_statement_data(ocr_text: str):
    """
    Garde l'API existante. Détecte Saphir et applique un parseur spécialisé
    pour les transactions, sinon fallback générique.
    """
    lines = [l.strip() for l in ocr_text.split('\n') if l.strip()]
    # ✅ Saphir → override nom banque et titulaire
    if is_safir_statement(lines):
        banque_name = "AFRILAND FIRST BANK"
        titulaire = "SAFIR CONSULTING CAMEROUN"
    else:
        banque_name = detect_bank(lines)
        titulaire = detect_title_holder(lines)

    data = {
        "banque": banque_name,
        "compte": detect_account(lines),
        "titulaire": titulaire,
        "periode": detect_period(lines),
        "transactions": detect_transactions(lines)
    }
    return data

# =========================
# Détections génériques
# =========================
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
                # retire espaces et tirets pour capturer un bloc de chiffres
                cleaned = line.replace(" ", "").replace("-", "")
                account_numbers = re.findall(r"\d{6,}", cleaned)
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

# =========================
# Détection transactions (générique)
# =========================
DATE_PATTERNS = [
    r"\d{2}/\d{2}/\d{4}",   # 03/02/2021
    r"\d{2}/\d{2}",         # 03/02
    r"\d{1,2} \w{3} \d{2,4}" # 14 Feb 13
]
DATE_REGEX_COMBINED = "(" + "|".join(DATE_PATTERNS) + ")"

# Montant « isolé » (prise stricte pour éviter les collages)
AMOUNT_REGEX = r"(?<!\d)(?:\d{1,3}(?:[ \u00A0]\d{3})+|\d+)(?:[.,]\d{2})?(?!\d)"

def detect_transactions(lines):
    """
    Si Saphir → parse spécialisé. Sinon fallback générique existant (légèrement fiabilisé).
    """
    if is_safir_statement(lines):
        return parse_safir_transactions(lines)

    # --------- Fallback générique (inchangé dans l’API, fiabilisé pour la description) ----------
    transactions = []
    buffer_line = ""

    for line in lines:
        if not re.search(DATE_REGEX_COMBINED, line) and buffer_line:
            buffer_line += " " + line
        else:
            if buffer_line:
                tx = parse_transaction_line(buffer_line)
                if tx:
                    transactions.append(tx)
            buffer_line = line

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

    # Trouve tous les montants avec leurs spans
    amounts = list(re.finditer(AMOUNT_REGEX, line))
    montant_str = None
    montant_span = None

    if amounts:
        # Premier montant après la date → évite typiquement le solde
        after_date_idx = date_match.end()
        after = [m for m in amounts if m.start() >= after_date_idx]
        pick = after[0] if after else amounts[0]
        montant_span = (pick.start(), pick.end())
        montant_str = _normalize_amount(pick.group())

    # Nettoyage de description en retirant la date et l’unique montant choisi (via spans)
    description = line
    # retire la date
    description = re.sub(DATE_REGEX_COMBINED, "", description)
    # retire le montant choisi par span (si trouvé)
    if montant_span:
        s, e = montant_span
        # il faut repérer ce span sur la chaîne RÉSIDUELLE : on recalcule en partant du texte original
        before = line[:s]
        middle = line[s:e]
        after = line[e:]
        # retire middle du texte re-daté
        desc_base = before + after
        description = re.sub(DATE_REGEX_COMBINED, "", desc_base)

    description = re.sub(r"\s+", " ", description).strip()

    # Sens basique
    sens = None
    if montant_str and montant_str.startswith("-"):
        sens = "Dr"
        montant_str = montant_str.lstrip("-")
    elif re.search(r"\bcredit\b|\bcr\b", line, re.I):
        sens = "Cr"
    elif re.search(r"\bdebit\b|\bdr\b", line, re.I):
        sens = "Dr"
    elif "+" in line:
        sens = "Cr"
    elif "-" in line and not sens:
        sens = "Dr"

    return {
        "date": date,
        "description": description,
        "montant": montant_str,
        "sens": sens
    }

# =========================
# Règles spécifiques SAFIR
# =========================
def is_safir_statement(lines):
    joined = " ".join(lines).lower()
    # marqueurs très stables visibles sur tes exemples
    return ("safir consulting cameroun" in joined) or ("extrait de compte" in joined and "débit (xaf)" in joined)

DEBIT_KEYWORDS = [
    "frais", "commission", "comm.", "tx", "taxe", "découvert", "decouvert",
    "intérêts", "interets", "intérêts débiteurs", "interets debiteurs", "prélèv", "prelev", "prelv", "dbt"
]
CREDIT_KEYWORDS = [
    "virement", "versement", "remboursement", "remb", "cime", "salaire", "crédit", "credit"
]

# Token montant plus permissif (accepte () et symboles)
_AMOUNT_TOKEN = re.compile(r"\(?[+\-]?(?:\d{1,3}(?:[ \u00A0]\d{3})+|\d+)(?:[.,]\d{2})?\)?")

def _normalize_amount(s: str) -> str:
    """
    "1 257 225" -> "1257225" ; "5,40" -> "5.40" ; enlève () XAF FCFA € $ et espaces.
    Supprime ponctuation orpheline à droite.
    """
    s = s.strip()
    s = s.replace("\u00A0", " ")
    s = s.replace(" ", "")
    # Retire symboles monnaie/parenthèses
    s = s.replace("XAF", "").replace("FCFA", "").replace("xaf", "").replace("fcfa", "")
    s = s.replace("€", "").replace("$", "").replace("(", "").replace(")", "")
    # virgules -> point
    s = s.replace(",", ".")
    # garde chiffres, point et signe
    s = re.sub(r"[^0-9\.\-]", "", s)
    # supprime point/virgule final(e)
    s = re.sub(r"[.,]$", "", s)
    return s

def _to_float(s: str):
    try:
        return float(s)
    except Exception:
        return None

def _close_enough(a: float, b: float) -> bool:
    """Tolérance ~2% ou ±5 unités."""
    if a is None or b is None:
        return False
    if a == 0:
        return abs(b) <= 1.0
    return (abs(a - b) / max(1.0, abs(a)) <= 0.02) or (abs(a - b) <= 5.0)

def _find_initial_balance(lines):
    """
    Cherche 'Solde initial' et renvoie sa valeur float si trouvée.
    """
    for l in lines:
        if re.search(r"solde\s+initial", l, re.I):
            am = list(re.finditer(AMOUNT_REGEX, l))
            if am:
                norm = _normalize_amount(am[-1].group())
                return _to_float(norm)
    return None

def _build_safir_rows(lines):
    """
    Recompose des lignes complètes Saphir :
    - si une ligne 'description' précède la ligne date, on l'attache (pending_prefix)
    - on concatène aussi les suites (lignes non-date) après la ligne date
    Renvoie une liste de strings 'DATE DATE_VALEUR ...'
    """
    date_line_re = re.compile(r"^\s*\d{2}/\d{2}/\d{4}\s+\d{2}/\d{2}/\d{4}\b")
    rows = []
    pending_prefix = ""
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        if date_line_re.match(line):
            row = line
            if pending_prefix:
                row = row + " " + pending_prefix
                pending_prefix = ""
            j = i + 1
            while j < n and not date_line_re.match(lines[j]):
                extra = lines[j].strip()
                # ignore les lignes purement bruitées trop courtes
                if extra:
                    row += " " + extra
                j += 1
            rows.append(row)
            i = j
        else:
            # si la prochaine est une ligne de date, on garde celle-ci pour l'ajouter
            if i + 1 < n and date_line_re.match(lines[i + 1]):
                pending_prefix = line
            # sinon, on ignore (souvent en-têtes ou bruit)
            i += 1
    return rows

def parse_safir_transactions(lines):
    """
    SAFIR : colonnes -> Date | Date valeur | Opération | Débit | Crédit | Solde
    - utilise Solde initial pour déduire le sens et valider le montant
    - retire proprement montant & solde de la description
    - robuste aux tokens cassés, () et symboles
    """
    transactions = []
    prev_solde = _find_initial_balance(lines)
    rows = _build_safir_rows(lines)

    row_re = re.compile(r"^\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(.+)$")

    for row in rows:
        m = row_re.match(row)
        if not m:
            continue
        date, _date_val, tail = m.groups()

        # Tous les tokens montants avec leurs spans
        tokens = [(mm.start(), mm.end(), mm.group()) for mm in _AMOUNT_TOKEN.finditer(tail)]
        # Garde uniquement ceux qui se convertissent en nombre
        parsed = []
        for s, e, txt in tokens:
            norm = _normalize_amount(txt)
            val = _to_float(norm)
            if val is not None:
                parsed.append((s, e, txt, norm, val))

        if not parsed:
            # aucune valeur exploitable -> on garde la description nettoyée
            description = re.sub(DATE_REGEX_COMBINED, "", tail)
            description = re.sub(r"\s+", " ", description).strip()
            transactions.append({
                "date": date,
                "description": description,
                "montant": None,
                "sens": None
            })
            continue

        # Hypothèse solide : le dernier token est le Solde
        parsed.sort(key=lambda t: t[0])
        solde_s, solde_e, solde_txt, solde_norm, solde_val = parsed[-1]

        # Choisir le montant : idéalement |solde - prev_solde|
        montant_match = None
        if prev_solde is not None and solde_val is not None:
            delta = abs(solde_val - prev_solde)
            # parmi les tokens sauf le dernier, on prend la valeur la plus proche de delta
            candidates = parsed[:-1]
            if candidates:
                scored = sorted(candidates, key=lambda t: abs(t[4] - delta))
                if scored and _close_enough(delta, scored[0][4]):
                    montant_match = scored[0]

        # fallback : si pas trouvé par delta, on prend l'avant-dernier token (si dispo)
        if montant_match is None:
            if len(parsed) >= 2:
                montant_match = parsed[-2]
            else:
                montant_match = parsed[0]

        m_s, m_e, m_txt, m_norm, m_val = montant_match

        # Déterminer le sens :
        # - si on connaît prev_solde : solde augmente -> Cr ; diminue -> Dr
        # - sinon heuristique sur mots-clés
        if prev_solde is not None and solde_val is not None:
            sens = "Cr" if solde_val >= prev_solde else "Dr"
        else:
            low = tail.lower()
            if any(k in low for k in CREDIT_KEYWORDS):
                sens = "Cr"
            elif any(k in low for k in DEBIT_KEYWORDS):
                sens = "Dr"
            else:
                sens = None

        # Nettoyer la description en retirant précisément montant & solde (par spans)
        spans_to_remove = sorted([(m_s, m_e), (solde_s, solde_e)], key=lambda x: x[0])
        description_parts = []
        last = 0
        for s, e in spans_to_remove:
            if s > last:
                description_parts.append(tail[last:s])
            last = e
        if last < len(tail):
            description_parts.append(tail[last:])
        description = "".join(description_parts)

        # Retire les dates résiduelles et nettoie espaces
        description = re.sub(DATE_REGEX_COMBINED, "", description, flags=re.IGNORECASE)
        # Retire mentions explicites de colonnes si l’OCR les recopie parfois
        description = re.sub(r"\b(débit|debit|crédit|credit|solde)\b", "", description, flags=re.IGNORECASE)
        description = re.sub(r"\s+", " ", description).strip(" :-\u00A0")

        # MAJ prev_solde pour prochaine ligne
        if solde_val is not None:
            prev_solde = solde_val

        transactions.append({
            "date": date,
            "description": description if description else None,
            "montant": m_norm,   # string normalisée "1257225" / "10195.00" etc.
            "sens": sens,
            "solde": solde_norm  # champ en plus (ignoré par ton Excel actuel, utile au debug)
        })

    return transactions
