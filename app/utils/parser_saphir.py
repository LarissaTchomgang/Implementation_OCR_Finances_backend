import re
from typing import List, Dict, Optional, Tuple

# =======================
# Dates & helpers
# =======================
DATE_RE = r"(?:0?[1-9]|[12][0-9]|3[01])/(?:0?[1-9]|1[0-2])/(?:\d{2}|\d{4})"
DATE_LINE_RE = re.compile(rf"^\s*({DATE_RE})\s+({DATE_RE})\s+(.+)$")

SPACE_VARIANTS = ("\u00A0", "\u202F", "\u2009", "\u2007")
THOUS_SEP_CLASS = r"[ \u00A0\u202F\u2009\u2007\.'’]"

# Montants (gros nombres, séparateurs, décimales, signe, devise optionnelle)
AMOUNT_RE = re.compile(
    rf"""(?ix)
    (?<!\d)
    (                                   # groupe 1 = texte du montant
        [\-−]?\s*(?:\d{{1,3}}(?:{THOUS_SEP_CLASS}\d{{3}})+|\d{{4,}})(?:[.,]\d{{2}})?
        | [\-−]?\s*\d{{1,3}}[.,]\d{{2}}
        | \(\s*\d{{1,3}}(?:{THOUS_SEP_CLASS}\d{{3}})+\s*\)
        | \(\s*\d+[.,]\d{{2}}\s*\)
    )
    (?:\s*(?:XAF|FCFA))?
    (?!\d)
    """
)

DEBIT_KW = ("frais", "commission", "comm.", "tx", "taxe", "découvert", "decouvert",
            "intérêts", "interets", "dbt", "débit", "debit")
CREDIT_KW = ("virement", "versement", "remboursement", "remb", "cime", "salaire",
             "crédit", "credit")


def _norm_spaces(s: str) -> str:
    for sp in SPACE_VARIANTS:
        s = s.replace(sp, " ")
    return re.sub(r"\s+", " ", s).strip()


def _strip_currency_and_sign(txt: str) -> Tuple[str, int]:
    t = txt.strip().replace("−", "-")
    t = re.sub(r"(XAF|FCFA)\b", "", t, flags=re.I).strip()
    sign = 1
    if t.startswith("(") and t.endswith(")"):
        t = t[1:-1].strip()
        sign = -1
    if t.endswith("-") and not t.lstrip().startswith("-"):
        t = t[:-1].strip()
        sign = -1
    if t.lstrip().startswith("-"):
        sign *= -1
        t = t.lstrip()[1:].strip()
    return t, sign


def _norm_amount_txt(txt: str) -> str:
    raw, sign = _strip_currency_and_sign(txt)
    for sp in SPACE_VARIANTS:
        raw = raw.replace(sp, " ")
    raw = raw.replace(" ", "")

    if "." in raw and "," in raw:
        raw = raw.replace(".", "")
        raw = raw.replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")

    raw = re.sub(r"[^0-9.]", "", raw)
    if sign < 0 and raw:
        raw = "-" + raw
    return raw


def _to_number(txt: str) -> Optional[float]:
    try:
        return float(_norm_amount_txt(txt))
    except Exception:
        return None


def _has_kw(s: str, kws: Tuple[str, ...]) -> bool:
    s = s.lower()
    return any(k in s for k in kws)


# =======================
#  Pré-fix : dates éclatées
# =======================
def _fix_split_dates(lines: List[str]) -> List[str]:
    """
    Recolle les "31/12" + "/24" → "31/12/24", y compris quand c'est sur deux lignes.
    """
    fixed: List[str] = []
    i = 0
    while i < len(lines):
        cur = _norm_spaces(lines[i])
        # cas 1 : sur la même ligne : "dd/mm / yy" → "dd/mm/yy"
        cur = re.sub(r"(\b\d{1,2}/\d{1,2})\s*/\s*(\d{2,4}\b)", r"\1/\2", cur)

        # cas 2 : la ligne courante finit par "dd/mm" et la suivante commence par "/yy"
        if re.search(r"\b\d{1,2}/\d{1,2}\s*$", cur) and i + 1 < len(lines):
            nxt = _norm_spaces(lines[i + 1])
            m = re.match(r"^\s*/\s*(\d{2,4})(.*)$", nxt)
            if m:
                yy = m.group(1)
                rest = m.group(2)
                cur = re.sub(r"(\b\d{1,2}/\d{1,2})\s*$", rf"\1/{yy}", cur)
                # on “consomme” la ligne suivante (son reste est ajouté)
                if rest.strip():
                    cur = (cur + " " + rest.strip()).strip()
                i += 1  # skip next line

        fixed.append(cur)
        i += 1
    return fixed


# =======================
#  Détection SAFIR
# =======================
def is_saphir_statement(text_or_lines) -> bool:
    if isinstance(text_or_lines, str):
        joined = text_or_lines.lower()
    else:
        joined = " ".join([str(x) for x in text_or_lines]).lower()
    return (
        "extrait de compte" in joined
        and ("afriland" in joined or "afriland first bank" in joined)
    ) or ("safir consulting cameroun" in joined or "saphir consulting" in joined)


# =======================
#  En-tête
# =======================
def _extract_header(lines: List[str]) -> Dict[str, Optional[str]]:
    banque = "Afriland First Bank"
    titulaire = "SAFIR CONSULTING CAMEROUN"
    compte = "00002-08237521001-09 XAF"
    solde_initial = None

    for raw in lines:
        l = _norm_spaces(raw)
        if "nom du client" in l.lower():
            parts = l.split(":", 1)
            if len(parts) == 2:
                titulaire = parts[1].strip()
        if (not titulaire) and "libellé du compte" in l.lower():
            parts = l.split(":", 1)
            if len(parts) == 2:
                titulaire = parts[1].strip()

        if "numéro de compte" in l.lower() or "numero de compte" in l.lower():
            parts = l.split(":", 1)
            if len(parts) == 2:
                compte = parts[1].strip()
                compte = re.sub(r"\bXAF\b", "", compte, flags=re.I).strip()

        if "solde initial" in l.lower():
            m = AMOUNT_RE.search(l)
            if m:
                solde_initial = _norm_amount_txt(m.group(1))

    return {"banque": banque, "titulaire": titulaire, "compte": compte, "solde_initial": solde_initial}


# =======================
#  Regroupement des lignes
# =======================
def _collect_table_rows(all_lines: List[str]) -> List[str]:
    rows: List[str] = []
    current: Optional[str] = None

    # repérer l'en-tête du tableau
    start_idx = 0
    for i, raw in enumerate(all_lines):
        low = raw.lower()
        if ("opération" in low or "operation" in low) and ("date" in low and "solde" in low):
            start_idx = i + 1
            break

    for raw in all_lines[start_idx:]:
        line = _norm_spaces(raw)
        if not line:
            continue

        m = re.match(rf"^\s*{DATE_RE}\s+{DATE_RE}\b", line)
        if m:
            if current:
                rows.append(current)
            current = line
        else:
            if current:
                current = (current + " " + line).strip()
            else:
                continue

    if current:
        rows.append(current)

    return rows


# =======================
#  Filtrage des nombres
# =======================
def _plausible_amount_token(text: str, full_line: str) -> bool:
    """
    Rejette :
      - 1–2 chiffres (ex: 31, 05)
      - années 19xx/20xx
      - fragments collés à une date (précédés d'un '/')
    Accepte :
      - >=4 chiffres
      - ou décimales (x.xx)
      - ou séparateurs de milliers
    """
    norm = _norm_amount_txt(text)
    if not norm:
        return False

    # fragment de date ? Juste avant le match, un '/'
    idx = full_line.find(text)
    if idx > 0 and full_line[idx - 1] == "/":
        return False

    # trop court
    digits = norm.replace(".", "")
    if len(digits) <= 2:
        return False

    # année pure
    if digits in {"2023", "2024", "2025", "2026", "2019", "2020", "2021", "2022"}:
        return False

    # ok si décimal
    if "." in norm:
        return True

    # ok si "gros" (>=4 chiffres) ou séparateurs de milliers
    return len(digits) >= 4


# =======================
#  Parse d'une ligne
# =======================
def _parse_saphir_row(row: str, prev_balance: Optional[float]) -> Optional[Dict]:
    m = DATE_LINE_RE.match(row)
    if not m:
        return None

    date, date_val, tail = m.groups()
    tail = _norm_spaces(tail)

    # ⚡ Étape 1 : enlever les dates parasites genre "31/12/24"
    tail = re.sub(DATE_RE, "", tail).strip()

    # ⚡ Étape 2 : extraire tous les nombres restants
    nums = [m.group(1) for m in AMOUNT_RE.finditer(tail)]
    nums = [_norm_amount_txt(n) for n in nums if _norm_amount_txt(n)]

    if not nums:
        return None

    # ⚡ Étape 3 : affecter aux colonnes (débit, crédit, solde)
    # On suppose que : debit? credit? solde
    debit, credit, solde = None, None, None
    if len(nums) >= 3:
        debit, credit, solde = nums[-3], nums[-2], nums[-1]
    elif len(nums) == 2:
        # souvent débit OU crédit manquant
        debit, credit, solde = nums[0], None, nums[1]
    elif len(nums) == 1:
        solde = nums[0]

    montant, sens = None, None
    if debit and debit != "0":
        montant = debit
        sens = "Dr"
    elif credit and credit != "0":
        montant = credit
        sens = "Cr"

    # ⚡ Étape 4 : nettoyer la description (en enlevant les nombres)
    desc = tail
    for n in nums:
        desc = desc.replace(n, "")
    desc = re.sub(r"\s+", " ", desc).strip()

    return {
        "date": date,
        "description": desc,
        "montant": montant,
        "sens": sens,
        "solde": solde,
    }

    m = DATE_LINE_RE.match(row)
    if not m:
        return None

    date, _date_val, tail = m.groups()
    tail = _norm_spaces(tail)

    # candidats montants (avec filtrage anti-"31/25/05")
    raw_tokens = list(AMOUNT_RE.finditer(tail))
    tokens = [t for t in raw_tokens if _plausible_amount_token(t.group(1), tail)]
    if len(tokens) < 1:
        return None

    # on prend le dernier "gros" nombre comme SOLDE
    solde_txt = tokens[-1].group(1)
    solde = _to_number(solde_txt)
    if solde is None:
        return None

    # montant = token juste avant
    amount = None
    amount_txt = None
    if len(tokens) >= 2:
        amount_txt = tokens[-2].group(1)
        amount = _to_number(amount_txt)

    # fallback par différence
    sens = None
    if amount is None and prev_balance is not None and prev_balance != solde:
        diff = round(abs(prev_balance - solde), 2)
        amount = diff
        if abs((prev_balance - diff) - solde) < 0.51:
            sens = "Dr"
        elif abs((prev_balance + diff) - solde) < 0.51:
            sens = "Cr"

    # sens via différence si possible
    if amount is not None and prev_balance is not None and sens is None:
        if abs((prev_balance - amount) - solde) < 0.51:
            sens = "Dr"
        elif abs((prev_balance + amount) - solde) < 0.51:
            sens = "Cr"

    # mots-clés (filet)
    if sens is None and amount is not None:
        if _has_kw(tail, CREDIT_KW):
            sens = "Cr"
        elif _has_kw(tail, DEBIT_KW):
            sens = "Dr"

    # nettoyage description : on retire solde + montant (si présent)
    desc = tail
    # retire solde (token complet)
    s_sol, e_sol = tokens[-1].span()
    desc = (desc[:s_sol] + " " + desc[e_sol:]).strip()

    # retire montant (si présent)
    if amount_txt is not None:
        # on cherche l'occurrence normalisée pour être robuste
        for m2 in AMOUNT_RE.finditer(desc):
            if _norm_amount_txt(m2.group(1)) == _norm_amount_txt(amount_txt):
                s2, e2 = m2.span()
                desc = (desc[:s2] + " " + desc[e2:]).strip()
                break

    desc = re.sub(r"\s+", " ", desc).strip()

    out = {
        "date": date,
        "description": desc,
        "montant": (
            None if amount is None
            else (_norm_amount_txt(str(int(amount))) if float(amount).is_integer()
                  else _norm_amount_txt(str(amount)))
        ),
        "sens": sens,
        "solde": _norm_amount_txt(str(int(solde))) if float(solde).is_integer() else _norm_amount_txt(str(solde)),
    }
    return out


# =======================
#  Parse du tableau complet
# =======================
def parse_saphir_transactions(lines: List[str], solde_initial_txt: Optional[str]) -> List[Dict]:
    # 1) recoller les dates cassées
    lines = _fix_split_dates(lines)
    # 2) regrouper les lignes
    rows = _collect_table_rows(lines)

    txs: List[Dict] = []
    prev_balance: Optional[float] = _to_number(solde_initial_txt) if solde_initial_txt else None

    for r in rows:
        parsed = _parse_saphir_row(r, prev_balance)
        if not parsed:
            continue

        if parsed.get("solde") is not None:
            try:
                prev_balance = float(parsed["solde"])
            except Exception:
                pass

        txs.append({
            "date": parsed["date"],
            "description": parsed["description"],
            "montant": parsed["montant"],
            "sens": parsed["sens"],
        })

    return txs


# =======================
#  Période min/max
# =======================
def _extract_period_from_txs(transactions: List[Dict]) -> Optional[str]:
    dates = []
    for t in transactions:
        d = t.get("date")
        if d and re.match(DATE_RE, d):
            parts = d.split("/")
            if len(parts[-1]) == 2:
                yy = int(parts[-1])
                parts[-1] = f"20{yy:02d}"
            dates.append("/".join(parts))
    if not dates:
        return None
    return f"{dates[0]} - {dates[-1]}"


# =======================
#  Entrée principale
# =======================
def extract_saphir_bank_statement_data(ocr_text: str) -> Dict:
    lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]

    if not is_saphir_statement(lines):
        return {
            "banque": None, "compte": None, "titulaire": None, "periode": None,
            "transactions": [], "_debug": {"reason": "not_saphir"},
        }

    header = _extract_header(lines)
    txs = parse_saphir_transactions(lines, header.get("solde_initial"))
    periode = _extract_period_from_txs(txs)

    return {
        "banque": header.get("banque"),
        "compte": header.get("compte"),
        "titulaire": header.get("titulaire"),
        "periode": periode,
        "transactions": txs,
        "_debug": {"solde_initial": header.get("solde_initial"), "tx_count": len(txs)},
    }
