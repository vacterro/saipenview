<div align="right">
  🌍 <strong>EN</strong> | <a href="README.ru.md">RU</a> | <a href="README.ee.md">EE</a> | <a href="README.ded.md">ДЕД</a> | <a href="README.ja.md">JA</a>
</div>

<div align="center">
  <img src="screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Peninjau baki desktop untuk setiap proyek SAIPEN di komputer Anda</strong>
    <br>
    Mendeteksi proyek <code>.saipen/</code> secara otomatis di seluruh drive lokal — fase langsung, tugas, pemblokir, status git, tiket, dan sub-agen.
    <br>
    Satu dasbor bertema Win95 emas-gelap klasik (vintage).
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Platform"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Release"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
    [🤍 Dukung Pengembang](https://buymeacoffee.com/vacuum34)
  </p>
</div>

<br>

---

<br>

## ✨ Sekilas Pandang

<p align="center">
  <img src="screenshots/dashboard.png" alt="SAIPENVIEW Dashboard Screenshot" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Setiap proyek SAIPEN, sub-agen, tiket, dan status git — semuanya dalam satu tampilan.</em>
</p>

<br>

---

## 🚀 Fitur

<table>
<tr>
<td width="50%">

### 🔍 Penemuan
- **Pindai otomatis** drive lokal untuk proyek `.saipen/`
- **Akar kustom** — pilih folder atau seluruh drive
- **Pengecualian pintar** — `node_modules`, `.git`, direktori sistem
- **Pindai ulang latar belakang** — interval yang dapat dikonfigurasi (bawaan 300 detik)
- **Worktree terhubung** — mendeteksi worktree git untuk penyetelan mudah

### 📊 Dasbor
- **Fase**, **tugas**, **tindakan selanjutnya**, **pemblokir** langsung
- **Cabang Git** + indikator status perubahan (dirty-state) per proyek
- **Filter** berdasarkan fase (Semua / Aktif / Selesai / Macet / kustom)
- **Urutkan** — Cerdas, Terbaru, Terlama, A–Z, Z–A
- **Cari** — filter nama/akar + pencarian tiket mendalam
- **Sematkan** proyek ke atas, **sembunyikan** yang tidak relevan
- **Sorotan kilat** — proyek yang berubah menyala & memudar selama 20 detik
- **Pewarnaan suhu** — proyek usang mendingin, proyek segar menghangat

</td>
<td width="50%">

### 🧩 Sub-Agen
- **Tampilan bersarang** — `saiwiki`, `saihunt`, `saitranslate` diinden di bawah induk
- **Jumlah Outbox** — siap/terblokir/draf/ditinjau sekilas pandang
- **Kumpulkan satu-klik** — gabungkan entri siap ke proyek utama
- **Peringatan kadaluwarsa** — mendeteksi berkas protokol yang usang

### 🎮 Interaksi
- **Penampil berkas** — baca & sunting STATE.md, BOARD.md, LOG.md
  - Mode Sumber (dapat disunting) + Mode Pembaca (dirender)
- **Tiket interaktif** — tombol Mulai / Selesai memperbarui BOARD.md secara langsung
- **Tindakan cepat** — kontekstual `npm run dev`, `cargo test`, dll.
- **Perintah kustom** — tombol tindakan yang ditentukan pengguna
- **Bagian yang dapat diciutkan** — per proyek, tersimpan
- **Bilah sisi yang dapat diubah ukurannya** — seret untuk mengubah ukuran

### ⌨️ Tombol Pintas & Jendela
- **Tampilkan/Sembunyikan** — `Ctrl+Alt+X` (dapat dikonfigurasi)
- **Jepret sudut** — `Ctrl+Q` berganti Kiri Atas → Kanan Atas → Kiri Bawah → Kanan Bawah
- **Perbesar/Perkecil** — `Ctrl+RodaTetikus`, `Ctrl+`+`/`-`
- **Baki sistem** — minimalkan ke baki, mulai tersembunyi
- Sakelar **Selalu di atas**
- **Mulai otomatis** — mulai otomatis Windows opsional
- **Mode tanpa bingkai** — matikan bilah judul untuk tampilan ultra-minimal

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Mulai Cepat

<table>
<tr>
<th width="33%">🐍 Jalankan dari sumber</th>
<th width="33%">📜 Skrip peluncuran</th>
<th width="33%">📦 Instalasi (masa mendatang)</th>
</tr>
<tr>
<td>

```bash
git clone https://github.com/vacterro/saipenview.git
cd saipenview
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m saipenview
```

</td>
<td>

| Skrip | Perilaku |
|---|---|
| `run.vbs` | Tersembunyi (hanya baki) |
| `run.bat` | Terlihat (konsol terbuka) |
Keduanya membuat `.venv` secara otomatis & menginstal dependensi.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Segera hadir ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Penggunaan

| Tindakan | Cara |
|---|---|
| **Tampilkan / Sembunyikan** | `Ctrl+Alt+X` atau `Alt+F15` (keduanya dapat dikonfigurasi) |
| **Jepret sudut** | `Ctrl+Q` — berganti Kiri-Atas → Kanan-Atas → Kiri-Bawah → Kanan-Bawah |
| **Sakelar darurat** | `Ctrl+Shift+Alt+Q` — menghentikan paksa proses |
| **Perbesar / Perkecil** | `Ctrl+RodaTetikus` atau `Ctrl` + `+` / `-` |
| **Reset zoom** | `Ctrl+0` |
| **Sembunyikan/tampilkan bilah alat** | `Alt+D` — ciutkan/perluas panel bilah alat |
| **Cari proyek** | Ketik di kotak pencarian; centang `D` untuk pencarian tiket mendalam |
| **Filter** | Menu turun: Semua / Aktif / Selesai / Macet, atau klik tombol fase |
| **Urutkan** | Cerdas / Terbaru / Terlama / A–Z / Z–A |
| **Pindai ulang** | Klik `Pindai ulang` atau tunggu pengatur waktu latar belakang (bawaan 300 detik) |
| **Jelajahi folder** | Klik `Jelajahi` untuk menambahkan folder ke set pemindaian |
| **Pengaturan** | Tombol ⚙ membuka modal pengaturan |
| **Wiki bantuan** | Tombol `?` membuka mini-wiki bawaan |
| **Klik-kanan proyek** | Salin jalur akar, filter berdasarkan fase, buka folder |
| **Klik-ganda bagian** | Membuka berkas yang terhubung (STATE.md, BOARD.md, LOG.md) |
| **Seret jendela** | Seret bilah judul (atau di mana saja dalam mode tanpa bingkai) |

### Modal

| Modal | Kegunaan |
|---|---|
| **Pengaturan** | Zoom, tombol pintas, penyesuaian pemindaian, mulai otomatis, selalu di atas, font, sakelar kilat, bawaan penampil berkas, perintah kustom, bahasa/lokal, akar pemindaian |
| **Penampil Berkas** | Baca & sunting STATE.md, BOARD.md, LOG.md — Mode Sumber (mentah) atau Pembaca (dirender) |
| **Bantuan** | Mini-wiki komprehensif yang mencakup setiap fitur, pintasan, dan konsep |
| **Konfirmasi** | Dialog DOM bergaya vintage (menggantikan `confirm()` bawaan) |

<br>

---

## 🧬 Protokol SAIPEN

SAIPENVIEW adalah pendamping untuk proyek yang menggunakan **Protokol SAIPEN** — kerangka kerja mesin status (state-machine) yang membimbing agen AI melalui pekerjaan proyek dalam fase-fase yang ditentukan:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                         ↓
                    HUNT / CLEAN
```

Setiap proyek SAIPEN menyimpan statusnya dalam tiga berkas kanonis:

| Berkas | Tujuan |
|---|---|
| `.saipen/STATE.md` | Frontmatter yang dapat dibaca mesin — fase, tugas, tindakan selanjutnya, pemblokir |
| `.saipen/BOARD.md` | Papan tiket — bagian DOING / TODO / DONE / BLOCKED |
| `.saipen/LOG.md` | Log peristiwa kronologis — setiap perintah dan hasilnya |

**Agen SubSaipen** (`saiwiki`, `saihunt`, `saitranslate`) berada di `.saipen/extensions/subs/` dan berkomunikasi melalui `kitchen/OUTBOX.md` — bus pesan antar-agen bawaan protokol. SAIPENVIEW menemukan semuanya dan merender dasbor yang terpadu.

### Kesesuaian (Konformansi)

Menampilkan apa yang *dikatakan* oleh suatu proyek hanyalah separuh darinya. Sebuah proyek dapat terbaca sempurna di daftar — suatu fase, tugas, tindakan selanjutnya — saat berada dalam status yang ditolak protokol, dan sebelum Anda menjalankan `tools/validate.py` secara manual, tidak ada cara untuk membedakan keduanya.

Setiap baris memiliki lencana vonis (verdict), dan panel detail mendaftar apa yang salah:

| Vonis | Arti |
|---|---|
| `OK` | Tidak ada masalah yang ditemukan di berkas `.saipen/` proyek ini sendiri |
| `N WARNS` | Legal, tetapi mengalami pergeseran (drifting) — titik pemulihan (checkpoint) usang, kata kerja LOG non-standar |
| `N FAILS` | Status yang ditolak protokol: `WAIT:` tanpa kategori, kotak centang yang tidak sesuai dengan bagiannya, `needs:` yang menunjuk ke tiket yang tidak ada, `STATE.md` UTF-16 yang tidak dapat dibaca oleh alat SAIPEN lain |

Setiap temuan menyebutkan nama aturan, berkas dan baris, serta klausul asalnya, sehingga dapat diperiksa daripada dipercaya mentah-mentah.

Ini adalah **pendapat kedua, bukan pengganti** untuk `tools/validate.py`. Ini hanya memeriksa ulang apa yang dapat ditentukan oleh berkas proyek itu sendiri, dan menilai terhadap salinan kosakata protokol — sehingga versi SAIPEN tempat ia dibaca dicetak di bawah setiap vonis. Peninjau diperbolehkan tertinggal dari protokol. Peninjau tidak diperbolehkan tertinggal secara diam-diam.

> 💡 *Nama "SAIPENVIEW" menjelaskan semuanya — memberikan **pandangan (view)** ke dalam setiap proyek **SAIPEN** di komputer Anda.*

<br>

---

## ⚙️ Konfigurasi

Konfigurasi bersifat portabel — disimpan di samping aplikasi, bukan di `%APPDATA%`:

```
saipenview/_data/config.json
```

Bawaan utama:

```json
{
  "hotkeys":          ["ctrl+alt+x", "alt+f15"],
  "snap_hotkey":      ["alt+f14"],
  "zoom_level":       1.0,
  "font_family":      "Verdana_m1",
  "scan_roots":       null,
  "rescan_interval":  300,
  "scan_depth":       6,
  "scan_delay_ms":    10,
  "auto_scan":        true,
  "show_on_launch":   true,
  "always_on_top":    true,
  "flash_changes":    true,
  "locale":           "en"
}
```

Atur `scan_roots: null` untuk mendeteksi otomatis semua drive lokal.  
Atur ke daftar jalur (misalnya `["V:\\", "D:\\projects"]`) untuk membatasi pemindaian.  
Semua pengaturan juga dapat dikonfigurasi melalui modal **Pengaturan** di aplikasi.

<br>

---

## 🏗️ Arsitektur

```
saipenview/
├── app.py              Pengabelan entri — baki, tombol pintas, jendela, api
├── api.py              Jembatan pywebview yang menghadap JS (30+ metode)
├── scanner.py          Penelusuran drive + ikal pindai ulang latar belakang
├── parser.py           Pemrosesan STATE.md / BOARD.md / LOG.md
├── textio.py           Satu pembaca untuk setiap berkas .saipen/ — BOM, UTF-16, cp1251
├── protocol.py         Kosakata tertutup protokol + BASELINE_VERSION
├── conformance.py      Menilai proyek terhadap kosakata tersebut
├── config.py           Muat/simpan pengaturan (penulisan atomik)
├── tray.py             Ikon baki sistem pystray + menu
├── hotkey.py           Pendaftaran tombol pintas global (pustaka keyboard)
├── autostart.py        Manajemen mulai otomatis Windows Registry
├── zone_picker.py      Hamparan penjepretan sudut Ctrl+Q (tkinter)
├── ui/
│   ├── window.py       Jendela pywebview — tampilkan/sembunyikan/sakelar/jepret
│   └── static/
│       ├── index.html
│       ├── style.css   Tema Win95 emas-gelap vintage
│       └── app.js      Logika frontend (~2600 baris)
├── assets/
│   └── tray_icon.png
├── screenshots/        Tangkapan layar README
└── _data/              Konfigurasi runtime + tembolok (diabaikan git)
```

### Prinsip Desain

- **Proses tunggal** — tanpa IPC latar belakang, tanpa server terpisah; satu proses Python menampung jendela WebView2 dan ikal pemindaian dalam `ThreadPoolExecutor`
- **Penulisan atomik** — setiap penulisan berkas menggunakan berkas sementara + `os.replace`; kegagalan (crash) tidak akan pernah memotong konfigurasi atau tembolok
- **Aman dari pembacaan usang** — pemungutan suara (polling) UI 5 detik memanggil `refresh_known()` (hanya membaca ulang berkas `.saipen/`, tanpa penelusuran direktori). Penyuntingan pada STATE.md muncul dalam hitungan detik tanpa memicu pemindaian drive penuh
- **Tanpa transisi CSS** — semua efek visual (kilat, suhu, sorot) adalah penghitungan ulang `hexBlend` berbasis JavaScript, dengan ketat mengikuti batasan tanpa animasi tema vintage
- **Tema vintage** — permukaan cokelat gelap, teks/aksen emas, batas miring (beveled) 3D, tanpa anti-aliasing, font Verdana_m1

<br>

---

## 🧪 Pengembangan

```bash
# Kloning & masuk
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Buat venv & instal
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Jalankan
python -m saipenview
```

Untuk penyetelan mendalam, konvensi pengodean, dan alur kerja PR, lihat [CONTRIBUTING.md](CONTRIBUTING.md).

### Persyaratan

- **Windows 10 / 11** — Runtime WebView2 (pra-terinstal di Win11, terinstal otomatis di Win10)
- **Python 3.10+**
- Dependensi: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Lisensi

MIT — lihat [LICENSE](LICENSE).

<br>

---

<div align="center">
  <sub>Dibuat dengan 🐍 Python • 🖼️ pywebview • 🎨 Estetika Win95 Vintage</sub>

<br>

---

## 📸 Tangkapan Layar Lainnya

<p align="center">
  <img src="screenshots/detail-pane.png" alt="SAIPENVIEW Detail Pane" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Panel detail dengan tiket, sub-agen, dan penampil berkas.</em>
</p>

<br>

</div>
