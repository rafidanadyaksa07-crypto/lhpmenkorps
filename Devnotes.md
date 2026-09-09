# Dev notes — LHP AKPOL (Free Edition)

Context for whoever (human or Claude) picks this project up next.

## Why this rebuild exists

An earlier version of this project (paid, token-gated, Google OAuth +
Midtrans/Duitku) accumulated a lot of fragile patches. This is a from-scratch
rebuild with the payment/OAuth complexity removed entirely: login is only for
attributing usage in the admin log, and generation is unlimited and free.

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

## Explicitly deferred (ask before adding)

- Google OAuth / any "verify identity" step before registering — the
  brief for this rebuild was explicitly "free of use, login is required only
  to monitor who is using it," i.e. no gatekeeping.
- Payment/token systems of any kind.
- Claude-API-based photo timestamp OCR — real feature, but costs money per
  call; a free EXIF-metadata fallback exists for photos with real camera
  metadata (won't read timestamps painted into the image pixels).


## Pemindaian tanggal dari foto

Hanya EXIF (`read_photo_datetime()` di `lhp_core.py`). Gratis, seketika, tanpa
panggilan ke layanan luar.

**OCR berbayar sudah dihapus atas permintaan pemilik proyek untuk menekan
biaya.** Jangan menambahkannya kembali tanpa persetujuan, karena biayanya per
foto dan tidak ada di lembar anggaran. Pengisian manual adalah jalur utama.

EXIF akan sering kosong: metadata hilang bila foto dibagikan lewat WhatsApp,
disalin dari Word, atau di-screenshot. Itu perilaku yang diharapkan, bukan
galat. Pesan yang muncul sudah menjelaskan sebabnya dan menyuruh mengisi manual.

Aturan yang tidak boleh dilanggar: hasil pembacaan **tidak pernah langsung
mengisi formulir**. Selalu ditampilkan sebagai usulan dengan tombol "Gunakan".
Tanggal salah pada dokumen resmi lebih merepotkan daripada mengetik sendiri.

Berkas foto pindaian dihapus di blok `finally` pada `/api/scan-photo`.
Jangan hilangkan penghapusan itu.


## Penyiapan gambar (HEIC dan pemerkecilan)

`_siapkan_gambar()` di `lhp_core.py` dipanggil untuk setiap foto sebelum
disisipkan. Dua tugasnya: mengubah HEIC menjadi JPEG (python-docx tidak
mengenal HEIC) dan memperkecil foto di atas 1600 piksel.

Uji nyata: satu foto 1,8 MB menjadi 293 KB; dokumen empat foto turun dari
sekitar 7,4 MB menjadi 358 KB.

Pemulihan sandi mandiri **tidak dipakai** atas keputusan pemilik proyek.
Taruna yang lupa sandi menghubungi pengelola, yang mengaturnya lewat tombol
"Ganti sandi" di halaman admin.

HEIC bergantung pada `pillow-heif` di `requirements.txt`. Bila pustaka itu
gagal dipasang, `HEIC_DIDUKUNG` bernilai False dan aplikasi tetap berjalan,
hanya HEIC yang tidak terbaca. **HEIC belum pernah diuji dengan berkas asli
dari iPhone**, karena pustakanya tidak tersedia di lingkungan pengembangan.
Uji dengan satu foto iPhone sungguhan setelah dipasang.

## Peran pengasuh dan halaman rekap

Peran ketiga selain taruna dan pengelola. Ditetapkan pengelola lewat tombol
"Peran" di halaman admin, berikut lingkup tingkat, kompi, dan peleton.

`_rekap_data()` mengenali taruna dari `defaults` yang tersimpan setelah ia
membuat dokumen. Akibatnya **taruna yang belum pernah membuat dokumen tidak
muncul di rekap** — satuannya memang belum diketahui. Ini keterbatasan yang
disengaja, bukan galat. Bila kelak perlu daftar lengkap, tambahkan pilihan
satuan saat mendaftar.

Pengasuh hanya melihat lingkupnya sendiri. Pengelola melihat semua.
