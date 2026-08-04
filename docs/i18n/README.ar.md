<div align="right">
  🌍 <a href="../../README.md">EN</a> | <strong>AR</strong> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>عارض صينية سطح المكتب لكل مشروع SAIPEN على جهازك</strong>
    <br>
    يكتشف تلقائياً مشاريع <code>.saipen/</code> عبر الأقراص المحلية — المرحلة الحية، المهمة، المانع، حالة git، التذاكر، والوكلاء الفرعيين.
    <br>
    لوحة تحكم واحدة بنمط Win95 كلاسيكي باللون الذهبي الداكن.
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

## 🚀 الميزات

<table>
<tr>
<td width="50%">

### 🔍 الاكتشاف
- **فحص تلقائي** للأقراص المحلية عن مشاريع `.saipen/`
- **جذور مخصصة** — اختر مجلدات أو أقراص كاملة
- **استثناءات ذكية** — `node_modules`، `.git`، ومجلدات النظام
- **إعادة فحص في الخلفية** — فاصل زمني قابل للضبط (الافتراضي 300 ثانية)
- **أشجار عمل مرتبطة (Worktrees)** — يكتشف أشجار عمل git لإعداد سهل

### 📊 لوحة التحكم
- **المرحلة** الحية، **المهمة**، **الإجراء التالي**، و**المانع**
- **فرع Git** + مؤشر التغييرات لكل مشروع
- **تصفية** حسب المرحلة (الكل / نشط / مكتمل / عالق / مخصص)
- **فرز** — ذكي، الأحدث، الأقدم، من أ إلى ي، من ي إلى أ
- **بحث** — تصفية بالاسم/القدم + بحث عميق في التذاكر
- **تثبيت** المشاريع في الأعلى، **إخفاء** المشاريع غير المهمة
- **تألق وميضي** — المشاريع المتغيرة تتوهج وتتلاشى خلال 20 ثانية
- **تلوين حراري** — المشاريع القديمة تبرد والمشاريع الحديثة تدمج بدفء

</td>
<td width="50%">

### 🧩 الوكلاء الفرعيون
- **عرض متداخل** — إزاحة `saiwiki`، `saihunt`، و`saitranslate` تحت المشروع الرئيسي
- **عدادات الصندوق الصادر** — جاهز/معطل/مسودة/تمت مراجعته بلمحة سريعة
- **تجميع بنقرة واحدة** — دمج المدخلات الجاهزة في المشروع الرئيسي
- **تحذير القدم** — اكتشاف ملفات البروتوكول غير المحدثة

- **محرك الوكيل** - تشغيل `claude-code` (أو محركات أخرى: codex, aider, gemini, cline, goose, agy, generic_cli) في مشروع
  - **الحالة الحية** - حالة التشغيل/الخروج، المعالج، الوقت المنقضي لكل مشروع
  - **وحدة الإخراج** - إخراج الوكيل المخزن (افتراضيًا 5000 سطر)، إدخال إلى stdin
  - **Kill / stop all** - قتل عملية المشروع وإيقاف شامل
  - **حماية النسخة الواحدة** - نسخة واحدة فقط من التطبيق؛ التشغيل الثاني يعيد إظهار النافذة
### 🎮 التفاعل
- **عارض الملفات** — قراءة وتعديل STATE.md، BOARD.md، LOG.md
  - وضع المصدر (قابل للتعديل) + وضع القارئ (منسق)
- **تذاكر تفاعلية** — أزرار البدء / الإنجاز تحدّث BOARD.md مباشرة
- **إجراءات سريعة** — سياقية مثل `npm run dev`، `cargo test`، إلخ.
- **أوامر مخصصة** — أزرار إجراءات يحددها المستخدم
- **أقسام قابلة للطي** — لكل مشروع، ومحفوظة
- **شريط جانبي قابل لتغيير الحجم** — السحب لتغيير الحجم

### ⌨️ اختصارات المفاتيح والنوافذ
- **إظهار/إخفاء** — `Ctrl+Alt+X` (قابل للضبط)
- **التصاق الزوايا** - `Alt+F14` يتنقل TL ← TR ← BL ← BR
- **التكبير/التصغير** — `Ctrl+عجلة الماوس`، `Ctrl+`+`/`-`
- **صينية النظام** — التصغير إلى الصينية، البدء مخفياً
- **دائماً في الأعلى** تبديل
- **تشغيل تلقائي** — بدء التشغيل مع Windows اختيارياً
- **وضع بدون إطار** — إخفاء شريط العنوان لعرض أدنى وبسيط

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 البدء السريع

<table>
<tr>
<th width="33%">🐍 التشغيل من المصدر</th>
<th width="33%">📜 سكريبتات التشغيل</th>
<th width="33%">📦 التثبيت (مستقبلاً)</th>
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

| السكريبت | السلوك |
|---|---|
| `run.vbs` | مخفي (العلبة فقط)، صامت |
| `run.bat` | تشغيل إلى العلبة؛ الطرفية مرئية فقط عند إعداد venv/التبعيات لمرة واحدة |
كلاهما ينشئ `.venv` تلقائياً ويثبت التبعيات.

</td>
<td>

```bash
pip install saipenview
saipenview
```
قريباً ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ الاستخدام

| الإجراء | كيفية الاستخدام |
|---|---|
| **إظهار / إخفاء** | `Ctrl+Alt+X` أو `Alt+F15` (كلاهما قابل للضبط) |
| **التصاق الزاوية** | `Alt+F14` - يتنقل أعلى-يسار ← أعلى-يمين ← أسفل-يسار ← أسفل-يمين |
| **مفتاح الإنهاء** | `Ctrl+Shift+Alt+Q` — إغلاق إجباري للعملية |
| **تكبير / تصغير** | `Ctrl+عجلة الماوس` أو `Ctrl` + `+` / `-` |
| **إعادة ضبط التكبير** | `Ctrl+0` |
| **تبديل شريط الأدوات** | `Alt+D` — طي/توسيع لوحة شريط الأدوات |
| **البحث في المشاريع** | الكتابة في صندوق البحث؛ تحديد `D` للبحث العميق في التذاكر |
| **التصفية** | القائمة المنسدلة: الكل / نشط / مكتمل / عالق، أو النقر على شارة المرحلة |
| **الفرز** | ذكي / الأحدث / الأقدم / من أ إلى ي / من ي إلى أ |
| **إعادة الفحص** | انقر `إعادة الفحص` أو انتظر مؤقت الخلفية (الافتراضي 300 ثانية) |
| **تصفح المجلدات** | انقر `تصفح` لإضافة مجلد إلى مجموعة الفحص |
| **الإعدادات** | زر ⚙ يفتح نافذة الإعدادات |
| **موسوعة المساعدة** | زر `?` يفتح الويكي المصغر المدمج |
| **النقر بالأزرار الأيمن للمشروع** | نسخ مسار الجذر، التصفية حسب المرحلة، فتح المجلد |
| **النقر المزدوج على القسم** | يفتح الملف المرتبط (STATE.md، BOARD.md، LOG.md) |
| **سحب النافذة** | سحب شريط العنوان (أو أي مكان في الوضع بدون إطار) |

### النوافذ المنبثقة

| النافذة | ماذا تفعل |
|---|---|
| **الإعدادات** | التكبير، الاختصارات، ضبط الفحص، التشغيل التلقائي، دائماً في الأعلى، الخط، تبديل الوميض، الوضع الافتراضي لعارض الملفات، الأوامر المخصصة، اللغة، جذور الفحص |
| **عارض الملفات** | قراءة وتعديل STATE.md، BOARD.md، LOG.md — وضع المصدر (خام) أو القارئ (منسق) |
| **المساعدة** | ويكي مصغر شامل يغطي كل ميزة واختصار ومفهوم |
| **التأكيد** | حوار DOM بنمط كلاسيكي (يستبدل `confirm()` الخاص بالمتصفح) |

<br>

---

## 🧬 بروتوكول SAIPEN

يعتبر SAIPENVIEW مكملًا للمشاريع التي تستخدم **بروتوكول SAIPEN** — وهو إطار عمل يعتمد على آلة الحالة (state-machine) لنوجه وكلاء الذكاء الاصطناعي خلال عمل المشروع في مراحل محدودة:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`، `MARKHUNT`، `TRANSLATE`، `PREPARE` موجودة أيضًا - القاموس الكامل وجدول الانتقالات في `saipenview/protocol.py` (و`BLOCKED` يمكن الوصول إليه من معظم المراحل).
يحفظ كل مشروع SAIPEN حالته في ثلاثة ملفات أساسية:

| الملف | الغرض |
|---|---|
| `.saipen/STATE.md` | ترويسة قابلة للقراءة آلياً — المرحلة، المهمة، الإجراء التالي، المانع |
| `.saipen/BOARD.md` | لوحة التذاكر — أقسام: قيد التنفيذ / للمتابعة / مكتمل / معطل |
| `.saipen/LOG.md` | سجل الأحداث الزمني — كل أمر ونتيجته |

تعيش **وكلاء SubSaipen** (`saiwiki`، `saihunt`، `saitranslate`) في المجلد `.saipen/extensions/subs/` وتتواصل عبر `kitchen/OUTBOX.md` — ناقل الرسائل بين الوكلاء المدمج في البروتوكول. يكتشف SAIPENVIEW جميع هذه الوكلاء ويعرض لوحة تحكم موحدة.

### المطابقة (Conformance)

عرض ما *يقوله* المشروع ليس إلا نصف الحقيقة. قد يبدو المشروع مثالياً في القائمة — مرحلة، مهمة، إجراء تالٍ — بينما ينطوي على حالة يرفضها البروتوكول، وحتى تقوم بتشغيل `tools/validate.py` يدوياً لم تكن هناك طريقة للتمييز بينهما.

تحمل كل صف شارة تقييم، وتعرض لوحة التفاصيل الأخطاء الموجودة:

| التقييم | المعنى |
|---|---|
| `OK` | لم يتم العثور على أخطاء في ملفات `.saipen/` الخاصة بالمشروع |
| `N WARNS` | مقبولة ولكن هناك انحراف — نقطة تحقق قديمة، فعل غير قياسي في LOG |
| `N FAILS` | حالة يرفضها البروتوكول: `WAIT:` بدون فئة، مربع اختيار يتعارض مع قسمه، `needs:` يشير إلى تذكرة غير موجودة، أو ملف `STATE.md` بتنسيق UTF-16 لا يمكن لأداة SAIPEN أخرى قراءته |

يسمي كل اكتشاف القاعدة، والملف والسطر، والبند الذي ينتمي إليه، بحيث يمكن البحث عنه بدلاً من التسليم به.

هذا **رأي ثانٍ وليس بديلاً** لـ `tools/validate.py`. فهو يعيد فحص ما يمكن لملفات المشروع تحديدها فقط، ويقيم مقابل نسخة من مصطلحات البروتوكول — لذلك يطبع إصدار SAIPEN المنقول منه تحت كل تقييم. يُسمح للعارض بالتأخر عن البروتوكول، لكن لا يُسمح له بالتأخر بصمت.

> 💡 *اسم "SAIPENVIEW" يشرح نفسه — فهو يقدم **عرضاً (view)** لكل مشروع **SAIPEN** على جهازك.*

<br>

---

## ⚙️ الإعدادات

التكوين محمول — يُحفظ بجوار التطبيق وليس في `%APPDATA%`:

```
saipenview/_data/config.json
```

القيم الافتراضية الرئيسية (مختصر - القاموس الكامل `DEFAULTS` في `saipenview/config.py`):

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

ضع `scan_roots: null` للاكتشاف التلقائي لجميع الأقراص المحلية.  
ضع قائمة بالمسارات (مثل `["V:\\", "D:\\projects"]`) للحد من الفحص.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` تتحكم في محرك الوكيل (انظر الميزات).  
جميع الإعدادات قابلة للتعديل أيضاً من خلال نافذة **الإعدادات** في التطبيق.

<br>

---

## 🏗️ البنية الهيكلية

```
saipenview/
├── app.py              مدخل التوصيل - العلبة، المفتاح الساخن، النافذة، api، حماية النسخة الواحدة
├── api.py              جسر pywebview لواجهة JS (66 طريقة عامة)
├── scanner.py          مسح الأقراص + حلقة إعادة الفحص في الخلفية
├── parser.py           تحليل ملفات STATE.md / BOARD.md / LOG.md
├── textio.py           قارئ واحد لكل ملف .saipen/ — BOM, UTF-16, cp1251
├── protocol.py         مصطلحات البروتوكول المغلقة + BASELINE_VERSION
├── conformance.py      تقييم المشروع مقابل تلك المصطلحات
├── config.py           تحميل/حفظ الإعدادات (كتابة ذرية)
├── tray.py             أيقونة صينية النظام والقائمة بـ pystray
├── hotkey.py           تسجيل الاختصارات العالمية (مكتبة keyboard)
├── autostart.py        إدارة التشغيل التلقائي في سجل Windows
├── zone_picker.py      تراكب التصاق الزاوية Alt+F14 (tkinter)
├── events.py           ناقل أحداث داخل العملية (EventBus)
├── guard.py            قفل النسخة الواحدة + تسليم طلب الإظهار
├── git_diff.py         فرق/تثبيت/تراجع شجرة العمل لإجراءات الوكيل
├── runtime.py          محرك الوكيل - مدير عمليات الوكلاء المشغلين
├── watcher.py          مراقب ملفات Watchdog لملفات .saipen/
├── engines/            محرك الوكيل - محركات CLI المدعومة (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       نافذة pywebview — إظهار/إخفاء/تبديل/محاذاة
│   └── static/
│       ├── index.html
│       ├── style.css   نسق Win95 الكلاسيكي باللون الذهبي الداكن
│       └── app.js      منطق الواجهة الأمامية (~3300 سطر)
├── assets/
│   └── tray_icon.png
├── screenshots/        لقطات شاشة README
└── _data/              تكوين وقت التشغيل + التخزين المؤقت (مستبعد في git)
```

### مبادئ التصميم

- **عملية واحدة** — لا يوجد IPC في الخلفية ولا خادم منفصل؛ عملية Python واحدة تستضيف نافذة WebView2 وحلقة الفحص في `ThreadPoolExecutor`
- **كتابة ذرية** — كل كتابة ملف تستخدم ملفاً مؤقتاً + `os.replace`؛ الانهيار لن يؤدي أبداً إلى اقتطاع التكوين أو التخزين المؤقت
- **آمن من القراءة القديمة** — استطلاع الواجهة كل 5 ثوانٍ يستدعي `refresh_known()` (يعيد قراءة ملفات `.saipen/` فقط، دون مسح المجلدات). تظهر التعديلات على STATE.md خلال ثوانٍ دون إطلاق فحص كامل للقرص
- **بدون انتقالات CSS** — جميع المؤثرات البصرية (الوميض، الحرارة، التحويم) هي إعادة حسابات `hexBlend` مدفوعة بـ JavaScript، مع الالتزام الصارم بقيد عدم وجود رسوم متحركة للنسق الكلاسيكي
- **نسق كلاسيكي** — أسطح بنية داكنة، نصوص/لمسات ذهبية، حواف 3D بارزة، بدون تنعيم حواف، وخط Verdana_m1

<br>

---

## 🧪 التطوير

```bash
# النسخ والانتقال
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# إنشاء البيئة الافتراضية والتثبيت
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# التشغيل
python -m saipenview
```

للحصول على تفاصيل الإعداد، وإرشادات البرمجة، وسير عمل طلبات السحب (PR)، انظر [CONTRIBUTING.md](../../CONTRIBUTING.md).

### المتطلبات

- **Windows 10 / 11** — بيئة تشغيل WebView2 (مثبتة مسبقاً على Win11، وتثبت تلقائياً على Win10)
- **Python 3.10+**
- التبعيات: `pystray`، `keyboard`، `pywebview`، `Pillow`، `watchdog`، `psutil`

<br>

---

## 📄 الترخيص

MIT — انظر [LICENSE](../../LICENSE).

<br>

---

<div align="center">
  <sub>تم التطوير باستخدام 🐍 Python • 🖼️ pywebview • 🎨 نسق Win95 الكلاسيكي</sub>

<br>

---

## 📸 المزيد من لقطات الشاشة

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="SAIPENVIEW Detail Pane" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>لوحة التفاصيل مع التذاكر، الوكلاء الفرعيين، وعارض الملفات.</em>
</p>

<br>

</div>
