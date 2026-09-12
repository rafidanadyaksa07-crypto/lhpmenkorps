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
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()          # agar Pillow bisa membuka .heic dari iPhone
    HEIC_DIDUKUNG = True
except Exception:
    HEIC_DIDUKUNG = False
from docx import Document
from docx.shared import Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

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
ROSTER_ERROR = None   # set when the workbook can't be read, surfaced in the UI


def _load_roster():
    global ROSTER_ERROR
    if not os.path.exists(EXCEL_PATH):
        ROSTER_ERROR = (
            "File DATA_DANTONTAR_DANKITAR.xlsx tidak ditemukan di server. "
            "Pastikan file itu ikut ter-upload ke repo."
        )
        return {t: [] for t in TINGKAT_CONFIG}

    mtime = os.path.getmtime(EXCEL_PATH)
    if _roster_cache["mtime"] == mtime and _roster_cache["data"] is not None:
        return _roster_cache["data"]

    try:
        wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    except Exception as exc:
        ROSTER_ERROR = f"Data satuan gagal dibaca: {exc}"
        return {t: [] for t in TINGKAT_CONFIG}

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
                header_row = [_norm(v) for v in values]
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

    ROSTER_ERROR = None
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
    """
    Ganti placeholder di dalam satu paragraf, termasuk yang terbelah.

    Word kerap memecah satu kata menjadi beberapa run tanpa alasan yang
    terlihat -- riwayat penyuntingan, pemeriksa ejaan, atau salin-tempel.
    Akibatnya "{{TTD_TEMPAT_TANGGAL}}" bisa tersimpan sebagai "{{" lalu
    "TTD_TEMPAT_TANGGAL}}" pada dua run terpisah.

    Mengganti per run akan melewatkan kasus itu dan placeholder tercetak apa
    adanya di dokumen resmi. Karena itu teks seluruh paragraf disambung dulu,
    lalu penggantian ditulis kembali ke run pertama yang terlibat -- sehingga
    huruf tebal, miring, dan ukurannya tetap mengikuti placeholder aslinya.
    """
    for _ in range(100):                       # batas aman dari putaran tak berujung
        runs = paragraph.runs
        if not runs:
            return
        gabung = "".join(r.text for r in runs)
        if "{{" not in gabung:
            return

        temuan = None
        for token, nilai in values.items():
            i = gabung.find(token)
            if i != -1:
                temuan = (i, token, nilai)
                break
        if temuan is None:
            return

        mulai, token, nilai = temuan
        akhir = mulai + len(token)

        batas, pos = [], 0
        for r in runs:
            batas.append((pos, pos + len(r.text)))
            pos += len(r.text)

        kena = [i for i, (a, b) in enumerate(batas) if a < akhir and b > mulai]
        if not kena:
            return

        pertama, terakhir = kena[0], kena[-1]
        awal_p = batas[pertama][0]
        awal_t = batas[terakhir][0]
        depan = runs[pertama].text[: mulai - awal_p]
        belakang = runs[terakhir].text[akhir - awal_t:]

        if pertama == terakhir:
            runs[pertama].text = depan + nilai + belakang
        else:
            runs[pertama].text = depan + nilai
            for i in kena[1:-1]:
                runs[i].text = ""
            runs[terakhir].text = belakang


def _semua_paragraf(doc):
    """
    Hasilkan SELURUH paragraf dokumen, termasuk yang bersarang.

    Sebelumnya hanya badan dokumen dan tabel satu tingkat yang disusuri,
    sehingga placeholder di kop halaman, kaki halaman, atau tabel di dalam
    tabel tidak pernah tergantikan dan tercetak apa adanya.
    """
    def dari_tabel(tabel):
        for baris in tabel.rows:
            for sel in baris.cells:
                for p in sel.paragraphs:
                    yield p
                for t in sel.tables:          # tabel bersarang, sedalam apa pun
                    yield from dari_tabel(t)

    for p in doc.paragraphs:
        yield p
    for t in doc.tables:
        yield from dari_tabel(t)

    for bagian in doc.sections:
        for wadah in (bagian.header, bagian.footer,
                      bagian.even_page_header, bagian.even_page_footer,
                      bagian.first_page_header, bagian.first_page_footer):
            if wadah is None:
                continue
            try:
                for p in wadah.paragraphs:
                    yield p
                for t in wadah.tables:
                    yield from dari_tabel(t)
            except Exception:
                continue


def _replace_everywhere(doc, values):
    for p in _semua_paragraf(doc):
        _replace_in_paragraph(p, values)


def _sapu_sisa(doc):
    """
    Jaring pengaman terakhir.

    Bila karena satu dan lain hal masih ada placeholder yang belum
    tergantikan, kosongkan agar tidak tercetak sebagai "{{NAMA_SESUATU}}"
    di dokumen resmi. Nama yang tersisa dicatat ke log supaya penyebabnya
    bisa ditelusuri, bukan disembunyikan diam-diam.
    """
    tersisa = set()
    pola = re.compile(r"\{\{[A-Z0-9_]+\}\}")
    for p in _semua_paragraf(doc):
        temuan = pola.findall(p.text)
        if not temuan:
            continue
        tersisa.update(temuan)
        _replace_in_paragraph(p, {t: "" for t in temuan})
    if tersisa:
        print("[template] placeholder tidak dikenali, dikosongkan:",
              ", ".join(sorted(tersisa)))
    return sorted(tersisa)


def token_template(path=None):
    """Daftar placeholder yang ada di berkas template. Dipakai /health."""
    path = path or TEMPLATE_PATH
    if not os.path.exists(path):
        return []
    try:
        doc = Document(path)
        pola = re.compile(r"\{\{[A-Z0-9_]+\}\}")
        hasil = set()
        for p in _semua_paragraf(doc):
            hasil.update(pola.findall(p.text))
        return sorted(hasil)
    except Exception:
        return []


def _siapkan_gambar(path, maks_piksel=1600, mutu=85):
    """
    Siapkan foto sebelum dimasukkan ke dokumen.

    Dua tugas:
      1. HEIC dari iPhone diubah menjadi JPEG, karena python-docx tidak
         mengenal HEIC dan akan melempar galat.
      2. Foto di atas 1600 piksel diperkecil. Sebelumnya berkas asli ikut
         tertanam utuh -- empat foto iPhone 5 MB menghasilkan dokumen 20 MB
         yang berat dibuka dan dikirim. Lebar 1600 piksel masih tajam pada
         ukuran cetak lampiran.

    Bila apa pun gagal, jalur aslinya dikembalikan agar dokumen tetap
    tersusun.
    """
    try:
        from PIL import Image
    except Exception:
        return path

    perlu_ubah = path.lower().endswith((".heic", ".heif"))
    try:
        with Image.open(path) as im:
            perlu_kecil = max(im.size) > maks_piksel
            if not perlu_ubah and not perlu_kecil:
                return path
            im = im.convert("RGB")
            if perlu_kecil:
                im.thumbnail((maks_piksel, maks_piksel), Image.LANCZOS)
            keluar = os.path.splitext(path)[0] + "_siap.jpg"
            im.save(keluar, "JPEG", quality=mutu, optimize=True)
            return keluar
    except Exception:
        return path


def _insert_photos(doc, photo_paths, cols=2):
    """
    Lay photos out in a borderless grid.

    The previous approach appended every picture to one paragraph at a fixed
    height. With mixed aspect ratios (portrait phone shots next to landscape
    screenshots) the wide ones overflowed their line and visibly overlapped
    the next photo. Here each image is scaled to FIT INSIDE a fixed box,
    preserving its aspect ratio, and each sits in its own table cell.
    """
    marker = "{{LAMPIRAN_FOTO}}"
    target = None
    for p in doc.paragraphs:
        # teks paragraf, bukan per run: penanda pun bisa terbelah oleh Word
        if marker in p.text:
            target = p
            break

    if target is None:
        return
    _replace_in_paragraph(target, {marker: ""})

    if not photo_paths:
        return

    BOX_W_CM, BOX_H_CM = 7.2, 7.0      # per-cell picture box

    rows = (len(photo_paths) + cols - 1) // cols
    table = doc.add_table(rows=rows, cols=cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _remove_table_borders(table)

    col_w = Cm(BOX_W_CM + 0.4)
    for row in table.rows:
        for c in row.cells:
            c.width = col_w

    photo_paths = [_siapkan_gambar(p) for p in photo_paths]

    for idx, path in enumerate(photo_paths):
        cell = table.rows[idx // cols].cells[idx % cols]
        cell.width = col_w
        for p in list(cell.paragraphs):
            p._element.getparent().remove(p._element)
        para = cell.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.paragraph_format.space_after = Pt(8)
        para.paragraph_format.space_before = Pt(4)

        width_cm, height_cm = _fit_box(path, BOX_W_CM, BOX_H_CM)
        try:
            para.add_run().add_picture(path, width=Cm(width_cm), height=Cm(height_cm))
        except Exception:
            continue

    # move the grid to where the marker paragraph is
    target._p.addnext(table._tbl)


def _fit_box(path, box_w_cm, box_h_cm):
    """Scale an image to fit inside the box while keeping its aspect ratio."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
        if not w or not h:
            raise ValueError
        scale = min(box_w_cm / w, box_h_cm / h)
        return w * scale, h * scale
    except Exception:
        # unknown dimensions: fall back to a 4:3 landscape box
        return box_w_cm, box_w_cm * 0.75


def _remove_table_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement('w:' + edge)
        el.set(qn('w:val'), 'none')
        el.set(qn('w:sz'), '0')
        borders.append(el)
    tblPr.append(borders)


def generate_document(form, photo_paths, output_path):
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(
            "File template_lhp.docx tidak ditemukan di server. "
            "Pastikan file itu ikut ter-upload ke repo."
        )
    doc = Document(TEMPLATE_PATH)
    values, meta = build_placeholder_values(form)
    _replace_everywhere(doc, values)
    _insert_photos(doc, photo_paths)
    meta["placeholder_tersisa"] = _sapu_sisa(doc)
    doc.save(output_path)
    return meta

# ---------------------------------------------------------------------------
# Membaca tanggal dan waktu dari foto
# ---------------------------------------------------------------------------
# Hanya membaca EXIF, yaitu metadata bawaan kamera. Tanpa biaya sama sekali
# dan tanpa panggilan ke layanan luar.
#
# Pembacaan tulisan tanggal yang tercetak di gambar (OCR) SENGAJA TIDAK
# dipakai karena berbiaya per foto. Pengisian manual adalah jalur utama.
#
# Hasil pembacaan hanya USULAN. Pengguna tetap harus menyetujui sebelum
# masuk ke formulir, dan kolomnya tetap bisa diketik sendiri.

_EXIF_DATE_TAGS = (36867, 36868, 306)   # DateTimeOriginal, Digitized, DateTime


def _parse_exif_datetime(text):
    """'2026:05:31 22:22:07' -> ('2026-05-31', '22:22')"""
    m = re.match(r"^(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2})", str(text or "").strip())
    if not m:
        return None
    y, mo, d, hh, mm = m.groups()
    try:
        datetime(int(y), int(mo), int(d), int(hh), int(mm))
    except ValueError:
        return None
    return f"{y}-{mo}-{d}", f"{hh}:{mm}"


def read_photo_datetime(path):
    """Baca tanggal dan waktu dari EXIF. Kembalikan None bila tidak ada."""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            if not exif:
                return None

            for tag in _EXIF_DATE_TAGS:
                got = _parse_exif_datetime(exif.get(tag))
                if got:
                    return {"tanggal": got[0], "waktu": got[1], "sumber": "EXIF"}

            # sebagian kamera hanya menulis tanggal pada blok GPS
            gps = exif.get_ifd(0x8825) if hasattr(exif, "get_ifd") else None
            if gps:
                stamp = str(gps.get(29) or "").strip()
                t = gps.get(7)
                if stamp and t and len(t) >= 2:
                    got = _parse_exif_datetime(
                        f"{stamp} {int(t[0]):02d}:{int(t[1]):02d}:00")
                    if got:
                        return {"tanggal": got[0], "waktu": got[1], "sumber": "EXIF GPS"}
    except Exception:
        return None
    return None


def scan_photo(path):
    """Hanya membaca EXIF. Tidak ada layanan berbayar di jalur ini."""
    return read_photo_datetime(path)
