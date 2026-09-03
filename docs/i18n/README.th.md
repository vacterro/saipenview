<div align="right">

  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <strong>TH</strong> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>
> **Note:** This is a translated copy. The canonical documentation is [README.md](../../README.md) — this translation may lag the English original.

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>ตัวดูโปรเจกต์ SAIPEN ในถาดระบบสำหรับทุกโปรเจกต์บนเครื่องของคุณ</strong>
    <br>
    ค้นพบโปรเจกต์ <code>.saipen/</code> โดยอัตโนมัติตามไดรฟ์ในเครื่อง — ดูเฟสสด, งาน, อุปสรรค (blocker), สถานะ git, ตั๋ว (tickets) และซับเอเจนต์ (sub-agents)
    <br>
    แดชบอร์ดธีม Win95 สีทองเข้มสไตล์วินเทจในตัวเดียว
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Platform"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Release"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
  </p>
</div>

<br>

---

## 🚀 ฟีเจอร์

<table>
<tr>
<td width="50%">

### 🔍 การค้นหา (Discovery)
- **สแกนอัตโนมัติ** ไดรฟ์ในเครื่องเพื่อหาโปรเจกต์ `.saipen/`
- **กำหนดรากแบบกำหนดเอง** — เลือกโฟลเดอร์หรือไดรฟ์ทั้งหมด
- **การยกเว้นอัจฉริยะ** — `node_modules`, `.git`, ไดเรกทอรีระบบ
- **สแกนซ้ำในเบื้องหลัง** — ตั้งค่าช่วงเวลาได้ (ค่าเริ่มต้น 300 วินาที)
- **Worktrees ที่เชื่อมโยง** — ตรวจจับ git worktrees เพื่อการตั้งค่าที่ง่ายดาย

### 📊 แดชบอร์ด (Dashboard)
- แสดง **เฟส**, **งาน (task)**, **การดำเนินการถัดไป (next action)**, **อุปสรรค (blocker)** แบบสด
- **สาขา Git** + ตัวบ่งชี้สถานะการแก้ไข (dirty-state) สำหรับแต่ละโปรเจกต์
- **กรอง** ตามเฟส (ทั้งหมด / กำลังทำ / เสร็จสิ้น / ติดขัด / กำหนดเอง)
- **เรียงลำดับ** — อัจฉริยะ, ล่าสุด, เก่าสุด, A–Z, Z–A
- **ค้นหา** — ตัวกรองชื่อ/ราก + การค้นหาตั๋วเชิงลึก
- **ปักหมุด** โปรเจกต์ไว้ด้านบน, **ซ่อน** โปรเจกต์ที่ไม่เกี่ยวข้อง
- **เน้นการกะพริบ (Flash highlight)** — โปรเจกต์ที่มีการเปลี่ยนแปลงจะสว่างขึ้นและค่อยๆ จางลงใน 20 วินาที
- **สีความร้อน (Heat coloring)** — โปรเจกต์ที่ไม่เคลื่อนไหวจะเย็นลง โปรเจกต์ใหม่จะอุ่นขึ้น

</td>
<td width="50%">

### 🧩 ซับเอเจนต์ (Sub-Agents)
- **การแสดงผลแบบย่อหน้า** — `saiwiki`, `saihunt`, `saitranslate` ย่อหน้าอยู่ใต้โปรเจกต์หลัก
- **จำนวน Outbox** — แสดง ready/blocked/draft/reviewed ได้ทันที
- **รวบรวมในคลิกเดียว** — พับรวมรายการที่พร้อมเข้าสู่โปรเจกต์หลัก
- **คำเตือนไฟล์เก่า** — ตรวจจับไฟล์โปรโตคอลที่ล้าสมัย

- **Agent Engine** - เปิด `claude-code` (หรือเอนจินอื่น: codex, aider, gemini, cline, goose, agy, generic_cli) ในโปรเจกต์
  - **สถานะสด** - สถานะกำลังทำงาน/ออก, CPU, เวลาที่ใช้ต่อโปรเจกต์
  - **คอนโซลเอาต์พุต** - เอาต์พุตเอเจนต์แบบบัฟเฟอร์ (ค่าเริ่มต้น 5000 บรรทัด), อินพุต stdin
  - **Kill / stop all** - ฆ่ากระบวนการและหยุดทั้งหมด
  - **ป้องกันหลายอินสแตนซ์** - แอปหนึ่งอินสแตนซ์เท่านั้น; การเปิดครั้งที่สองแสดงหน้าต่างอีกครั้ง
### 🎮 การโต้ตอบ (Interaction)
- **ตัวดูไฟล์** — อ่านและแก้ไข STATE.md, BOARD.md, LOG.md
  - โหมดโค้ดต้นฉบับ (แก้ไขได้) + โหมดการอ่าน (แสดงผลแล้ว)
- **ตั๋วโต้ตอบได้** — ปุ่ม Start / Done อัปเดต BOARD.md แบบสด
- **การดำเนินการด่วน** — บริบทตามโปรเจกต์เช่น `npm run dev`, `cargo test` เป็นต้น
- **คำสั่งกำหนดเอง** — ปุ่มดำเนินการที่ผู้ใช้กำหนดเอง
- **ส่วนที่พับได้** — แยกตามโปรเจกต์ และบันทึกสถานะไว้
- **แถบข้างปรับขนาดได้** — ลากเพื่อปรับขนาด

### ⌨️ คีย์ลัดและหน้าต่าง (Hotkeys & Window)
- **แสดง/ซ่อน** — `Ctrl+Alt+X` (ตั้งค่าได้)
- **ติดมุม** - `Ctrl+Q` สลับ บน-ซ้าย → บน-ขวา → ล่าง-ซ้าย → ล่าง-ขวา
- **ย่อ/ขยาย (Zoom)** — `Ctrl+MouseWheel`, `Ctrl+`+`/`-`
- **ถาดระบบ (System tray)** — ย่อลงถาดระบบ, เริ่มต้นแบบซ่อน
- **อยู่บนสุดเสมอ (Always-on-top)** — สลับโหมด
- **เริ่มทำงานอัตโนมัติ** — เลือกเปิดเมื่อ Windows เริ่มทำงานได้
- **โหมดไร้กรอบ (Frameless mode)** — ซ่อนแถบชื่อเพื่อมุมมองที่มินิมอลขั้นสุด

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 เริ่มต้นใช้งานด่วน

<table>
<tr>
<th width="33%">🐍 รันจากโค้ดต้นฉบับ</th>
<th width="33%">📜 สคริปต์เปิดทำงาน</th>
<th width="33%">📦 ติดตั้ง (อนาคต)</th>
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

| สคริปต์ | พฤติกรรม |
|---|---|
| `run.vbs` | ซ่อน (ถาดเท่านั้น), เงียบ |
| `run.bat` | เปิดไปถาด; คอนโซลมองเห็นเฉพาะระหว่างตั้งค่า venv/ดีเพนเดนซีครั้งเดียว |
ทั้งคู่จะสร้าง `.venv` อัตโนมัติและติดตั้งไลบรารีที่จำเป็น

</td>
<td>

```bash
pip install saipenview
saipenview
```
เร็วๆ นี้ ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ การใช้งาน

| การดำเนินการ | วิธีการ |
|---|---|
| **แสดง / ซ่อน** | `Ctrl+Alt+X` หรือ `Alt+F15` (ตั้งค่าได้ทั้งคู่) |
| **ติดมุม** | `Ctrl+Q` - สลับ บน-ซ้าย → บน-ขวา → ล่าง-ซ้าย → ล่าง-ขวา |
| **ปุ่มบังคับปิด** | `Ctrl+Shift+Alt+Q` — บังคับปิดโปรเซสทันที |
| **ขยาย / ย่อ** | `Ctrl+MouseWheel` หรือ `Ctrl` + `+` / `-` |
| **รีเซ็ตการขยาย** | `Ctrl+0` |
| **สลับแถบเครื่องมือ** | `Alt+D` — พับ/ขยายแผงแถบเครื่องมือ |
| **ค้นหาโปรเจกต์** | พิมพ์ในช่องค้นหา; ติ๊ก `D` เพื่อค้นหาตั๋วเชิงลึก |
| **ตัวกรอง** | เมนูดรอปดาวน์: ทั้งหมด / กำลังทำ / เสร็จสิ้น / ติดขัด หรือคลิกแท็บเฟส |
| **เรียงลำดับ** | อัจฉริยะ / ล่าสุด / เก่าสุด / A–Z / Z–A |
| **สแกนใหม่** | คลิก `Rescan` หรือรอตัวนับเวลาในเบื้องหลัง (ค่าเริ่มต้น 300 วินาที) |
| **เรียกดูโฟลเดอร์** | คลิก `Browse` เพื่อเพิ่มโฟลเดอร์ในรายการสแกน |
| **การตั้งค่า** | ปุ่ม ⚙ สำหรับเปิดหน้าต่างการตั้งค่า |
| **มินิวิกิช่วยเหลือ** | ปุ่ม `?` เปิดมินิวิกิช่วยเหลือในตัว |
| **คลิกขวาที่โปรเจกต์** | คัดลอกพาธราก, กรองตามเฟส, เปิดโฟลเดอร์ |
| **ดับเบิลคลิกที่ส่วน** | เปิดไฟล์ที่เชื่อมโยง (STATE.md, BOARD.md, LOG.md) |
| **ลากหน้าต่าง** | ลากที่แถบชื่อ (หรือบริเวณใดก็ได้ในโหมดไร้กรอบ) |

### หน้าต่างม็อดดัล (Modals)

| หน้าต่างม็อดดัล | สิ่งที่ทำ |
|---|---|
| **การตั้งค่า** | การขยาย, คีย์ลัด, ปรับแต่งการสแกน, เริ่มทำงานอัตโนมัติ, อยู่บนสุดเสมอ, ฟอนต์, การสลับการกะพริบ, ค่าเริ่มต้นตัวดูไฟล์, คำสั่งกำหนดเอง, ภาษา, รากการสแกน |
| **ตัวดูไฟล์** | อ่านและแก้ไข STATE.md, BOARD.md, LOG.md — โหมดต้นฉบับ (raw) หรือโหมดการอ่าน (rendered) |
| **ช่วยเหลือ** | มินิวิกิครอบคลุมทุกฟีเจอร์ คีย์ลัด และคอนเซปต์ |
| **ยืนยัน** | กล่องโต้ตอบ DOM สไตล์วินเทจ (ทดแทน `confirm()` ดั้งเดิม) |

<br>

---

## 🧬 โปรโตคอล SAIPEN

SAIPENVIEW เป็นเครื่องมือคู่หูสำหรับโปรเจกต์ที่ใช้ **โปรโตคอล SAIPEN** — เฟรมเวิร์กสเตตแมชชีนที่ชี้นำเอเจนต์ AI ผ่านการทำงานในโปรเจกต์ตามเฟสที่กำหนด:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` ก็มีเช่นกัน - คำศัพท์ทั้งหมดและตารางเปลี่ยนสถานะอยู่ใน `saipenview/protocol.py` (`BLOCKED` เข้าถึงได้จากเกือบทุกเฟส)
แต่ละโปรเจกต์ SAIPEN จะจัดเก็บสถานะในไฟล์หลักสามไฟล์:

| ไฟล์ | วัตถุประสงค์ |
|---|---|
| `.saipen/STATE.md` | ส่วนหน้าข้อมูลที่เครื่องอ่านได้ — เฟส, งาน, การดำเนินการถัดไป, อุปสรรค |
| `.saipen/BOARD.md` | บอร์ดตั๋ว — ส่วน DOING / TODO / DONE / BLOCKED |
| `.saipen/LOG.md` | บันทึกเหตุการณ์ตามลำดับเวลา — ทุกคำสั่งและผลลัพธ์ |

**เอเจนต์ SubSaipen** (`saiwiki`, `saihunt`, `saitranslate`) จะอยู่ใน `.saipen/extensions/subs/` และสื่อสารกันผ่าน `kitchen/OUTBOX.md` — บัสส่งข้อความระหว่างเอเจนต์ในตัวโปรโตคอล โดย SAIPENVIEW จะค้นพบเอเจนต์ทั้งหมดและแสดงผลบนแดชบอร์ดเดียว

### การปฏิบัติตามข้อกำหนด (Conformance)

การแสดงสิ่งที่โปรเจกต์ *แจ้ง* เป็นเพียงแค่ครึ่งเดียว โปรเจกต์อาจดูสมบูรณ์แบบในรายการ — มีเฟส, งาน, การดำเนินการถัดไป — ในขณะที่เป็นสถานะที่โปรโตคอลปฏิเสธ และจนกว่าคุณจะรัน `tools/validate.py` ด้วยตนเอง คุณก็จะไม่สามารถแยกแยะความแตกต่างของทั้งสองอย่างนั้นได้

ทุกแถวจะมีตราคำตัดสิน (verdict badge) และแผงรายละเอียดจะระบุสิ่งที่ผิดปกติ:

| คำตัดสิน | ความหมาย |
|---|---|
| `OK` | ไม่พบข้อผิดพลาดในไฟล์ `.saipen/` ของโปรเจกต์เอง |
| `N WARNS` | ถูกต้องตามกฎ แต่เริ่มเบี่ยงเบน — จุดตรวจสอบเก่า, คำกริยา LOG ที่ไม่อยู่ในมาตรฐาน |
| `N FAILS` | สถานะที่โปรโตคอลปฏิเสธ: `WAIT:` ที่ไม่มีหมวดหมู่, ช่องติ๊กที่ไม่ตรงกับส่วนของมัน, `needs:` ที่ชี้ไปยังตั๋วที่ไม่มีอยู่จริง, ไฟล์ `STATE.md` แบบ UTF-16 ที่เครื่องมือ SAIPEN อื่นอ่านไม่ได้ |

ข้อตรวจพบแต่ละรายการจะระบุชื่อกฎ, ไฟล์และบรรทัด, รวมถึงข้อกำหนดที่เป็นที่มา เพื่อให้สามารถค้นหาตรวจสอบได้แทนที่จะเชื่อโดยไม่มีหลักฐาน

นี่คือ **ความเห็นที่สอง ไม่ใช่การทดแทน** `tools/validate.py` โดยมันจะตรวจสอบซ้ำเฉพาะสิ่งที่ไฟล์ของโปรเจกต์เองสามารถตัดสินได้ และประเมินกับสำเนาคลังคำศัพท์ของโปรโตคอล — ดังนี้เวอร์ชัน SAIPEN ที่อ่านมาจะถูกพิมพ์ไว้ใต้ทุกคำตัดสิน ตัวดูได้รับอนุญาตให้ล้าหลังโปรโตคอลได้ แต่ไม่อนุญาตให้ล้าหลังอย่างเงียบๆ

> 💡 *ชื่อ "SAIPENVIEW" บอกทุกอย่างในตัวเอง — มันให้ **มุมมอง (view)** เข้าสู่ทุกโปรเจกต์ **SAIPEN** บนเครื่องของคุณ*

<br>

---

## ⚙️ การกำหนดค่า

การกำหนดค่าสามารถพกพาได้ — จัดเก็บไว้ข้างๆ แอป ไม่ใช่ใน `%APPDATA%`:

```
saipenview/_data/config.json
```

ค่าเริ่มต้นหลัก (ย่อ - พจนานุกรม `DEFAULTS` เต็มอยู่ใน `saipenview/config.py`):

```json
{
  "hotkeys":          ["ctrl+alt+x", "alt+f15"],
  "snap_hotkey":      ["ctrl+q"],
  "zoom_level":       1.0,
  "font_family":      "Verdana_m1",
  "scan_roots":       null,
  "rescan_interval":  300,
  "scan_depth":       6,
  "scan_delay_ms":    10,
  "exclude_dirs":     [],
  "auto_scan":        true,
  "show_on_launch":   true,
  "always_on_top":    true,
  "frameless":        true,
  "flash_changes":    true,
  "locale":           "en",
  "default_engine":   "claude-code",
  "file_viewer_default": "source",
  "layout_swap":      false
}
```

ตั้งค่า `scan_roots: null` เพื่อตรวจจับไดรฟ์ทั้งหมดในเครื่องโดยอัตโนมัติ  
ตั้งค่าเป็นรายการพาธ (เช่น `["V:\\", "D:\\projects"]`) เพื่อจำกัดการสแกน  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` ขับเคลื่อน Agent Engine (ดูคุณสมบัติ)  
การตั้งค่าทั้งหมดสามารถกำหนดค่าผ่านหน้าต่าง **การตั้งค่า (Settings)** ในแอปได้เช่นกัน

<br>

---

## 🏗️ สถาปัตยกรรม

```
saipenview/
├── app.py              การเชื่อมต่อจุดเข้า - ถาด, ปุ่มลัด, หน้าต่าง, api, ป้องกันหลายอินสแตนซ์
├── api.py              บริดจ์ pywebview สำหรับ JS (89 เมธอดสาธารณะ)
├── scanner.py          การวนสแกนไดรฟ์ + ลูปสแกนซ้ำในเบื้องหลัง
├── parser.py           การแยกวิเคราะห์ STATE.md / BOARD.md / LOG.md
├── textio.py           ตัวอ่านหนึ่งเดียวสำหรับทุกไฟล์ .saipen/ — BOM, UTF-16, cp1251
├── protocol.py         คลังคำศัพท์ปิดของโปรโตคอล + BASELINE_VERSION
├── conformance.py      ประเมินโปรเจกต์เทียบกับคลังคำศัพท์เหล่านั้น
├── config.py           โหลด/บันทึกการตั้งค่า (การเขียนแบบ atomic)
├── tray.py             ไอคอนถาดระบบ pystray + เมนู
├── hotkey.py           การลงทะเบียนคีย์ลัดระดับโกลบอล (ไลบรารี keyboard)
├── autostart.py        การจัดการการเริ่มทำงานอัตโนมัติของ Windows Registry
├── zone_picker.py      โอเวอร์เลย์ติดมุม Ctrl+Q (tkinter)
├── events.py           บัสเหตุการณ์ภายในกระบวนการ (EventBus)
├── guard.py            ล็อกอินสแตนซ์เดียว + ส่งต่อคำขอแสดง
├── git_diff.py         diff / commit / revert ทรีทำงานสำหรับการกระทำของเอเจนต์
├── runtime.py          Agent Engine - ผู้จัดการกระบวนการของเอเจนต์ที่เปิดอยู่
├── watcher.py          ตัวเฝ้าดูไฟล์ Watchdog สำหรับไฟล์ .saipen/
├── engines/            Agent Engine - เอนจิน CLI ที่รองรับ (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       หน้าต่าง pywebview — แสดง/ซ่อน/สลับ/ยึดมุม
│   └── static/
│       ├── index.html
│       ├── style.css   ธีม Win95 สีทองเข้มสไตล์วินเทจ
│       └── app.js      ลอจิกฟรอนต์เอนด์ (~3300 บรรทัด)
├── assets/
│   └── tray_icon.png
├── screenshots/        ภาพหน้าจอ README
└── _data/              การกำหนดค่าเวลาทำงาน + แคช (ถูกละเว้นใน git)
```

### หลักการออกแบบ

- **โปรเซสเดียว** — ไม่มี IPC เบื้องหลัง, ไม่มีเซิร์ฟเวอร์แยก; โปรเซส Python เดียวโฮสต์ทั้งหน้าต่าง WebView2 และลูปการสแกนใน `ThreadPoolExecutor`
- **การเขียนแบบ Atomic** — ทุกการเขียนไฟล์ใช้ไฟล์ชั่วคราว + `os.replace`; การล่มของโปรแกรมจะไม่ทำให้ไฟล์คอนฟิกหรือแคชถูกตัดขาด
- **ปลอดภัยจากการอ่านข้อมูลเก่า** — การดึงข้อมูล UI ทุก 5 วินาทีจะเรียก `refresh_known()` (อ่านซ้ำเฉพาะไฟล์ `.saipen/` โดยไม่เดินสแกนไดเรกทอรี) การแก้ไข STATE.md จะแสดงผลในไม่กี่วินาทีโดยไม่ต้องสแกนไดรฟ์ใหม่ทั้งหมด
- **ไม่มี CSS transition** — เอฟเฟกต์ภาพทั้งหมด (การกะพริบ, ความร้อน, โฮเวอร์) คำนวณใหม่ด้วย `hexBlend` ผ่าน JavaScript ซึ่งปฏิบัติตามข้อจำกัดไร้แอนิเมชันของธีมวินเทจอย่างเคร่งครัด
- **ธีมวินเทจ** — พื้นผิวสีน้ำตาลเข้ม, ข้อความ/ไฮไลท์สีทอง, ขอบนูน 3 มิติ, ไม่มี anti-aliasing, ฟอนต์ Verdana_m1

<br>

---

## 🧪 การพัฒนา

```bash
# โคลนและเข้าไปยังโฟลเดอร์
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# สร้าง venv และติดตั้ง
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# รันโปรแกรม
python -m saipenview
```

สำหรับรายละเอียดการตั้งค่า ข้อตกลงในการเขียนโค้ด และขั้นตอนการส่ง PR ดูได้ที่ [CONTRIBUTING.md](../../CONTRIBUTING.md)

### ความต้องการของระบบ

- **Windows 10 / 11** — WebView2 runtime (ติดตั้งมาล่วงหน้าใน Win11, ติดตั้งอัตโนมัติใน Win10)
- **Python 3.10+**
- ไลบรารีที่ต้องใช้: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 ใบอนุญาต

MIT — ดูที่ [LICENSE](../../LICENSE)

<br>

---

<div align="center">
  <sub>สร้างด้วย 🐍 Python • 🖼️ pywebview • 🎨 ความสวยงามสไตล์ Vintage Win95</sub>

<br>

---

## 📸 ภาพหน้าจอเพิ่มเติม

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="SAIPENVIEW Detail Pane" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>แผงรายละเอียดพร้อมตั๋ว, ซับเอเจนต์ และตัวดูไฟล์</em>
</p>

<br>

</div>
