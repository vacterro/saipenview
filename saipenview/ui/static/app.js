window.agentTestState = {};
const POLL_MS = 5000;
let currentFilter = "ALL";
let searchQuery = "";
let selectedRoot = null;
let rawProjects = [];
let isScanned = false;
let deepSearchMode = false;
let deepSearchTimer = null;
let searchItems = [];
let searchItemIndex = -1;
let showHidden = false;
let currentSort = "smart";
let collapsedConfig = {};
let currentDetailRoot = null;
let stateEditActive = false;
let agentSinceLineNum = {};
let availableEnginesCache = [];
// Which engine the launcher opens on. Loaded from config.default_engine and
// re-saved whenever the user launches with a different one, so the choice
// survives a restart instead of resetting to registry order every time.
let defaultEngine = "claude-code";
let agentStatusCache = {};
let currentAgentPanelRoot = null;
// detail pane via innerHTML, which destroyed the open edit form (and anything
// typed into it) within seconds -- that was T-066's "Edit does nothing" AND
// "form collapses itself". Live refresh pauses for this pane while it's true.

// Flash highlight: snapshot-based change detection, hexBlend decay over ~20s
let flashChangesEnabled = true;
const FLASH_DECAY_SECONDS = 20;
const FLASH_HOT = "#5a4a2a";   // muted gold flash
const FLASH_COLD = "transparent";
let prevSnapshot = {};    // {root: {phase, task, updated, git_dirty}}
let flashState = {};      // {root: flashTime} epoch ms when change was detected

// Hover transition: hexBlend fade for project rows (no CSS transitions allowed)

// ===== i18n runtime =====
let currentLocale = "en";

// Locale string tables — loaded from locale-*.js, fallback to LOCALE_EN
const _localeTables = {
  en: typeof LOCALE_EN !== "undefined" ? LOCALE_EN : {},
  ar: typeof LOCALE_AR !== "undefined" ? LOCALE_AR : {},
  bg: typeof LOCALE_BG !== "undefined" ? LOCALE_BG : {},
  cs: typeof LOCALE_CS !== "undefined" ? LOCALE_CS : {},
  da: typeof LOCALE_DA !== "undefined" ? LOCALE_DA : {},
  de: typeof LOCALE_DE !== "undefined" ? LOCALE_DE : {},
  ded: typeof LOCALE_DED !== "undefined" ? LOCALE_DED : {},
  el: typeof LOCALE_EL !== "undefined" ? LOCALE_EL : {},
  es: typeof LOCALE_ES !== "undefined" ? LOCALE_ES : {},
  et: typeof LOCALE_ET !== "undefined" ? LOCALE_ET : {},
  fi: typeof LOCALE_FI !== "undefined" ? LOCALE_FI : {},
  fr: typeof LOCALE_FR !== "undefined" ? LOCALE_FR : {},
  he: typeof LOCALE_HE !== "undefined" ? LOCALE_HE : {},
  hi: typeof LOCALE_HI !== "undefined" ? LOCALE_HI : {},
  hr: typeof LOCALE_HR !== "undefined" ? LOCALE_HR : {},
  hu: typeof LOCALE_HU !== "undefined" ? LOCALE_HU : {},
  id: typeof LOCALE_ID !== "undefined" ? LOCALE_ID : {},
  it: typeof LOCALE_IT !== "undefined" ? LOCALE_IT : {},
  ja: typeof LOCALE_JA !== "undefined" ? LOCALE_JA : {},
  ko: typeof LOCALE_KO !== "undefined" ? LOCALE_KO : {},
  nl: typeof LOCALE_NL !== "undefined" ? LOCALE_NL : {},
  no: typeof LOCALE_NO !== "undefined" ? LOCALE_NO : {},
  pl: typeof LOCALE_PL !== "undefined" ? LOCALE_PL : {},
  pt: typeof LOCALE_PT !== "undefined" ? LOCALE_PT : {},
  ro: typeof LOCALE_RO !== "undefined" ? LOCALE_RO : {},
  ru: typeof LOCALE_RU !== "undefined" ? LOCALE_RU : {},
  sk: typeof LOCALE_SK !== "undefined" ? LOCALE_SK : {},
  sv: typeof LOCALE_SV !== "undefined" ? LOCALE_SV : {},
  th: typeof LOCALE_TH !== "undefined" ? LOCALE_TH : {},
  tr: typeof LOCALE_TR !== "undefined" ? LOCALE_TR : {},
  uk: typeof LOCALE_UK !== "undefined" ? LOCALE_UK : {},
  vi: typeof LOCALE_VI !== "undefined" ? LOCALE_VI : {},
  zh: typeof LOCALE_ZH !== "undefined" ? LOCALE_ZH : {},
  "zh-CN": typeof LOCALE_ZH_CN !== "undefined" ? LOCALE_ZH_CN : {},
};

function t(key, vars) {
  // Look up key in current locale; fallback to English, then raw key.
  const table = _localeTables[currentLocale] || {};
  let val = table[key];
  if (val === undefined) {
    val = _localeTables["en"][key];
  }
  if (val === undefined) return key;
  // Replace ${var} placeholders
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      val = val.replace("${" + k + "}", String(v));
    }
  }
  return val;
}

function hydrateDOM(locale) {
  currentLocale = locale || currentLocale;
  // Walk all elements with data-i18n attribute (textContent)
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    const translated = t(key);
    // Only replace if the translation is different from the key and non-empty
    if (translated !== key && translated) {
      // NEVER use textContent on an element that has element children --
      // it deletes them. 11 Settings <label>s wrap their own control
      // (setZoomLevel, setFontFamily, setHotkeys, setSnapHotkey,
      // setScanDepth, setScanDelay, setRescanInterval, setFileViewerDefault,
      // setLocale, customCommands*, drivesBar), so a blanket textContent
      // assignment wiped the entire settings form the moment i18n ran --
      // which is why Settings "didn't work" and the drives list vanished.
      if (el.children.length === 0) {
        el.textContent = translated;
      } else {
        // Replace only this element's OWN leading text, leave children alone.
        const ownText = Array.from(el.childNodes).find(
          (n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim()
        );
        if (ownText) {
          ownText.textContent = translated;
        } else {
          el.insertBefore(document.createTextNode(translated), el.firstChild);
        }
      }
    }
  });
  // Walk all elements with data-i18n-title attribute
  document.querySelectorAll("[data-i18n-title]").forEach(el => {
    const key = el.getAttribute("data-i18n-title");
    const translated = t(key);
    if (translated !== key && translated) {
      el.setAttribute("title", translated);
    }
  });
  // Walk all elements with data-i18n-placeholder attribute
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.getAttribute("data-i18n-placeholder");
    const translated = t(key);
    if (translated !== key && translated) {
      el.setAttribute("placeholder", translated);
    }
  });
  // Walk all elements with data-i18n-value attribute (button textContent)
  document.querySelectorAll("[data-i18n-value]").forEach(el => {
    const key = el.getAttribute("data-i18n-value");
    const translated = t(key);
    if (translated !== key && translated) {
      el.textContent = translated;
    }
  });
  // Translate sort select options
  document.querySelectorAll("#sortSelect option[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    const translated = t(key);
    if (translated !== key && translated) el.textContent = translated;
  });
  // Translate filter select options
  document.querySelectorAll("#filterSelect option[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    const translated = t(key);
    if (translated !== key && translated) el.textContent = translated;
  });
}
// ===== end i18n =====

function persistCollapseState() {
  if (!currentDetailRoot) return;
  const s = {};
  document.querySelectorAll('.collapsible[data-section]').forEach(el => {
    s[el.getAttribute('data-section')] = el.classList.contains('collapsed');
  });
  collapsedConfig = Object.assign({}, collapsedConfig, { [currentDetailRoot]: s });
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.save_view_config({ collapsed_sections: collapsedConfig });
  }
}

// --- Toast notification system ---
function showToast(message, type, duration) {
  type = type || 'info';
  duration = duration || 4000;
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast raised toast-' + type;
  toast.innerHTML = '<span>' + escapeHtml(message) + '</span><button class="toast-close" onclick="this.parentElement.remove()">✕</button>';
  container.appendChild(toast);
  setTimeout(() => {
    if (toast.parentElement) toast.remove();
  }, duration);
}

// --- DOM-based confirm dialog (replaces native confirm()) ---
let _confirmResolve = null;

function showConfirm(message, onOk, onCancel) {
  const overlay = document.getElementById('confirmOverlay');
  const msgEl = document.getElementById('confirmMessage');
  const okBtn = document.getElementById('confirmOkBtn');
  const cancelBtn = document.getElementById('confirmCancelBtn');
  if (!overlay || !msgEl || !okBtn || !cancelBtn) {
    // Fallback: if DOM elements don't exist, use native confirm
    if (confirm(message) && onOk) onOk();
    else if (onCancel) onCancel();
    return;
  }
  msgEl.textContent = message;
  overlay.style.display = 'flex';

  function cleanup() {
    overlay.style.display = 'none';
    okBtn.removeEventListener('click', onOkHandler);
    cancelBtn.removeEventListener('click', onCancelHandler);
    overlay.removeEventListener('mousedown', clickOutside);
  }

  function onOkHandler() {
    cleanup();
    if (onOk) onOk();
  }
  function onCancelHandler() {
    cleanup();
    if (onCancel) onCancel();
  }

  okBtn.addEventListener('click', onOkHandler);
  cancelBtn.addEventListener('click', onCancelHandler);

  // Click outside closes (on overlay itself)
  overlay.addEventListener('mousedown', function clickOutside(e) {
    if (e.target === overlay) {
      cleanup();
      overlay.removeEventListener('mousedown', clickOutside);
      if (onCancel) onCancel();
    }
  });
}

// --- Right-click context menu ---
let _contextMenuActive = null;
let _contextMenuKeyHandler = null;

function showContextMenu(e, root, phase) {
  // Remove any existing context menu first
  hideContextMenu();

  const menu = document.createElement("div");
  menu.className = "context-menu raised";
  menu.innerHTML =
    `<div class="context-menu-item" data-action="show-phase">${t("context.showPhase", { phase: escapeHtml(phase) })}</div>` +
    `<div class="context-menu-item" data-action="copy-root">${t("context.copyRoot")}</div>` +
    `<div class="context-menu-sep"></div>` +
    `<div class="context-menu-item" data-action="open-folder">${t("context.openFolder")}</div>`;

  // Position: clamp to viewport
  const mx = Math.min(e.clientX, window.innerWidth - 200);
  const my = Math.min(e.clientY, window.innerHeight - 120);
  menu.style.left = Math.max(0, mx) + "px";
  menu.style.top = Math.max(0, my) + "px";

  document.body.appendChild(menu);
  _contextMenuActive = menu;

  // Handle item clicks
  menu.addEventListener("click", (ce) => {
    const item = ce.target.closest(".context-menu-item");
    if (!item) return;
    const action = item.getAttribute("data-action");
    hideContextMenu();
    if (action === "show-phase" && phase) {
      showPhaseOverlay(phase);
    } else if (action === "copy-root" && root) {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.clipboard_copy) {
        window.pywebview.api.clipboard_copy(root).catch((e) => console.error("clipboard_copy(root) failed:", e));
      } else {
        navigator.clipboard.writeText(root).catch((e) => console.error("clipboard writeText(root) failed:", e));
      }
      showToast("Copied: " + root, "info", 2000);
    } else if (action === "open-folder" && root) {
      window.pywebview.api.open_folder(root);
    }
  });

  // Close on Escape
  _contextMenuKeyHandler = (ke) => {
    if (ke.key === "Escape") {
      hideContextMenu();
    }
  };
  document.addEventListener("keydown", _contextMenuKeyHandler);

  // Close on click outside (delayed to not immediately close on the right-click itself)
  setTimeout(() => {
    document.addEventListener("click", hideContextMenu, { once: true });
  }, 0);
}

function hideContextMenu() {
  if (_contextMenuKeyHandler) {
    document.removeEventListener("keydown", _contextMenuKeyHandler);
    _contextMenuKeyHandler = null;
  }
  if (_contextMenuActive) {
    _contextMenuActive.remove();
    _contextMenuActive = null;
  }
}

// --- Right-click context menu for detail pane section headers ---
function _sectionFileFor(section) {
  if (section === "state-summary") return "STATE.md";
  if (section && section.startsWith("tickets-")) return "BOARD.md";
  if (section === "sub-agents") return "MANIFEST.md";
  if (section === "log") return "LOG.md";
  return null;
}

function _sectionFilePath(root, section) {
  const fn = _sectionFileFor(section);
  if (!fn) return null;
  if (section === "sub-agents") return root + "\\.saipen\\extensions\\subs\\" + fn;
  return root + "\\.saipen\\" + fn;
}

function showSectionContextMenu(e, root, section) {
  hideContextMenu();

  const fileName = _sectionFileFor(section);
  const filePath = _sectionFilePath(root, section);

  const menu = document.createElement("div");
  menu.className = "context-menu raised";
  let items = [];
  if (fileName && filePath) {
    items.push(`<div class="context-menu-item" data-action="open-section-file" data-path="${escapeHtml(filePath)}" data-filename="${escapeHtml(fileName)}">${t("sectionContext.openFile", { file: escapeHtml(fileName) })}</div>`);
    items.push(`<div class="context-menu-item" data-action="copy-section-path" data-path="${escapeHtml(filePath)}">${t("sectionContext.copyPath")}</div>`);
    items.push(`<div class="context-menu-sep"></div>`);
  }
  items.push(`<div class="context-menu-item" data-action="open-project-folder" data-root="${escapeHtml(root)}">${t("sectionContext.openProject")}</div>`);
  menu.innerHTML = items.join("");

  const mx = Math.min(e.clientX, window.innerWidth - 200);
  const my = Math.min(e.clientY, window.innerHeight - 120);
  menu.style.left = Math.max(0, mx) + "px";
  menu.style.top = Math.max(0, my) + "px";

  document.body.appendChild(menu);
  _contextMenuActive = menu;

  menu.addEventListener("click", (ce) => {
    const item = ce.target.closest(".context-menu-item");
    if (!item) return;
    const action = item.getAttribute("data-action");
    hideContextMenu();
    if (action === "open-section-file") {
      const path = item.getAttribute("data-path");
      const fn = item.getAttribute("data-filename");
      window.pywebview.api.read_file_text(path).then((text) => {
        if (text !== null) openFileViewer(fn, path, text);
        else showToast("Can't read " + fn, "error", 2000);
      });
    } else if (action === "copy-section-path") {
      const path = item.getAttribute("data-path");
      if (window.pywebview && window.pywebview.api && window.pywebview.api.clipboard_copy) {
        window.pywebview.api.clipboard_copy(path).catch((e) => console.error("clipboard_copy(path) failed:", e));
      } else {
        navigator.clipboard.writeText(path).catch((e) => console.error("clipboard writeText(path) failed:", e));
      }
      showToast("Copied path", "info", 2000);
    } else if (action === "open-project-folder") {
      const r = item.getAttribute("data-root");
      if (r) window.pywebview.api.open_folder(r);
    }
  });

  _contextMenuKeyHandler = (ke) => {
    if (ke.key === "Escape") hideContextMenu();
  };
  document.addEventListener("keydown", _contextMenuKeyHandler);
  setTimeout(() => {
    document.addEventListener("click", hideContextMenu, { once: true });
  }, 0);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function highlightMatch(text, query) {
  // Escapes text, then wraps the first case-insensitive match of query
  // in a <span class="search-highlight"> for visual emphasis.
  const escaped = escapeHtml(text);
  if (!query) return escaped;
  const lower = escaped.toLowerCase();
  const q = query.toLowerCase();
  const idx = lower.indexOf(q);
  if (idx === -1) return escaped;
  const before = escaped.slice(0, idx);
  const match = escaped.slice(idx, idx + q.length);
  const after = escaped.slice(idx + q.length);
  return before + '<span class="search-highlight">' + match + '</span>' + after;
}

// --- Floating search overlay ---
const PHASE_DESCRIPTIONS = {
  INIT: "phase.INIT",
  PLAN: "phase.PLAN",
  SCOUT: "phase.SCOUT",
  BUILD: "phase.BUILD",
  REVIEW: "phase.REVIEW",
  HUNT: "phase.HUNT",
  ADD: "phase.ADD",
  CLEAN: "phase.CLEAN",
  TRANSLATE: "phase.TRANSLATE",
  VALIDATE: "phase.VALIDATE",
  BLOCKED: "phase.BLOCKED",
  DONE: "phase.DONE",
  VERIFY: "phase.VERIFY",
  SHIP: "phase.SHIP"
};

const SEARCH_PAGE_SIZE = 5;

function showSearchOverlay() {
  const overlay = document.getElementById("searchOverlay");
  if (overlay) overlay.style.display = "block";
}

function hideSearchOverlay() {
  const overlay = document.getElementById("searchOverlay");
  if (overlay) overlay.style.display = "none";
  searchItems = [];
  searchItemIndex = -1;
  const countEl = document.getElementById("searchOverlayCount");
  if (countEl) countEl.textContent = "";
  const cycleEl = document.getElementById("searchOverlayCycle");
  if (cycleEl) cycleEl.textContent = "";
  // Reset overlay title back to default
  const titleEl = document.querySelector(".search-overlay-title");
  if (titleEl) titleEl.textContent = "Search Results";
  // Remove phase-overlay filter button if present
  const oldFilterBtn = document.querySelector(".overlay-filter-btn");
  if (oldFilterBtn) oldFilterBtn.remove();
  // Restore normal sidebar view
  render(rawProjects, isScanned);
}

function cycleSearchResult(direction) {
  if (!searchItems.length) return;
  // Remove active class from current item
  if (searchItemIndex >= 0 && searchItems[searchItemIndex]) {
    searchItems[searchItemIndex].classList.remove("search-item-active");
  }
  // Calculate next index
  if (direction > 0) {
    searchItemIndex = (searchItemIndex + 1) % searchItems.length;
  } else {
    searchItemIndex = (searchItemIndex - 1 + searchItems.length) % searchItems.length;
  }
  // Add active class and scroll into view
  const el = searchItems[searchItemIndex];
  el.classList.add("search-item-active");
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  // Update cycling position indicator
  updateCycleStatus();
}

function jumpToFirstResult() {
  if (!searchItems.length) return;
  if (searchItemIndex >= 0 && searchItems[searchItemIndex]) {
    searchItems[searchItemIndex].classList.remove("search-item-active");
  }
  searchItemIndex = 0;
  const el = searchItems[searchItemIndex];
  el.classList.add("search-item-active");
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  updateCycleStatus();
}

function jumpToLastResult() {
  if (!searchItems.length) return;
  if (searchItemIndex >= 0 && searchItems[searchItemIndex]) {
    searchItems[searchItemIndex].classList.remove("search-item-active");
  }
  searchItemIndex = searchItems.length - 1;
  const el = searchItems[searchItemIndex];
  el.classList.add("search-item-active");
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  updateCycleStatus();
}

function cycleSearchPage(direction) {
  if (!searchItems.length) return;
  if (searchItemIndex >= 0 && searchItems[searchItemIndex]) {
    searchItems[searchItemIndex].classList.remove("search-item-active");
  }
  // Jump forward/backward by a page
  const step = direction > 0 ? SEARCH_PAGE_SIZE : -SEARCH_PAGE_SIZE;
  // Double-modulo to handle negative remainder (JS % is remainder, not modulo)
  searchItemIndex = ((searchItemIndex + step) % searchItems.length + searchItems.length) % searchItems.length;
  const el = searchItems[searchItemIndex];
  el.classList.add("search-item-active");
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  updateCycleStatus();
}

function updateCycleStatus() {
  const cycleEl = document.getElementById("searchOverlayCycle");
  if (!cycleEl) return;
  if (!searchItems.length) {
    cycleEl.textContent = "";
    return;
  }
  cycleEl.textContent = "| " + (searchItemIndex + 1) + " of " + searchItems.length;
}

function restoreCollapseState(root) {
  const s = (collapsedConfig && collapsedConfig[root]) || {};
  document.querySelectorAll('.collapsible[data-section]').forEach(el => {
    const collapsed = !!s[el.getAttribute('data-section')];
    el.classList.toggle('collapsed', collapsed);
    const ic = el.querySelector('.collapse-icon');
    if (ic) ic.textContent = collapsed ? '\u25B6' : '\u25BC';
  });
}

// If an ISO timestamp has no timezone info (no Z, no +HH:MM), treat it as UTC.
// The Python backend writes UTC with Z, but STATE.md files created before this
// app or edited manually may lack the Z suffix. Without this, JS interprets
// timezone-naive strings as LOCAL time, making relativeTime() and heatColor()
// off by the timezone offset (user report: "updated time 1-2 hours ahead").
function _ensureTz(s) {
  if (!s) return s;
  const t = s.trim();
  if (t.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(t)) return t;
  return t + 'Z';
}

function formatLocalTime(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(_ensureTz(isoStr));
    if (isNaN(d.getTime())) return isoStr;
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return isoStr;
  }
}

function nowStr() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// T-076: user-selectable UI font. Fallbacks are appended here (not stored in
// config) so the saved value stays exactly what the user typed.
function applyFontFamily(fam) {
  const stack = (fam && fam.trim() ? fam.trim() : "Verdana_m1")
    + ', Verdana, "Microsoft Sans Serif", sans-serif';
  document.documentElement.style.setProperty("--uiFont", stack);
}

// The theme currently on screen. Not read from the config object, because the
// slug that was asked for and the slug that applied are not always the same:
// an unknown one resolves to the default (themes.resolve).
let currentTheme = "";
// What to restore if the Settings dialog is closed without saving.
let themeBeforeSettings = "";

// Setting custom properties on the root element, rather than rewriting
// style.css on disk the way the external Wintage installer did. That script
// destroyed the stylesheet twice (T-096, T-142). style.css's own :root stays
// as the fallback, so a failed theme load renders the shipped look rather than
// a half-painted one.
function applyTheme(payload) {
  if (!payload || !payload.tokens) return;
  const root = document.documentElement;
  Object.keys(payload.tokens).forEach(function (name) {
    root.style.setProperty("--" + name, payload.tokens[name]);
  });
  currentTheme = payload.slug || "";
  const picker = document.getElementById("setTheme");
  if (picker && currentTheme) picker.value = currentTheme;
}

function relativeTime(isoStr) {
  if (!isoStr) return "";
  const ts = new Date(_ensureTz(isoStr)).getTime();
  if (isNaN(ts)) return "";
  // FLOOR, not round: "2h ago" must mean at least 2 hours have passed. Rounding
  // claimed MORE elapsed time than actually had (90min showed as "2h ago"),
  // which is part of what read as "the timing is wrong" (T-072).
  let diff = Math.max(0, (Date.now() - ts) / 1000);
  if (diff < 5) return t("time.justNow");
  if (diff < 60) return t("time.secondsAgo", { n: Math.floor(diff) });
  diff /= 60;
  if (diff < 60) return t("time.minutesAgo", { n: Math.floor(diff) });
  diff /= 60;
  if (diff < 24) return t("time.hoursAgo", { n: Math.floor(diff) });
  diff /= 24;
  if (diff < 30) return t("time.daysAgo", { n: Math.floor(diff) });
  diff /= 30;
  if (diff < 12) return t("time.monthsAgo", { n: Math.floor(diff) });
  diff /= 12;
  return t("time.yearsAgo", { n: Math.floor(diff) });
}

function hexBlend(hexA, hexB, t) {
  t = Math.max(0, Math.min(1, t));
  const pa = parseInt(hexA.slice(1), 16), pb = parseInt(hexB.slice(1), 16);
  const ar = (pa >> 16) & 255, ag = (pa >> 8) & 255, ab = pa & 255;
  const br = (pb >> 16) & 255, bg = (pb >> 8) & 255, bb = pb & 255;
  const r = Math.round(ar + (br - ar) * t), g = Math.round(ag + (bg - ag) * t), b = Math.round(ab + (bb - ab) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

function flashColorFor(root) {
  if (!flashChangesEnabled) return "";
  const t = flashState[root];
  if (!t) return "";
  const ageSec = Math.max(0, (Date.now() - t) / 1000);
  if (ageSec >= FLASH_DECAY_SECONDS) {
    delete flashState[root];
    return "";
  }
  const surf = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#1a1408";
  const color = hexBlend(FLASH_HOT, surf, ageSec / FLASH_DECAY_SECONDS);
  return `background-color:${color};`;
}

// Edit-temperature: age-blended color, hot (just changed) -> cold (stale) --
// same concept as FastPrompter's per-line heat (ui/editor.py _heat_colour_for:
// age-bucketed color blend over a window), adapted to CSS via UI.md tokens
// only (--borderHighlight hot, --textMuted cold), no new hex.
const HEAT_WINDOW_SECONDS = 86400; // fully cooled after 1 day, matches FastPrompter's "day" bucket
const HEAT_HOT = "#C0A060";  // --borderHighlight
const HEAT_COLD = "#7A6838"; // --textMuted

function heatColorFor(isoStr) {
  const t = isoStr ? new Date(_ensureTz(isoStr)).getTime() : NaN;
  if (isNaN(t)) return HEAT_COLD;
  const ageSec = Math.max(0, (Date.now() - t) / 1000);
  return hexBlend(HEAT_HOT, HEAT_COLD, Math.min(1, ageSec / HEAT_WINDOW_SECONDS));
}

function timeWithHeat(isoStr) {
  if (!isoStr) return "";
  const color = heatColorFor(isoStr);
  return ` <span class="time-heat" style="color:${color}" title="${escapeHtml(formatLocalTime(isoStr))}">(${relativeTime(isoStr)})</span>`;
}

function subRowHtml(sub) {
  const sp = sub.path || "";
  return `<div class="sub-row" data-sub-path="${escapeHtml(sp)}">
    <span class="name">${escapeHtml(sub.name)}</span>
    <span class="phase-dot phase-${escapeHtml(sub.phase)}"></span>
    <span class="phase phase-${escapeHtml(sub.phase)}">${escapeHtml(sub.phase)}</span>
    <span class="task">${escapeHtml(sub.task)}</span>
  </div>`;
}

function outboxCountsSummary(counts) {
  const order = ["ready", "blocked", "draft", "reviewed", "stale"];
  const parts = order.filter((k) => counts && counts[k]).map((k) => `${counts[k]} ${k}`);
  return parts.length ? parts.join(", ") : "empty";
}

function subOutboxHtml(sub) {
  const entries = sub.outbox || [];
  const counts = sub.outbox_counts || {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const criticalReady = sub.outbox_critical_ready || 0;
  const summaryText = total ? outboxCountsSummary(counts) : "empty";

  const collectBtn = (e) => {
    if (e.status !== 'ready') return '';
    return `<button class="collect-btn" data-sub-name="${escapeHtml(sub.name)}" data-eid="${escapeHtml(e.id)}" data-critical="${e.critical ? 'true' : 'false'}" title="Collect this entry into main project">Collect</button>`;
  };
  const items = entries.slice(0, 8).map((e) => `
    <div class="outbox-item">
      <span class="outbox-id">${escapeHtml(e.id)}</span>
      <span class="outbox-status outbox-status-${escapeHtml(e.status)}">${escapeHtml(e.status)}</span>
      ${e.critical ? '<span class="outbox-critical-flag">CRIT</span>' : ""}
      <span class="outbox-summary" title="${escapeHtml(e.summary || e.title)}">${escapeHtml(e.summary || e.title)}</span>
      ${collectBtn(e)}
    </div>`).join("");

  return `<div class="outbox-block">
    <div class="outbox-header">
      <span>Outbox: ${escapeHtml(summaryText)}${criticalReady ? ` <span class="outbox-critical-flag">${criticalReady} CRITICAL</span>` : ""}</span>
      ${sub.outbox_path ? `<button class="open-sub-file-btn" data-path="${escapeHtml(sub.outbox_path)}" data-name="${escapeHtml(sub.name)}-OUTBOX.md" title="Open raw OUTBOX.md">OUTBOX</button>` : ""}
    </div>
    ${items ? `<div class="outbox-items">${items}</div>` : ""}
  </div>`;
}

// --- Conformance verdict -------------------------------------------------
// The grade comes from saipenview/conformance.py, which re-checks the rules a
// project's own .saipen/ files can decide alone. It is a second opinion, not a
// replacement for `tools/validate.py` -- which is why the baseline version it
// was read against is printed under every verdict rather than left implied.
function conformanceBadgeHtml(project) {
  const c = project && project.conformance;
  if (!c || !c.verdict) return "";
  const v = c.verdict;
  let label;
  if (v === "fail") label = c.fails + (c.fails === 1 ? " FAIL" : " FAILS");
  else if (v === "warn") label = c.warns + (c.warns === 1 ? " WARN" : " WARNS");
  else if (v === "pass") label = "OK";
  else label = "?";
  const top = (c.findings || []).slice(0, 6)
    .map((f) => f.severity.toUpperCase() + ": " + f.message).join("\n");
  const title = v === "pass"
    ? t("conf.tooltipPass") + " " + (c.baseline || "")
    : top;
  return `<span class="conf-badge ${v}" title="${escapeHtml(title)}">${escapeHtml(label)}</span>`;
}

function conformanceCardHtml(detail) {
  const c = detail && detail.conformance;
  if (!c) return "";
  // A clean verdict is not news. The card used to render anyway, saying
  // "no findings" in a section the user then has to read past on every single
  // conforming project. Silence is the report: nothing here means nothing
  // wrong, and the OK badge in the header still says so in one glyph for
  // anyone who wants the verdict confirmed rather than inferred.
  if (c.verdict === "pass" && !(c.findings || []).length) return "";
  const rows = (c.findings || []).map((f) => `
      <div class="conf-item">
        <span class="conf-sev ${escapeHtml(f.severity)}">${escapeHtml(f.severity.toUpperCase())}</span>
        <span class="conf-rule">${escapeHtml(f.rule)}</span>
        <span class="conf-msg">${escapeHtml(f.message)}</span>
        ${f.file ? `<span class="conf-where">${escapeHtml(f.file)}${f.line ? ":" + f.line : ""}</span>` : ""}
        ${f.cite ? `<span class="conf-cite">${escapeHtml(f.cite)}</span>` : ""}
      </div>`).join("");
  // Reached only when there IS something to show -- a fail, a warn, or a pass
  // that still carries info-level findings -- so the findings are the summary.
  const summary = `<div class="conf-list">${rows}</div>`;
  return `
      <div class="detail-card">
        <div class="collapsible" data-section="conformance">
          <div class="card-title collapsible-header">
            <span>${escapeHtml(t("conf.title"))} ${conformanceBadgeHtml(detail)}</span>
            <span class="collapse-icon">&#9660;</span>
          </div>
          <div class="collapsible-body">
            ${summary}
            <div class="conf-baseline">${escapeHtml(t("conf.baseline"))} ${escapeHtml(c.baseline || "?")}</div>
          </div>
        </div>
      </div>`;
}

function projectRowHtml(project) {
  const subs = [...project.subs];
  if (project.translate) subs.push(project.translate);
  const blockerHtml = project.phase === "BLOCKED" && project.blocker !== "none"
    ? `<span class="blocker">${escapeHtml(project.blocker)}</span>` : "";
  const isSelected = selectedRoot && selectedRoot.toLowerCase() === project.root.toLowerCase();
  const starSymbol = project.is_pinned ? "★" : "☆";
  const starClass = project.is_pinned ? "pin-btn pinned" : "pin-btn";
  const gitHtml = project.git_branch ? `<span class="git-badge ${project.git_dirty ? 'dirty' : ''}">⎇ ${escapeHtml(project.git_branch)}${project.git_dirty ? '*' : ''}</span>` : "";

  const flashStyle = flashColorFor(project.root);
  return `<div class="project-row ${isSelected ? "selected" : ""}" data-root="${escapeHtml(project.root)}" data-phase="${escapeHtml(project.phase)}" style="${flashStyle}">
    <span class="phase-indicator phase-${escapeHtml(project.phase)}" title="${escapeHtml(project.phase)}"></span>
    <div class="head">
      <button class="${starClass}" data-pin-root="${escapeHtml(project.root)}" title="Toggle Pin">${starSymbol}</button>
      <span class="name" title="${escapeHtml(project.root)}">${escapeHtml(project.name)}</span>
      ${gitHtml}
      ${conformanceBadgeHtml(project)}
      <span class="phase phase-${escapeHtml(project.phase)}">${escapeHtml(project.phase)}</span>
      <span class="updated" title="${escapeHtml(formatLocalTime(project.updated))}">${timeWithHeat(project.updated)}</span>
      <span class="hide-btn" data-hide-root="${escapeHtml(project.root)}" title="Hide project from list">✕</span>
    </div>
    <div class="task">${escapeHtml(project.task)}</div>
    ${blockerHtml}
    ${subs.map(subRowHtml).join("")}
  </div>`;
}

function filterProjects(projects) {
  let res = projects || [];
  if (searchQuery.trim()) {
    const q = searchQuery.toLowerCase().trim();
    res = res.filter((p) => p.name.toLowerCase().includes(q) || p.root.toLowerCase().includes(q));
  }
  if (currentFilter === "ALL") return res;
  if (currentFilter === "DONE") return res.filter((p) => p.phase === "DONE");
  if (currentFilter === "BLOCKED") return res.filter((p) => p.phase === "BLOCKED");
  if (currentFilter === "ACTIVE") return res.filter((p) => p.phase !== "DONE");
  // Arbitrary phase name filter (set via detail pane phase bar click)
  return res.filter((p) => p.phase === currentFilter);
}

function renderDetailPane(detail) {
  const pane = document.getElementById("detailPane");
  if (!pane) return;
  // T-066: never rebuild the pane out from under an open editor. The poll fires
  // every 5s and this function replaces the whole pane's innerHTML, so an open
  // edit form (and whatever the user had typed) was wiped before they could
  // finish. Same project + editor open => leave the DOM alone entirely.
  if (stateEditActive && detail && currentDetailRoot === detail.root) return;
  if (!detail) {
    currentDetailRoot = null;
    stateEditActive = false;
    pane.innerHTML = '<div class="detail-placeholder">Select a project to view details</div>';
    currentAgentPanelRoot = null;
    return;
  }
  currentDetailRoot = detail.root;

  let contentDiv = document.getElementById("detailPaneContent");
  if (!contentDiv) {
    // .detail-content, not an inline style: the layout has to be able to
    // change with the pane's width (style.css responsive bands, T-155), and an
    // inline declaration outranks every rule that would do that.
    pane.innerHTML = '<div id="detailPaneContent" class="detail-content"></div><div id="agentPanelContainer"></div>';
    contentDiv = document.getElementById("detailPaneContent");
  }

  const starSymbol = detail.is_pinned ? "★" : "☆";
  const starText = detail.is_pinned ? "Unpin ★" : "Pin ☆";

  let ticketsHtml = "";
  // The collapsed CSS state only ever hides the 6th-from-end item onward
  // (style.css .collapsible.collapsed .collapsible-body > :nth-last-child(n+6)),
  // so a section with 5 or fewer entries can never visibly change -- the arrow
  // was clickable and animating with nothing behind it. Recent DONE in
  // particular is server-capped to exactly 5 (api.py done[-5:]), so its arrow
  // was 100% dead every single time. Only render the affordance when there's
  // something it could actually hide.
  const renderTicketGroup = (title, tickets) => {
    if (!tickets || !tickets.length) return "";
    const sectionKey = "tickets-" + title.toLowerCase().replace(/[^a-z]+/g, "-");
    const canCollapse = tickets.length > 5;
    return `<div class="collapsible" data-section="${sectionKey}">
      <div class="card-title${canCollapse ? " collapsible-header" : ""}">
        <span>${title} (${tickets.length}) <span class="dblclick-hint">📄</span></span>
        ${canCollapse ? '<span class="collapse-icon">▼</span>' : ""}
      </div>
      <div class="ticket-list collapsible-body">
        ${tickets.map((t) => `<div class="ticket-item"><span class="ticket-id">${escapeHtml(t.id)}</span><span class="ticket-desc">${escapeHtml(t.desc)}</span></div>`).join("")}
      </div>
    </div>`;
  };
  const renderTicketGroupWithActions = (title, tickets, root) => {
    if (!tickets || !tickets.length) return "";
    const sectionKey = "tickets-" + title.toLowerCase().replace(/[^a-z]+/g, "-");
    const canCollapse = tickets.length > 5;
    return `<div class="collapsible" data-section="${sectionKey}">
      <div class="card-title${canCollapse ? " collapsible-header" : ""}">
        <span>${title} (${tickets.length}) <span class="dblclick-hint">📄</span></span>
        ${canCollapse ? '<span class="collapse-icon">▼</span>' : ""}
      </div>
      <div class="ticket-list collapsible-body">
        ${tickets.map((t) => {
          const isDoing = title === "DOING";
          const actionBtn = isDoing
            ? `<button class="ticket-action-btn ticket-done-btn" data-tid="${escapeHtml(t.id)}" data-action="done" title="Mark ticket done">Done</button>`
            : "";
          return `<div class="ticket-item"><span class="ticket-id">${escapeHtml(t.id)}</span><span class="ticket-desc">${escapeHtml(t.desc)}</span>${actionBtn}</div>`;
        }).join("")}
      </div>
    </div>`;
  };    ticketsHtml += renderTicketGroupWithActions("DOING", detail.doing_tickets, detail.root);
  ticketsHtml += renderTicketGroup("BLOCKED", detail.blocked_tickets);
  ticketsHtml += renderTicketGroupWithActions("TODO", detail.todo_tickets, detail.root);
  ticketsHtml += renderTicketGroupWithActions("Recent DONE", detail.done_tickets, detail.root);

  let logHtml = "";
  if (detail.log_tail && detail.log_tail.length) {
    const canCollapse = detail.log_tail.length > 5;
    logHtml = `<div class="detail-card history">
      <div class="collapsible" data-section="log">
        <div class="card-title${canCollapse ? " collapsible-header" : ""}">
          <span>Recent Activity (LOG.md) <span class="dblclick-hint">📄</span></span>
          ${canCollapse ? '<span class="collapse-icon">▼</span>' : ""}
        </div>
        <div class="ticket-list collapsible-body">
          ${detail.log_tail.map((l) => `<div class="log-item">${escapeHtml(l)}</div>`).join("")}
        </div>
      </div>
    </div>`;
  }

    let subsHtml = "";
    if (detail.subs && detail.subs.length) {
      const staleBadge = detail.subs_stale
        ? `<span class="stale-badge" title="Sub-agent protocol files are out of date — ${escapeHtml(detail.subs_stale_details || '')}">STALE</span>`
        : "";
      const canCollapse = detail.subs.length > 5;
      subsHtml = `<div class="detail-card">
        <div class="collapsible" data-section="sub-agents">
          <div class="card-title${canCollapse ? " collapsible-header" : ""}">
            <span>Sub-agents (${detail.subs.length})${staleBadge ? ' ' + staleBadge : ''} <span class="dblclick-hint">📄</span></span>
            ${canCollapse ? '<span class="collapse-icon">▼</span>' : ""}
          </div>
          <div class="ticket-list collapsible-body">
            ${detail.subs.map((s) => {
              const bc = s.board_counts || {};
              const bcParts = [];
              if (bc.doing) bcParts.push(bc.doing + ' DOING');
              if (bc.todo) bcParts.push(bc.todo + ' TODO');
              if (bc.done) bcParts.push(bc.done + ' DONE');
              if (bc.blocked) bcParts.push(bc.blocked + ' BLOCKED');
              const bcText = bcParts.length ? bcParts.join(', ') : '0 open';
              const nextActionHtml = s.next_action
                ? '<div class="sub-next-action"><span class="label">Next:</span> ' + escapeHtml(s.next_action) + '</div>'
                : '';
              const logTailHtml = (s.log_tail && s.log_tail.length)
                ? '<div class="sub-log-section"><span class="label">Recent:</span>' + s.log_tail.slice(0, 3).map(l => '<div class="sub-log-line">' + escapeHtml(l) + '</div>').join('') + '</div>'
                : '';
              const sp = escapeHtml(s.path || '');
              return `
              <div class="sub-detail-item" data-sub-path="${sp}">
                <div class="sub-item-head">
                  <span class="sub-name">${escapeHtml(s.name)}</span>
                  <span class="sub-file-btns">
                    <button class="sub-file-btn" data-sub-path="${sp}" data-file="STATE.md" title="Open STATE.md">S</button>
                    <button class="sub-file-btn" data-sub-path="${sp}" data-file="BOARD.md" title="Open BOARD.md">B</button>
                    <button class="sub-file-btn" data-sub-path="${sp}" data-file="LOG.md" title="Open LOG.md">L</button>
                    <span class="phase-dot phase-${escapeHtml(s.phase)}"></span>
                    <span class="sub-phase phase phase-${escapeHtml(s.phase)}">${escapeHtml(s.phase)}</span>
                  </span>
                </div>
                <div style="font-size:11px; margin-top:3px;"><span class="detail-field"><span class="label">Task:</span> ${escapeHtml(s.task)}</span></div>
                <div class="sub-board-summary">${escapeHtml(bcText)}</div>
                ${nextActionHtml}
                ${logTailHtml}
                ${s.phase === 'BLOCKED' && s.blocker && s.blocker !== 'none' ? '<div style="font-size:11px; margin-top:2px; color:var(--danger)"><span style="color:var(--textMuted)">Blocker:</span> ' + escapeHtml(s.blocker) + '</div>' : ''}
                <div style="font-size:10px; color:var(--textMuted); margin-top:2px;">Updated: ${escapeHtml(formatLocalTime(s.updated))}${timeWithHeat(s.updated)} <span class="now-clock" style="font-size:10px;margin-left:4px;">(now: ${nowStr()})</span></div>
                ${subOutboxHtml(s)}
              </div>`;
            }).join("")}
          </div>
        </div>
      </div>`;
    }

    // Fetch scan errors for the error card (polled fresh each renderDetailPane)
    const errorApi = window.pywebview && window.pywebview.api;
    let errorCardHtml = "";
    if (errorApi) {
      errorApi.get_scan_error_log().then((errors) => {
        if (errors && errors.length) {
          const errorCard = document.getElementById("errorCard");
          if (errorCard) {
            errorCard.style.display = "block";
            const body = errorCard.querySelector(".collapsible-body");
            if (body) {
              body.innerHTML = errors.slice(0, 20).map(e =>
                `<div class="error-item"><span class="error-time">${escapeHtml(formatLocalTime(e.time))}</span><span class="error-message">${escapeHtml(e.message)}</span></div>`
              ).join("");
            }
          }
        }
      }).catch((e) => console.error("error card fetch failed:", e));
    }

    contentDiv.innerHTML = `
      <div class="detail-header">
        <div class="detail-title">
          <span class="detail-name-group">
            <span class="detail-name" title="${escapeHtml(detail.name)}">${escapeHtml(detail.name)}</span>
            ${detail.git_branch ? `<span class="git-badge ${detail.git_dirty ? 'dirty' : ''}" style="font-size:10px; font-weight:normal;">⎇ ${escapeHtml(detail.git_branch)}${detail.git_dirty ? '*' : ''}</span>` : ""}
            ${conformanceBadgeHtml(detail)}
          </span>
          <span class="detail-title-right">
            <span class="phase-indicator phase-${escapeHtml(detail.phase)}" title="${escapeHtml(detail.phase)} — ${escapeHtml(t(PHASE_DESCRIPTIONS[detail.phase] || ''))}"></span>
            <span class="phase phase-${escapeHtml(detail.phase)}">${escapeHtml(detail.phase)}</span>
          </span>
        </div>
        <div class="detail-path">${escapeHtml(detail.root)}</div>
        <div class="action-bar">
          <button id="openFolderBtn" title="Open project folder in file explorer">📁 Folder</button>
          <button id="openTerminalBtn" title="Open command prompt in project folder">💻 CMD</button>
          <button id="openEditorBtn" title="Open project folder in VS Code">📝 Code</button>
          ${(detail.quick_actions || []).map(a => `<button class="quick-action-btn" data-command="${escapeHtml(a.command)}" title="Run: ${escapeHtml(a.command)}">${escapeHtml(a.label)}</button>`).join("")}
          ${(detail.custom_commands || []).map(a => `<button class="custom-cmd-btn" data-command="${escapeHtml(a.command)}" title="Custom: ${escapeHtml(a.command)}">${escapeHtml(a.label)}</button>`).join("")}
          <button class="open-file-btn" data-file="STATE.md" title="Open STATE.md" style="margin-left:8px;">STATE</button>
          <button class="open-file-btn" data-file="BOARD.md" title="Open BOARD.md">BOARD</button>
          <button class="open-file-btn" data-file="LOG.md" title="Open LOG.md">LOG</button>
          <button id="togglePinDetailBtn" title="Pin/unpin project to top of list" style="margin-left:8px;">${starText}</button>
          <button id="hideDetailBtn" title="Remove project from list (can restore via Hidden checkbox)">Hide</button>
        </div>
      </div>

      <div class="next-action-banner">
        <span class="next-action-label">&#9654; NEXT</span>
        <span class="next-action-text">${escapeHtml(detail.next_action || "none")}</span>
      </div>

      ${conformanceCardHtml(detail)}

      <div class="detail-card">
        <div class="collapsible" data-section="state-summary">
          <div class="card-title collapsible-header">
            <span>State Summary <span class="dblclick-hint">📄</span></span>
            <span style="display:flex; align-items:center; gap:4px;">
              <button id="editStateBtn" title="Edit project state fields" style="font-size:9px; padding:0 4px; border-radius:2px;">Edit</button>
              <span class="collapse-icon">▼</span>
            </span>
          </div>
          <div class="collapsible-body">
            <div id="stateDisplayMode">
              <div class="detail-field"><span class="label">Current Task:</span> ${escapeHtml(detail.task)}</div>
              <div class="detail-field"><span class="label">Next:</span> ${escapeHtml(detail.next_action || "none")}</div>
              ${detail.phase === "BLOCKED" ? `<div class="detail-field"><span class="label" style="color:var(--danger)">Blocker:</span> ${escapeHtml(detail.blocker)}</div>` : ""}
              <div class="detail-field"><span class="label">Updated:</span> ${escapeHtml(formatLocalTime(detail.updated))}${timeWithHeat(detail.updated)}</div>
              ${detail.subs && detail.subs.length ? `<div style="margin-top:4px; padding-top:4px; border-top:1px solid var(--borderMuted);">
                <div class="detail-field" style="margin-bottom:1px;"><span class="label">Sub-agents:</span> ${detail.subs.length}</div>
                ${detail.subs.slice().sort(function(a, b) {
                  const ta = a.updated ? new Date(_ensureTz(a.updated)).getTime() : 0;
                  const tb = b.updated ? new Date(_ensureTz(b.updated)).getTime() : 0;
                  return tb - ta;
                }).map(function(s) {
                  const bc = s.board_counts || {};
                  const counts = [];
                  if (bc.doing) counts.push(bc.doing + ' DOING');
                  if (bc.todo) counts.push(bc.todo + ' TODO');
                  if (bc.blocked) counts.push(bc.blocked + ' BLOCKED');
                  if (bc.done) counts.push(bc.done + ' DONE');
                  const bcText = counts.length ? counts.join(', ') : '';
                  // Classes, not inline styles (T-155): this row was the widest
                  // fixed thing in the pane -- a hard 76px indent plus a 60px
                  // name plus a 36px pill plus counts -- and at a narrow width
                  // it overflowed the card by up to 100px. style.css can only
                  // shrink it in the narrow band if the values live there.
                  return '<div class="sub-detail-row">' +
                    '<span class="phase-dot phase-' + escapeHtml(s.phase) + '"></span>' +
                    '<span class="sd-name">' + escapeHtml(s.name || '') + '</span>' +
                    '<span class="phase sd-phase phase-' + escapeHtml(s.phase) + '">' + escapeHtml(s.phase) + '</span>' +
                    '<span class="sd-task" title="' + escapeHtml(s.task || '') + '">' + escapeHtml(s.task || '') + '</span>' +
                    (bcText ? '<span class="sd-counts">' + escapeHtml(bcText) + '</span>' : '') +
                    (s.updated ? timeWithHeat(s.updated) : '') +
                    '</div>';
                }).join('')}
              </div>` : ""}
              ${detail.log_tail && detail.log_tail.length ? `<div class="mini-c collapsed" style="margin-top:4px; padding-top:4px; border-top:1px solid var(--borderMuted);">
                <div class="mini-c-header" style="cursor:pointer;font-size:9px;color:var(--textSecondary);display:flex;align-items:center;gap:3px;">
                  <span>Last 5 actions</span>
                  <span class="mini-c-icon" style="font-size:7px;">▶</span>
                </div>
                <div class="mini-c-body" style="margin-top:2px;">
                  ${detail.log_tail.slice(0, 5).map(function(l) {
                    return '<div style="font-size:8px;color:var(--textMuted);padding:1px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + escapeHtml(l) + '">' + escapeHtml(l) + '</div>';
                  }).join('')}
                </div>
              </div>` : ""}
            </div>
            <div id="stateEditMode" style="display:none; flex-direction:column; gap:4px; margin-top:4px;">
              <label style="font-size:10px; color:var(--textMuted)">Next Action:</label>
              <input type="text" id="editNextAction" value="${escapeHtml(detail.next_action || "")}" style="width:100%;">
              <label style="font-size:10px; color:var(--textMuted)">Current Task:</label>
              <input type="text" id="editTask" value="${escapeHtml(detail.task || "")}" style="width:100%;">
              <div style="display:flex; gap:4px; margin-top:4px; align-items:center;">
                  <button id="saveStateBtn" style="color:var(--success)">Save</button>
                  <button id="cancelStateBtn">Cancel</button>
                  <span style="font-size:8px; color:var(--textMuted); margin-left:4px;">auto-refresh paused while editing</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div id="errorCard" class="detail-card error-card" style="display:none;">
        <div class="collapsible" data-section="scan-errors">
          <div class="card-title collapsible-header" style="color:var(--danger);">
            <span>Scan Errors</span>
            <span class="collapse-icon">▼</span>
          </div>
          <div class="ticket-list collapsible-body"></div>
        </div>
      </div>
  
      ${ticketsHtml ? `<div class="detail-card">${ticketsHtml}</div>` : ""}
      ${subsHtml}
      ${logHtml}
    `;

    renderAgentPanel(detail.root, document.getElementById("agentPanelContainer"));

  document.getElementById("openFolderBtn")?.addEventListener("click", () => {
    window.pywebview.api.open_folder(detail.root);
  });

  document.getElementById("openTerminalBtn")?.addEventListener("click", () => {
    window.pywebview.api.open_terminal(detail.root);
  });

  document.getElementById("openEditorBtn")?.addEventListener("click", (e) => {
    const btn = e.currentTarget;
    window.pywebview.api.open_editor(detail.root).then((ok) => {
      if (!ok) {
        btn.textContent = "VS Code not found";
        setTimeout(() => { btn.textContent = "📝 Code"; }, 2000);
      }
    });
  });

  document.getElementById("togglePinDetailBtn")?.addEventListener("click", () => {
    window.pywebview.api.toggle_pin(detail.root).then((updatedProjects) => {
      rawProjects = updatedProjects;
      loadDetail(detail.root);
      render(rawProjects, isScanned);
    });
  });

  // Quick-action buttons: run command in project directory
  document.querySelectorAll(".quick-action-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const cmd = e.currentTarget.getAttribute("data-command");
      if (cmd) {
        window.pywebview.api.run_command(detail.root, cmd);
      }
    });
  });

  // Custom command buttons (user-defined quick actions)
  document.querySelectorAll(".custom-cmd-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const cmd = e.currentTarget.getAttribute("data-command");
      if (cmd) {
        window.pywebview.api.run_command(detail.root, cmd);
      }
    });
  });

  document.querySelectorAll(".open-file-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const fileName = e.currentTarget.getAttribute("data-file");
      const path = detail.root + "\\.saipen\\" + fileName;
      window.pywebview.api.read_file_text(path).then((text) => {
        if (text !== null) {
          openFileViewer(fileName, path, text);
        } else {
          const oldText = btn.textContent;
          btn.textContent = "Err";
          setTimeout(() => { btn.textContent = oldText; }, 2000);
        }
      });
    });
  });

  document.querySelectorAll(".open-sub-file-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const path = e.currentTarget.getAttribute("data-path");
      const label = e.currentTarget.getAttribute("data-name");
      window.pywebview.api.read_file_text(path).then((text) => {
        if (text !== null) {
          openFileViewer(label, path, text);
        } else {
          const oldText = btn.textContent;
          btn.textContent = "Err";
          setTimeout(() => { btn.textContent = oldText; }, 2000);
        }
      });
    });
  });

  // Sub-agent file buttons: open STATE/BOARD/LOG in file viewer
  document.querySelectorAll(".sub-file-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const subPath = btn.getAttribute("data-sub-path");
      const fileName = btn.getAttribute("data-file");
      if (!subPath || !fileName) return;
      const path = subPath + "\\" + fileName;
      const label = btn.parentElement.parentElement.querySelector(".sub-name").textContent + " " + fileName;
      window.pywebview.api.read_file_text(path).then((text) => {
        if (text !== null) {
          openFileViewer(label, path, text);
        } else {
          const oldText = btn.textContent;
          btn.textContent = "Err";
          setTimeout(() => { btn.textContent = oldText; }, 2000);
        }
      });
    });
  });

  // Dblclick on sub-agent detail items opens their STATE.md
  document.querySelectorAll(".sub-detail-item").forEach((item) => {
    const sp = item.getAttribute("data-sub-path");
    if (sp) {
      item.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        const path = sp + "\\STATE.md";
        const label = (item.querySelector(".sub-name") || {}).textContent || "sub";
        window.pywebview.api.read_file_text(path).then((text) => {
          if (text !== null) openFileViewer(label + " STATE.md", path, text);
          else showToast("Can't read STATE.md", "error", 2000);
        });
      });
    }
  });

  // Single-click on the 📄 icon opens the connected file
  document.querySelectorAll(".dblclick-hint").forEach((hint) => {
    hint.addEventListener("click", (e) => {
      e.stopPropagation();
      const collapsible = hint.closest(".collapsible");
      const sec = collapsible ? collapsible.getAttribute("data-section") : null;
      const root = detail.root;
      const fileName = _sectionFileFor(sec);
      const path = _sectionFilePath(root, sec);
      if (path && fileName) {
        window.pywebview.api.read_file_text(path).then((text) => {
          if (text !== null) openFileViewer(fileName, path, text);
          else showToast("Can't read " + fileName, "error", 2000);
        });
      }
    });
  });

  // Dblclick on collapsible sections opens their connected file (fallback)
  document.querySelectorAll(".collapsible[data-section]").forEach((section) => {
    section.addEventListener("dblclick", (e) => {
      if (e.target.closest("button") || e.target.closest(".dblclick-hint")) return;
      e.stopPropagation();
      const sec = section.getAttribute("data-section");
      const root = detail.root;
      const fileName = _sectionFileFor(sec);
      const path = _sectionFilePath(root, sec);
      if (path && fileName) {
        window.pywebview.api.read_file_text(path).then((text) => {
          if (text !== null) openFileViewer(fileName, path, text);
          else showToast("Can't read " + fileName, "error", 2000);
        });
      }
    });
  });

  document.getElementById("hideDetailBtn")?.addEventListener("click", () => {
    window.pywebview.api.hide_project(detail.root).then((updatedProjects) => {
      rawProjects = updatedProjects;
      selectedRoot = null;
      render(rawProjects, isScanned);
    });
  });

  const disp = document.getElementById("stateDisplayMode");
  const edit = document.getElementById("stateEditMode");
  document.getElementById("editStateBtn")?.addEventListener("click", () => {
    stateEditActive = true;   // freeze auto-refresh for this pane (T-066)
    disp.style.display = "none";
    edit.style.display = "flex";
    document.getElementById("editNextAction")?.focus();
  });
  document.getElementById("cancelStateBtn")?.addEventListener("click", () => {
    stateEditActive = false;
    edit.style.display = "none";
    disp.style.display = "block";
  });
  document.getElementById("saveStateBtn")?.addEventListener("click", () => {
    const btn = document.getElementById("saveStateBtn");
    const nextA = document.getElementById("editNextAction").value;
    const taskV = document.getElementById("editTask").value;
    const updates = { "next_action": nextA, "task": taskV };
    btn.textContent = "Saving...";
    window.pywebview.api.update_project_state(detail.root, updates).then((updatedDetail) => {
      // Clear the freeze only once the write actually came back, otherwise the
      // next poll could repaint over the editor before the save landed.
      stateEditActive = false;
      if (updatedDetail) {
        renderDetailPane(updatedDetail);
        window.pywebview.api.get_projects().then((proj) => render(proj, isScanned));
        if (typeof showToast === "function") showToast("State saved", "info", 1500);
      } else {
        btn.textContent = "Save failed -- retry?";
        stateEditActive = true;   // keep the editor open so nothing typed is lost
      }
    }).catch((err) => {
      btn.textContent = "Save failed -- retry?";
      stateEditActive = true;
      console.error("update_project_state failed:", err);
    });
  });

  document.querySelectorAll('.collapsible-header').forEach(header => {
    header.addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      const collapsible = header.parentElement;
      collapsible.classList.toggle('collapsed');
      const icon = header.querySelector('.collapse-icon');
      if (icon) { icon.textContent = collapsible.classList.contains('collapsed') ? '\u25B6' : '\u25BC'; }
      persistCollapseState();
    });
  });

  // Mini-collapsible toggle for Last 5 actions inside State Summary
  document.querySelectorAll('.mini-c-header').forEach(header => {
    header.addEventListener('click', (e) => {
      const miniC = header.closest('.mini-c');
      if (!miniC) return;
      miniC.classList.toggle('collapsed');
      const icon = header.querySelector('.mini-c-icon');
      if (icon) { icon.textContent = miniC.classList.contains('collapsed') ? '\u25B6' : '\u25BC'; }
    });
  });

  // Right-click on collapsible headers opens section context menu
  document.querySelectorAll('.collapsible-header').forEach(header => {
    header.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      e.stopPropagation();
      const collapsible = header.closest('.collapsible');
      const section = collapsible ? collapsible.getAttribute('data-section') : null;
      if (section) showSectionContextMenu(e, detail.root, section);
    });
  });

  // Collect OUTBOX buttons: fold ready entries into main project
  document.querySelectorAll('.collect-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const subName = btn.getAttribute('data-sub-name');
      const eid = btn.getAttribute('data-eid');
      const isCritical = btn.getAttribute('data-critical') === 'true';

      // Freshness caveat per PROTOCOL.md §4 step 1
      const notice = isCritical
        ? `This will create a new T-### TODO ticket for ${subName}'s "${eid}".\n\nNote: main_project_refs NOT freshness-checked — verify against current HEAD before acting on the ticket.`
        : `This will append "${eid}" from ${subName} to the shared inbox for next planning round.\n\nNote: main_project_refs NOT freshness-checked — spot-check before PLANNING.`;

      const btnSelector = `button[data-eid="${eid}"]`;
      showConfirm(notice, () => {
        // OK clicked — proceed with collect (find button by data attribute,
        // not closure capture — detail pane may re-render between dialog open
        // and user click, which would make the closure-captured btn a detached
        // DOM element)
        const liveBtn = document.querySelector(btnSelector);
        if (!liveBtn) return;
        const origText2 = liveBtn.textContent;
        liveBtn.textContent = "...";
        liveBtn.disabled = true;

        window.pywebview.api.collect_outbox(detail.root, subName, eid).then((result2) => {
          if (result2 && result2.ok) {
            if (result2.updated_detail) {
              renderDetailPane(result2.updated_detail);
              window.pywebview.api.get_projects().then((proj) => render(proj, isScanned));
            } else {
              liveBtn.textContent = "Done!";
              setTimeout(() => { liveBtn.textContent = origText2; liveBtn.disabled = false; }, 2000);
            }
          } else {
            liveBtn.textContent = "Err";
            setTimeout(() => { liveBtn.textContent = origText2; liveBtn.disabled = false; }, 2000);
          }
        }).catch(() => {
          liveBtn.textContent = "Err";
          setTimeout(() => { liveBtn.textContent = origText2; liveBtn.disabled = false; }, 2000);
        });
      }, () => {
        // Cancel clicked — re-enable button
        const liveBtn = document.querySelector(btnSelector);
        if (liveBtn) liveBtn.disabled = false;
      });
    });
  });

  // Interactive ticket action buttons: Start / Done / Reopen
  document.querySelectorAll('.ticket-action-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const tid = btn.getAttribute('data-tid');
      const action = btn.getAttribute('data-action');
      if (!tid || !action) return;
      const origText = btn.textContent;
      btn.textContent = "...";
      btn.disabled = true;
      window.pywebview.api.toggle_ticket_status(detail.root, tid, action).then((updatedDetail) => {
        if (updatedDetail) {
          renderDetailPane(updatedDetail);
          window.pywebview.api.get_projects().then((proj) => render(proj, isScanned));
        } else {
          btn.textContent = origText;
          btn.disabled = false;
        }
      }).catch(() => {
        btn.textContent = origText;
        btn.disabled = false;
      });
    });
  });

  // Click on phase-indicator bar: single-click filters sidebar, double-click opens overlay
  const detailPhaseBar = document.querySelector(".detail-title .phase-indicator");
  if (detailPhaseBar) {
    detailPhaseBar.addEventListener("click", (e) => {
      e.stopPropagation();
      const phase = detail.phase;
      currentFilter = phase;
      // Update filter dropdown: add option if missing, then select it
      const fs = document.getElementById("filterSelect");
      if (fs) {
        if (!fs.querySelector(`option[value="${phase}"]`)) {
          const opt = document.createElement("option");
          opt.value = phase;
          opt.textContent = phase;
          opt.setAttribute("data-dynamic", "true");
          fs.appendChild(opt);
        }
        fs.value = phase;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
          window.pywebview.api.save_view_config({ filter_phase: phase });
        }
      }
      render(rawProjects, isScanned);
    });
    detailPhaseBar.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      showPhaseOverlay(detail.phase);
    });
  }

  restoreCollapseState(detail.root);

  // If deep search requested a specific section, expand it
  if (_expandSectionAfterLoad) {
    const sectionKey = "tickets-" + _expandSectionAfterLoad.toLowerCase().replace(/[^a-z]+/g, "-");
    document.querySelectorAll(".collapsible[data-section]").forEach(function(el) {
      if (el.getAttribute("data-section") === sectionKey) {
        el.classList.remove("collapsed");
        const icon = el.querySelector(".collapse-icon");
        if (icon) icon.textContent = "\u25BC";
      }
    });
    _expandSectionAfterLoad = null;
  }
}

function loadDetail(rootStr) {
  if (!rootStr) {
    renderDetailPane(null);
    return;
  }
  window.pywebview.api.get_project_detail(rootStr).then((detail) => {
    renderDetailPane(detail);
  });
}

function selectProject(rootStr) {
  // Switching projects abandons any open editor -- otherwise the freeze from
  // T-066 would follow you to the new project and stop it ever refreshing.
  if (rootStr !== selectedRoot) stateEditActive = false;
  selectedRoot = rootStr;
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
    window.pywebview.api.save_view_config({ selected_root: selectedRoot });
  }
  loadDetail(selectedRoot);

  document.querySelectorAll(".project-row").forEach((row) => {
    if (row.getAttribute("data-root").toLowerCase() === (selectedRoot || "").toLowerCase()) {
      row.classList.add("selected");
    } else {
      row.classList.remove("selected");
    }
  });
}

// --- Linked worktree rows (never mixed into normal .saipen/ project list) ---
let linkedWorktrees = [];

function linkedWorktreeHtml(wt) {
  return `<div class="project-row wt-row" data-root="${escapeHtml(wt.root)}" title="Linked worktree — run 'saipen set' to add .saipen/">
    <span class="phase-indicator wt-indicator" style="background:var(--accentTealDeep);"></span>
    <div class="head">
      <span class="wt-icon" style="color:var(--accentTeal);flex:0 0 auto;font-size:10px;">⎇</span>
      <span class="name" style="color:var(--accentTeal);font-style:italic;" title="${escapeHtml(wt.root)}">${escapeHtml(wt.name)}</span>
      <span class="wt-label">worktree</span>
    </div>
  </div>`;
}

function renderLinkedWorktrees() {
  const list = document.getElementById("projectList");
  const status = document.getElementById("status");
  if (!window.pywebview || !window.pywebview.api) return;
  window.pywebview.api.get_linked_worktrees().then((wts) => {
    linkedWorktrees = wts || [];
    const badge = document.getElementById("wtBadge");
    if (badge) {
      if (linkedWorktrees.length) {
        badge.textContent = "WT" + linkedWorktrees.length;
        badge.style.display = "inline";
      } else {
        badge.style.display = "none";
      }
    }
    // If no main projects and not in hidden/show-other mode, show worktrees
    // inline at the bottom of the regular project list
    if (!document.querySelector("#projectList .project-row:not(.wt-row)") && linkedWorktrees.length) {
      list.innerHTML += `<div class="wt-section">
        <div class="wt-section-title" style="font-size:9px;color:var(--textMuted);padding:4px 6px;border-top:1px solid var(--borderMuted);">Linked Worktrees (${linkedWorktrees.length})</div>
        ${linkedWorktrees.map(linkedWorktreeHtml).join("")}
      </div>`;
      // Attach click handlers — open folder on click
      list.querySelectorAll(".wt-row").forEach((row) => {
        const root = row.getAttribute("data-root");
        if (root) {
          row.addEventListener("click", () => {
            window.pywebview.api.open_folder(root);
          });
        }
      });
    }
  }).catch((e) => console.error("renderLinkedWorktrees failed:", e));
}

function hiddenRowHtml(project) {
  return `<div class="project-row hidden-row" data-root="${escapeHtml(project.root)}" data-phase="${escapeHtml(project.phase)}">
    <span class="phase-indicator phase-${escapeHtml(project.phase)}" title="${escapeHtml(project.phase)}"></span>
    <div class="head">
      <span class="name" title="${escapeHtml(project.root)}">${escapeHtml(project.name)}</span>
      <span class="phase phase-${escapeHtml(project.phase)}">${escapeHtml(project.phase)}</span>
      <span class="updated" title="${escapeHtml(formatLocalTime(project.updated))}">${timeWithHeat(project.updated)}</span>
      <span class="unhide-btn" data-unhide-root="${escapeHtml(project.root)}" title="Unhide project">&#x21A9;</span>
    </div>
    <div class="task" style="color:var(--textMuted);">${escapeHtml(project.task)}</div>
  </div>`;
}

function updateFlashSnapshot(projects) {
  const now = Date.now();
  for (const p of projects || []) {
    const prev = prevSnapshot[p.root];
    const cur = { phase: p.phase, task: p.task, updated: p.updated, git_dirty: p.git_dirty };
    if (prev) {
      if (prev.phase !== cur.phase || prev.task !== cur.task || prev.updated !== cur.updated || prev.git_dirty !== cur.git_dirty) {
        flashState[p.root] = now;
      }
    }
    prevSnapshot[p.root] = cur;
  }
  // Clean up stale entries from prevSnapshot and flashState
  const currentRoots = new Set((projects || []).map(p => p.root));
  for (const k of Object.keys(prevSnapshot)) {
    if (!currentRoots.has(k)) delete prevSnapshot[k];
  }
  for (const k of Object.keys(flashState)) {
    if (!currentRoots.has(k)) delete flashState[k];
  }
}

function render(projects, scanned) {
  rawProjects = projects || [];
  isScanned = scanned;
  updateFlashSnapshot(rawProjects);

  const list = document.getElementById("projectList");
  const status = document.getElementById("status");

  if (showHidden) {
    window.pywebview.api.get_hidden_projects().then((hidden) => {
      if (!hidden || !hidden.length) {
        list.innerHTML = '<div class="empty">no hidden projects</div>';
        status.textContent = "0 hidden";
      } else {
        // Sort: active phases first, then blocked, then done. Within same group, newest updated first.
        const PHASE_ORDER = { DONE: 10, VERIFY: 10, SHIP: 10, BLOCKED: 5 };
        hidden.sort((a, b) => {
          const pa = PHASE_ORDER[a.phase] || 0;
          const pb = PHASE_ORDER[b.phase] || 0;
          if (pa !== pb) return pa - pb;
          const ta = a.updated ? new Date(_ensureTz(a.updated)).getTime() : 0;
          const tb = b.updated ? new Date(_ensureTz(b.updated)).getTime() : 0;
          return tb - ta; // newest first
        });
        list.innerHTML = hidden.map(hiddenRowHtml).join("");
        // Build phase breakdown for status bar
        const phaseCounts = {};
        hidden.forEach((p) => { phaseCounts[p.phase] = (phaseCounts[p.phase] || 0) + 1; });
        const breakdown = Object.entries(phaseCounts)
          .sort((a, b) => (PHASE_ORDER[a[0]] || 0) - (PHASE_ORDER[b[0]] || 0))
          .map(([ph, cnt]) => `${cnt} ${ph}`).join(", ");
        status.textContent = `${hidden.length} hidden (${breakdown})`;
        list.querySelectorAll(".project-row").forEach((row) => {
          const hRoot = row.getAttribute("data-root");
          const hPhase = row.getAttribute("data-phase");
          row.addEventListener("click", (e) => {
            if (e.target.classList.contains("unhide-btn")) {
              e.stopPropagation();
              const hRoot = e.target.getAttribute("data-unhide-root");
              window.pywebview.api.unhide_project(hRoot).then((updatedProjects) => {
                rawProjects = updatedProjects;
                render(rawProjects, isScanned);
              });
            }
          });
          row.addEventListener("contextmenu", (e) => {
            e.preventDefault();
            if (hRoot && hPhase) showContextMenu(e, hRoot, hPhase);
          });
        });
      }
    });
    return;
  }

  if (!scanned) {
    list.innerHTML = '<div class="empty">scanning...</div>';
    status.textContent = "scanning...";
    return;
  }

  const filtered = filterProjects(rawProjects);

  if (!filtered.length) {
    list.innerHTML = `<div class="empty">${rawProjects.length ? "no matching projects" : "no .saipen projects found"}</div>`;
  } else {
    list.innerHTML = filtered.map(projectRowHtml).join("");
  }
  status.textContent = `${filtered.length}/${rawProjects.length} project(s)`;

  // Attach click / hover handlers to project rows
  list.querySelectorAll(".project-row").forEach((row) => {
    const root = row.getAttribute("data-root");
    row.addEventListener("click", (e) => {
      if (e.target.classList.contains("pin-btn")) {
        e.stopPropagation();
        const pinRoot = e.target.getAttribute("data-pin-root");
        window.pywebview.api.toggle_pin(pinRoot).then((updatedProjects) => {
          rawProjects = updatedProjects;
          if (selectedRoot === pinRoot) loadDetail(selectedRoot);
          render(rawProjects, isScanned);
        });
        return;
      }
      if (e.target.classList.contains("hide-btn") || e.target.classList.contains("unhide-btn")) {
        e.stopPropagation();
        const hRoot = e.target.getAttribute("data-hide-root") || e.target.getAttribute("data-unhide-root");
        if (e.target.classList.contains("hide-btn")) {
          window.pywebview.api.hide_project(hRoot).then((updatedProjects) => {
            rawProjects = updatedProjects;
            if (selectedRoot === hRoot) { selectedRoot = null; }
            render(rawProjects, isScanned);
          });
        } else {
          window.pywebview.api.unhide_project(hRoot).then((updatedProjects) => {
            rawProjects = updatedProjects;
            render(rawProjects, isScanned);
          });
        }
        return;
      }
      selectProject(root);
    });

    row.addEventListener("dblclick", () => {
      const path = root + "\\.saipen\\STATE.md";
      window.pywebview.api.read_file_text(path).then((text) => {
        if (text !== null) openFileViewer("STATE.md", path, text);
        else showToast("Can't read STATE.md", "error", 2000);
      });
    });

    row.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const phase = row.getAttribute("data-phase");
      if (phase) showContextMenu(e, root, phase);
    });
  });

  // Attach dblclick handler for sub-rows (opens sub STATE.md in file viewer)
  list.querySelectorAll(".sub-row").forEach((sr) => {
    const sp = sr.getAttribute("data-sub-path");
    if (sp) {
      sr.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        const path = sp + "\\STATE.md";
        const label = (sr.querySelector(".name") || {}).textContent || "sub";
        window.pywebview.api.read_file_text(path).then((text) => {
          if (text !== null) openFileViewer(label + " STATE.md", path, text);
          else showToast("Can't read STATE.md", "error", 2000);
        });
      });
    }
  });

  // If selected project is not in filtered list, clear selection
  // T-121: never clear the selection out from under an open edit form.
  // If the user is mid-edit, keep everything as-is -- the poll will
  // retry when they're done. Discarding typed work is worse than a
  // briefly stale list.
  if (selectedRoot && !filtered.some(p => p.root.toLowerCase() === selectedRoot.toLowerCase())) {
    if (!stateEditActive) {
      selectedRoot = null;
      renderDetailPane(null);
    }
  }

  // If selected project is in list, trigger detail load
  // T-121: skip the async get_project_detail + renderDetailPane chain
  // while the inline state editor is open. renderDetailPane's own
  // stateEditActive guard already protects it (T-066), but the guard
  // fires *inside* the callback -- after the API call and after the
  // callback is scheduled, by which point a change to stateEditActive
  // cannot be seen. Skipping here is deterministic.
  if (selectedRoot && !stateEditActive) {
    loadDetail(selectedRoot);
  } else if (selectedRoot) {
    // selectedRoot is set but we skipped loadDetail: the sidebar row
    // still needs its .selected class and handlers. applyProjectRowHandlers
    // already runs above (attaches to every row in the list), and
    // selectedRoot is unchanged, so the previously-attached handlers
    // and selection class are still current.
  } else if (filtered.length > 0) {
    selectProject(filtered[0].root);
  }
}

function normalizeDrive(pathStr) {
  if (!pathStr) return "";
  let s = pathStr.toUpperCase().trim();
  if (s.endsWith(":") && s.length === 2) return s + "\\";
  if (!s.endsWith("\\") && !s.endsWith("/")) return s + "\\";
  return s;
}

function renderDrives(drives, selectedRoots) {
  const bar = document.getElementById("drivesBar");
  if (!bar) return;

  // null = auto (scan every drive); [] = deliberately nothing selected.
  // The two are NOT the same on the Python side (scan(None) = auto,
  // scan([]) = no projects), so they must not both render as "all checked".
  const isAll = selectedRoots == null;
  const normSelected = selectedRoots && selectedRoots.length ? selectedRoots.map(normalizeDrive) : [];

  let html = '<span class="label">Drives:</span>';
  drives.forEach((drv) => {
    const normDrv = normalizeDrive(drv);
    const letter = drv.substring(0, 2);
    const checked = isAll || (normSelected && normSelected.includes(normDrv)) ? "checked" : "";
    html += `<label><input type="checkbox" class="drive-chk" value="${escapeHtml(drv)}" ${checked}> ${escapeHtml(letter)}</label>`;
  });

  if (selectedRoots && selectedRoots.length) {
    const customRoots = selectedRoots.filter((r) => {
      const norm = normalizeDrive(r);
      return !drives.some((d) => normalizeDrive(d) === norm);
    });
    if (customRoots.length) {
      html += '<span class="label" style="margin-left:8px;">Folders:</span>';
      customRoots.forEach((r) => {
        const short = r.length > 30 ? "..." + r.slice(-27) : r;
        html += `<span class="custom-root" data-root="${escapeHtml(r)}" title="${escapeHtml(r)}">${escapeHtml(short)} <span class="remove-root" style="cursor:pointer;color:var(--danger);margin-left:2px;">✕</span></span>`;
      });
    }
  }

  bar.innerHTML = html;

  bar.querySelectorAll(".drive-chk").forEach((chk) => {
    chk.addEventListener("change", () => {
      let selected = Array.from(bar.querySelectorAll(".drive-chk:checked")).map((el) => el.value);
      const currentCustomRoots = (selectedRoots || []).filter((r) => {
        const norm = normalizeDrive(r);
        return !drives.some((d) => normalizeDrive(d) === norm);
      });
      selected = selected.concat(currentCustomRoots);
      const newRoots = (selected.length === drives.length && currentCustomRoots.length === 0) ? null : selected;
      document.getElementById("status").textContent = "rescanning...";
      document.getElementById("projectList").innerHTML = '<div class="empty">scanning...</div>';
      window.pywebview.api.set_scan_roots(newRoots).then((projects) => {
        render(projects, true);
      });
    });
  });

  bar.querySelectorAll(".remove-root").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      const rootToRemove = el.parentElement.getAttribute("data-root");
      if (!rootToRemove) return;
      const remaining = selectedRoots.filter((r) => normalizeDrive(r) !== normalizeDrive(rootToRemove));
      const newRoots = remaining.length ? remaining : null;
      document.getElementById("status").textContent = "rescanning...";
      document.getElementById("projectList").innerHTML = '<div class="empty">scanning...</div>';
      window.pywebview.api.set_scan_roots(newRoots).then((projects) => {
        render(projects, true);
      });
    });
  });
}

function updateScanIndicator(scanning) {
  const ind = document.getElementById("scanIndicator");
  if (!ind) return;
  ind.style.display = scanning ? "inline" : "none";

  const wrap = document.getElementById("scanProgressWrap");
  if (!wrap) return;
  if (!scanning) {
    wrap.style.display = "none";
    return;
  }
  wrap.style.display = "inline-flex";
  if (window.pywebview && window.pywebview.api && window.pywebview.api.get_scan_progress) {
    window.pywebview.api.get_scan_progress().then((p) => {
      const fill = document.getElementById("scanProgressFill");
      if (fill) {
        const pct = Math.min(100, Math.max(0, p.pct || 0));
        fill.style.width = pct + "%";
        if (p.root) wrap.title = "Scanning " + p.root;
      }
    }).catch((e) => console.error("scan progress fetch failed:", e));
  }
}

function updateErrorBadge() {
  const badge = document.getElementById("errorBadge");
  if (!badge || !window.pywebview || !window.pywebview.api) return;
  window.pywebview.api.get_scan_errors().then((errors) => {
    if (errors && errors.length) {
      badge.textContent = "!" + errors.length;
      badge.style.display = "inline";
      badge.title = errors.join(" | ");
    } else {
      badge.style.display = "none";
    }
  }).catch((e) => console.error("wtBadge update failed:", e));
}

// WT badge click: scroll to or toggle linked worktrees section
const wtBadge = document.getElementById("wtBadge");
if (wtBadge) {
  wtBadge.addEventListener("click", () => {
    const wtSection = document.querySelector(".wt-section");
    if (wtSection) {
      wtSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else if (linkedWorktrees.length) {
      // Not shown inline — show in a phase overlay style
      showToast(linkedWorktrees.length + " linked worktree(s) found — run 'saipen set' to add .saipen/", "info", 4000);
    }
  });
}

document.getElementById("errorBadge")?.addEventListener("click", () => {
  if (!window.pywebview || !window.pywebview.api) return;
  window.pywebview.api.get_scan_errors().then((errors) => {
    if (errors && errors.length) {
      showToast(errors.length + " scan error(s) — see Scan Errors card in detail pane", "error", 6000);
    }
    // Show and scroll to the error card
    const errorCard = document.getElementById("errorCard");
    if (errorCard) {
      errorCard.style.display = "block";
      // Ensure it's expanded (not collapsed)
      const collapsible = errorCard.querySelector(".collapsible");
      if (collapsible) {
        collapsible.classList.remove("collapsed");
        const icon = collapsible.querySelector(".collapse-icon");
        if (icon) icon.textContent = "▼";
      }
      // Fetch fresh error log and fill the body
      window.pywebview.api.get_scan_error_log().then((log) => {
        const body = errorCard.querySelector(".collapsible-body");
        if (body && log) {
          body.innerHTML = log.slice(0, 20).map(e =>
            `<div class="error-item"><span class="error-time">${escapeHtml(formatLocalTime(e.time))}</span><span class="error-message">${escapeHtml(e.message)}</span></div>`
          ).join("");
        }
      }).catch((e) => console.error("updateErrorBadge failed:", e));
      // Scroll the error card into view
      setTimeout(() => {
        errorCard.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
    }
  }).catch((e) => console.error("updateErrorBadge scroll failed:", e));
});

// Whether the native window is actually on screen. Driven from Python
// (MainWindow._notify_visibility) because a pywebview hide() is a native window
// hide that the Page Visibility API never reports -- document.hidden stays
// false the whole time the tray app is put away.
//
// Starts true: if the notify bridge ever breaks, the app degrades to the old
// always-poll behaviour rather than to a window that silently never refreshes.
let windowVisible = true;

window.__saipenSetVisible = function (visible) {
  const was = windowVisible;
  windowVisible = !!visible;
  // Catch up the moment we become visible, instead of showing whatever was on
  // screen 5 seconds before the user hit the hotkey and waiting out the timer.
  if (windowVisible && !was) poll();
};

let fileChangeDebounce = null;
window.onSaipenFileChanged = function(root, fileName) {
  if (fileChangeDebounce) clearTimeout(fileChangeDebounce);
  fileChangeDebounce = setTimeout(() => {
    // The backend already re-read the changed project (one targeted refresh,
    // T-124) before pushing this notification. Reading the fresh cache here --
    // NOT calling refresh_known() again -- is the one-refresh-per-event rule;
    // a second full re-parse of every project for one file change is the
    // defect T-124 removes.
    window.pywebview.api.get_projects().then(projects => {
      render(projects, true);
      renderLinkedWorktrees();
    }).catch(() => {});
  }, 100);
};

function poll() {
  // Hidden means nobody can see the result, and the work is not free:
  // refresh_known() re-reads every known project's .saipen/ files and render()
  // rebuilds the detail pane's innerHTML. On a machine with a large scan that
  // was hundreds of ms of disk I/O every 5s, forever, for an invisible window.
  if (!windowVisible) return;
  // refresh_known() re-reads only the .saipen/ files of projects we already
  // know (no drive walk, git skipped -> ~1.7ms/project), so edits show up in
  // seconds instead of waiting out rescan_interval, and the sidebar can no
  // longer disagree with the detail pane's live read (T-071 + T-072).
  Promise.all([window.pywebview.api.get_status(), window.pywebview.api.refresh_known()])
    .then(([status, projects]) => {
      render(projects, status.scanned);
      renderLinkedWorktrees();
      updateScanIndicator(status.scanning);
      pollAgentOutput();
    })
    .catch(() => {
      const statusEl = document.getElementById("status");
      if (statusEl) statusEl.textContent = "poll failed";
    });
  updateErrorBadge();
}

document.getElementById("rescanBtn")?.addEventListener("click", () => {
  document.getElementById("status").textContent = "rescanning...";
  updateScanIndicator(true);
  window.pywebview.api.rescan().then((projects) => {
    render(projects, true);
    renderLinkedWorktrees();
    updateScanIndicator(false);
    updateErrorBadge();
  }).catch(() => {
    document.getElementById("status").textContent = "rescan failed";
    updateScanIndicator(false);
  });
});

document.getElementById("browseBtn")?.addEventListener("click", () => {
  document.getElementById("status").textContent = "selecting folder...";
  window.pywebview.api.browse_folder().then((projects) => {
    render(projects, true);
    renderLinkedWorktrees();
    updateErrorBadge();
    window.pywebview.api.get_config().then((cfg) => {
      window.pywebview.api.get_local_drives().then((drives) => {
        renderDrives(drives, cfg.scan_roots);
      });
    });
  }).catch(() => {
    document.getElementById("status").textContent = "browse failed";
  });
});

function renderSearchResults(query, results) {
  const body = document.getElementById("searchOverlayBody");
  const status = document.getElementById("searchOverlayStatus");
  if (!body || !status) return;

  showSearchOverlay();

  if (!results || !results.length) {
    body.innerHTML = '<div class="empty">no results for "' + escapeHtml(query) + '"</div>';
    status.textContent = "0 results";
    const toolbarStatus = document.getElementById("status");
    if (toolbarStatus) toolbarStatus.textContent = "0 results (0 items)";
    const countEl = document.getElementById("searchOverlayCount");
    if (countEl) countEl.textContent = "";
    const cycleEl = document.getElementById("searchOverlayCycle");
    if (cycleEl) cycleEl.textContent = "";
    return;
  }

  let html = '<div class="search-results-header">Results for "' + escapeHtml(query) + '"</div>';
  results.forEach(function(r) {
    const matchTag = r.matched_field === 'name' ? 'name-match' : 'ticket-match';
    html += '<div class="search-project-group" data-root="' + escapeHtml(r.root) + '">';
    html += '<div class="search-project-head ' + matchTag + '">';
    html += '<span class="name">' + highlightMatch(r.name, query) + '</span>';
    html += '<span class="phase phase-' + escapeHtml(r.phase) + '">' + escapeHtml(r.phase) + '</span>';
    if (r.matched_tickets && r.matched_tickets.length) {
      html += '<span class="search-ticket-count">' + r.matched_tickets.length + ' ticket(s)</span>';
    }
    html += '</div>';
    if (r.matched_tickets && r.matched_tickets.length) {
      r.matched_tickets.forEach(function(t) {
        html += '<div class="search-ticket-row" data-root="' + escapeHtml(r.root) + '" data-section="' + escapeHtml(t.section) + '">';
        html += '<span class="search-ticket-section section-' + escapeHtml(t.section.toLowerCase()) + '">[' + escapeHtml(t.section) + ']</span>';
        html += '<span class="search-ticket-id">' + highlightMatch(t.id, query) + '</span>';
        html += '<span class="search-ticket-desc">' + highlightMatch(t.desc, query) + '</span>';
        html += '</div>';
      });
    }
    // Sub-agent matched tickets
    if (r.sub_matched_tickets && r.sub_matched_tickets.length) {
      r.sub_matched_tickets.forEach(function(t) {
        html += '<div class="search-ticket-row search-sub-ticket-row" data-root="' + escapeHtml(r.root) + '" data-section="' + escapeHtml(t.section) + '">';
        html += '<span class="search-sub-label">' + escapeHtml(t.sub_name) + '</span>';
        html += '<span class="search-ticket-section section-' + escapeHtml(t.section.toLowerCase()) + '">[' + escapeHtml(t.section) + ']</span>';
        html += '<span class="search-ticket-id">' + highlightMatch(t.id, query) + '</span>';
        html += '<span class="search-ticket-desc">' + highlightMatch(t.desc, query) + '</span>';
        html += '</div>';
      });
    }
    html += '</div>';
  });
  body.innerHTML = html;
  status.textContent = results.length + ' project(s) match';
  // Update header count and cycle status
  const countEl = document.getElementById("searchOverlayCount");
  const cycleEl = document.getElementById("searchOverlayCycle");
  const toolbarStatus = document.getElementById("status");
  if (countEl) {
    const items = body.querySelectorAll(".search-project-head, .search-ticket-row");
    countEl.textContent = "\u2014 " + items.length + " items";
    // Update toolbar status bar with project + item counts
    if (toolbarStatus) {
      toolbarStatus.textContent = results.length + " project(s) match (" + items.length + " items)";
    }
  }
  if (cycleEl) cycleEl.textContent = "";

  // Wire click: project head -> select project + close overlay
  body.querySelectorAll(".search-project-head").forEach(function(head) {
    head.addEventListener("click", function() {
      const root = head.parentElement.getAttribute("data-root");
      if (root) {
        hideSearchOverlay();
        selectProject(root);
      }
    });
  });
  // Wire click: ticket row -> select project, expand section, close overlay
  body.querySelectorAll(".search-ticket-row").forEach(function(row) {
    row.addEventListener("click", function() {
      const root = row.getAttribute("data-root");
      const section = row.getAttribute("data-section");
      if (root) {
        _expandSectionAfterLoad = section || null;
        hideSearchOverlay();
        selectProject(root);
      }
    });
  });

  // Collect all clickable items for F3/Shift+F3 cycling
  searchItems = [];
  body.querySelectorAll(".search-project-head, .search-ticket-row").forEach(function(el) {
    searchItems.push(el);
  });
  searchItemIndex = -1;
  // Highlight the first item
  if (searchItems.length) {
    cycleSearchResult(1);
  }
}

// --- Phase overlay: double-click on detail phase bar -> floating list of all projects in that phase ---
function showPhaseOverlay(phase) {
  const body = document.getElementById("searchOverlayBody");
  const status = document.getElementById("searchOverlayStatus");
  const countEl = document.getElementById("searchOverlayCount");
  const cycleEl = document.getElementById("searchOverlayCycle");
  if (!body || !status) return;

  const phaseProjects = (rawProjects || []).filter((p) => p.phase === phase);

  // Reset search overlay state so F3 cycling is disabled
  searchItems = [];
  searchItemIndex = -1;
  if (cycleEl) cycleEl.textContent = "";

  // Update overlay title
  const titleEl = document.querySelector(".search-overlay-title");
  if (titleEl) titleEl.textContent = phase + " Phase";

  showSearchOverlay();

  if (!phaseProjects.length) {
    body.innerHTML = '<div class="empty">no projects in phase ' + escapeHtml(phase) + '</div>';
    status.textContent = "0 projects";
    if (countEl) countEl.textContent = "";
    return;
  }

  // Sort by updated descending (newest first)
  phaseProjects.sort((a, b) => {
    const ta = a.updated ? new Date(_ensureTz(a.updated)).getTime() : 0;
    const tb = b.updated ? new Date(_ensureTz(b.updated)).getTime() : 0;
    return tb - ta;
  });

  body.innerHTML = phaseProjects.map((p) =>
    `<div class="search-project-group" data-root="${escapeHtml(p.root)}">
      <div class="search-project-head name-match" style="border-left-color:var(--accentTeal);">
        <span class="name">${escapeHtml(p.name)}</span>
        ${p.git_branch ? `<span class="git-badge ${p.git_dirty ? 'dirty' : ''}" style="font-size:8px;flex:0 0 auto;">⎇ ${escapeHtml(p.git_branch)}${p.git_dirty ? '*' : ''}</span>` : ''}
        <span class="phase phase-${escapeHtml(p.phase)}">${escapeHtml(p.phase)}</span>
        <span class="updated" style="color:var(--textMuted);font-size:8px;flex:0 0 auto;">${escapeHtml(formatLocalTime(p.updated))}</span>
      </div>
      <div style="padding:0 6px 4px 6px;font-size:10px;color:var(--textSecondary);">${escapeHtml(p.task)}</div>
    </div>`
  ).join("");

  status.textContent = phase + " phase \u2014 " + phaseProjects.length + " project(s)";
  if (countEl) countEl.textContent = "";

  // Add "Filter sidebar" button in the footer
  const footer = document.querySelector(".search-overlay-footer");
  if (footer) {
    // Remove any previous filter button (in case overlay is re-opened)
    const oldBtn = footer.querySelector(".overlay-filter-btn");
    if (oldBtn) oldBtn.remove();
    const filterBtn = document.createElement("button");
    filterBtn.className = "overlay-filter-btn";
    filterBtn.textContent = "Filter sidebar";
    filterBtn.title = "Show only " + phase + " projects in sidebar (keeps overlay open)";
    filterBtn.style.cssText = "font-size:9px;padding:0 6px;height:16px;line-height:12px;margin-left:6px;color:var(--accentTeal);border-color:var(--accentTeal);";
    footer.appendChild(filterBtn);
    filterBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      currentFilter = phase;
      const fs = document.getElementById("filterSelect");
      if (fs) {
        if (!fs.querySelector(`option[value="${phase}"]`)) {
          const opt = document.createElement("option");
          opt.value = phase;
          opt.textContent = phase;
          opt.setAttribute("data-dynamic", "true");
          fs.appendChild(opt);
        }
        fs.value = phase;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
          window.pywebview.api.save_view_config({ filter_phase: phase });
        }
      }
      render(rawProjects, isScanned);
    });
  }

  // Wire click to select project and close
  body.querySelectorAll(".search-project-head").forEach(function(head) {
    head.addEventListener("click", function() {
      const root = head.parentElement.getAttribute("data-root");
      if (root) {
        hideSearchOverlay();
        selectProject(root);
      }
    });
  });
}

// Hook for deep search: expand a specific ticket section after detail loads
let _expandSectionAfterLoad = null;

const searchInput = document.getElementById("searchInput");
if (searchInput) {
  searchInput.addEventListener("input", () => {
    searchQuery = searchInput.value;
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
      window.pywebview.api.save_view_config({ search_query: searchQuery });
    }
    if (searchQuery.trim() && deepSearchMode && window.pywebview && window.pywebview.api) {
      // Deep search: debounced, query backend for ticket + project matches
      clearTimeout(deepSearchTimer);
      deepSearchTimer = setTimeout(function() {
        window.pywebview.api.quick_search(searchQuery.trim()).then(function(results) {
          renderSearchResults(searchQuery.trim(), results);
        }).catch(function() {
          render(rawProjects, isScanned);
        });
      }, 300);
    } else {
      hideSearchOverlay();
      render(rawProjects, isScanned);
    }
  });
}

const filterSelect = document.getElementById("filterSelect");
if (filterSelect) {
  filterSelect.addEventListener("change", () => {
    currentFilter = filterSelect.value;
    // Remove dynamically-added phase options when switching to standard filter
    if (["ALL", "ACTIVE", "DONE", "BLOCKED"].includes(currentFilter)) {
      filterSelect.querySelectorAll("option[data-dynamic]").forEach((o) => o.remove());
    }
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
      window.pywebview.api.save_view_config({ filter_phase: currentFilter });
    }
    render(rawProjects, isScanned);
  });
}

// Deep search mode toggle
const deepSearchChk = document.getElementById("deepSearchChk");
if (deepSearchChk) {
  deepSearchChk.addEventListener("change", () => {
    deepSearchMode = deepSearchChk.checked;
    if (!deepSearchMode) {
      // Deep search turned off — just hide overlay, let caller handle re-render
      const overlay2 = document.getElementById("searchOverlay");
      if (overlay2) overlay2.style.display = "none";
    }
    // Re-trigger search if query is non-empty
    if (searchInput && searchInput.value.trim()) {
      searchInput.dispatchEvent(new Event("input"));
    }
  });
}

const sortSelect = document.getElementById("sortSelect");
if (sortSelect) {
  sortSelect.addEventListener("change", () => {
    currentSort = sortSelect.value;
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.set_sort_order(currentSort).then(() => {
        render(rawProjects, isScanned);
      });
    }
  });
}

let excludeTimer = null;
const excludeInput = document.getElementById("excludeInput");
if (excludeInput) {
  excludeInput.addEventListener("input", () => {
    clearTimeout(excludeTimer);
    excludeTimer = setTimeout(() => {
      const dirs = excludeInput.value.split(",").map((s) => s.trim()).filter(Boolean);
      if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.set_exclude_dirs(dirs).then((projects) => {
          render(projects, true);
        });
      }
    }, 600);
  });
}

const compactModeChk = document.getElementById("compactModeChk");
if (compactModeChk) {
  compactModeChk.addEventListener("change", () => {
    const list = document.getElementById("projectList");
    if (compactModeChk.checked) {
      list.classList.add("compact");
    } else {
      list.classList.remove("compact");
    }
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
      window.pywebview.api.save_view_config({ compact_mode: compactModeChk.checked });
    }
  });
}

const autoScanChk = document.getElementById("autoScanChk");
if (autoScanChk) {
  autoScanChk.addEventListener("change", () => {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.set_auto_scan(autoScanChk.checked);
    }
  });
}

const showHiddenChk = document.getElementById("showHiddenChk");
if (showHiddenChk) {
  showHiddenChk.addEventListener("change", () => {
    showHidden = showHiddenChk.checked;
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
      window.pywebview.api.save_view_config({ show_hidden: showHidden });
    }
    if (showHidden) {
      selectedRoot = null;
      renderDetailPane(null);
    }
    render(rawProjects, isScanned);
  });
}

const quitBtn = document.getElementById("quitBtn");
if (quitBtn) {
  quitBtn.addEventListener("click", () => {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.quit) {
      window.pywebview.api.quit();
    }
  });
}

const minimizeBtn = document.getElementById("minimizeBtn");
if (minimizeBtn) {
  minimizeBtn.addEventListener("click", () => {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.minimize_window) {
      window.pywebview.api.minimize_window();
    }
  });
}

// Close hides to tray; Exit (quitBtn) ends the process. Both existed on the Python
// side -- api.close_window() has always hidden to tray -- but nothing in the UI ever
// called it, so the only exit-shaped control was the one that kills the app.
const closeBtn = document.getElementById("closeBtn");
if (closeBtn) {
  closeBtn.addEventListener("click", () => {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.close_window) {
      window.pywebview.api.close_window();
    }
  });
}

const maximizeBtn = document.getElementById("maximizeBtn");
if (maximizeBtn) {
  maximizeBtn.addEventListener("click", () => {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.maximize_window) {
      window.pywebview.api.maximize_window();
    }
  });
}

let collapseHintAcknowledged = false;

function showCollapseHint() {
  const hint = document.getElementById("collapseHint");
  if (!hint) return;
  const show = document.body.classList.contains("collapsed") && !collapseHintAcknowledged;
  hint.style.display = show ? "flex" : "none";
}

function toggleCollapse() {
  const isCollapsed = document.body.classList.toggle("collapsed");
  const btn = document.getElementById("togglePanelBtn");
  if (btn) btn.textContent = isCollapsed ? "▼" : "▲";
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
    window.pywebview.api.save_view_config({ top_panel_collapsed: isCollapsed });
  }
  showCollapseHint();
  // The titlebar used to be toggled from here, so collapsed mode looked like a
  // floating panel. It is off by default now (config "frameless"), so this was
  // a blind flip that ADDED a titlebar on collapse -- the opposite of what it
  // was written to do, and a duplicate of the toolbar's own window buttons.
}

const togglePanelBtn = document.getElementById("togglePanelBtn");
if (togglePanelBtn) {
  togglePanelBtn.addEventListener("click", toggleCollapse);
}

// Settings panel
const settingsModal = document.getElementById("settingsModal");
// ===== Wiki / Help system =====
let _wikiPages = [];
let _currentWikiPage = null;

function openWiki() {
  const modal = document.getElementById("wikiModal");
  if (!modal) return;
  modal.style.display = "flex";
  loadWikiPages();
}

function closeWiki() {
  document.getElementById("wikiModal").style.display = "none";
}

function loadWikiPages() {
  const api = window.pywebview && window.pywebview.api;
  if (!api) return;
  document.getElementById("wikiLoading").style.display = "block";
  document.getElementById("wikiMarkdown").innerHTML = "";
  api.get_wiki_pages().then((pages) => {
    _wikiPages = pages || [];
    const list = document.getElementById("wikiTocList");
    if (!list) return;
    list.innerHTML = _wikiPages.map((p) =>
      `<div class="wiki-toc-item" data-wiki-id="${escapeHtml(p.id)}">${escapeHtml(p.title)}</div>`
    ).join("");
    // Wire TOC click handlers
    list.querySelectorAll(".wiki-toc-item").forEach((item) => {
      item.addEventListener("click", () => {
        const id = item.getAttribute("data-wiki-id");
        if (id) navigateToWikiPage(id);
      });
    });
    // Load first page if none loaded yet
    if (!_currentWikiPage && _wikiPages.length) {
      navigateToWikiPage(_wikiPages[0].id);
    }
  }).catch((e) => {
    console.error("loadWikiPages failed:", e);
    document.getElementById("wikiLoading").style.display = "none";
    document.getElementById("wikiMarkdown").innerHTML = "<p style='color:var(--danger)'>Failed to load wiki.</p>";
  });
}

function navigateToWikiPage(pageId) {
  _currentWikiPage = pageId;
  const api = window.pywebview && window.pywebview.api;
  if (!api) return;
  document.getElementById("wikiLoading").style.display = "block";
  document.getElementById("wikiMarkdown").innerHTML = "";
  // Highlight active TOC item
  document.querySelectorAll(".wiki-toc-item").forEach((el) => {
    el.classList.toggle("active", el.getAttribute("data-wiki-id") === pageId);
  });
  api.get_wiki_page(pageId).then((page) => {
    document.getElementById("wikiLoading").style.display = "none";
    if (!page || !page.content) {
      document.getElementById("wikiMarkdown").innerHTML = "<p style='color:var(--textMuted)'>Page not found.</p>";
      return;
    }
    document.getElementById("wikiMarkdown").innerHTML = renderWikiMarkdown(page.content);
    document.getElementById("wikiTitle").textContent = page.title || "Wiki";
  }).catch((e) => {
    console.error("navigateToWikiPage failed:", e);
    document.getElementById("wikiLoading").style.display = "none";
    document.getElementById("wikiMarkdown").innerHTML = "<p style='color:var(--danger)'>Failed to load page.</p>";
  });
}

function renderWikiMarkdown(md) {
  if (!md) return "";
  let html = md;
  // ---- Extract fenced code blocks BEFORE escapeHtml ----
  const codeBlocks = [];
  let cbIdx = 0;
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (m, lang, code) => {
    const idx = cbIdx++;
    codeBlocks[idx] = { lang, code: code.replace(/^\n|\n$/g, "") };
    return `%%CODEBLOCK_${idx}%%`;
  });
  // ---- Extract inline code BEFORE escapeHtml ----
  const inlineCodes = [];
  let icIdx = 0;
  html = html.replace(/`([^`]+)`/g, (m, code) => {
    const idx = icIdx++;
    inlineCodes[idx] = code;
    return `%%INLINECODE_${idx}%%`;
  });
  // ---- Escape HTML to prevent XSS ----
  html = escapeHtml(html);
  // ---- Restore code blocks ----
  codeBlocks.forEach((cb, i) => {
    const escaped = escapeHtml(cb.code);
    html = html.replace(`%%CODEBLOCK_${i}%%`, `<pre><code${cb.lang ? ' class="lang-' + escapeHtml(cb.lang) + '"' : ''}>${escaped}</code></pre>`);
  });
  // ---- Restore inline code ----
  inlineCodes.forEach((code, i) => {
    const escaped = escapeHtml(code);
    html = html.replace(`%%INLINECODE_${i}%%`, `<code>${escaped}</code>`);
  });
  // ---- Markdown syntax conversion (safe on escaped text) ----
  // Headers
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  // HR
  html = html.replace(/^---$/gm, "<hr>");
  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italic
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  // Links (text is already escaped, so this is safe)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
  // Tables: collect rows, rebuild as HTML
  const lines = html.split("\n");
  let inTable = false;
  let tableRows = [];
  let tableIsHeader = false;
  const resultLines = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\|/.test(line) && /\|$/.test(line)) {
      const cells = line.split("|").filter((c, j) => j > 0 && j < line.split("|").length - 1).map(c => c.trim());
      if (!inTable) {
        inTable = true;
        tableRows = [];
        tableIsHeader = false;
      }
      if (cells.length && /^[-\s:]+$/.test(cells[0])) {
        tableIsHeader = true;
        continue;
      }
      const tag = tableIsHeader ? "th" : "td";
      tableRows.push("<tr>" + cells.map(c => `<${tag}>${c}</${tag}>`).join("") + "</tr>");
      tableIsHeader = false; // only first post-separator row is header
      // Emit at end of table
      if (i + 1 >= lines.length || !/^\|/.test(lines[i + 1])) {
        resultLines.push("<table>" + tableRows.join("") + "</table>");
        inTable = false;
      }
    } else {
      if (inTable) {
        inTable = false;
      }
      resultLines.push(line);
    }
  }
  html = resultLines.join("\n");
  // Unordered lists
  html = html.replace(/^\* (.+)$/gm, "<li>$1</li>");
  html = html.replace(/^\- (.+)$/gm, "<li>$1</li>");
  // Ordered lists
  html = html.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");
  // Wrap consecutive <li> in <ul>
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");
  // Blockquotes
  html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");
  // Paragraphs (any line not already a block element)
  html = html.replace(/^(?!<(?:\/?[hupolbtd]|table|thead|tbody|tr|th|td|pre|code)|%%|\s*$)(.+)$/gm, "<p>$1</p>");
  // Deduplicate empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, "");
  // Clean nested <p> inside block elements
  html = html.replace(/<(li|th|td|h[1-3])><p>/g, "<$1>");
  html = html.replace(/<\/p><\/(li|th|td|h[1-3])>/g, "</$1>");
  return html;
}

function openQuickHelp() {
  document.getElementById("helpOverlay").style.display = "flex";
}
function closeQuickHelp() {
  document.getElementById("helpOverlay").style.display = "none";
}

const settingsBtn = document.getElementById("settingsBtn");

function openSettings() {
  Promise.all([window.pywebview.api.get_config(), window.pywebview.api.get_autostart_enabled()]).then(([cfg, autostart]) => {
    document.getElementById("setZoomLevel").value = String(cfg.zoom_level || 1.0);
    document.getElementById("setHotkeys").value = (cfg.hotkeys || []).join(", ");
    // Fallback is alt+f14, NOT ctrl+q: ctrl+q was freed in 4d291a0 because a
    // global binding hijacks it in every app. Handing it back here would put
    // it straight back into the config the migration just cleaned.
    document.getElementById("setSnapHotkey").value = Array.isArray(cfg.snap_hotkey) ? cfg.snap_hotkey.join(", ") : (cfg.snap_hotkey || "alt+f14");
    document.getElementById("setScanDepth").value = cfg.scan_depth || 6;
    document.getElementById("setScanDelay").value = cfg.scan_delay_ms != null ? cfg.scan_delay_ms : 10;
    document.getElementById("setRescanInterval").value = Math.round((cfg.rescan_interval || 300) / 60);
    document.getElementById("setAutostart").checked = !!autostart;
    document.getElementById("setShowOnLaunch").checked = cfg.show_on_launch !== false;
    document.getElementById("setAlwaysOnTop").checked = cfg.always_on_top !== false;
    // Inverted on purpose: the config stores "frameless", the checkbox offers
    // the titlebar. Default is frameless, so this starts unchecked.
    document.getElementById("setNativeTitlebar").checked = cfg.frameless === false;
    document.getElementById("setFontFamily").value = cfg.font_family || "Verdana_m1";
    document.getElementById("setFlashChanges").checked = cfg.flash_changes !== false;
    document.getElementById("setFileViewerDefault").value = cfg.file_viewer_default || "source";
    document.getElementById("setLocale").value = cfg.locale || "en";
    // Remember what is on screen so closing without saving puts it back --
    // the picker previews live, and a preview that survives Cancel is not a
    // preview, it is an unannounced save.
    themeBeforeSettings = currentTheme || cfg.theme || "";
    const themePicker = document.getElementById("setTheme");
    if (themePicker) {
      window.pywebview.api.get_themes().then((list) => {
        themePicker.innerHTML = (list || []).map((th) =>
          '<option value="' + escapeHtml(th.slug) + '">' + escapeHtml(th.label) + '</option>'
        ).join("");
        themePicker.value = themeBeforeSettings || "goldendefault";
      });
    }
    hydrateDOM(cfg.locale || "en");
    // Render custom commands
    const cmdList = document.getElementById("customCommandsList");
    if (cmdList) {
      const cmds = cfg.custom_commands || [];
      cmdList.innerHTML = cmds.map((c, i) =>
        `<div class="custom-cmd-row" style="display:flex; gap:2px; align-items:center;">
          <input type="text" class="custom-cmd-label" value="${escapeHtml(c.label || '')}" placeholder="Label" style="flex:1; width:auto;" data-idx="${i}">
          <input type="text" class="custom-cmd-command" value="${escapeHtml(c.command || '')}" placeholder="Command" style="flex:2; width:auto;" data-idx="${i}">
          <button class="remove-cmd-btn" data-idx="${i}" style="font-size:9px; padding:0 4px; min-width:20px;" title="Remove command">✕</button>
        </div>`
      ).join("");
      // Wire remove buttons
      cmdList.querySelectorAll(".remove-cmd-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          btn.parentElement.remove();
        });
      });
    }
    // Wire "+ Add command" button
    const addCmdBtn = document.getElementById("addCustomCmdBtn");
    if (addCmdBtn) {
      addCmdBtn.onclick = () => {
        const list = document.getElementById("customCommandsList");
        if (!list) return;
        const row = document.createElement("div");
        row.className = "custom-cmd-row";
        row.style.cssText = "display:flex; gap:2px; align-items:center;";
        row.innerHTML = `
          <input type="text" class="custom-cmd-label" placeholder="Label" style="flex:1; width:auto;">
          <input type="text" class="custom-cmd-command" placeholder="Command" style="flex:2; width:auto;">
          <button class="remove-cmd-btn" style="font-size:9px; padding:0 4px; min-width:20px;" title="Remove command">✕</button>
        `;
        row.querySelector(".remove-cmd-btn").onclick = () => row.remove();
        list.appendChild(row);
      };
    }
    document.getElementById("saveSettingsBtn").textContent = "Save";
    settingsModal.style.display = "flex";
    window.pywebview.api.get_local_drives().then((drives) => {
      renderDrives(drives, cfg.scan_roots);
    });
  });
}

function closeSettings() {
  settingsModal.style.display = "none";
  // Undo a live preview the user did not save.
  if (themeBeforeSettings && themeBeforeSettings !== currentTheme) {
    window.pywebview.api.get_theme_tokens(themeBeforeSettings).then(applyTheme);
  }
}

if (settingsBtn) settingsBtn.addEventListener("click", openSettings);

document.getElementById("closeSettingsBtn")?.addEventListener("click", closeSettings);    // --- Locale change handler ---
    document.getElementById("setLocale")?.addEventListener("change", (e) => {
      // Preview translation without saving
      hydrateDOM(e.target.value);
    });

    document.getElementById("swapBtn")?.addEventListener("click", () => {
  const isSwapped = document.body.classList.toggle("swapped");
  const btn = document.getElementById("swapBtn");
  if (btn) {
    btn.textContent = isSwapped ? "⇆" : "⇄";
    btn.title = isSwapped ? "Restore default layout" : "Swap sidebar/detail pane position";
  }
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
    window.pywebview.api.save_view_config({ layout_swap: isSwapped });
  }
});

document.getElementById("helpBtn")?.addEventListener("click", openWiki);
document.getElementById("closeWikiBtn")?.addEventListener("click", closeWiki);
document.getElementById("wikiOverviewBtn")?.addEventListener("click", openQuickHelp);
document.getElementById("closeHelpOverlayBtn")?.addEventListener("click", closeQuickHelp);

const wikiModal = document.getElementById("wikiModal");
if (wikiModal) {
  wikiModal.addEventListener("mousedown", (e) => {
    if (e.target === wikiModal) closeWiki();
  });
}

const helpOverlay = document.getElementById("helpOverlay");
if (helpOverlay) {
  helpOverlay.addEventListener("mousedown", (e) => {
    if (e.target === helpOverlay) closeQuickHelp();
  });
}

settingsModal?.addEventListener("mousedown", (e) => {
  if (e.target === settingsModal) closeSettings();
});

document.getElementById("saveSettingsBtn")?.addEventListener("click", () => {
  const zoomLevel = parseFloat(document.getElementById("setZoomLevel").value) || 1.0;
  const hotkeys = document.getElementById("setHotkeys").value.split(",").map((s) => s.trim()).filter(Boolean);
  const snapHotkey = document.getElementById("setSnapHotkey").value.split(",").map((s) => s.trim()).filter(Boolean);
  const scanDepth = parseInt(document.getElementById("setScanDepth").value, 10) || 6;
  const scanDelay = parseInt(document.getElementById("setScanDelay").value, 10) || 0;
  const rescanMinutes = parseInt(document.getElementById("setRescanInterval").value, 10) || 5;
  const autostart = document.getElementById("setAutostart").checked;
  const showOnLaunch = document.getElementById("setShowOnLaunch").checked;
  const alwaysOnTop = document.getElementById("setAlwaysOnTop").checked;
  const frameless = !document.getElementById("setNativeTitlebar").checked;
  const fontFamily = document.getElementById("setFontFamily").value.trim();
  const flashChanges = document.getElementById("setFlashChanges").checked;
  const localeVal = document.getElementById("setLocale").value;
  const locale = document.getElementById("setLocale").value;
  const fvd = document.getElementById("setFileViewerDefault").value;
  const themeSlug = document.getElementById("setTheme")?.value || currentTheme;

  // Read custom commands from UI
  const customCommands = [];
  const cmdLabels = document.querySelectorAll(".custom-cmd-label");
  const cmdCommands = document.querySelectorAll(".custom-cmd-command");
  for (let ci = 0; ci < Math.min(cmdLabels.length, cmdCommands.length); ci++) {
    const lbl = cmdLabels[ci].value.trim();
    const cmd = cmdCommands[ci].value.trim();
    if (lbl && cmd) customCommands.push({ label: lbl, command: cmd });
  }

  const saveBtn = document.getElementById("saveSettingsBtn");
  const api = window.pywebview.api;
  saveBtn.textContent = "Saving...";
  saveBtn.disabled = true;
  const resetHint = document.getElementById("resetCollapseHint").checked;
  const ackPromise = resetHint
    ? api.save_view_config({ collapse_hint_acknowledged: false })
    : Promise.resolve();

  // Timeout guard: if API calls don't resolve in 10s, force-unlock
  let saveTimedOut = false;
  const saveTimeout = setTimeout(() => {
    saveTimedOut = true;
    saveBtn.textContent = "Save timed out -- retry?";
    saveBtn.disabled = false;
  }, 10000);

  ackPromise.then(() => {
    if (saveTimedOut) return;
    if (resetHint) collapseHintAcknowledged = false;
    return Promise.all([
      api.set_zoom_level(zoomLevel),
      hotkeys.length ? api.set_hotkeys(hotkeys) : Promise.resolve(),
      snapHotkey.length ? api.set_snap_hotkey(snapHotkey) : Promise.resolve(),
      api.set_scan_tuning(scanDepth, scanDelay, rescanMinutes * 60),
      api.set_autostart_enabled(autostart),
      api.set_always_on_top(alwaysOnTop),
      api.set_frameless(frameless),
      api.set_locale(localeVal),
      api.save_view_config({ show_on_launch: showOnLaunch, flash_changes: flashChanges, custom_commands: customCommands, file_viewer_default: fvd, locale: locale, theme: themeSlug }),
    ]);
  }).then(() => {
    if (saveTimedOut) return;
    clearTimeout(saveTimeout);
    document.body.style.zoom = zoomLevel;
    applyFontFamily(fontFamily);
    flashChangesEnabled = flashChanges;
    fileViewerDefault = fvd;
    themeBeforeSettings = themeSlug;
    closeSettings();
  }).catch((err) => {
    clearTimeout(saveTimeout);
    saveBtn.textContent = "Save failed -- retry?";
    saveBtn.disabled = false;
    console.error("settings save failed:", err);
  });
});



// Sidebar resize: drag the handle to resize the project list vs detail pane
const resizeHandle = document.getElementById("resizeHandle");
const projectListEl = document.getElementById("projectList");
let resizing = false;

// The width the user last chose, in CSS px. Kept in memory because a window
// resize has to re-clamp against the ORIGINAL choice, not against whatever the
// previous resize already squeezed it down to -- otherwise narrowing the window
// and widening it again leaves the sidebar permanently thin (T-155).
let preferredSidebarWidth = null;

// Floor and ceiling here mirror .project-list's `min-width: 88px` and
// `max-width: 60cqi` in style.css. Two copies of one rule is a drift risk, so
// if either moves, move both.
const SIDEBAR_MIN = 88;
const SIDEBAR_MAX_FRACTION = 0.6;

function applySidebarWidth(px, remember) {
  const container = document.querySelector(".main-container");
  const containerWidth = container ? container.clientWidth : 800;
  if (remember !== false) preferredSidebarWidth = px;
  const max = Math.max(SIDEBAR_MIN, Math.min(containerWidth * SIDEBAR_MAX_FRACTION,
                                             containerWidth - SIDEBAR_MIN - 4));
  const clamped = Math.min(max, Math.max(SIDEBAR_MIN, px));
  projectListEl.style.width = clamped + "px";
  return clamped;
}

// Nothing re-ran the clamp when the window changed size, so a sidebar sized on
// a wide window kept its absolute pixels on a narrow one and ate the detail
// pane. Re-clamp the user's preference against the new container instead.
window.addEventListener("resize", () => {
  if (preferredSidebarWidth === null || !projectListEl) return;
  applySidebarWidth(preferredSidebarWidth, false);
});

if (resizeHandle && projectListEl) {
  resizeHandle.addEventListener("mousedown", (e) => {
    resizing = true;
    resizeHandle.classList.add("dragging");
    e.preventDefault();
  });
  document.addEventListener("mousemove", (e) => {
    if (!resizing) return;
    const containerRect = document.querySelector(".main-container").getBoundingClientRect();
    applySidebarWidth(e.clientX - containerRect.left);
  });
  document.addEventListener("mouseup", () => {
    if (!resizing) return;
    resizing = false;
    resizeHandle.classList.remove("dragging");
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
      window.pywebview.api.save_view_config({ sidebar_width: projectListEl.getBoundingClientRect().width });
    }
  });
}

document.getElementById("hintGotIt")?.addEventListener("click", () => {
  collapseHintAcknowledged = true;
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_view_config) {
    window.pywebview.api.save_view_config({ collapse_hint_acknowledged: true });
  }
  document.getElementById("collapseHint").style.display = "none";
});

document.getElementById("hintDismiss")?.addEventListener("click", () => {
  document.getElementById("collapseHint").style.display = "none";
});

// Search overlay: close button + backdrop click
const searchOverlay = document.getElementById("searchOverlay");
document.getElementById("searchOverlayCloseBtn")?.addEventListener("click", hideSearchOverlay);
if (searchOverlay) {
  searchOverlay.addEventListener("mousedown", function(e) {
    if (e.target === searchOverlay) {
      hideSearchOverlay();
    }
  });
}

// Keyboard Navigation (Up / Down / Enter)
window.addEventListener("keydown", (e) => {
  // Escape: close search overlay if open
  if (e.key === "Escape") {
    const overlay = document.getElementById("searchOverlay");
    if (overlay && overlay.style.display !== "none" && overlay.style.display !== "") {
      e.preventDefault();
      hideSearchOverlay();
      return;
    }
  }

  // F3 / Shift+F3: cycle search results when overlay is open
  if (e.code === "F3") {
    const so = document.getElementById("searchOverlay");
    if (so && so.style.display !== "none" && so.style.display !== "") {
      e.preventDefault();
      if (e.shiftKey) {
        cycleSearchResult(-1);  // previous
      } else {
        cycleSearchResult(1);   // next
      }
      return;
    }
  }

  // Home / End: jump to first/last search result when overlay is open
  if (e.key === "Home" || e.key === "End") {
    const so = document.getElementById("searchOverlay");
    if (so && so.style.display !== "none" && so.style.display !== "") {
      e.preventDefault();
      if (e.key === "Home") {
        jumpToFirstResult();
      } else {
        jumpToLastResult();
      }
      return;
    }
  }

  // PageUp / PageDown: jump by a page of search results
  if (e.key === "PageUp" || e.key === "PageDown") {
    const so = document.getElementById("searchOverlay");
    if (so && so.style.display !== "none" && so.style.display !== "") {
      e.preventDefault();
      cycleSearchPage(e.key === "PageDown" ? 1 : -1);
      return;
    }
  }

  // Enter on highlighted search item: navigate (simulate click)
  if (e.key === "Enter") {
    const so = document.getElementById("searchOverlay");
    if (so && so.style.display !== "none" && so.style.display !== "" && searchItemIndex >= 0 && searchItems[searchItemIndex]) {
      e.preventDefault();
      searchItems[searchItemIndex].click();
      return;
    }
  }

  // Global hotkeys: Ctrl+F, Alt+D — work regardless of focus
  if (e.ctrlKey && e.code === "KeyF") {
    e.preventDefault();
    // Focus search input, enable deep search mode, show feedback
    const si = document.getElementById("searchInput");
    const dsc = document.getElementById("deepSearchChk");
    if (si) {
      si.focus();
      si.select();
    }
    if (dsc && !dsc.checked) {
      dsc.checked = true;
      // Trigger the change event to activate deep search
      const evt = new Event("change");
      dsc.dispatchEvent(evt);
    }
    showToast("Deep search (Ctrl+F) — searching projects + tickets", "info", 3000);
    return;
  }

  if (e.altKey && e.code === "KeyD") {
    e.preventDefault();
    toggleCollapse();  // also calls toggle_frameless internally
    return;
  }

  const filtered = filterProjects(rawProjects);
  if (!filtered.length) return;

  let currentIndex = filtered.findIndex((p) => p.root.toLowerCase() === (selectedRoot || "").toLowerCase());

  if (e.key === "ArrowDown") {
    e.preventDefault();
    const nextIndex = (currentIndex + 1) % filtered.length;
    selectProject(filtered[nextIndex].root);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    const prevIndex = (currentIndex - 1 + filtered.length) % filtered.length;
    selectProject(filtered[prevIndex].root);
  } else if (e.key === "Enter" && selectedRoot) {
    e.preventDefault();
    window.pywebview.api.open_folder(selectedRoot);
  }
});

window.addEventListener("pywebviewready", () => {
  window.pywebview.api.get_engines().then(e => { availableEnginesCache = e || []; });
  Promise.all([window.pywebview.api.get_config(), window.pywebview.api.get_local_drives()])
    .then(([cfg, drives]) => {
      applyFontFamily(cfg.font_family);
      window.pywebview.api.get_theme_tokens(cfg.theme).then(applyTheme);
      if (cfg.zoom_level) {
        document.body.style.zoom = cfg.zoom_level;
      }
      if (cfg.sidebar_width) {
        applySidebarWidth(cfg.sidebar_width);
      }
      if (cfg.filter_phase && filterSelect) {
        currentFilter = cfg.filter_phase;
        filterSelect.value = cfg.filter_phase;
      }
      if (cfg.search_query && searchInput) {
        searchQuery = cfg.search_query;
        searchInput.value = cfg.search_query;
      }
      if (cfg.selected_root) {
        selectedRoot = cfg.selected_root;
      }
      if (cfg.compact_mode && compactModeChk) {
        compactModeChk.checked = true;
        document.getElementById("projectList").classList.add("compact");
      }
      if (cfg.exclude_dirs && excludeInput) {
        excludeInput.value = cfg.exclude_dirs.join(", ");
      }
      if (autoScanChk) {
        autoScanChk.checked = cfg.auto_scan !== false;
      }
      if (cfg.sort_order && sortSelect) {
        currentSort = cfg.sort_order;
        sortSelect.value = cfg.sort_order;
      }
      if (cfg.show_hidden && showHiddenChk) {
        showHidden = true;
        showHiddenChk.checked = true;
      }
      if (cfg.top_panel_collapsed) {
        document.body.classList.add("collapsed");
        const btn = document.getElementById("togglePanelBtn");
        if (btn) btn.textContent = "▼";
      }
      if (cfg.collapse_hint_acknowledged) {
        collapseHintAcknowledged = true;
      }
      if (cfg.collapsed_sections) {
        collapsedConfig = cfg.collapsed_sections;
      }
      if (cfg.layout_swap) {
        document.body.classList.add("swapped");
      }
      // default_engine sat in config.py's DEFAULTS since the engine layer
      // landed and was read by nothing at all, so the dropdown always opened
      // on whatever engine the registry happened to list first.
      if (cfg.default_engine) {
        defaultEngine = cfg.default_engine;
      }
      renderDrives(drives, cfg.scan_roots);
      showCollapseHint();
    })
    .catch(() => {
      console.error("init: failed to load config or drives");
    });
  poll();
  setInterval(poll, POLL_MS);
});
// File Viewer Modal
const fileViewerModal = document.getElementById("fileViewerModal");
let currentFilePath = null;
let fileViewerMode = "source"; // "source" | "reader"
let fileViewerDefault = "source"; // default mode on open, from config
let currentFilename = "";

function renderStateAsHtml(text) {
  // Parse frontmatter --- ... ---
  let body = text;
  let fmHtml = "";
  const fmMatch = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
  if (fmMatch) {
    body = text.slice(fmMatch[0].length);
    const lines = fmMatch[1].split("\n").filter(l => l.trim());
    fmHtml = '<div class="reader-fm">' + lines.map(l => {
      const [k, ...v] = l.split(":");
      return `<div class="reader-fm-row"><span class="reader-fm-key">${escapeHtml(k.trim())}</span><span class="reader-fm-val">${escapeHtml(v.join(":").trim())}</span></div>`;
    }).join("") + '</div>';
  }
  const bodyHtml = '<pre class="reader-raw">' + escapeHtml(body.trim()) + '</pre>';
  return fmHtml + bodyHtml;
}

function renderBoardAsHtml(text) {
  const sections = text.split(/^##\s+/m);
  return sections.map(section => {
    const lines = section.split("\n").filter(l => l.trim());
    if (!lines.length) return "";
    const heading = lines[0];
    const items = lines.slice(1).filter(l => /^\s*-\s*\[[ x/]\]/.test(l));
    if (!items.length && !heading) return "";
    if (!items.length) return `<div class="reader-section"><div class="reader-section-title">${escapeHtml(heading)}</div><div class="reader-empty">empty</div></div>`;
    return `<div class="reader-section">
      <div class="reader-section-title">${escapeHtml(heading)}</div>
      ${items.map(l => {
        const checked = l.includes("[x]") ? "reader-done" : l.includes("[/]") ? "reader-doing" : "";
        const text = l.replace(/^\s*-\s*\[[ x/]\]\s*/, "").replace(/\s*\|.*$/, "");
        return `<div class="reader-ticket ${checked}"><span class="reader-bullet">${l.includes("[x]") ? "✓" : l.includes("[/]") ? "◷" : "○"}</span>${escapeHtml(text)}</div>`;
      }).join("")}
    </div>`;
  }).join("");
}

function renderLogAsHtml(text) {
  const lines = text.split("\n").filter(l => l.trim());
  return '<div class="reader-log">' + lines.map(l => {
    const match = l.match(/^-\s*(\S+\s+\S+)\s+(\[E-\d+\])(.*)/);
    if (match) {
      return `<div class="reader-log-line"><span class="reader-log-date">${escapeHtml(match[1])}</span> <span class="reader-log-eid">${escapeHtml(match[2])}</span><span class="reader-log-text">${escapeHtml(match[3])}</span></div>`;
    }
    return `<div class="reader-log-line"><span class="reader-log-text">${escapeHtml(l)}</span></div>`;
  }).join("") + '</div>';
}

function renderAsReader(filename, text) {
  const name = filename.toLowerCase();
  if (name.includes("state")) return renderStateAsHtml(text);
  if (name.includes("board")) return renderBoardAsHtml(text);
  if (name.includes("log")) return renderLogAsHtml(text);
  // Generic fallback: simple markdown rendering
  return '<pre class="reader-raw">' + escapeHtml(text) + '</pre>';
}

function applyFileViewerMode() {
  const ta = document.getElementById("fileViewerContent");
  const rd = document.getElementById("fileViewerRendered");
  const btn = document.getElementById("fileViewerModeBtn");
  const saveBtn = document.getElementById("saveFileViewerBtn");
  if (fileViewerMode === "reader") {
    ta.style.display = "none";
    rd.style.display = "block";
    rd.innerHTML = renderAsReader(currentFilename, ta.value);
    btn.textContent = "Source";
    saveBtn.disabled = true;
    saveBtn.style.opacity = "0.4";
  } else {
    ta.style.display = "block";
    rd.style.display = "none";
    btn.textContent = "Reader";
    saveBtn.disabled = false;
    saveBtn.style.opacity = "1";
  }
}

function openFileViewer(filename, filepath, content) {
  currentFilename = filename;
  document.getElementById("fileViewerFilename").textContent = escapeHtml(filename);
  document.getElementById("fileViewerStatus").textContent = escapeHtml(filepath);
  document.getElementById("fileViewerContent").value = content;
  currentFilePath = filepath;
  fileViewerMode = fileViewerDefault || "source";
  applyFileViewerMode();
  fileViewerModal.style.display = "flex";
}

function closeFileViewer() {
  fileViewerModal.style.display = "none";
  currentFilePath = null;
}

document.getElementById("closeFileViewerBtn")?.addEventListener("click", closeFileViewer);
fileViewerModal?.addEventListener("mousedown", (e) => {
  if (e.target === fileViewerModal) closeFileViewer();
});

document.getElementById("fileViewerModeBtn")?.addEventListener("click", () => {
  fileViewerMode = fileViewerMode === "reader" ? "source" : "reader";
  applyFileViewerMode();
});

document.getElementById("saveFileViewerBtn")?.addEventListener("click", () => {
  if (!currentFilePath) return;
  const content = document.getElementById("fileViewerContent").value;
  const btn = document.getElementById("saveFileViewerBtn");
  btn.textContent = "Saving...";
  window.pywebview.api.write_file_text(currentFilePath, content).then((ok) => {
    if (ok) {
      btn.textContent = "Saved";
      setTimeout(() => { btn.textContent = "Save"; }, 2000);
      if (selectedRoot) loadDetail(selectedRoot);
    } else {
      btn.textContent = "Err";
      setTimeout(() => { btn.textContent = "Save"; }, 2000);
    }
  });
});

// --- Quick UI Zoom ---
let currentZoomLevel = 1.0;

window.addEventListener("pywebviewready", () => {
  window.pywebview.api.get_config().then((cfg) => {
    currentZoomLevel = cfg.zoom_level || 1.0;
    if (cfg.file_viewer_default) fileViewerDefault = cfg.file_viewer_default;
  });
});

function adjustZoomLevel(delta) {
  const sizes = [0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0];
  let idx = sizes.indexOf(currentZoomLevel);
  if (idx === -1) {
    idx = 0;
    for (let i = 0; i < sizes.length; i++) {
      if (sizes[i] >= currentZoomLevel) {
        idx = i;
        if (i > 0 && sizes[i] - currentZoomLevel > currentZoomLevel - sizes[i-1]) idx = i-1;
        break;
      }
    }
  }
  let newIdx = idx + delta;
  if (newIdx < 0) newIdx = 0;
  if (newIdx >= sizes.length) newIdx = sizes.length - 1;
  const newSize = sizes[newIdx];
  
  if (newSize !== currentZoomLevel) {
    currentZoomLevel = newSize;
    document.body.style.zoom = currentZoomLevel;
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.set_zoom_level(currentZoomLevel);
    }
    const setZoomLevelInput = document.getElementById("setZoomLevel");
    if (setZoomLevelInput) setZoomLevelInput.value = currentZoomLevel;
  }
}

window.addEventListener("wheel", (e) => {
  if (e.ctrlKey) {
    e.preventDefault();
    if (e.deltaY < 0) {
      adjustZoomLevel(1);
    } else if (e.deltaY > 0) {
      adjustZoomLevel(-1);
    }
  }
}, { passive: false });

setInterval(() => {
  // Same reasoning as poll()'s guard: a clock nobody is looking at does not
  // need a querySelectorAll every second. Repainted on show by the catch-up
  // poll's render, so it is never stale by the time it is visible.
  if (!windowVisible) return;
  document.querySelectorAll('.now-clock').forEach(el => { el.textContent = `(now: ${nowStr()})`; });
}, 1000);

// Flash recompute: hexBlend background colors every 30ms for smooth decay
let _flashSurfColor = null;
setInterval(() => {
  if (!flashChangesEnabled || !Object.keys(flashState).length) return;

  if (!_flashSurfColor) {
    _flashSurfColor = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#4a341b";
  }

  const now = Date.now();
  let anyActive = false;

  document.querySelectorAll(".project-row").forEach(row => {
    const root = row.getAttribute("data-root");
    if (!root) return;

    const ft = flashState[root];
    if (ft) {
      const ageMs = now - ft;
      if (ageMs >= FLASH_DECAY_SECONDS * 1000) {
        delete flashState[root];
        if (row.style.backgroundColor) row.style.backgroundColor = "";
      } else {
        const t = ageMs / (FLASH_DECAY_SECONDS * 1000);
        row.style.backgroundColor = hexBlend(FLASH_HOT, _flashSurfColor, t);
        anyActive = true;
      }
    }
  });

  if (!anyActive) {
    // Flash completed -- interval short-circuits next tick
  }
}, 30);

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    const wikiModal = document.getElementById("wikiModal");
    if (wikiModal && wikiModal.style.display !== "none") {
      closeWiki();
      e.preventDefault();
      return;
    }
    const helpOverlay = document.getElementById("helpOverlay");
    if (helpOverlay && helpOverlay.style.display !== "none") {
      closeQuickHelp();
      e.preventDefault();
      return;
    }
    const searchOverlay = document.getElementById("searchOverlay");
    if (searchOverlay && searchOverlay.style.display !== "none") {
      hideSearchOverlay();
      e.preventDefault();
    }
  }
  if (e.ctrlKey) {
    if (e.key === "=" || e.key === "+") {
      e.preventDefault();
      adjustZoomLevel(1);
    } else if (e.key === "-") {
      e.preventDefault();
      adjustZoomLevel(-1);
    } else if (e.key === "0") {
      e.preventDefault();
      if (currentZoomLevel !== 1.0) {
        currentZoomLevel = 1.0;
        document.body.style.zoom = "1.0";
        if (window.pywebview && window.pywebview.api) window.pywebview.api.set_zoom_level(1.0);
        const setZoomLevelInput = document.getElementById("setZoomLevel");
        if (setZoomLevelInput) setZoomLevelInput.value = 1.0;
      }
    }
  }
});

// --- Window dragging: left-click + drag anywhere moves the window ---
// No threshold — the moment the cursor moves while holding left button, the
// window follows. Skips inputs, selects, textareas, resize handle, overlays.
let _dragState = null;

document.body.addEventListener("mousedown", (e) => {
  if (e.button !== 0 || _dragState) return;
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "select" || tag === "textarea") return;
  if (e.target.closest(".resize-handle, .modal-overlay, .confirm-overlay, .search-overlay")) return;
  _dragState = { sx: e.screenX, sy: e.screenY };
  document.body.style.userSelect = "none";
  e.preventDefault();
});

function renderAgentPanel(root, container) {
  if (!container) return;
  const status = agentStatusCache[root];
  const isRunning = status && status.status === "running";
  // T-167: a one-shot engine reads no later stdin, so Send must not be
  // offered for it. supports_stdin is a per-engine capability with evidence,
  // never an assumption.
  const runningEngineStdin = (status && status.engine)
    ? (availableEnginesCache.find(e => e.name === status.engine) || {}).supports_stdin
    : false;

  const switchedProject = currentAgentPanelRoot !== root;
  if (switchedProject) {
    currentAgentPanelRoot = root;
    agentSinceLineNum[root] = 0;
  }

  const stateStr = isRunning ? "running" : "stopped";
  const existingPanel = container.querySelector('.agent-panel');
  // `switchedProject`, not `currentAgentPanelRoot === root` -- that comparison
  // was made three lines after the assignment above, so it was always true and
  // the skeleton was never rebuilt when the user moved to another project. The
  // panel kept the previous project's output.
  const shouldBuildSkeleton = switchedProject || !existingPanel;

  if (shouldBuildSkeleton) {
    // Static ids, and the project root on a data attribute instead (T-159).
    // These used to be `id="agentControlTop-${root}"`, which put a Windows path
    // -- drive letter, colon, backslashes -- inside an id, and then read it
    // back with `container.querySelector('#agentControlTop-' + root)`. That is
    // not a valid selector, so querySelector THREW, and because
    // renderDetailPane calls this function as its last statement the throw took
    // the rest of the detail pane with it. There is exactly one agent panel in
    // the document (#agentPanelContainer, one detail pane), so the path was
    // never needed to tell instances apart.
    container.innerHTML = `<div class="agent-panel detail-card" style="margin-top:4px;" data-state="${stateStr}" data-root="${escapeHtml(root)}">
      <div class="card-title">${escapeHtml(t("agent.title"))}</div>
      <div class="agent-subtitle" id="agentSubtitle">${escapeHtml(t(isRunning ? "agent.subtitle.running" : "agent.subtitle.idle"))}</div>
      <div id="agentControlTop"></div>
      <div class="agent-output-panel sunken" id="agentOutputPanel" title="${escapeHtml(t("agent.output.title"))}">
        <div id="agentOutputLines"></div>
        <div class="agent-output-meta" id="agentOutputMeta">${escapeHtml(t("agent.output.lines"))}: 0</div>
      </div>
      <div id="agentControlBottom"></div>
    </div>`;
    // Nothing running means the console would otherwise be blank, with no
    // sign an agent had ever been here -- the transcript used to die with the
    // process. Pull the last stored run back in from disk.
    if (!isRunning) restoreLastTranscript(root, container);
  } else {
    // If state hasn't changed, we just update the elapsed and meta.
    if (existingPanel.getAttribute("data-state") === stateStr) {
      if (isRunning) {
        const elapsedEl = container.querySelector(".agent-status-elapsed");
        if (elapsedEl && status.elapsed) elapsedEl.textContent = Math.floor(status.elapsed) + 's';
        const metaEl = container.querySelector(".agent-output-meta");
        if (metaEl && status.total_lines) metaEl.textContent = t("agent.output.lines") + ": " + status.total_lines;
      }
      return; // Nothing else to rebuild!
    } else {
      existingPanel.setAttribute("data-state", stateStr);
      // The subtitle explains the state, so it has to follow the state.
      const subEl = existingPanel.querySelector(".agent-subtitle");
      if (subEl) subEl.textContent = t(isRunning ? "agent.subtitle.running" : "agent.subtitle.idle");
    }
  }

  const topEl = container.querySelector("#agentControlTop");
  const bottomEl = container.querySelector("#agentControlBottom");

  let topHtml = "";
  if (status) {
    let phaseDot = 'DONE';
    if (status.status === 'failed' || status.status === 'killed') phaseDot = 'BLOCKED';
    else if (status.status === 'running') phaseDot = 'BUILD';

    
    const ts = window.agentTestState[root];
    let testBadgeHtml = "";
    if (ts && ts.status !== 'none') {
      let color = ts.status === 'fail' ? 'var(--danger)' : (ts.status === 'pass' ? 'var(--success)' : 'var(--accentTeal)');
      let label = ts.status === 'running' ? 'Tests: RUN' : (ts.status === 'fail' ? 'Tests: FAIL' : 'Tests: PASS');
      testBadgeHtml = `<span style="color:${color}; font-size:10px; padding:2px 4px; margin-right:4px; font-weight:bold; border: 1px inset var(--borderDark); background: var(--surfaceRaised);">${label}</span>`;
    }
topHtml = `<div class="agent-status-bar raised">
      <div class="agent-status-info">
        <span class="phase-indicator phase-${phaseDot}" style="position:static; display:inline-block; width:6px; height:6px;"></span>
        <span>${escapeHtml(status.engine_display || status.engine)}</span>
        <span>[${escapeHtml(status.status)}]</span>
        <span class="agent-status-elapsed">${status.elapsed ? Math.floor(status.elapsed) + 's' : ''}</span>
      </div>
      <div>
${testBadgeHtml}
                ${isRunning ? `<button class="stop-agent-btn" data-root="${escapeHtml(root)}" style="color:var(--dangerText)" title="${escapeHtml(t("agent.stop.title"))}">${escapeHtml(t("agent.stop.label"))}</button>` : ''}
        <button class="view-diff-btn" data-root="${escapeHtml(root)}" title="${escapeHtml(t("agent.diff.title"))}">${escapeHtml(t("agent.diff.label"))}</button>
      </div>
    </div>`;
  }
  topEl.innerHTML = topHtml;

  let bottomHtml = "";
  if (isRunning) {
    if (runningEngineStdin) {
      bottomHtml = `<div class="agent-chat-panel" style="padding:4px;">
      <div class="agent-chat-shortcuts" style="display:flex; gap:4px; margin-bottom:4px;">
        <button class="chat-shortcut-btn raised" data-cmd="saipen continue" style="font-size:10px; padding:2px 4px;" title="${escapeHtml(t("agent.shortcut.continue.title"))}">Continue</button>
        <button class="chat-shortcut-btn raised" data-cmd="saipen hunt" style="font-size:10px; padding:2px 4px;" title="${escapeHtml(t("agent.shortcut.hunt.title"))}">Hunt</button>
        <button class="chat-shortcut-btn raised" data-cmd="saipen clean" style="font-size:10px; padding:2px 4px;" title="${escapeHtml(t("agent.shortcut.clean.title"))}">Clean</button>
      </div>
      <div class="agent-launch-row">
        <textarea id="agentChatInput" placeholder="${escapeHtml(t("agent.chat.placeholder"))}"></textarea>
        <button id="agentSendBtn" data-root="${escapeHtml(root)}" style="color:var(--success)" title="${escapeHtml(t("agent.send.title"))}">${escapeHtml(t("agent.send.label"))}</button>
      </div>
    </div>`;
    } else {
      bottomHtml = `<div class="agent-chat-panel" style="padding:4px;">
      <div style="font-size:10px; color:var(--textSecondary); background:var(--surfaceRaised); border:1px solid var(--borderHighlight); border-right-color:var(--borderDark); border-bottom-color:var(--borderDark); padding:2px 4px;">
        ${escapeHtml(t("agent.noStdin"))}
      </div>
    </div>`;
    }
  } else {
    const available = availableEnginesCache.filter(e => e.available);
    // Preselect the configured engine, but only when it is actually installed
    // -- an unavailable default must not silently select nothing and leave the
    // launcher pointing at whatever the browser picks instead.
    const preselect = available.some(e => e.name === defaultEngine) ? defaultEngine : null;
    const engineOptions = available.map(e =>
      `<option value="${escapeHtml(e.name)}"${e.name === preselect ? " selected" : ""}>${escapeHtml(e.display_name)}</option>`).join("");
    const availableCount = availableEnginesCache.filter(e => e.available && e.name !== "generic-cli").length;
    let hintHtml = "";
    if (availableCount === 0) {
      hintHtml = `<div style="color:var(--textSecondary);font-size:10px;padding:2px;margin-bottom:2px;background:var(--surfaceRaised);border:1px solid var(--borderHighlight);border-right-color:var(--borderDark);border-bottom-color:var(--borderDark);">
        <span style="color:var(--dangerText);font-weight:bold;">!</span> ${escapeHtml(t("agent.noEngines"))}
      </div>`;
    }
    bottomHtml = `<div class="agent-launch-panel">
      ${hintHtml}
      <div class="agent-launch-row">
        <select id="agentEngineSelect" title="${escapeHtml(t("agent.engine.title"))}">${engineOptions}</select>
        <textarea id="agentInstructionInput" title="${escapeHtml(t("agent.instruction.title"))}" placeholder="${escapeHtml(t("agent.instruction.placeholder"))}">saipen continue</textarea>
        <div style="display:flex; flex-direction:column; gap:2px;">
          <button id="agentLaunchBtn" data-root="${escapeHtml(root)}" style="color:var(--success)" title="${escapeHtml(t("agent.launch.title"))}" ${!engineOptions ? "disabled" : ""}>${escapeHtml(t("agent.launch.label"))}</button>
          <button id="agentHumanNoteBtn" data-root="${escapeHtml(root)}" style="font-size:10px; padding:2px 4px;" title="${escapeHtml(t("agent.note.title"))}">${escapeHtml(t("agent.note.label"))}</button>
        </div>
      </div>
    </div>`;
  }
  bottomEl.innerHTML = bottomHtml;

  const stopBtn = container.querySelector(".stop-agent-btn");
  if (stopBtn) {
    stopBtn.addEventListener("click", () => {
      window.pywebview.api.stop_agent(root).then(res => {
        if (res.ok) showToast("Agent stopped", "info");
        else showToast("Stop failed: " + res.error, "error");
        pollAgentOutput();
      });
    });
  }
  
  const diffBtn = container.querySelector(".view-diff-btn");
  if (diffBtn) {
    diffBtn.addEventListener("click", () => openDiffViewer(root));
  }

  if (isRunning) {
    const sendBtn = container.querySelector("#agentSendBtn");
    const chatInput = container.querySelector("#agentChatInput");
    
    const sendInput = () => {
      const text = chatInput.value;
      if (!text.trim()) return;
      window.pywebview.api.send_agent_input(root, text).then(res => {
        if (res.ok) {
          chatInput.value = "";
          showToast("Sent", "success");
        } else {
          showToast("Send failed: " + res.error, "error");
        }
      });
    };

    if (sendBtn) sendBtn.addEventListener("click", sendInput);
    if (chatInput) {
      chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          sendInput();
        }
      });
    }

    const shortcuts = container.querySelectorAll(".chat-shortcut-btn");
    shortcuts.forEach(btn => {
      btn.addEventListener("click", (e) => {
        const cmd = e.target.getAttribute("data-cmd");
        if (cmd) {
          window.pywebview.api.send_agent_input(root, cmd).then(res => {
            if (res.ok) showToast("Sent: " + cmd, "success");
            else showToast("Send failed: " + res.error, "error");
          });
        }
      });
    });
  } else {
    const launchBtn = container.querySelector("#agentLaunchBtn");
    if (launchBtn) {
      launchBtn.addEventListener("click", () => {
        const engine = container.querySelector("#agentEngineSelect").value;
        const instruction = container.querySelector("#agentInstructionInput").value;
        if (!engine || !instruction.trim()) {
          showToast("Engine and instruction required", "warning");
          return;
        }
        if (engine !== defaultEngine) {
          defaultEngine = engine;
          window.pywebview.api.save_view_config({ default_engine: engine });
        }
        window.pywebview.api.launch_agent(root, engine, instruction.trim()).then(res => {
          if (res.ok) {
            agentSinceLineNum[root] = 0;
            // Drop the restored transcript: the console now belongs to the
            // run that just started, not to the one before it.
            agentRestoredRoots.delete(root);
            // T-169: the user may have switched projects while the launch was
            // in flight -- do not clear the new project's console.
            if (currentDetailRoot === root) {
              const lines = document.getElementById("agentOutputLines");
              if (lines) lines.innerHTML = "";
              pollAgentOutput();
            }
            showToast("Agent launched", "success");
          } else {
            showToast("Launch failed: " + res.error, "error");
          }
        });
      });
    }

    const humanNoteBtn = container.querySelector("#agentHumanNoteBtn");
    if (humanNoteBtn) {
      humanNoteBtn.addEventListener("click", () => {
        const note = prompt("Enter human note to append to STATE.md:");
        if (note) {
          window.pywebview.api.add_human_note(root, note).then(res => {
            if (res.ok) showToast("Note added", "success");
            else showToast("Failed to add note: " + res.error, "error");
          });
        }
      });
    }
  }
}


function parseTestLine(root, line) {
  const ts = window.agentTestState[root] || { status: 'none' };
  const l = line.toLowerCase();
  
  if (l.includes('==== test session starts ====') || /^> .*test/.test(line) || l.includes('starting test')) {
    ts.status = 'running';
  } else if (/(\d+) passed.*(\d+) failed/.test(l)) {
    const m = l.match(/(\d+) passed.*(\d+) failed/);
    if (parseInt(m[2]) > 0) ts.status = 'fail';
    else ts.status = 'pass';
  } else if (/\b(\d+) failed\b/.test(l)) {
    ts.status = 'fail';
  } else if (/\b(\d+) passed\b/.test(l)) {
    if (ts.status !== 'fail') ts.status = 'pass';
  } else if (/^failed\b/.test(l) || l.includes('test failed')) {
    ts.status = 'fail';
  } else if (/^ok\s+/.test(line)) {
    if (ts.status !== 'fail') ts.status = 'pass';
  }
  
  window.agentTestState[root] = ts;
}
// Roots whose stored transcript has already been pulled into the panel, so a
// re-render does not fetch and re-append it every poll tick.
const agentRestoredRoots = new Set();

// T-169: an async callback that captured `root` before an await must verify
// the user is still looking at that project before it mutates the panel. A
// stale response must never write into a different project's Detail Pane.
function isCurrentProjectPanel(root) {
  if (currentDetailRoot !== root) return false;
  const panel = document.getElementById("agentPanelContainer");
  if (!panel) return true;
  return panel.dataset.root === root;
}

function restoreLastTranscript(root, container) {
  if (agentRestoredRoots.has(root)) return;
  const api = window.pywebview && window.pywebview.api;
  if (!api || !api.get_last_agent_transcript) return;
  api.get_last_agent_transcript(root).then((res) => {
    if (!res || !res.found) return;
    // T-169: the user may have switched projects while this was in flight.
    if (!isCurrentProjectPanel(root)) return;
    // The panel may have been rebuilt, or a live run may have started, while
    // this was in flight. Either way the stored lines are no longer wanted.
    const linesContainer = document.getElementById("agentOutputLines");
    if (!linesContainer || linesContainer.childElementCount) return;
    const status = agentStatusCache[root];
    if (status && status.status === "running") return;

    const run = res.run || {};
    const head = document.createElement("div");
    head.className = "agent-output-restored";
    head.textContent = t("agent.restored", {
      engine: run.engine_display || run.engine || "?",
      status: run.status || "?",
      when: run.started_at ? formatLocalTime(run.started_at) : "?",
    });
    linesContainer.appendChild(head);

    (res.lines || []).forEach((line) => {
      const div = document.createElement("div");
      div.className = "agent-output-line";
      div.textContent = line;
      linesContainer.appendChild(div);
    });

    const meta = document.getElementById("agentOutputMeta");
    if (meta) {
      meta.textContent =
        t("agent.output.lines") + ": " + (res.total || 0) +
        (run.truncated ? " (" + t("agent.output.truncated") + ")" : "");
    }
    const panel = linesContainer.parentElement;
    if (panel) panel.scrollTop = panel.scrollHeight;
    // Marked only after a SUCCESSFUL restore (T-169): on a transient failure
    // or found=false the root stays unmarked, so a later poll retries instead
    // of being blocked from ever restoring.
    agentRestoredRoots.add(root);
  }).catch(() => {
    // Transient failure: not marked, the next poll retries (T-169).
  });
}

function pollAgentOutput() {
  window.pywebview.api.list_running_agents().then(agents => {
    const badge = document.getElementById("runningAgentsBadge");
    if (badge) {
      if (agents && agents.length > 0) {
        badge.style.display = "inline-flex";
        badge.textContent = "🤖 " + agents.length;
      } else {
        badge.style.display = "none";
      }
    }
  });

  if (!currentDetailRoot) return;
  const root = currentDetailRoot;
  
  window.pywebview.api.get_agent_status(root).then(status => {
    // T-169: a project switch while this was in flight must not let the old
    // project's status rebuild the current panel.
    if (currentDetailRoot !== root) return;
    agentStatusCache[root] = status;
    const container = document.getElementById("agentPanelContainer");
    if (container) {
      renderAgentPanel(root, container);
    }
    
    if (status && (status.status === "running" || status.status === "done" || status.status === "failed" || status.status === "killed")) {
      let since = agentSinceLineNum[root] || 0;
      window.pywebview.api.get_agent_output(root, since).then(res => {
        if (currentDetailRoot !== root) return;
        if (res && res.lines && res.lines.length > 0) {
          const linesContainer = document.getElementById("agentOutputLines");
          if (linesContainer) {
            const panel = linesContainer.parentElement;
            const isScrolledToBottom = panel.scrollHeight - panel.clientHeight <= panel.scrollTop + 10;
            
            res.lines.forEach(line => {
              parseTestLine(root, line);
              const div = document.createElement("div");
              div.className = "agent-output-line";
              div.textContent = line;
              linesContainer.appendChild(div);
            });
            
            if (isScrolledToBottom) {
              panel.scrollTop = panel.scrollHeight;
            }
          }
        }
        // The cursor is the backend's canonical next_since, never
        // since + lines.length -- on buffer rollover that arithmetic
        // would resend lines (T-166).
        if (res && typeof res.next_since === "number") {
          agentSinceLineNum[root] = res.next_since;
        }
      });
    }
  });
}

document.body.addEventListener("mousemove", (e) => {
  if (!_dragState) return;
  const dx = e.screenX - _dragState.sx;
  const dy = e.screenY - _dragState.sy;
  if (dx === 0 && dy === 0) return;
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.move_by(dx, dy);
  }
  _dragState.sx = e.screenX;
  _dragState.sy = e.screenY;
});

document.body.addEventListener("mouseup", () => {
  document.body.style.userSelect = "";
  _dragState = null;
});


let currentDiffRoot = null;
let currentDiffFingerprint = null;
let currentDiffScope = null;

function colorizeDiff(diffText) {
  if (!diffText.trim()) return "<div style='color:var(--textMuted);'>No changes.</div>";
  return diffText.split('\n').map(line => {
    let color = "var(--textPrimary)";
    if (line.startsWith("+")) color = "var(--success)";
    else if (line.startsWith("-")) color = "var(--dangerText)";
    else if (line.startsWith("@@")) color = "var(--accentTeal)";
    return `<div style="color:${color};">${escapeHtml(line)}</div>`;
  }).join("");
}

function diffScopeSummary(scope) {
  if (!scope) return "";
  const c = scope.counts || {};
  const parts = [];
  if (c.staged) parts.push(c.staged + " staged");
  if (c.modified) parts.push(c.modified + " modified");
  if (c.deleted) parts.push(c.deleted + " deleted");
  if (c.renamed) parts.push(c.renamed + " renamed");
  const tracked = (c.staged || 0) + (c.modified || 0) + (c.deleted || 0) + (c.renamed || 0);
  const lines = [];
  if (tracked) lines.push(tracked + " tracked file(s) changed (" + parts.join(", ") + ")");
  if (c.untracked) lines.push(c.untracked + " untracked file(s)");
  lines.push("Ignored files are excluded from every operation.");
  return lines.join("  |  ");
}

function diffScopeFileList(scope) {
  if (!scope) return "";
  const rows = [];
  if (scope.staged && scope.staged.length) rows.push("<b>Staged:</b> " + scope.staged.map(escapeHtml).join(", "));
  if (scope.modified && scope.modified.length) rows.push("<b>Modified:</b> " + scope.modified.map(escapeHtml).join(", "));
  if (scope.deleted && scope.deleted.length) rows.push("<b>Deleted:</b> " + scope.deleted.map(escapeHtml).join(", "));
  if (scope.renamed && scope.renamed.length) rows.push("<b>Renamed:</b> " + scope.renamed.map(r => escapeHtml(r.from) + " -> " + escapeHtml(r.to)).join(", "));
  if (scope.untracked && scope.untracked.length) rows.push("<b>Untracked:</b> " + scope.untracked.map(escapeHtml).join(", "));
  if (!rows.length) return "";
  return rows.join("<br>");
}

function openDiffViewer(root) {
  currentDiffRoot = root;
  currentDiffFingerprint = null;
  currentDiffScope = null;
  const modal = document.getElementById("diffViewerModal");
  const content = document.getElementById("diffViewerContent");
  const status = document.getElementById("diffViewerStatus");
  modal.style.display = "flex";
  content.innerHTML = "Loading...";
  status.textContent = "";
  refreshDiff();
}

function refreshDiff() {
  if (!currentDiffRoot) return;
  const content = document.getElementById("diffViewerContent");
  const status = document.getElementById("diffViewerStatus");
  const requestedRoot = currentDiffRoot;
  window.pywebview.api.get_diff(requestedRoot).then(res => {
    // T-169: the modal may have been reopened for another project while this
    // was in flight -- a stale response must not overwrite it.
    if (currentDiffRoot !== requestedRoot) return;
    if (res.ok) {
      currentDiffFingerprint = res.fingerprint || null;
      currentDiffScope = res.scope || null;
      status.textContent = diffScopeSummary(res.scope);
      const list = diffScopeFileList(res.scope);
      content.innerHTML = (list ? `<div style="font-size:10px; padding:2px 4px; margin-bottom:4px; background:var(--surfaceSoft);">${list}</div>` : "") + colorizeDiff(res.diff);
    } else {
      currentDiffFingerprint = null;
      currentDiffScope = null;
      status.textContent = "";
      content.innerHTML = `<div style="color:var(--danger)">Error: ${escapeHtml(res.error)}</div>`;
    }
  });
}

document.getElementById("closeDiffViewerBtn")?.addEventListener("click", () => {
  document.getElementById("diffViewerModal").style.display = "none";
});
document.getElementById("refreshDiffBtn")?.addEventListener("click", refreshDiff);

document.getElementById("commitChangesBtn")?.addEventListener("click", () => {
  if (!currentDiffRoot) return;
  if (!currentDiffScope || !currentDiffFingerprint) { showToast("Open the diff first", "error"); return; }
  const msg = prompt("Enter commit message:");
  if (!msg) return;
  const c = currentDiffScope.counts || {};
  const tracked = (c.staged || 0) + (c.modified || 0) + (c.deleted || 0) + (c.renamed || 0);
  const total = tracked + (c.untracked || 0);
  showConfirm("Commit " + total + " file(s)? (tracked " + tracked + ", untracked " + (c.untracked || 0) + "). Ignored files excluded. This is everything the preview shows.", () => {
    window.pywebview.api.commit_agent_work(currentDiffRoot, msg, currentDiffFingerprint).then(res => {
      if (res.ok) {
        showToast("Committed", "success");
        refreshDiff();
      } else {
        showToast("Commit failed: " + res.error, "error");
        refreshDiff();
      }
    });
  });
});

document.getElementById("revertChangesBtn")?.addEventListener("click", () => {
  if (!currentDiffRoot) return;
  if (!currentDiffScope || !currentDiffFingerprint) { showToast("Open the diff first", "error"); return; }
  const c = currentDiffScope.counts || {};
  const tracked = (c.staged || 0) + (c.modified || 0) + (c.deleted || 0) + (c.renamed || 0);
  const untracked = c.untracked || 0;
  showConfirm("Restore " + tracked + " tracked file(s) to the last commit? " + untracked + " untracked file(s) will NOT be touched.", () => {
    window.pywebview.api.revert_agent_work(currentDiffRoot, currentDiffFingerprint).then(res => {
      if (res.ok) {
        showToast("Restored tracked changes", "info");
        refreshDiff();
      } else {
        showToast("Revert failed: " + res.error, "error");
        refreshDiff();
      }
    });
  });
});

document.getElementById("deleteUntrackedBtn")?.addEventListener("click", () => {
  if (!currentDiffRoot) return;
  if (!currentDiffScope || !currentDiffFingerprint) { showToast("Open the diff first", "error"); return; }
  const untracked = (currentDiffScope.untracked || []).slice(0, 30);
  const total = (currentDiffScope.counts || {}).untracked || 0;
  if (!total) { showToast("No untracked files", "info"); return; }
  const listed = untracked.join("\n");
  const msg = "DELETE " + total + " untracked file(s)? This cannot be undone. Ignored files are safe."
    + (total > 30 ? " First 30 listed:" : " Listed:") + "\n" + listed;
  showConfirm(msg, () => {
    window.pywebview.api.delete_untracked_files(currentDiffRoot, currentDiffFingerprint).then(res => {
      if (res.ok) {
        showToast("Untracked files deleted", "info");
        refreshDiff();
      } else {
        showToast("Delete failed: " + res.error, "error");
        refreshDiff();
      }
    });
  });
});



function openFleetDashboard() {
  const modal = document.getElementById("fleetDashboardModal");
  modal.style.display = "flex";
  refreshFleetDashboard();
}

function refreshFleetDashboard() {
  const tbody = document.getElementById("fleetDashboardTableBody");
  const summary = document.getElementById("fleetDashboardSummary");
  if (!tbody || !summary) return;

  window.pywebview.api.list_running_agents().then(agents => {
    if (!agents || agents.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding: 10px; color:var(--textMuted)">No running agents</td></tr>';
      summary.textContent = "0 agents running";
      return;
    }

    let totalCpu = 0;
    let totalRam = 0;
    
    tbody.innerHTML = agents.map(a => {
      const isRunning = a.status === "running";
      const cpu = isRunning ? (a.cpu_percent || 0) : 0;
      const ram = isRunning ? (a.memory_mb || 0) : 0;
      
      totalCpu += cpu;
      totalRam += ram;
      
      return `
        <tr style="border-bottom: 1px solid var(--surfaceRaised);">
          <td style="padding: 2px 4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width: 250px;" title="${escapeHtml(a.root)}">${escapeHtml(a.root.split(/[\\/]/).pop())}</td>
          <td style="padding: 2px 4px;">${escapeHtml(a.engine_display || a.engine)}</td>
          <td style="padding: 2px 4px; color:${isRunning ? 'var(--success)' : 'var(--textMuted)'}">${escapeHtml(a.status)}</td>
          <td style="padding: 2px 4px;">${cpu.toFixed(1)}%</td>
          <td style="padding: 2px 4px;">${ram.toFixed(1)}</td>
          <td style="padding: 2px 4px;">${formatUptime(a.elapsed)}</td>
          <td style="padding: 2px 4px;">
            ${isRunning ? `<button class="kill-agent-btn" data-root="${escapeHtml(a.root)}" style="font-size:9px; padding:0 4px; color:var(--danger)">Kill</button>` : ''}
          </td>
        </tr>
      `;
    }).join("");
    
    summary.textContent = `${agents.length} agent(s) | CPU: ${totalCpu.toFixed(1)}% | RAM: ${totalRam.toFixed(1)} MB`;
    
    // Bind kill buttons
    tbody.querySelectorAll(".kill-agent-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const root = btn.getAttribute("data-root");
        window.pywebview.api.stop_agent(root).then(res => {
          if (res.ok) {
            showToast("Agent stopped", "info");
            refreshFleetDashboard();
            pollAgentOutput();
          } else {
            showToast("Failed to stop: " + res.error, "error");
          }
        });
      });
    });
  });
}

function formatUptime(seconds) {
  if (!seconds || seconds < 0) return "0s";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s}s`;
}

document.getElementById("closeFleetDashboardBtn")?.addEventListener("click", () => {
  document.getElementById("fleetDashboardModal").style.display = "none";
});
document.getElementById("refreshFleetBtn")?.addEventListener("click", refreshFleetDashboard);

document.getElementById("killAllAgentsBtn")?.addEventListener("click", () => {
  showConfirm("Are you sure you want to kill ALL running agents?", () => {
    window.pywebview.api.list_running_agents().then(agents => {
      const running = agents.filter(a => a.status === "running");
      if (running.length === 0) return showToast("No agents to kill", "info");
      
      let promises = running.map(a => window.pywebview.api.stop_agent(a.root));
      Promise.all(promises).then(() => {
        showToast(`Killed ${running.length} agent(s)`, "info");
        refreshFleetDashboard();
        pollAgentOutput();
      });
    });
  });
});

// Bind runningAgentsBadge in toolbar to open dashboard
document.getElementById("runningAgentsBadge")?.addEventListener("click", () => {
  openFleetDashboard();
});

