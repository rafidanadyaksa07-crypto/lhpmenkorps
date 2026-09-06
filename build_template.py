"""
Builds template_lhp.docx.

Layout decisions (learned from real output that came out messy):
  * The signature block is a borderless 2-column TABLE, not tab stops.
    Tab stops let a long name run past its column and collide with the
    other signature ("MUHAMMADRAFIDANADYAKSAMULYANTO" overlapping the
    Danton name). A table cell wraps instead.
  * Signature paragraphs are LEFT/CENTER aligned, never justified --
    justification stretched short names into "MUHAMMAD   RAFI   DANADYAKSA".
  * keep_with_next is set across the signature rows so the block is not
    split across pages, which previously left an almost-empty page.
  * Placeholders are whole tokens ({{NAME}}) each in their own run, so
    replacement never depends on ordering. See CLAUDE.md.
"""
from docx import Document
from docx.shared import Pt, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FONT = "Arial Narrow"


def style_run(r, bold=False, underline=False, italic=False, size=12, font=FONT):
    r.font.name = font
    r.font.size = Pt(size)
    r.bold = bold
    r.underline = underline
    r.italic = italic
    rpr = r._element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts')
        rpr.append(rf)
    rf.set(qn('w:eastAsia'), font)
    return r


def add_run(p, text, **kw):
    return style_run(p.add_run(text), **kw)


def para(container, align=None, after=0, before=0, keep=False):
    p = container.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(after)
    pf.space_before = Pt(before)
    pf.keep_with_next = keep
    if align is not None:
        p.alignment = align
    return p


def clear_cell(cell):
    """Remove the default empty paragraph so cells start clean."""
    for p in list(cell.paragraphs):
        p._element.getparent().remove(p._element)


def no_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement('w:' + edge)
        el.set(qn('w:val'), 'none')
        el.set(qn('w:sz'), '0')
        borders.append(el)
    tblPr.append(borders)


def build():
    doc = Document()

    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21.59), Cm(33.02)   # F4
    s.left_margin, s.right_margin = Cm(2.2), Cm(2.0)
    s.top_margin, s.bottom_margin = Cm(1.4), Cm(1.4)

    normal = doc.styles['Normal']
    normal.font.name = FONT
    normal.font.size = Pt(12)
    normal.paragraph_format.space_after = Pt(0)

    USABLE = Inches(6.45)   # page width minus margins

    # ---------------- KOP ----------------
    p = para(doc, WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, "RESIMEN TARUNA DAN SISWA", size=12)
    p = para(doc, WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, "{{KOP_BATALYON}}", size=12)
    p = para(doc, WD_ALIGN_PARAGRAPH.CENTER, before=6, after=8)
    add_run(p, "{{JUDUL_LAPORAN}}", bold=True, underline=True, size=13)

    # ---------------- identitas ----------------
    t0 = doc.add_table(rows=2, cols=3)
    t0.style = 'Table Grid'
    t0.alignment = WD_TABLE_ALIGNMENT.CENTER
    widths = [Inches(1.75), Inches(2.65), Inches(2.05)]
    for row in t0.rows:
        for i, c in enumerate(row.cells):
            c.width = widths[i]

    c00, c01, c02 = t0.rows[0].cells
    clear_cell(c00); clear_cell(c01); clear_cell(c02)
    para(c00)
    p = para(c01, WD_ALIGN_PARAGRAPH.CENTER)
    p.add_run().add_picture('static/logo_akpol.png', height=Cm(2.3))
    p = para(c02, after=4); add_run(p, "ACCEPTED:", bold=True, size=11)
    p = para(c02);          add_run(p, "INPUT :",   bold=True, size=11)

    c10, c11, c12 = t0.rows[1].cells
    for cell, head, val in (
        (c10, "NO AKADEMI",  "{{NO_AKADEMI}}"),
        (c11, "NAMA TARUNA", "{{NAMA_TARUNA}}"),
    ):
        clear_cell(cell)
        p = para(cell, WD_ALIGN_PARAGRAPH.CENTER); add_run(p, head, bold=True, size=11)
        p = para(cell, WD_ALIGN_PARAGRAPH.CENTER); add_run(p, val, bold=True, italic=True, size=11)
    clear_cell(c12)
    p = para(c12, WD_ALIGN_PARAGRAPH.CENTER); add_run(p, "{{KOMPI_LABEL}}", bold=True, size=11)
    p = para(c12, WD_ALIGN_PARAGRAPH.CENTER); add_run(p, "{{PELETON_LABEL}}", bold=True, size=11)

    para(doc, after=4)

    # ---------------- kegiatan ----------------
    t1 = doc.add_table(rows=5, cols=1)
    t1.style = 'Table Grid'
    t1.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r in t1.rows:
        r.cells[0].width = USABLE

    head = t1.rows[0].cells[0]
    clear_cell(head)
    for label, token in (("NAMA KEGIATAN",     "{{NAMA_KEGIATAN}}"),
                         ("WAKTU PELAKSANAAN", "{{WAKTU_PELAKSANAAN}}"),
                         ("TEMPAT",            "{{TEMPAT}}")):
        p = para(head, after=2)
        p.paragraph_format.tab_stops.add_tab_stop(Inches(2.15))
        add_run(p, label, bold=True, size=11)
        add_run(p, "\t:  ", bold=True, size=11)
        add_run(p, token, bold=True, size=11)

    cell = t1.rows[1].cells[0]; clear_cell(cell)
    p = para(cell, WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, "URAIAN KEGIATAN", bold=True, underline=True, size=11)

    cell = t1.rows[2].cells[0]; clear_cell(cell)
    p = para(cell, WD_ALIGN_PARAGRAPH.JUSTIFY, after=2, before=2)
    add_run(p, "{{URAIAN_KEGIATAN}}", size=11)

    cell = t1.rows[3].cells[0]; clear_cell(cell)
    p = para(cell, WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, "DISPOSISI DANTONTAR", bold=True, underline=True, size=11)

    cell = t1.rows[4].cells[0]; clear_cell(cell)
    p = para(cell, before=26, after=4)   # blank space for handwriting

    # ---------------- tanggal + tanda tangan ----------------
    p = para(doc, WD_ALIGN_PARAGRAPH.RIGHT, before=10, after=2, keep=True)
    add_run(p, "{{TTD_TEMPAT_TANGGAL}}", bold=True, size=11)

    sig = doc.add_table(rows=1, cols=2)
    no_borders(sig)
    sig.alignment = WD_TABLE_ALIGNMENT.CENTER
    left, right = sig.rows[0].cells
    left.width = right.width = Inches(3.2)
    clear_cell(left); clear_cell(right)

    # left column: Dantontar
    p = para(left, after=0, keep=True); add_run(p, "{{DANTON_JABATAN}}", bold=True, size=11)
    for _ in range(3):
        para(left, after=0, keep=True)
    p = para(left, after=0, keep=True); add_run(p, "{{DANTON_NAMA}}", bold=True, size=11)
    p = para(left, after=0);            add_run(p, "{{DANTON_PANGKAT_NRP}}", bold=True, size=11)

    # right column: the cadet
    p = para(right, after=0, keep=True); add_run(p, "YANG MEMBUAT LAPORAN", bold=True, size=11)
    for _ in range(3):
        para(right, after=0, keep=True)
    p = para(right, after=0, keep=True); add_run(p, "{{NAMA_TARUNA}}", bold=True, size=11)
    p = para(right, after=0);            add_run(p, "{{TARUNA_PANGKAT_NOAK}}", bold=True, size=11)

    # Danki, centred beneath both
    p = para(doc, WD_ALIGN_PARAGRAPH.CENTER, before=12, after=0, keep=True)
    add_run(p, "Mengetahui,", bold=True, size=11)
    p = para(doc, WD_ALIGN_PARAGRAPH.CENTER, after=0, keep=True)
    add_run(p, "{{DANKI_JABATAN}}", bold=True, size=11)
    for _ in range(3):
        para(doc, after=0, keep=True)
    p = para(doc, WD_ALIGN_PARAGRAPH.CENTER, after=0, keep=True)
    add_run(p, "{{DANKI_NAMA}}", bold=True, size=11)
    p = para(doc, WD_ALIGN_PARAGRAPH.CENTER, after=0)
    add_run(p, "{{DANKI_PANGKAT_NRP}}", bold=True, size=11)

    # ---------------- lampiran (own page) ----------------
    doc.add_page_break()
    p = para(doc, WD_ALIGN_PARAGRAPH.CENTER, after=10)
    add_run(p, "LAMPIRAN DOKUMENTASI", bold=True, underline=True, size=12)

    p = doc.add_paragraph()
    add_run(p, "{{LAMPIRAN_FOTO}}", size=1)   # photo table gets inserted here

    p = para(doc, WD_ALIGN_PARAGRAPH.RIGHT, before=14, after=0, keep=True)
    add_run(p, "{{LAMP_TEMPAT_TANGGAL}}", bold=True, size=11)
    p = para(doc, WD_ALIGN_PARAGRAPH.RIGHT, after=0, keep=True)
    add_run(p, "YANG MEMBUAT LAPORAN", bold=True, size=11)
    for _ in range(3):
        para(doc, after=0, keep=True)
    p = para(doc, WD_ALIGN_PARAGRAPH.RIGHT, after=0, keep=True)
    add_run(p, "{{NAMA_TARUNA}}", bold=True, size=11)
    p = para(doc, WD_ALIGN_PARAGRAPH.RIGHT, after=0)
    add_run(p, "{{LAMP_PANGKAT_NOAK}}", bold=True, size=11)

    doc.save('template_lhp.docx')
    print("template_lhp.docx written")


if __name__ == '__main__':
    build()
