<div align="right">
  🌍 <strong>EN</strong> | <a href="README.ru.md">RU</a> | <a href="README.ee.md">EE</a> | <a href="README.ded.md">ДЕД</a> | <a href="README.ja.md">JA</a>
</div>

<div align="center">
  <img src="screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Makinenizdeki her SAIPEN projesi için masaüstü sistem tepsisi görüntüleyicisi</strong>
    <br>
    Yerel sürücülerdeki <code>.saipen/</code> projelerini otomatik keşfeder — canlı aşama, görev, engelleyici, git durumu, biletler ve alt ajanlar.
    <br>
    Tek bir nostaljik koyu-altın Win95 temalı gösterge paneli.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Platform"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Release"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
    [🤍 Geliştiriciyi Destekle](https://buymeacoffee.com/vacuum34)
  </p>
</div>

<br>

---

<br>

## ✨ Hızlı Bakış

<p align="center">
  <img src="screenshots/dashboard.png" alt="SAIPENVIEW Gösterge Paneli Ekran Görüntüsü" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Her SAIPEN projesi, alt ajan, bilet ve git durumu — hepsi tek bir görünümde.</em>
</p>

<br>

---

## 🚀 Özellikler

<table>
<tr>
<td width="50%">

### 🔍 Keşif
- **Otomatik tarama** — yerel sürücülerde `.saipen/` projelerini tarar
- **Özel kök dizinler** — klasörleri veya tüm sürücüleri seçin
- **Akıllı hariç tutmalar** — `node_modules`, `.git`, sistem dizinleri
- **Arka planda yeniden tarama** — yapılandırılabilir aralık (varsayılan 300sn)
- **Bağlı çalışma ağaçları (worktrees)** — kolay kurulum için git worktree'lerini algılar

### 📊 Gösterge Paneli
- Canlı **aşama**, **görev**, **sonraki eylem**, **engelleyici**
- Proje başına **Git dalı** + değişiklik durumu göstergesi
- Aşamaya göre **Filtrele** (Tümü / Canlı / Tamamlandı / Tıkandı / özel)
- **Sırala** — Akıllı, En Yeni, En Eski, A–Z, Z–A
- **Ara** — ad/kök filtresi + derin bilet araması
- Projeleri üste **Sabitle**, ilgisiz olanları **Gizle**
- **Flaş vurgulaması** — değişen projeler parlar ve 20sn içinde söner
- **Sıcaklık renklendirmesi** — güncel olmayan projeler soğur, taze projeler ısınır

</td>
<td width="50%">

### 🧩 Alt Ajanlar
- **İç içe görünüm** — `saiwiki`, `saihunt`, `saitranslate` ana projenin altında girintili gösterilir
- **Outbox sayıları** — hazır/engellendi/taslak/incelendi bir bakışta
- **Tek tıkla toplama** — hazır girdileri ana projeye birleştirin
- **Eski protokol uyarısı** — güncel olmayan protokol dosyalarını algılar

### 🎮 Etkileşim
- **Dosya görüntüleyici** — STATE.md, BOARD.md, LOG.md dosyalarını okuyun ve düzenleyin
  - Kaynak modu (düzenlenebilir) + Okuyucu modu (görselleştirilmiş)
- **Etkileşimli biletler** — Başlat / Tamamlandı butonları BOARD.md dosyasını canlı günceller
- **Hızlı eylemler** — bağlamsal `npm run dev`, `cargo test`, vb.
- **Özel komutlar** — kullanıcı tanımlı eylem butonları
- **Daraltılabilir bölümler** — proje bazlı, kalıcı
- **Yeniden boyutlandırılabilir kenar çubuğu** — sürükleyerek boyutlandırın

### ⌨️ Kısayollar ve Pencere
- **Göster/Gizle** — `Ctrl+Alt+X` (yapılandırılabilir)
- **Köşelere hizala** — `Ctrl+Q` SolÜst → SağÜst → SolAlt → SağAlt arasında geçiş yapar
- **Yakınlaştırma** — `Ctrl+FareTekerleği`, `Ctrl+`+`/`-`
- **Sistem tepsisi** — tepsiye küçült, gizli başlat
- **Her zaman üstte** geçişi
- **Otomatik başlatma** — isteğe bağlı Windows başlangıcında çalıştırma
- **Çerçevesiz mod** — ultra minimal görünüm için başlık çubuğunu kapatın

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Hızlı Başlangıç

<table>
<tr>
<th width="33%">🐍 Kaynaktan çalıştır</th>
<th width="33%">📜 Başlatma betikleri</th>
<th width="33%">📦 Yükleme (gelecekte)</th>
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

| Betik | Davranış |
|---|---|
| `run.vbs` | Gizli (yalnızca tepsi) |
| `run.bat` | Görünür (konsol açık) |
Her ikisi de `.venv` klasörünü otomatik oluşturur ve bağımlılıkları yükler.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Yakında geliyor ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Kullanım

| Eylem | Nasıl |
|---|---|
| **Göster / Gizle** | `Ctrl+Alt+X` veya `Alt+F15` (her ikisi de yapılandırılabilir) |
| **Köşeye hizala** | `Ctrl+Q` — Sol-Üst → Sağ-Üst → Sol-Alt → Sağ-Alt arasında geçiş yapar |
| **Acil kapatma** | `Ctrl+Shift+Alt+Q` — işlemi zorla kapatır |
| **Yakınlaştır / Uzaklaştır** | `Ctrl+FareTekerleği` veya `Ctrl` + `+` / `-` |
| **Yakınlaştırmayı sıfırla** | `Ctrl+0` |
| **Araç çubuğunu aç/kapat** | `Alt+D` — araç çubuğu panelini daraltır/genişletir |
| **Projelerde ara** | Arama kutusuna yazın; derin bilet araması için `D` kutucuğunu işaretleyin |
| **Filtrele** | Açılır menü: Tümü / Canlı / Tamamlandı / Tıkandı veya bir aşama etiketine tıklayın |
| **Sırala** | Akıllı / En Yeni / En Eski / A–Z / Z–A |
| **Yeniden tara** | `Yeniden Tara` butonuna tıklayın veya arka plan zamanlayıcısını bekleyin (varsayılan 300sn) |
| **Klasöre göz at** | Tarama kümesine bir klasör eklemek için `Göz At` butonuna tıklayın |
| **Ayarlar** | ⚙ butonu ayarlar penceresini açar |
| **Yardım vikisi** | `?` butonu yerleşik mini-vikiyi açar |
| **Projeye sağ tıkla** | Kök yolu kopyala, aşamaya göre filtrele, klasörü aç |
| **Bölüme çift tıkla** | Bağlı dosyayı açar (STATE.md, BOARD.md, LOG.md) |
| **Pencereyi sürükle** | Başlık çubuğunu sürükleyin (veya çerçevesiz modda herhangi bir yeri) |

### Pencereler (Modallar)

| Pencere | Ne yapar |
|---|---|
| **Ayarlar** | Yakınlaştırma, kısayollar, tarama ayarları, otomatik başlatma, her zaman üstte, yazı tipi, flaş geçişi, varsayılan dosya görüntüleyici, özel komutlar, dil/bölge, tarama kökleri |
| **Dosya Görüntüleyici** | STATE.md, BOARD.md, LOG.md okuyun ve düzenleyin — Kaynak (ham) veya Okuyucu (görselleştirilmiş) modu |
| **Yardım** | Her özelliği, kısayolu ve kavramı kapsayan kapsamlı mini-viki |
| **Onay** | Nostaljik stilli DOM iletişim kutusu (yerel `confirm()` işlevinin yerini alır) |

<br>

---

## 🧬 SAIPEN Protokolü

SAIPENVIEW, **SAIPEN Protokolü**'nü kullanan projeler için bir yardımcıdır — AI ajanlarına belirli aşamalardaki proje çalışmalarında rehberlik eden bir durum makinesi çerçevesi:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                         ↓
                    HUNT / CLEAN
```

Her SAIPEN projesi durumunu üç standart dosyada saklar:

| Dosya | Amaç |
|---|---|
| `.saipen/STATE.md` | Makine tarafından okunabilir ön bilgi — aşama, görev, sonraki eylem, engelleyici |
| `.saipen/BOARD.md` | Bilet panosu — DOING / TODO / DONE / BLOCKED bölümleri |
| `.saipen/LOG.md` | Kronolojik olay günlüğü — her komut ve sonucu |

**SubSaipen ajanları** (`saiwiki`, `saihunt`, `saitranslate`), `.saipen/extensions/subs/` dizininde yaşar ve protokolün yerleşik ajanlar arası mesaj veriyolu olan `kitchen/OUTBOX.md` aracılığıyla iletişim kurar. SAIPENVIEW hepsini keşfeder ve birleşik bir gösterge paneli sunar.

### Uyumluluk (Conformance)

Bir projenin ne *söylediğini* göstermek işin sadece yarısıdır. Bir proje listede mükemmel görünebilir — bir aşama, bir görev, bir sonraki eylem — ancak protokolün reddettiği bir durumda olabilir ve elle `tools/validate.py` çalıştırmadığınız sürece bu ikisini ayırt etmenin bir yolu yoktu.

Her satır bir karar rozeti taşır ve detay paneli neyin yanlış olduğunu listeler:

| Karar | Anlamı |
|---|---|
| `OK` | Bu projenin kendi `.saipen/` dosyalarında hiçbir sorun bulunamadı |
| `N WARNS` | Geçerli ama kayma var — eski bir kontrol noktası, standart dışı bir LOG fiili |
| `N FAILS` | Protokolün reddettiği bir durum: kategorisi olmayan bir `WAIT:`, bölümüyle uyuşmayan bir onay kutusu, var olmayan bir bilete işaret eden bir `needs:`, başka hiçbir SAIPEN aracının okuyamadığı UTF-16 `STATE.md` |

Her bulgu kuralı, dosyayı, satırı ve geldiği maddeyi adlandırır, böylece körü körüne kabul edilmek yerine kaynağına bakılabilir.

Bu `tools/validate.py` için bir **ikinci görüştür, onun yerine geçmez**. Yalnızca bir projenin kendi dosyalarının karar verebileceği şeyleri yeniden kontrol eder ve protokolün kelime dağarcığının bir kopyasına göre derecelendirir — böylece okunduğu SAIPEN sürümü her kararın altında yazdırılır. Görüntüleyicinin protokolden geride kalmasına izin verilir. Ancak sessizce geride kalmasına izin verilmez.

> 💡 *"SAIPENVIEW" adı her şeyi anlatıyor — makinenizdeki her **SAIPEN** projesine bir **görünüm** sağlar.*

<br>

---

## ⚙️ Yapılandırma

Yapılandırma taşınabilirdir — `%APPDATA%` yerine uygulamanın yanında saklanır:

```
saipenview/_data/config.json
```

Temel varsayılanlar:

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

Tüm yerel sürücüleri otomatik algılamak için `scan_roots: null` olarak ayarlayın.  
Taramayı sınırlandırmak için bir yol listesine ayarlayın (ör. `["V:\\", "D:\\projects"]`).  
Tüm ayarlar ayrıca uygulamadaki **Ayarlar** penceresinden de yapılandırılabilir.

<br>

---

## 🏗️ Mimari

```
saipenview/
├── app.py              Giriş bağlantıları — sistem tepsisi, kısayol, pencere, api
├── api.py              JS tarafına bakan pywebview köprüsü (30+ metot)
├── scanner.py          Sürücü gezintisi + arka plan yeniden tarama döngüsü
├── parser.py           STATE.md / BOARD.md / LOG.md ayrıştırma
├── textio.py           Her .saipen/ dosyası için tek okuyucu — BOM, UTF-16, cp1251
├── protocol.py         Protokolün kapalı kelime dağarcığı + BASELINE_VERSION
├── conformance.py      Bir projeyi bu kelime dağarcıklarına göre derecelendirir
├── config.py           Ayarları yükleme/kaydetme (atomik yazmalar)
├── tray.py             pystray sistem tepsisi simgesi + menüsü
├── hotkey.py           Genel kısayol kaydı (keyboard kütüphanesi)
├── autostart.py        Windows Kayıt Defteri otomatik başlatma yönetimi
├── zone_picker.py      Ctrl+Q köşe hizalama katmanı (tkinter)
├── ui/
│   ├── window.py       pywebview penceresi — göster/gizle/geçiş yap/hizala
│   └── static/
│       ├── index.html
│       ├── style.css   Nostaljik koyu-altın Win95 teması
│       └── app.js      Ön yüz mantığı (~2600 satır)
├── assets/
│   └── tray_icon.png
├── screenshots/        README ekran görüntüleri
└── _data/              Çalışma zamanı yapılandırması + önbellek (gitignored)
```

### Tasarım ilkeleri

- **Tek işlem** — arka plan IPC yok, ayrı sunucu yok; tek bir Python işlemi hem WebView2 penceresini hem de tarama döngüsünü bir `ThreadPoolExecutor` içinde barındırır
- **Atomik yazmalar** — her dosya yazma işlemi geçici dosya + `os.replace` kullanır; bir çökme yapılandırmayı veya önbelleği asla boza/kesemez
- **Eski okuma güvenli** — 5 saniyelik UI sorgulaması `refresh_known()` çağırır (yalnızca `.saipen/` dosyalarını yeniden okur, dizin gezintisi yapmaz). STATE.md değişiklikleri tam sürücü taramasını tetiklemeden saniyeler içinde görünür
- **CSS geçişleri yok** — tüm görsel efektler (flaş, sıcaklık, üzerine gelme) JavaScript tabanlı `hexBlend` yeniden hesaplamalarıdır ve nostaljik temanın sıfır animasyon kısıtlamasına kesinlikle uyar
- **Nostaljik tema** — koyu kahverengi yüzeyler, altın rengi metin/vurgular, 3B eğimli kenarlıklar, sıfır kenar yumuşatma (anti-aliasing), Verdana_m1 yazı tipi

<br>

---

## 🧪 Geliştirme

```bash
# Klonlayın ve dizine girin
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# venv oluşturun ve yükleyin
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Çalıştırın
python -m saipenview
```

Ayrıntılı kurulum, kodlama kuralları ve PR iş akışı için [CONTRIBUTING.md](CONTRIBUTING.md) dosyasına bakın.

### Gereksinimler

- **Windows 10 / 11** — WebView2 çalışma zamanı (Win11'de önceden yüklüdür, Win10'da otomatik yüklenir)
- **Python 3.10+**
- Bağımlılıklar: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Lisans

MIT — [LICENSE](LICENSE) dosyasına bakın.

<br>

---

<div align="center">
  <sub>🐍 Python • 🖼️ pywebview • 🎨 Nostaljik Win95 estetiği ile oluşturuldu</sub>

<br>

---

## 📸 Daha Fazla Ekran Görüntüsü

<p align="center">
  <img src="screenshots/detail-pane.png" alt="SAIPENVIEW Detay Paneli" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Biletler, alt ajanlar ve dosya görüntüleyici içeren detay paneli.</em>
</p>

<br>

</div>
