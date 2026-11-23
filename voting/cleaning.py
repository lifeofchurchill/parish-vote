"""
Helpers that clean raw values from the church's CSV export.

Plain Python with no Django imports, so each one can be tested on its own.
"""
import csv
import re
from datetime import date, datetime

# Formats the church software uses for birthDate (month first, e.g. 9/23/1993).
# Some exports add a time after the date, so we accept that too.
DATE_FORMATS = ["%m/%d/%Y", "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S"]

# Characters that separate two DIFFERENT phone numbers in one cell
PHONE_SEPARATORS = re.compile(r"[/,;]")


def clean_name(raw):
    """
    Tidy a name for display.
    'ESESI AMEBEH  YAA' -> 'Esesi Amebeh Yaa', 'abigail kum' -> 'Abigail Kum'.
    Mixed-case names like 'Tetteh Anita' are left exactly as they are.
    """
    # Collapse double spaces and trim the ends
    name = " ".join(raw.split())
    # Only fix names typed entirely in capitals or entirely in lowercase
    if name.isupper() or name.islower():
        name = name.title()
    return name


def parse_birth_date(raw):
    """
    '9/23/1993' -> date(1993, 9, 23).
    Returns None for a blank cell. Raises ValueError if the text can't be read
    or the date is impossible (e.g. in the future).
    """
    raw = raw.strip()
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt).date()
        except ValueError:
            continue  # try the next format
        # A birth date can't be in the future or absurdly old
        if parsed > date.today() or parsed.year < 1900:
            raise ValueError(f"impossible date {raw!r}")
        return parsed
    raise ValueError(f"unreadable date {raw!r}")


def clean_phones(raw):
    """
    Split one phone cell into clean numbers.
    '0271394092 /   456789123' -> ['0271394092', '0456789123']
    '021-403098'               -> ['021403098']
    Placeholders ('999999999') and Excel-damaged values ('5.47E+08') are dropped.
    """
    numbers = []
    for part in PHONE_SEPARATORS.split(raw):
        # Excel scientific notation means digits were lost; can't be recovered
        if "E+" in part.upper():
            continue
        # Keep digits only: removes spaces, dashes, brackets, '+'
        digits = re.sub(r"\D", "", part)
        if not digits:
            continue
        # Placeholder numbers like 999999999 or 0000000000
        if len(set(digits)) == 1:
            continue
        # +233 24 123 4567 -> 0241234567
        if digits.startswith("233") and len(digits) == 12:
            digits = "0" + digits[3:]
        # Excel often drops the leading 0: 241234567 -> 0241234567
        elif len(digits) == 9 and not digits.startswith("0"):
            digits = "0" + digits
        # Too short or too long to be a real number
        if not 7 <= len(digits) <= 13:
            continue
        if digits not in numbers:  # skip repeats of the same number
            numbers.append(digits)
    return numbers


def phone_looks_damaged(raw):
    """True if the cell contains Excel scientific notation (digits already lost)."""
    return "E+" in raw.upper()


def read_csv_rows(path, required_columns):
    """
    Read the CSV and return (encoding_used, rows).
    Each row is (line_number, dict of column -> value), so problems can be
    reported with the line to look at in Notepad.
    Raises ValueError if a required column is missing or the file can't be read.
    """
    # utf-8-sig = normal UTF-8, and also strips the invisible marker Excel adds.
    # cp1252 = older Windows encoding, used as a fallback.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                # Trim spaces around header names, e.g. " birthDate" -> "birthDate"
                reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
                missing = set(required_columns) - set(reader.fieldnames)
                if missing:
                    raise ValueError(
                        f"Missing column(s): {', '.join(sorted(missing))}. "
                        f"Found: {', '.join(reader.fieldnames)}"
                    )
                rows = [(reader.line_num, row) for row in reader]
                return encoding, rows
        except UnicodeDecodeError:
            continue  # wrong guess, try the next encoding
    raise ValueError("Could not read the file's text encoding.")