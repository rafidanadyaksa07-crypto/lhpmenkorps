# -*- coding: utf-8 -*-
"""
Core LHP document-generation logic: kompi/tingkat config, Danton/Danki lookup
from the Excel roster, date/time parsing, and template filling.

IMPORTANT (lesson learned from earlier iterations of this project):
Every placeholder in template_lhp.docx lives in its OWN dedicated run and is a
complete, self-contained token like {{NAMA_TARUNA}}. We never do partial/
substring replacement across a shared dict of fragments, because doing that
made replacement order matter and produced silent bugs (e.g. a generic
"KOMPI III" replacement running before a more specific "DANTONTAR 1 KOMPI III"
replacement, permanently corrupting the more specific one). One token -> one
final string, always assembled BEFORE we touch the document.
"""
import os
import re
import copy
import unicodedata
from datetime import datetime

import openpyxl
from docx import Document
from docx.shared import Cm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH = os.path.join(BASE_DIR, "DATA_DANTONTAR_DANKITAR.xlsx")
TEMPLATE_PATH = os.path.join(BASE_DIR, "template_lhp.docx")

# ---------------------------------------------------------------------------
# Tingkat / batalyon configuration
# ---------------------------------------------------------------------------
# Sheet name in the Excel workbook -> config. Add more tingkat here as data
# becomes available (e.g. a future "TK I - XX" sheet).
TINGKAT_CONFIG = {
    "3": {"label": "III", "angkatan": "59", "batalyon_singkat": "BD",
          "batalyon_nama": "BHAYANGKARA DHARMA", "sheet": "TK III - BD"},
    "2": {"label": "II", "angkatan": "60", "batalyon_singkat": "MS",
          "batalyon_nama": "MANGGALA SATYA", "sheet": "TK II - MS"},
}

PANGKAT_SINGKAT = {
    "BHAYANGKARA TARUNA": "BHATAR",
    "AJUN BRIGADIR TARUNA": "ABRIGTAR",
    "BRIGADIR TARUNA": "BRIGTAR",
    "BRIGADIR KEPALA TARUNA": "BRIGKATAR",
}
PANGKAT_LIST = list(PANGKAT_SINGKAT.keys())

HARI_MAP = {
    0: "SENIN", 1: "SELASA", 2: "RABU", 3: "KAMIS",
    4: "JUMAT", 5: "SABTU", 6: "MINGGU",
}
BULAN_MAP = {
    1: "JANUARI", 2: "FEBRUARI", 3: "MARET", 4: "APRIL", 5: "MEI", 6: "JUNI",
    7: "JULI", 8: "AGUSTUS", 9: "SEPTEMBER", 10: "OKTOBER", 11: "NOVEMBER",
    12: "DESEMBER",
}
BULAN_INDEX = {v: k for k, v in BULAN_MAP.items()}

# Manual overrides: (tingkat, kompi, jenis) -> dict of overrides.
# jenis is "danki". Kept here (not scattered in app.py) so it's one obvious
# place to edit when personnel changes happen mid-cycle.
PERSONNEL_OVERRIDES = {
    # Example of the shape, left empty by default:
    # ("2", "A", "danki"): {"source_kompi": "B"},
}


def _norm(s):
    if s is None:
        return ""
    s = str(s).strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_jabatan_key(s):
    """Collapse all whitespace so 'DANKI TAR B' and 'DANKITAR B' compare equal."""
    return re.sub(r"\s+", "", _norm(s))


# ---------------------------------------------------------------------------
# Excel roster loading (cached, invalidated by file mtime)
# ---------------------------------------------------------------------------
_roster_cache = {"mtime": None, "data": None}


def _load_roster():
    mtime = os.path.getmtime(EXCEL_PATH) if os.path.exists(EXCEL_PATH) else None
    if _roster_cache["mtime"] == mtime and _roster_cache["data"] is not None:
        return _roster_cache["data"]

    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    data = {}
    for tingkat, cfg in TINGKAT_CONFIG.items():
        sheet_name = cfg["sheet"]
        if sheet_name not in wb.sheetnames:
            data[tingkat] = []
            continue
        ws = wb[sheet_name]
        rows = []
        header_row = None
        for row in ws.iter_rows(values_only=False):
            values = [c.value for c in row]
            if values and _norm(values[0]) == "NO" and _norm(values[1]) == "NAMA":
                header_row = [ _norm(v) for v in values ]
                continue
            if header_row is None:
                continue
            if values[1] is None and values[3] is None:
                continue
            record = {}
            for i, key in enumerate(header_row):
                if not key:
                    continue
                record[key] = values[i] if i < len(values) else None
            rows.append(record)
        data[tingkat] = rows
    _roster_cache["mtime"] = mtime
    _roster_cache["data"] = data
    return data


def available_tingkat():
    roster = _load_roster()
    return [t for t, cfg in TINGKAT_CONFIG.items() if roster.get(t)]


def kompi_letters(tingkat):
    """A-E is the standard structure for this battalion, letters used for
    both TK II and TK III per the current roster format."""
    return ["A", "B", "C", "D", "E"]


def peleton_numbers():
    return ["1", "2", "3"]


def _find_by_jabatan(records, target_key):
    for rec in records:
        jab = _norm_jabatan_key(rec.get("JABATAN"))
        if jab == target_key:
            return rec
    return None


def lookup_danton(tingkat, peleton, kompi):
    roster = _load_roster().get(tingkat, [])
    target = _norm_jabatan_key(f"DANTON TAR {peleton}{kompi}")
    rec = _find_by_jabatan(roster, target)
    return _format_person(rec)


def lookup_danki(tingkat, kompi):
    override = PERSONNEL_OVERRIDES.get((tingkat, kompi, "danki"))
    source_kompi = override["source_kompi"] if override else kompi
    roster = _load_roster().get(tingkat, [])
    target = _norm_jabatan_key(f"DANKI TAR {source_kompi}")
    rec = _find_by_jabatan(roster, target)
    person = _format_person(rec)
    # The signature line still shows the taruna's OWN kompi letter unless
    # the override says otherwise (kept explicit, not inferred).
    person["signature_kompi"] = override.get("signature_kompi", kompi) if override else kompi
    return person


def _format_person(rec):
    if not rec:
        return {"nama": "", "pangkat": "", "nrp": "", "found": False}
    nrp = rec.get("NRP")
    nrp = "" if nrp in (None, "") else str(nrp).strip()
    return {
        "nama": (rec.get("NAMA") or "").strip(),
        "pangkat": (rec.get("PANGKAT") or "").strip(),
        "nrp": nrp,
        "found": True,
    }


# ---------------------------------------------------------------------------
# Date / time parsing -> the exact strings the document needs
# ---------------------------------------------------------------------------
def parse_tanggal(raw):
    """
    Accepts things like:
      '2026-08-23' (HTML date input)
      'SENIN, 23 AGUSTUS 2026'
      'SENIN 23 AGUSTUS 2026' (no comma)
      '23 AGUSTUS 2026' (no day name -- we compute it)
    Returns dict with hari, tanggal, bulan, tahun (all strings, uppercase)
    plus a datetime object for downstream use.
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    # ISO format from <input type=date>
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", raw)
    if m:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return {
            "hari": HARI_MAP[dt.weekday()],
            "tanggal": str(dt.day),
            "bulan": BULAN_MAP[dt.month],
            "tahun": str(dt.year),
            "dt": dt,
        }

    text = _norm(raw).replace(",", " ")
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split(" ")

    hari = None
    if tokens and tokens[0] in HARI_MAP.values():
        hari = tokens.pop(0)

    # remaining tokens should be: DD MONTHNAME YYYY
    if len(tokens) >= 3 and tokens[1] in BULAN_INDEX:
        tanggal, bulan_name, tahun = tokens[0], tokens[1], tokens[2]
        try:
            dt = datetime(int(tahun), BULAN_INDEX[bulan_name], int(tanggal))
        except ValueError:
            dt = None
        if hari is None and dt is not None:
            hari = HARI_MAP[dt.weekday()]
        return {
            "hari": hari or "",
            "tanggal": str(int(tanggal)),
            "bulan": bulan_name,
            "tahun": tahun,
            "dt": dt,
        }
    return None


def parse_waktu(raw):
    """Accepts '14.50', '14:50', '14.50 WIB' -> returns '14.50' (WIB implied)."""
    raw = (raw or "").strip()
    m = re.search(r"(\d{1,2})[.:](\d{2})", raw)
    if not m:
        return raw.upper().replace("WIB", "").strip()
    return f"{int(m.group(1))}.{m.group(2)}"


# ---------------------------------------------------------------------------
# Assembling every placeholder value BEFORE touching the document
# ---------------------------------------------------------------------------
def build_placeholder_values(form):
    tingkat = form["tingkat"]
    cfg = TINGKAT_CONFIG[tingkat]
    kompi = form["kompi"].upper()
    peleton = form["peleton"]

    danton = form.get("danton_override") or lookup_danton(tingkat, peleton, kompi)
    danki = form.get("danki_override") or lookup_danki(tingkat, kompi)
    signature_kompi = danki.get("signature_kompi", kompi)

    tgl = parse_tanggal(form["tanggal"])
    waktu = parse_waktu(form["waktu"])
    if tgl is None:
        tgl = {"hari": "", "tanggal": form.get("tanggal", ""), "bulan": "", "tahun": ""}

    pangkat_taruna = form["pangkat"].upper()
    pangkat_singkat = PANGKAT_SINGKAT.get(pangkat_taruna, pangkat_taruna)

    kop_batalyon = f"BATALYON TARUNA TK {cfg['label']}/{cfg['angkatan']}/{cfg['batalyon_singkat']}"
    judul = f"LAPORAN KEGIATAN TARUNA TK. {cfg['label']}/{cfg['angkatan']}/{cfg['batalyon_singkat']}"

    waktu_pelaksanaan = f"{tgl['hari']}, {tgl['tanggal']} {tgl['bulan']} {tgl['tahun']}, {waktu} WIB".strip(", ")

    uraian = (
        f"PADA HARI {tgl['hari']} TANGGAL {tgl['tanggal']} BULAN {tgl['bulan']} "
        f"TAHUN {tgl['tahun']} PUKUL {waktu} WIB, SAYA {form['nama_taruna'].upper()} "
        f"TARUNA AKPOL, PANGKAT {pangkat_taruna}, NO AKADEMI {form['no_akademi']}, "
        f"ANGKATAN KE-{cfg['angkatan']}, BATALYON {cfg['batalyon_nama']}, TELAH "
        f"MELAKSANAKAN KEGIATAN POSITIF BERUPA {form['nama_kegiatan'].upper()}"
    )

    ttd_tempat_tanggal = f"{form.get('lokasi_ttd', 'SEMARANG').upper()}, {tgl['hari']}, {tgl['tanggal']} {tgl['bulan']} {tgl['tahun']}"

    danton_jabatan = f"DANTONTAR {peleton} KOMPI {kompi} TK {cfg['label']}/{cfg['angkatan']}/{cfg['batalyon_singkat']}"
    danki_jabatan = f"DANKITAR {signature_kompi} TK {cfg['label']}/{cfg['angkatan']}/{cfg['batalyon_singkat']}"

    danton_pangkat_nrp = f"{danton['pangkat']} NRP {danton['nrp']}".strip()
    danki_pangkat_nrp = f"{danki['pangkat']} NRP {danki['nrp']}".strip()
    taruna_pangkat_noak = f"{pangkat_singkat} NO. AK {form['no_akademi']}"
    lamp_pangkat_noak = f"{pangkat_singkat} NO. AK. {form['no_akademi']}"

    values = {
        "{{KOP_BATALYON}}": kop_batalyon,
        "{{JUDUL_LAPORAN}}": judul,
        "{{NO_AKADEMI}}": form["no_akademi"],
        "{{NAMA_TARUNA}}": form["nama_taruna"].upper(),
        "{{KOMPI_LABEL}}": f"KOMPI {kompi}",
        "{{PELETON_LABEL}}": f"PLETON {peleton}",
        "{{NAMA_KEGIATAN}}": form["nama_kegiatan"].upper(),
        "{{WAKTU_PELAKSANAAN}}": waktu_pelaksanaan,
        "{{TEMPAT}}": form["tempat"].upper(),
        "{{URAIAN_KEGIATAN}}": uraian,
        "{{TTD_TEMPAT_TANGGAL}}": ttd_tempat_tanggal,
        "{{DANTON_JABATAN}}": danton_jabatan,
        "{{DANTON_NAMA}}": danton["nama"].upper(),
        "{{DANTON_PANGKAT_NRP}}": danton_pangkat_nrp,
        "{{TARUNA_PANGKAT_NOAK}}": taruna_pangkat_noak,
        "{{DANKI_JABATAN}}": danki_jabatan,
        "{{DANKI_NAMA}}": danki["nama"].upper(),
        "{{DANKI_PANGKAT_NRP}}": danki_pangkat_nrp,
        "{{LAMP_TEMPAT_TANGGAL}}": f"{form.get('lokasi_ttd', 'Semarang').title()}, {tgl['hari']}, {tgl['tanggal']} {tgl['bulan']} {tgl['tahun']}",
        "{{LAMP_PANGKAT_NOAK}}": lamp_pangkat_noak,
    }
    return values, {"danton": danton, "danki": danki, "tanggal": tgl, "waktu": waktu}


# ---------------------------------------------------------------------------
# Document filling
# ---------------------------------------------------------------------------
def _replace_in_paragraph(paragraph, values):
    for run in paragraph.runs:
        for token, val in values.items():
            if token in run.text:
                run.text = run.text.replace(token, val)


def _replace_everywhere(doc, values):
    for p in doc.paragraphs:
        _replace_in_paragraph(p, values)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _replace_in_paragraph(p, values)
                for t in cell.tables:
                    for r2 in t.rows:
                        for c2 in r2.cells:
                            for p2 in c2.paragraphs:
                                _replace_in_paragraph(p2, values)


def _insert_photos(doc, photo_paths, max_height_cm=5.0):
    marker_text = "{{LAMPIRAN_FOTO}}"
    for p in doc.paragraphs:
        if any(marker_text in r.text for r in p.runs):
            for r in p.runs:
                r.text = r.text.replace(marker_text, "")
            for path in photo_paths:
                run = p.add_run()
                try:
                    run.add_picture(path, height=Cm(max_height_cm))
                    p.add_run("   ")
                except Exception:
                    continue
            return
    # marker not found (shouldn't happen) -- append at end as fallback
    p = doc.add_paragraph()
    for path in photo_paths:
        run = p.add_run()
        try:
            run.add_picture(path, height=Cm(max_height_cm))
            p.add_run("   ")
        except Exception:
            continue


def generate_document(form, photo_paths, output_path):
    doc = Document(TEMPLATE_PATH)
    values, meta = build_placeholder_values(form)
    _replace_everywhere(doc, values)
    _insert_photos(doc, photo_paths)
    doc.save(output_path)
    return meta
