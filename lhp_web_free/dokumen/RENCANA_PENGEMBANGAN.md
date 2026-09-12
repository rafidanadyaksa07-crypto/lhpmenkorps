# Rencana Pengembangan — LHP AKPOL

Disusun 9 September 2026. Daftar ini berdasarkan pemeriksaan langsung terhadap
kode dan data yang berjalan sekarang, bukan perkiraan umum.

Urutannya sengaja: nomor kecil dikerjakan lebih dulu karena berdampak pada
kebenaran dokumen dan keamanan akun. Fitur tambahan ada di bagian akhir.

Perkiraan waktu memakai satuan jam kerja. Dengan tarif Rp 75.000 per jam pada
lembar anggaran, satu jam setara Rp 75.000 bila dikerjakan pihak ketiga.

---

## PRIORITAS 1 — Wajib segera

### 1.1 Ganti kunci rahasia dan sandi admin bawaan

**Masalah.** Di `app.py` ada nilai bawaan:

```python
app.secret_key   = os.environ.get("SECRET_KEY", "dev-secret-change-me")
ADMIN_PASSWORD   = os.environ.get("ADMIN_PASSWORD", "admin123")
```

Bila kedua env var itu tidak diisi di Railway, siapa pun yang membaca kode ini
bisa masuk sebagai pengelola, dan bisa memalsukan kuki sesi untuk menyamar
sebagai taruna mana pun.

**Kenapa mendesak.** Kode ini akan dibagikan atau disimpan di GitHub. Nilai
bawaannya bukan rahasia.

**Langkah.**
1. Buka Railway → proyek → Variables.
2. Pastikan tiga variabel ini terisi, bukan memakai bawaan:
   - `SECRET_KEY` — isi dengan teks acak panjang. Buat dengan:
     `python3 -c "import secrets; print(secrets.token_hex(32))"`
   - `ADMIN_USERNAME` — jangan `admin`.
   - `ADMIN_PASSWORD` — minimal 16 karakter.
3. Simpan, tunggu Railway memasang ulang.
4. Buka `/login-admin`, pastikan sandi lama sudah tidak berlaku.

**Catatan.** Mengganti `SECRET_KEY` akan mengeluarkan semua taruna yang sedang
masuk. Itu wajar, mereka tinggal masuk lagi.

**Waktu.** 15 menit. **Biaya.** Nol.

---

### 1.2 Perbaiki janji dukungan HEIC

> **SUDAH DIKERJAKAN — 9 September 2026.**

**Masalah.** Antarmuka menulis "JPG, PNG, atau HEIC" di kotak unggah, tetapi
pustaka `pillow-heif` tidak terpasang dan tidak ada di `requirements.txt`.
Foto HEIC dari iPhone akan gagal dimasukkan ke dokumen.

**Kenapa penting.** Sebagian besar taruna memakai iPhone dengan pengaturan
bawaan yang menghasilkan HEIC. Mereka akan mengira aplikasinya rusak.

**Langkah — pilih salah satu.**

*Cara A, dukung HEIC sungguhan (disarankan):*
1. Tambahkan ke `requirements.txt`:
   ```
   pillow-heif==0.18.0
   ```
2. Di awal `lhp_core.py`, setelah impor lain, tambahkan:
   ```python
   try:
       from pillow_heif import register_heif_opener
       register_heif_opener()
   except ImportError:
       pass          # HEIC tidak didukung bila pustaka tidak ada
   ```
3. Pada `_insert_photos`, ubah berkas HEIC menjadi JPEG sebelum disisipkan,
   karena python-docx tidak mengenal HEIC:
   ```python
   if path.lower().endswith((".heic", ".heif")):
       from PIL import Image
       jpg = path.rsplit(".", 1)[0] + ".jpg"
       Image.open(path).convert("RGB").save(jpg, quality=88)
       path = jpg
   ```
4. Uji dengan satu foto HEIC asli dari iPhone sebelum dipasang.

*Cara B, jujur saja tidak mendukung:*
Ubah tulisan di `templates/index.html` menjadi "JPG atau PNG", lalu ganti
`accept="image/*"` menjadi `accept="image/jpeg,image/png"` agar pemilih berkas
menolaknya sejak awal.

**Waktu.** Cara A 3 jam termasuk pengujian. Cara B 15 menit.
**Biaya.** Nol.

---

### 1.3 Lengkapi data satuan yang masih kosong

**Masalah.** Hasil pemeriksaan `DATA_DANTONTAR_DANKITAR.xlsx`:

| Lembar | Jabatan tanpa NRP |
|---|---|
| TK III - BD | Danton 3B, 1D, 2D, 3D |
| TK II - MS | Danton 1A, 3C |

Tingkat I belum ada lembarnya sama sekali.

Selain itu ada dua hal yang belum terselesaikan:
- **NRP Satria Ardi Yana bertentangan.** Berkas personel menulis `93060352`
  di sembilan potretnya, sedangkan LHP contoh menulis `92060352`. Salah satu
  keliru dan belum dipastikan yang mana.
- **Danton 1A TK II belum jelas orangnya.** Data lama mencatat Steven Khyta
  Lubis, berkas pengasuh baru mencatat Rahmat Hersa Widiatmoko. NRP sengaja
  tidak diambil karena NRP melekat pada orang, bukan pada jabatan.

**Kenapa penting.** Kolom kosong memaksa taruna memakai tombol "Isi sendiri",
dan di situlah salah ketik NRP paling mungkin terjadi pada dokumen resmi.

**Langkah.**
1. Minta data NRP keenam Danton itu ke bagian personel.
2. Buka berkas Excel, isi kolom **NRP** pada baris yang sesuai. Ketik sebagai
   teks agar angka nol di depan tidak hilang.
3. Pastikan NRP Satria Ardi Yana ke bagian personel, lalu perbaiki yang keliru.
4. Pastikan siapa Danton 1A TK II sekarang, ganti nama dan NRP-nya sekalian.
5. Unggah berkas Excel yang sudah diperbarui ke repo. Tidak perlu ubah kode —
   `_load_roster()` membaca ulang otomatis begitu berkasnya berubah.

**Untuk menambah Tingkat I:**
1. Tambahkan lembar baru bernama `TK I - XX` (XX singkatan batalyonnya).
2. Susun kolomnya sama persis: `NO | NAMA | PANGKAT | JABATAN | ANGKATAN | NRP`.
3. Format jabatan harus sama: `DANKI TAR A`, `DANTON TAR 1A`, dan seterusnya.
4. Daftarkan di `lhp_core.py` pada `TINGKAT_CONFIG`:
   ```python
   "1": {"label": "I", "angkatan": "61", "batalyon_singkat": "XX",
         "batalyon_nama": "NAMA BATALYON", "sheet": "TK I - XX"},
   ```
5. Pilihan Tingkat I akan muncul sendiri di formulir.

**Waktu.** 2 jam untuk melengkapi NRP, 3 jam untuk menambah Tingkat I.
**Biaya.** Nol.

---

## PRIORITAS 2 — Kekokohan

### 2.1 Pindahkan data akun dari berkas JSON ke PostgreSQL

**Masalah.** Akun, catatan aktivitas, dan penghitung kunjungan disimpan sebagai
berkas JSON di `data/`. Penulisannya sudah dibuat aman lewat berkas sementara
dan `os.replace`, tetapi bila dua taruna mendaftar pada detik yang sama, yang
belakangan menimpa yang duluan. Semakin banyak pengguna, semakin sering.

**Kenapa penting.** Dengan 980 taruna, tabrakan penulisan bukan lagi
kemungkinan kecil. Biayanya sudah dianggarkan di lembar anggaran, USD 8 per
bulan, jadi tinggal dikerjakan.

**Langkah.**
1. Railway → proyek → New → Database → PostgreSQL. Railway mengisi
   `DATABASE_URL` secara otomatis.
2. Tambahkan ke `requirements.txt`:
   ```
   psycopg[binary]==3.2.3
   ```
3. Buat tabelnya:
   ```sql
   CREATE TABLE users (
     uid           TEXT PRIMARY KEY,
     username      TEXT UNIQUE NOT NULL,
     nama          TEXT NOT NULL,
     password_hash TEXT NOT NULL,
     defaults      JSONB DEFAULT '{}',
     created_at    TIMESTAMPTZ DEFAULT now()
   );
   CREATE TABLE activity (
     id        BIGSERIAL PRIMARY KEY,
     username  TEXT, action TEXT, detail JSONB,
     ip        TEXT, ts TIMESTAMPTZ DEFAULT now()
   );
   CREATE INDEX ON activity (ts DESC);
   ```
4. Di `app.py`, ganti isi `load_users`, `save_users`, dan `log_activity` dengan
   kueri SQL. **Jangan ubah nama fungsinya** — seluruh kode lain memanggil
   nama itu, jadi perubahan cukup di satu tempat.
5. Pindahkan data lama sekali jalan dengan skrip yang membaca `users.json` dan
   memasukkannya ke tabel.
6. Uji pendaftaran, masuk, penyusunan dokumen, dan halaman pengelola sebelum
   menghapus berkas JSON lama. Simpan salinannya beberapa minggu.

**Waktu.** 10 jam. **Biaya.** USD 8 per bulan, sudah masuk anggaran.

---

### 2.2 Pencadangan otomatis

**Masalah.** Bila volume Railway rusak atau terhapus, seluruh akun hilang dan
tidak ada salinannya di tempat lain.

**Langkah.**
1. Buat akun penyimpanan objek murah, misalnya Backblaze B2. Kuota gratisnya
   10 GB, jauh lebih dari cukup untuk berkas teks.
2. Tambahkan rute tersembunyi yang hanya bisa dipanggil pengelola, misalnya
   `/api/admin/backup`, yang mengunggah berkas data ke sana.
3. Jalankan terjadwal lewat Railway Cron, sekali sehari.
4. **Uji pemulihannya, bukan hanya pencadangannya.** Cadangan yang belum pernah
   dicoba dipulihkan belum tentu berfungsi.

**Waktu.** 6 jam. **Biaya.** USD 3 per bulan, sudah masuk anggaran.

---

### 2.3 Batasi percobaan masuk

**Masalah.** Tidak ada pembatasan jumlah percobaan pada `/login` dan
`/login-admin`. Sandi bisa ditebak berulang kali tanpa hambatan.

**Langkah.**
1. Tambahkan ke `requirements.txt`:
   ```
   Flask-Limiter==3.8.0
   ```
2. Di `app.py`:
   ```python
   from flask_limiter import Limiter
   from flask_limiter.util import get_remote_address
   limiter = Limiter(get_remote_address, app=app, default_limits=[])
   ```
3. Beri hiasan pada kedua rute masuk:
   ```python
   @limiter.limit("8 per minute; 40 per hour")
   ```
4. Uji dengan mencoba masuk sembilan kali berturut-turut, pastikan yang
   kesembilan ditolak.

**Catatan.** Bila memakai Cloudflare, penyimpan hitungan sebaiknya diarahkan
ke Redis agar tetap berlaku walau aplikasi dipasang ulang.

**Waktu.** 3 jam. **Biaya.** Nol.

---

### 2.4 Perkecil foto sebelum dimasukkan ke dokumen

> **SUDAH DIKERJAKAN — 9 September 2026.**

**Masalah.** Foto disisipkan apa adanya. Ukuran tampilnya memang diperkecil,
tetapi isi berkasnya tetap utuh. Empat foto iPhone 5 MB menghasilkan dokumen
20 MB yang berat dibuka dan dikirim.

**Langkah.** Di `lhp_core.py` pada `_insert_photos`, sebelum `add_picture`:
```python
from PIL import Image
with Image.open(path) as im:
    if max(im.size) > 1600:
        im = im.convert("RGB")
        im.thumbnail((1600, 1600), Image.LANCZOS)
        kecil = path.rsplit(".", 1)[0] + "_kecil.jpg"
        im.save(kecil, quality=85, optimize=True)
        path = kecil
```
Lebar 1600 piksel masih tajam saat dicetak pada ukuran lampiran.

**Waktu.** 2 jam. **Biaya.** Nol.

---

## PRIORITAS 3 — Mempermudah pemakaian

### 3.1 Pratinjau dokumen sebelum diunduh

**Masalah.** Taruna baru tahu hasilnya setelah mengunduh dan membuka Word.
Bila ada yang keliru, harus mengisi ulang dari awal.

**Langkah.**
1. Tambah rute `/api/preview` yang menyusun dokumen ke berkas sementara.
2. Ubah ke PDF dengan LibreOffice, lalu ubah halaman pertama menjadi gambar.
3. Tampilkan gambar itu di halaman, dengan tombol "Unduh" dan "Perbaiki".
4. Hapus berkas sementaranya di blok `finally`.

**Peringatan.** LibreOffice berat dan lambat. Sediakan paling tidak 1 GB RAM,
atau jalankan sebagai antrean latar belakang agar tidak menghambat pengguna
lain. Uji dulu pengaruhnya pada kecepatan sebelum dipasang untuk semua.

**Waktu.** 12 jam. **Biaya.** Kemungkinan perlu tambahan RAM, USD 5 per bulan.

---

### 3.2 Riwayat dokumen milik sendiri

**Masalah.** Dokumen yang sudah dibuat tidak tersimpan. Bila berkasnya hilang,
taruna harus mengisi formulir lagi dari nol.

**Langkah.**
1. Simpan dokumen hasil ke volume, dengan nama `{username}/{waktu}_{kegiatan}.docx`.
2. Catat berkasnya di tabel `activity` pada kolom `detail`.
3. Buat halaman `/riwayat` berisi daftar dokumen milik pengguna itu saja,
   dengan tombol unduh ulang.
4. **Wajib:** pastikan pengguna hanya bisa mengunduh berkas miliknya sendiri.
   Periksa pemiliknya di sisi server, jangan mengandalkan nama berkas.
5. Hapus otomatis dokumen yang lebih tua dari 90 hari agar volume tidak penuh.

**Waktu.** 10 jam. **Biaya.** Tambahan penyimpanan sekitar USD 1 per bulan.

---

### 3.3 Halaman rekap untuk pengasuh

> **SUDAH DIKERJAKAN — 9 September 2026.**

**Masalah.** Dantontar tidak punya cara melihat siapa yang sudah dan belum
menyusun LHP. Sekarang hanya pengelola yang bisa melihat catatan.

**Langkah.**
1. Tambah peran baru `pengasuh` pada tabel `users`.
2. Buat halaman `/rekap` yang hanya menampilkan taruna di peleton dan kompi
   pengasuh itu, dengan jumlah dokumen per taruna pada bulan berjalan.
3. Sediakan tombol unduh rekap ke Excel.

**Pertimbangkan dulu.** Ini mengubah aplikasi dari alat bantu pribadi menjadi
alat pengawasan. Sebaiknya dibicarakan dengan taruna dan pengasuh lebih dulu,
karena bisa mengubah cara orang memakainya.

**Waktu.** 14 jam. **Biaya.** Nol.

---

### 3.4 Atur ulang sandi sendiri

> **BELUM DIKERJAKAN.** Sempat dibuat memakai kode pemulihan, lalu dibatalkan
> atas keputusan pemilik proyek. Untuk sementara pengaturan ulang sandi
> dilakukan pengelola lewat halaman admin.

**Masalah.** Taruna yang lupa sandi harus menghubungi pengelola. Dengan 980
pengguna, ini akan sering terjadi dan memakan jam dukungan.

**Langkah.**
1. Tambah kolom `email` saat mendaftar.
2. Buat rute `/lupa-sandi` yang mengirim tautan berisi token acak, berlaku
   satu jam dan hanya sekali pakai.
3. Kirim lewat layanan surel. Resend dan Brevo punya kuota gratis yang cukup.

**Alternatif tanpa surel:** buat kode pemulihan sekali pakai yang ditampilkan
saat mendaftar dan disuruh dicatat taruna.

**Waktu.** 8 jam. **Biaya.** Nol pada kuota gratis.

---

## PRIORITAS 4 — Nilai tambah

### 4.1 Ekspor catatan aktivitas ke Excel

Untuk keperluan pelaporan. Tambah tombol di halaman pengelola yang menyusun
berkas `.xlsx` dari tabel `activity` memakai openpyxl, yang sudah terpasang.
**Waktu.** 4 jam.

### 4.2 Pemantauan waktu aktif

Daftarkan alamat situs ke UptimeRobot, arahkan ke `/health` yang sudah ada.
Rute itu sudah mengembalikan status 503 bila berkas satuan hilang, jadi
pemberitahuan akan datang sebelum taruna melapor. **Waktu.** 30 menit. Gratis.

### 4.3 Cloudflare paket gratis

Pasang di depan situs untuk SSL, penahan serangan, dan pengantar isi.
Menghilangkan alamat asli server dari pandangan umum. **Waktu.** 2 jam. Gratis.

### 4.4 Bisa dipasang di layar utama ponsel

Tambahkan `manifest.json` dan ikon agar situs bisa ditambahkan ke layar utama
seperti aplikasi. Tidak perlu masuk toko aplikasi. **Waktu.** 4 jam. Gratis.

---

## Yang sengaja TIDAK dilakukan

Dicatat agar tidak dikerjakan ulang tanpa sengaja.

| Hal | Alasan |
|---|---|
| Pembacaan tulisan tanggal pada foto (OCR) | Dihapus atas permintaan untuk menekan biaya. Berbiaya per foto dan tidak ada di anggaran. |
| Sistem token dan pembayaran | Situs ini gratis bagi taruna. |
| Masuk lewat akun Google | Menambah kerumitan tanpa manfaat, karena akun hanya untuk mencatat pemakaian. |
| Kompi memakai angka Romawi | Data satuan sekarang memakai huruf A sampai E untuk TK II dan TK III. |

---

## Biaya layanan yang perlu dianggarkan

Dua pos berikut wajib berjalan agar situs tetap hidup. Keduanya di luar jam
kerja pengembangan yang tercantum pada butir-butir di atas.

Kurs yang dipakai: **Rp 17.700 per USD**.

| Pos | Harga | Per bulan | Per tahun |
|---|---|---|---|
| Layanan hosting domain | USD 20 / tahun | Rp 29.500 | Rp 354.000 |
| Railway paket Pro | USD 25 / bulan | Rp 442.500 | Rp 5.310.000 |
| **Jumlah** | | **Rp 472.000** | **Rp 5.664.000** |

### Layanan hosting domain — USD 20 per tahun

Nama situs beserta pengelolaan DNS-nya, misalnya `lhpakpol.com`. Dibayar
sekali setahun dan wajib diperpanjang, karena domain yang kedaluwarsa membuat
situs tidak bisa dibuka sama sekali walaupun aplikasinya tetap berjalan.

**Langkah.**
1. Beli di penyedia domain, misalnya Niagahoster, Domainesia, atau Cloudflare
   Registrar.
2. Railway → service → Settings → Networking → Custom Domain, masukkan nama
   domainnya.
3. Salin catatan CNAME yang ditampilkan Railway ke pengaturan DNS di penyedia
   domain tadi.
4. Nyalakan perpanjangan otomatis agar tidak terlewat.

### Railway paket Pro — USD 25 per bulan

Naik dari paket Hobby. Memberi jatah sumber daya lebih besar, batas pemakaian
lebih longgar, dan dukungan yang lebih baik. Diperlukan ketika jumlah pemakai
mendekati 980 taruna, agar situs tidak melambat saat banyak yang memakai
bersamaan.

**Langkah.**
1. Railway → Account Settings → Plans → pilih Pro.
2. Pantau pemakaian di tab Usage selama satu bulan pertama.
3. Bila pemakaian nyata ternyata jauh di bawah jatah, turunkan kembali ke
   Hobby. Paket bisa diubah kapan saja.

### Catatan

Harga resmi Railway Pro yang tercantum di railway.com/pricing adalah **USD 20
per bulan**. Angka USD 25 di atas dipakai sesuai permintaan, sehingga sudah
termasuk kelebihan sekitar USD 5 sebagai penyangga bila pemakaian sumber daya
melebihi jatah. Silakan turunkan ke USD 20 bila ingin memakai harga resmi
tanpa penyangga.

Domain diasumsikan **per tahun**, sesuai kebiasaan penagihan domain. Bila
ternyata USD 20 itu per bulan, biaya per tahunnya menjadi Rp 4.248.000 dan
jumlah keseluruhan menjadi Rp 9.558.000 per tahun.

Lembar `Estimasi_Anggaran_LHP_AKPOL.xlsx` di folder yang sama **sudah memakai
angka ini**. Totalnya menjadi Rp 46.860.689 untuk tiga tahun, dengan batas
anggaran Rp 50 juta, sehingga masih tersisa sekitar Rp 3,1 juta.

---

## Urutan pengerjaan yang disarankan

| Tahap | Isi | Jam | Hasilnya |
|---|---|---|---|
| 1 | 1.1, 1.2, 1.3 | ~6 | Akun aman, tidak ada janji palsu, data satuan benar |
| 2 | 2.3, 2.4 | ~5 | Tahan tebakan sandi, dokumen lebih ringan |
| 3 | 2.1, 2.2 | ~16 | Data akun kokoh dan ada cadangannya |
| 4 | 3.4, 4.2, 4.3 | ~11 | Beban dukungan turun, situs terpantau |
| 5 | 3.1, 3.2 | ~22 | Taruna bisa memeriksa dan mengunduh ulang |

Tahap 1 sebaiknya dikerjakan sebelum jumlah pengguna bertambah menjadi 980,
karena tiga butir di dalamnya menyangkut keamanan dan kebenaran dokumen.

Bila ada perubahan yang tidak jelas alasannya dari kode, catat di
`Devnotes.md` supaya tidak dibongkar ulang di kemudian hari.
