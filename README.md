# LHP AKPOL — Free Edition

LHP AKPOL MENKOPRS ini dibuat murni untuk menentang monetisasi dan memberikan semua taruna peluang yang sama dan adil beserta menghilangkan penggolongan taruna yang memiliki rezeki lebih dan tidak semua dapat perlakuan yang sama dan adil

walaupun begitu fungsi dari suatu website ini adalah "agar memotong waktu yang dimakan oleh taruna untuk membuat laporan secara manual dan agar memfokuskan taruna untuk menggunakan waktunya untuk melakukan kegiatan positif lainnya" -Danmentarsis
## Features

- **Self-register** — username + password, instant, no approval needed.
- **Unlimited, free document generation** — no tokens, no payment gateway.
- **Danton/Danki autofill** — pulls from `DATA_DANTONTAR_DANKITAR.xlsx`
  based on Tingkat + Kompi + Peleton.
- **Manual override** — if the roster data is missing (e.g. NRP not filled
  in yet), users can click "Edit Manual" and type the komando data by hand
  for that one document.
- **Admin panel** (`/login-admin`) — see every registered user, reset
  passwords, delete accounts, and read a full activity log (who logged in,
  registered, or generated a document, and what they generated).
- **Photo attachments** — uploaded photos are embedded in the "Lampiran
  Dokumentasi" section automatically.

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

Visit `http://localhost:5000`.

## Deploying (Railway or similar)

1. Push this folder to a GitHub repo connected to Railway (or any host that
   reads a `Procfile`).
2. Set environment variables:

   | Variable | Purpose | Default |
   |---|---|---|
   | `SECRET_KEY` | Flask session signing key — **set this in production** | `dev-secret-change-me` |
   | `ADMIN_USERNAME` | Admin panel login | `admin` |
   | `ADMIN_PASSWORD` | Admin panel login | `admin123` |
   | `PORT` | Set automatically by most hosts | `5000` |

3. **Attach a persistent volume mounted at `data/`** — this is where
   `users.json`, `activity_log.json`, and `visitors.json` live. Without a
   volume, every redeploy wipes all accounts and history.

## Updating the Danton/Danki roster

Edit `DATA_DANTONTAR_DANKITAR.xlsx` directly. Each tingkat is its own sheet
(`TK III - BD`, `TK II - MS`). Columns: `NO | NAMA | PANGKAT | JABATAN | ANGKATAN | NRP`.
`JABATAN` must read `DANKI TAR <letter>` or `DANTON TAR <peleton><letter>`
(spacing doesn't matter — it's normalized). NRP can be left blank; users can
fill it in manually per-document via "Edit Manual" until you update the sheet.

To add a new tingkat (e.g. Tingkat I), add a new sheet and register it in
`lhp_core.TINGKAT_CONFIG`.

## Personnel changes mid-cycle

If a Danki/Danton is temporarily standing in for another kompi, don't hand-edit
the generated document each time — add an entry to `lhp_core.PERSONNEL_OVERRIDES`
instead. See the comment above that dict for the shape.

## What's intentionally NOT included

Compared to the earlier paid version of this project, this build has no
Google OAuth, no Midtrans/Duitku payment integration, and no Claude-API
photo-timestamp scanning (that feature costs money per use — ask if you want
it added back; a free EXIF-based fallback is also possible for photos that
carry real camera metadata, though it won't read text painted into the image
itself).
