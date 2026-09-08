

Website ini dibuat untuk menghilangkan kesenjangan antar-taruna akibat monetisasi LHP dan perbedaan kepemilikan barang. Setiap taruna berhak mendapatkan akses yang sama terhadap LHP secara gratis, umum, dan adil. Dengan mempercepat akses dan pembuatan LHP, waktu dapat dialihkan untuk kegiatan lain yang lebih positif dan bermanfaat. Kesetaraan tercipta ketika sesuatu yang bermanfaat dapat diakses oleh semua, bukan hanya mereka yang mampu mendapatkannya.


## Template placeholder design — read this before touching `template_lhp.docx`

Every placeholder is a **complete, self-contained token** like `{{NAMA_TARUNA}}`
living in its own dedicated run, and `lhp_core.build_placeholder_values()`
assembles every final string BEFORE any replacement touches the document.
`_replace_in_paragraph` in `lhp_core.py` does a plain `str.replace` per run.

**Do not** go back to the old approach of a big dict of text *fragments*
(`"KOMPI III" -> "KOMPI IV"`) applied in sequence to whole paragraphs. That
was the root cause of a real, hard-to-find bug in the previous version: a
generic fragment replacement ran before a more specific one that depended on
the original text still being there, silently corrupting output (e.g.
`DANTONTAR 1 KOMPI III` never matched because `KOMPI III` had already been
turned into `KOMPI IV` by an earlier, unrelated replacement). One token, one
final value, always — if you add a new field to the document, add a new
`{{TOKEN}}` rather than trying to compose it from replacements of other
tokens.

If you regenerate `template_lhp.docx` via `build_template.py`, always
re-render it (`soffice --headless --convert-to pdf` then `pdftoppm`) and look
at the image before trusting it — Word XML is invisible from the outside and
`python-docx` will happily produce garbage layouts.

## Known gaps in the current roster data

`DATA_DANTONTAR_DANKITAR.xlsx` (as uploaded) has no NRP column populated —
sheet has NO / NAMA / PANGKAT / JABATAN / ANGKATAN, and an empty NRP column
was added for future fill-in. Kompi "A" Danki row is also blank for TK III.
Until the roster is filled in, users will need "Edit Manual" for those
kompi/tingkat combinations. Don't silently invent NRPs.

Only two tingkat are present: TK II (Manggala Satya, angkatan 60) and TK III
(Bhayangkara Dharma, angkatan 59). TK I has no data and isn't registered in
`lhp_core.TINGKAT_CONFIG` — add it once a roster sheet exists (see README).

Both TK II and TK III use **letter-based kompi (A–E)** in the current data —
this differs from an earlier iteration of the project where TK II used roman
numerals (I–V). If new roster data reintroduces roman numerals for a given
tingkat, `kompi_letters()` and the jabatan-matching regexes in `lhp_core.py`
will need a per-tingkat branch, not a single hardcoded A–E list.

## Personnel overrides

`lhp_core.PERSONNEL_OVERRIDES` is the one place to record "kompi X's Danki
is temporarily filled by kompi Y's Danki" situations. Don't hardcode these
as string replacements in `app.py` — that's how the fragile
`(BRIGKATARakhir)` bug family happened last time. The dict key is
`(tingkat, kompi, "danki")`; `signature_kompi` controls what letter appears
in `DANKITAR {letter} TK ...` if it should differ from the taruna's own kompi.

## Performance

Single gunicorn worker with 8 threads (`Procfile`) — this app has no slow
outbound network calls (no OAuth, no payment gateway, no external AI API), so
lag risk is much lower than the previous version, but keep threads rather
than reverting to a sync worker: concurrent document generation should not
serialize behind each other.

`lhp_core._load_roster()` caches the parsed Excel by file mtime — if you
update the roster on disk, the next request picks it up automatically, no
restart needed.

## Data files (never commit)

`data/users.json`, `data/activity_log.json`, `data/visitors.json` are
gitignored and written atomically (temp file + `os.replace`). On a host like
Railway, mount a persistent volume at `data/` or every redeploy wipes all
accounts.


