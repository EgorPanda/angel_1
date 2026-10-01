const API = "/api/v1";
let currentView = "dashboard";
let selectedNote = null;
let selectedNoteImportance = "medium";
let notesData = [];
let foldersData = [];
let categoriesData = [];
let confirmations = [];
let notesTreeExpanded = {};

const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => [...(root || document).querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error((data && (data.message || data.detail)) || `HTTP ${res.status}`);
  return data;
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}

const RU = {
  low: "низкая", medium: "средняя", high: "высокая",
  running: "работает", stopped: "остановлен", error: "ошибка", starting: "запуск", stopping: "остановка",
  scheduled: "запланировано", completed: "выполнено", cancelled: "отменено", triggered: "сработало", overdue: "просрочено",
  once: "один раз", daily: "ежедневно", weekly: "еженедельно", monthly: "ежемесячно", yearly: "ежегодно",
};
const importanceKeys = { низкая: "low", средняя: "medium", высокая: "high" };
const impBadge = (imp) => `<span class="imp imp-${imp}">${RU[imp] || imp}</span>`;

function showView(name) {
  currentView = name;
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  $$(".sidebar nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  const loaders = {
    dashboard: loadDashboard,
    notes: loadNotes,
    reminders: loadReminders,
    activity: loadActivity,
    stats: loadStats,
    settings: loadSettings,
    system: loadSystem,
    ai: loadAiSession,
  };
  if (loaders[name]) loaders[name]();
}

$$(".sidebar nav button").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));

/* ---------- Обзор ---------- */

async function loadDashboard() {
  const view = $("#view-dashboard");
  try {
    const d = await api("/dashboard");
    view.innerHTML = `
      <h1>Обзор</h1>
      <div class="grid">
        <div class="stat"><div class="num">${d.notes}</div><div class="lbl">Заметок</div></div>
        <div class="stat"><div class="num">${d.upcoming_reminders.length}</div><div class="lbl">Ближайшие напоминания</div></div>
        <div class="stat"><div class="num">${d.unread_notifications}</div><div class="lbl">Уведомлений</div></div>
        <div class="stat"><div class="num">${d.activity_count}</div><div class="lbl">Действий</div></div>
      </div>
      <h2>Ближайшие напоминания</h2>
      ${d.upcoming_reminders.length ? `<div class="card">${d.upcoming_reminders.map((r) => `<div class="row remind-inline">
        <span style="flex:1">🔔 ${esc(r.text)}</span>
        <span class="muted">${new Date(r.trigger_at).toLocaleString()}</span>
      </div>`).join("")}</div>` : '<div class="card muted">Нет запланированных напоминаний.</div>'}
      <h2>Система</h2>
      <div class="card system-line">
        <span>Состояние: <b>${esc(d.system_state)}</b></span>
        <span>LLM: <b>${esc(d.llm_provider)}</b></span>
        <span>Telegram: <b>${d.telegram ? "включён" : "не настроен"}</b></span>
      </div>
    `;
  } catch (e) { toast("Обзор: " + e.message); }
}

/* ---------- Заметки ---------- */

let notesViewReady = false;
async function loadNotes() {
  const view = $("#view-notes");
  if (!notesViewReady) {
    view.innerHTML = `
      <h1>Заметки</h1>
      <div class="notes-layout">
        <div class="notes-tree pane">
          <div class="pane-head">
            <b>Дерево заметок</b>
            <span class="row gap4">
              <button class="btn ghost small" data-act="new-note" onclick="newNoteForm()">+ Заметка</button>
              <button class="btn ghost small" data-act="new-folder" onclick="newFolderForm()">+ Папка</button>
              <button class="btn ghost small" data-act="new-category" onclick="newCategoryForm()">+ Категория</button>
            </span>
          </div>
          <div id="notes-tree-body"></div>
          <div class="notes-search">
            <input id="search-q" placeholder="Поиск по заголовку и содержимому…" onkeydown="if(event.key==='Enter')searchNotes()" />
            <button class="btn" onclick="searchNotes()">Искать</button>
          </div>
          <div id="search-results"></div>
        </div>
        <div class="notes-editor pane" id="notes-editor"></div>
      </div>
    `;
    notesViewReady = true;
  }
  try {
    [notesData, foldersData, categoriesData] = await Promise.all([api("/notes"), api("/folders"), api("/categories")]);
    renderNotesTree();
    renderNotesEditor();
  } catch (e) { toast("Заметки: " + e.message); }
}

function childMap() {
  const byParent = {};
  notesData.forEach((n) => {
    if (n.parent_id && notesData.some((x) => x.id === n.parent_id)) {
      (byParent[n.parent_id] = byParent[n.parent_id] || []).push(n);
    }
  });
  Object.values(byParent).forEach((arr) => arr.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0) || a.title.localeCompare(b.title)));
  return byParent;
}

function isChildOfNote(n) {
  return notesData.some((x) => x.id === n.parent_id);
}

function renderNotesTree() {
  const body = $("#notes-tree-body");
  if (!body) return;
  const byParent = childMap();

  const noteRow = (n, depth, asFolderless) => {
    const kids = byParent[n.id] || [];
    const kidsHtml = kids.length
      ? `<div class="node-children">${kids.map((k) => noteRow(k, depth + 1, false)).join("")}</div>`
      : "";
    const sw = (kids.length || n.has_children) ? `<button class="sw ${notesTreeExpanded[n.id] === false ? "" : "exp"}" onclick="event.stopPropagation();toggleNode('${n.id}')">▾</button>` : '<span class="sw"></span>';
    return `<div class="node" data-id="${n.id}" data-exp="${notesTreeExpanded[n.id] !== false ? "1" : "0"}">
      <div class="node-row ${selectedNote && selectedNote.id === n.id ? "sel" : ""}" onclick="pickNote('${n.id}')">
        ${sw}<span class="node-title">${impBadge(n.importance)} ${esc(n.title)}</span>
        <span class="node-meta">${(n.tags || []).map((t) => `#${esc(t)}`).join(" ")}</span>
      </div>
      ${kidsHtml}
    </div>`;
  };

  const folderBlock = (f) => {
    const fnotes = notesData.filter((n) => n.folder_id === f.id && !isChildOfNote(n));
    const key = "f:" + f.id;
    const expanded = notesTreeExpanded[key] !== false;
    const kids = expanded ? fnotes.map((n) => noteRow(n, 1, false)).join("") : "";
    return `<div class="node folder" data-id="${key}">
      <div class="node-row folder-row ${selectedNote && selectedNote.folder_id === f.id && !isChildOfNote(selectedNote) ? "sel" : ""}"
           onclick="toggleNode('${key}')" data-id="${f.id}">
        <span class="sw ${expanded ? "exp" : ""}">▾</span>
        <span class="folder-ico">📁</span><span class="node-title">${esc(f.name)}</span>
        <span class="node-meta muted">${fnotes.length}</span>
      </div>
      ${expanded ? `<div class="node-children">${kids}</div>` : ""}
    </div>`;
  };

  const orphanNotes = notesData.filter((n) => !n.folder_id && !isChildOfNote(n));

  let html = "";
  if (foldersData.length) {
    html += `<div class="tree-group">${foldersData.map(folderBlock).join("")}</div>`;
  }
  if (orphanNotes.length) {
    html += `<div class="tree-group tree-group-label">Без папки</div><div class="tree-group">${orphanNotes.map((n) => noteRow(n, 0, true)).join("")}</div>`;
  }
  if (!html) html = '<div class="muted pad">Нет заметок. Создайте первую через «+ Заметка».</div>';
  body.innerHTML = html;
}

window.toggleNode = (key) => {
  if (notesTreeExpanded[key] === false) delete notesTreeExpanded[key];
  else notesTreeExpanded[key] = false;
  renderNotesTree();
  renderNotesEditor();
};

function isDescendant(id, target) {
  const byParent = childMap();
  const seen = new Set();
  const stack = [target];
  while (stack.length) {
    const cur = stack.pop();
    if (cur === id) return true;
    if (seen.has(cur)) continue;
    seen.add(cur);
    (byParent[cur] || []).forEach((c) => stack.push(c.id));
  }
  return false;
}

function folderOptions(current) {
  return '<option value="">— без папки —</option>' + foldersData.map((f) => `<option value="${f.id}" ${f.id === current ? "selected" : ""}>${esc(f.name)}</option>`).join("");
}
function categoryOptions(current) {
  return '<option value="">— без категории —</option>' + categoriesData.map((c) => `<option value="${c.id}" ${c.id === current ? "selected" : ""}>${esc(c.name)}</option>`).join("");
}

function renderNotesEditor() {
  const editor = $("#notes-editor");
  if (!editor) return;
  if (!selectedNote) {
    editor.innerHTML = `
      <div class="pane-head"><b>Заметка</b></div>
      <div class="card muted empty-editor">
        <div style="font-size:44px">📄</div>
        <div>Выберите заметку слева или создайте новую.</div>
        <button class="btn" style="margin-top:12px" onclick="newNoteForm()">+ Создать заметку</button>
      </div>
    `;
    return;
  }
  const n = selectedNote;
  const rootOptions = notesData.filter((x) => x.id !== n.id && !isDescendant(n.id, x.id))
    .map((x) => `<option value="${x.id}" ${n.parent_id === x.id ? "selected" : ""}>${esc(x.title)}</option>`).join("");
  const tags = (n.tags || []).map((t) => `<span class="chip">${esc(t)}<button class="chip-x" onclick="removeChip(this)">×</button></span>`).join("");
  const preview = getPreviewState() ? `<div class="md-preview" id="md-preview">${renderMarkdown(n.content)}</div>` : `<textarea id="n-content" placeholder="Пишите в Markdown…">${esc(n.content)}</textarea>`;

  editor.innerHTML = `
    <div class="pane-head">
      <b>Заметка</b>
      <div class="row gap4">
        <input id="n-title" class="title-input" placeholder="Заголовок" value="${esc(n.title)}" />
        <button class="btn danger small" onclick="deleteNote()" title="Удалить заметку">Удалить</button>
      </div>
    </div>
    <div class="card editor-meta">
      <div class="row">
        <div><label>Папка</label><select id="n-folder" onchange="noteFolderChanged(this)">${folderOptions(n.folder_id)}</select></div>
        <div><label>Категория</label><select id="n-category">${categoryOptions(n.category_id)}</select></div>
        <div><label>Родительская заметка</label><select id="n-parent"><option value="">— нет —</option>${rootOptions}</select></div>
      </div>
      <div class="row importance-row">
        <label>Важность</label>
        <div class="seg">
          ${["низкая", "средняя", "высокая"].map((k) => `<button class="seg-btn ${selectedNoteImportance === importanceKeys[k] ? "on" : ""}" data-imp="${importanceKeys[k]}" onclick="setImportance('${importanceKeys[k]}')">${k === "низкая" ? "🟢 " : k === "средняя" ? "🟡 " : "🔴 "}${k}</button>`).join("")}
        </div>
      </div>
      <div><label>Теги</label>
        <div class="chips"><span class="chips-list">${tags}</span><input id="n-tags" class="chips-input" placeholder="тег + Enter или запятая" onkeydown="chipsKey(this,event)" onblur="flushChip(this)" /></div>
      </div>
    </div>
    <div class="card md-card">
      <div class="md-toolbar">
        <button class="btn ghost small" onclick="mdCmd('bold')">** Ж</button>
        <button class="btn ghost small" onclick="mdCmd('italic')">* К</button>
        <button class="btn ghost small" onclick="mdCmd('strike')">~~ З</button>
        <button class="btn ghost small" onclick="mdCmd('code')"><span class="mono">Код</span></button>
        <button class="btn ghost small" onclick="mdCmd('link')">🔗 Ссылка</button>
        <button class="btn ghost small" onclick="mdCmd('list')">• Список</button>
        <button class="btn ghost small" onclick="mdCmd('quote')">❝ Цитата</button>
        <span style="flex:1"></span>
        <label class="toggle"><input type="checkbox" id="n-preview" onchange="togglePreview()" ${getPreviewState() ? "checked" : ""} /> Предпросмотр</label>
        <button class="btn" onclick="saveNote()">Сохранить (Ctrl+S)</button>
      </div>
      ${preview}
      <div class="md-hints">
        <b>Горячие клавиши:</b>
        <span>Ctrl+S — сохранить</span><span>Ctrl+B — жирный</span><span>Ctrl+I — курсив</span>
        <span>Ctrl+K — ссылка</span><span>Ctrl+E — код</span><span>Ctrl+Enter — предпросмотр</span>
      </div>
    </div>
    <div class="card">
      <b>Связи</b>
      ${notesData.filter((x) => x.id !== n.id).map((x) => `<div class="row rel-row">
        <span style="flex:1">${esc(x.title)}</span>
        <button class="btn ghost small" onclick="relateNote('${n.id}','${x.id}','related')">Связать</button>
        <button class="btn ghost small" onclick="relateNote('${n.id}','${x.id}','depends_on')">Зависит</button>
      </div>`).join("")}
      <div class="muted" style="margin-top:8px">Обновлено: ${n.updated_at ? new Date(n.updated_at).toLocaleString() : "—"}</div>
    </div>
  `;
  const mel = $("#notes-editor");
  if (!getPreviewState()) {
    const ta = $("#n-content");
    if (ta) ta.focus();
  }
}

function hasNodeChildren(n) {
  return notesData.some((x) => x.parent_id === n.id);
}

function getPreviewState() {
  return localStorage.getItem("angel.mdpreview") === "1";
}

function setPreviewState(v) {
  localStorage.setItem("angel.mdpreview", v ? "1" : "0");
}

window.togglePreview = () => {
  const box = $("#n-preview");
  setPreviewState(box.checked);
  const content = $("#n-content") ? $("#n-content").value : selectedNote.content;
  renderNotesEditor();
  if (box.checked && selectedNote) selectedNote.content = content;
};

function renderMarkdown(src) {
  let h = esc(src);
  h = h.replace(/^### (.*)$/gm, '<h4>$1</h4>');
  h = h.replace(/^## (.*)$/gm, '<h3>$1</h3>');
  h = h.replace(/^# (.*)$/gm, '<h2>$1</h2>');
  h = h.replace(/^> (.*)$/gm, '<blockquote>$1</blockquote>');
  h = h.replace(/^\s*[-*] (.*)$/gm, '<li>$1</li>');
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  h = h.replace(/\*\*\*([^*]+)\*\*\*/g, '<b><i>$1</i></b>');
  h = h.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  h = h.replace(/\*([^*]+)\*/g, '<i>$1</i>');
  h = h.replace(/~~([^~]+)~~/g, '<s>$1</s>');
  h = h.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  h = h.replace(/\n/g, '<br/>');
  return h || '<div class="muted">Пусто…</div>';
}

window.setImportance = (imp) => {
  selectedNoteImportance = imp;
  renderNotesEditor();
  if (selectedNote) selectedNote.importance = imp;
};

function currentContent() {
  const ta = $("#n-content");
  return ta ? ta.value : selectedNote.content;
}

window.mdCmd = (cmd) => {
  const ta = $("#n-content");
  if (ta && !getPreviewState()) applyMarkdownCmd(ta, cmd);
};

function applyMarkdownCmd(ta, cmd) {
  const s = ta.selectionStart, e = ta.selectionEnd, v = ta.value;
  let sel = v.slice(s, e) || "текст";
  let ins, cursor;
  if (cmd === "bold") { ins = "**" + sel + "**"; cursor = s + 2; }
  else if (cmd === "italic") { ins = "*" + sel + "*"; cursor = s + 1; }
  else if (cmd === "strike") { ins = "~~" + sel + "~~"; cursor = s + 2; }
  else if (cmd === "code") { ins = "`" + sel + "`"; cursor = s + 1; }
  else if (cmd === "link") { ins = "[" + sel + "](https://example.com)"; cursor = s + sel.length + 2; }
  else if (cmd === "list") { ins = "- " + sel; cursor = s; }
  else if (cmd === "quote") { ins = "> " + sel; cursor = s; }
  ta.setRangeText(ins, s, e);
  ta.selectionStart = ta.selectionEnd = cursor + (sel === "текст" ? 0 : 0);
  ta.focus();
}

const NOTE_HOTKEYS = {
  "s": "save", "b": "md_bold", "i": "md_italic", "k": "md_link", "e": "md_code", ";": "md_strike",
};

$("#view-notes").addEventListener("keydown", (ev) => {
  const ta = ev.target;
  if (ta && ta.id === "n-content") {
    if (ev.ctrlKey || ev.metaKey) {
      const k = ev.key.toLowerCase();
      if (k === "Enter") { ev.preventDefault(); window.togglePreview(); return; }
      const act = NOTE_HOTKEYS[k];
      if (!act) return;
      ev.preventDefault();
      if (act === "save") window.saveNote();
      else applyMarkdownCmd(ta, act.slice(3));
      return;
    }
    if (ev.key === "Tab") {
      ev.preventDefault();
      ta.setRangeText("  ", ta.selectionStart, ta.selectionEnd, "end");
    }
  }
});

window.pickNote = async (id) => {
  try {
    const detail = await api(`/notes/${id}`);
    const base = notesData.find((x) => x.id === id) || {};
    selectedNote = { ...base, ...detail };
    selectedNoteImportance = selectedNote.importance || "medium";
    renderNotesTree();
    renderNotesEditor();
  } catch (e) { toast(e.message); }
};

function newNoteForm(folderId, parentId) {
  selectedNote = { title: "", content: "", folder_id: folderId || null, category_id: null, parent_id: parentId || null, importance: "medium", tags: [] };
  selectedNoteImportance = "medium";
  renderNotesEditor();
}
window.newNoteForm = newNoteForm;

function newFolderForm() {
  const name = prompt("Название папки:");
  if (!name) return;
  api("/folders", { method: "POST", body: JSON.stringify({ name }) }).then(loadNotes).catch((e) => toast(e.message));
}
window.newFolderForm = newFolderForm;

function newCategoryForm() {
  const name = prompt("Название категории:");
  if (!name) return;
  api("/categories", { method: "POST", body: JSON.stringify({ name }) }).then(loadNotes).catch((e) => toast(e.message));
}
window.newCategoryForm = newCategoryForm;

function readChips() {
  const list = $("#notes-editor .chips-list");
  if (!list) return [];
  return $$(".chip", list).map((c) => c.childNodes[0].nodeValue.trim()).filter(Boolean);
}

window.removeChip = (btn) => {
  const chip = btn.closest(".chip");
  chip.remove();
};

window.flushChip = (input) => {
  const v = input.value.trim();
  if (!v) return;
  let tags = v.split(/[,;]/).map((s) => s.trim()).filter(Boolean);
  tags.forEach((t) => {
    const list = $("#notes-editor .chips-list");
    if (list && !readChips().includes(t)) list.insertAdjacentHTML("beforeend", `<span class="chip">${esc(t)}<button class="chip-x" onclick="removeChip(this)">×</button></span>`);
  });
  input.value = "";
};

window.chipsKey = (input, ev) => {
  if (ev.key === "Enter" || ev.key === "," || ev.key === ";") {
    ev.preventDefault();
    window.flushChip(input);
  } else if (ev.key === "Backspace" && !input.value) {
    const list = $("#notes-editor .chips-list");
    if (list) { const last = list.querySelector(".chip:last-child"); if (last) last.remove(); }
  }
};

window.saveNote = async () => {
  const title = ($("#n-title") && $("#n-title").value.trim()) || "Без названия";
  const payload = {
    title,
    content: $("#n-content") ? $("#n-content").value : selectedNote.content,
    folder_id: ($("#n-folder") ? $("#n-folder").value : selectedNote.folder_id) || null,
    category_id: ($("#n-category") ? $("#n-category").value : selectedNote.category_id) || null,
    importance: selectedNoteImportance,
    parent_id: ($("#n-parent") ? $("#n-parent").value : selectedNote.parent_id) || null,
    tags: readChips(),
  };
  try {
    if (selectedNote.id) await api(`/notes/${selectedNote.id}`, { method: "PATCH", body: JSON.stringify(payload) });
    else await api("/notes", { method: "POST", body: JSON.stringify(payload) });
    toast("Сохранено");
    selectedNote = null;
    await loadNotes();
  } catch (e) { toast(e.message); }
};

window.deleteNote = async () => {
  if (!confirm("Удалить заметку?")) return;
  try {
    await api(`/notes/${selectedNote.id}`, { method: "DELETE" });
    selectedNote = null;
    await loadNotes();
  } catch (e) { toast(e.message); }
};

window.relateNote = async (source, target, type) => {
  try {
    await api(`/notes/${source}/relations`, { method: "POST", body: JSON.stringify({ target_id: target, relation_type: type }) });
    toast("Связь добавлена");
  } catch (e) { toast(e.message); }
};

window.searchNotes = async () => {
  const q = $("#search-q").value.trim();
  if (!q) return;
  const box = $("#search-results");
  box.innerHTML = '<div class="muted">Ищем…</div>';
  try {
    const results = await api(`/notes/search?q=${encodeURIComponent(q)}`);
    box.innerHTML = results.length
      ? results.map((r) => `<div class="search-hit" onclick="pickNote('${r.id}')">
          <b>${esc(r.title)}</b> ${impBadge(r.importance)} <span class="muted">${r.updated_at ? new Date(r.updated_at).toLocaleDateString() : ""}</span>
          <div class="muted sm">${esc((r.snippet || "").slice(0, 180))}</div>
        </div>`).join("")
      : '<div class="muted">Ничего не найдено.</div>';
  } catch (e) { toast(e.message); }
};

/* ---------- Напоминания ---------- */

async function loadReminders() {
  const view = $("#view-reminders");
  try {
    const reminders = await api("/reminders");
    view.innerHTML = `
      <h1>Напоминания</h1>
      <div class="card row remind-create align-end">
        <div><label>Текст</label><input id="r-text" placeholder="Например: купить ножницы" /></div>
        <div><label>Дата и время</label><input id="r-time" type="datetime-local" /></div>
        <div><label>Повтор</label><select id="r-freq"><option value="once">Один раз</option><option value="daily">Ежедневно</option><option value="weekly">Еженедельно</option><option value="monthly">Ежемесячно</option></select></div>
        <button class="btn" onclick="createReminder()">Создать</button>
      </div>
      <h2>Запланированные</h2>
      ${reminders.length ? `<div class="card">${reminders.map(reminderRow).join("")}</div>` : '<div class="card muted">Нет напоминаний.</div>'}
    `;
  } catch (e) { toast("Напоминания: " + e.message); }
}

window.createReminder = async () => {
  const text = $("#r-text").value.trim();
  const time = $("#r-time").value;
  if (!text || !time) return toast("Заполните текст и время");
  const payload = { text, trigger_at: new Date(time).toISOString(), repeat_rule: { freq: $("#r-freq").value } };
  try {
    await api("/reminders", { method: "POST", body: JSON.stringify(payload) });
    toast("Напоминание создано");
    loadReminders();
  } catch (e) { toast(e.message); }
};

function reminderRow(r) {
  const d = new Date(r.trigger_at);
  const cls = r.status === "scheduled" ? "ok" : r.status === "completed" ? "neutral" : r.status === "cancelled" ? "warn" : "bad";
  return `<div class="row align-center remind-inline">
    <span class="remind-dot" style="flex:0"></span>
    <span style="flex:1">${esc(r.text)} <span class="muted">— ${d.toLocaleString()}</span>
      ${r.repeat_rule && r.repeat_rule.freq !== "once" ? `<span class="pill">${RU[r.repeat_rule.freq] || esc(r.repeat_rule.freq)}</span>` : ""}
    </span>
    <span class="badge ${cls}">${RU[r.status] || esc(r.status)}</span>
    ${r.status === "scheduled" ? `<button class="btn ghost small" onclick="cancelReminder('${r.id}')">Отмена</button>` : ""}
  </div>`;
}

window.cancelReminder = async (id) => {
  try { await api(`/reminders/${id}/cancel`, { method: "POST" }); loadReminders(); } catch (e) { toast(e.message); }
};

/* ---------- AI-чат ---------- */

let aiMessages = [];
async function loadAiSession() {
  const view = $("#view-ai");
  view.innerHTML = `
    <h1>AI-чат</h1>
    <div id="chat-log"></div>
    <div class="chat-input">
      <input id="ai-input" placeholder="Например: создай заметку о запуске Angel AI…" onkeydown="if(event.key==='Enter')sendAi()" />
      <button class="btn" onclick="sendAi()">Отправить</button>
    </div>
  `;
  aiMessages = [];
  await loadConfirmations();
  renderChat();
}

async function loadConfirmations() {
  try { confirmations = await api("/system/confirmations"); } catch (e) { confirmations = []; }
}

function renderChat() {
  const log = $("#chat-log");
  if (!log) return;
  log.innerHTML = aiMessages.map((m) => `<div class="msg ${m.role}">${esc(m.text)}</div>`).join("");
  const pending = confirmations.filter((c) => c.status === "pending" || c.status === "awaiting" || !c.status);
  pending.forEach((c) => {
    log.insertAdjacentHTML("beforeend", `<div class="confirm-bar">
      <b>Требуется подтверждение:</b> <code>${esc(c.tool)}</code> — ${esc(c.message || "")}
      <div class="row gap4" style="margin-top:8px">
        <button class="btn ok small" onclick="approveConfirm('${c.id}')">Подтвердить</button>
        <button class="btn danger small" onclick="denyConfirm('${c.id}')">Отклонить</button>
      </div>
    </div>`);
  });
  log.scrollTop = log.scrollHeight;
}

window.sendAi = async () => {
  const input = $("#ai-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  aiMessages.push({ role: "user", text });
  aiMessages.push({ role: "ai", text: "…думаю…" });
  renderChat();
  try {
    const res = await api("/ai/chat", { method: "POST", body: JSON.stringify({ text }) });
    aiMessages.pop();
    if (res.status === "awaiting_confirmation") {
      aiMessages.push({ role: "ai", text: "Для этого действия требуется подтверждение." });
      await loadConfirmations();
    } else if (res.status === "completed") {
      aiMessages.push({ role: "ai", text: res.text });
    } else {
      aiMessages.push({ role: "ai", text: "Ошибка: " + (res.error || res.status) });
    }
    renderChat();
  } catch (e) {
    aiMessages.pop();
    aiMessages.push({ role: "ai", text: "Ошибка: " + e.message });
    renderChat();
  }
};

window.approveConfirm = async (id) => {
  try { await api(`/system/confirmations/${id}/approve`, { method: "POST" }); toast("Подтверждено"); await loadConfirmations(); renderChat(); }
  catch (e) { toast(e.message); }
};
window.denyConfirm = async (id) => {
  try { await api(`/system/confirmations/${id}/deny`, { method: "POST" }); toast("Отклонено"); await loadConfirmations(); renderChat(); }
  catch (e) { toast(e.message); }
};

/* ---------- Журнал ---------- */

async function loadActivity() {
  const view = $("#view-activity");
  try {
    const acts = await api("/activity");
    view.innerHTML = `
      <h1>Журнал действий</h1>
      <div class="card table-scroll"><table>
        <thead><tr><th>Время</th><th>Участник</th><th>Действие</th><th>Модуль</th><th>Инструмент</th><th>Статус</th><th>Длительность</th></tr></thead>
        <tbody>${acts.map((a) => `
          <tr>
            <td class="muted">${a.created_at ? new Date(a.created_at).toLocaleString() : ""}</td>
            <td>${esc(a.actor)}</td>
            <td>${esc(a.action)}</td>
            <td class="muted">${esc(a.module)}</td>
            <td class="muted">${esc(a.tool || "")}</td>
            <td><span class="badge ${a.status === "ok" ? "ok" : "bad"}">${a.status === "ok" ? "ОК" : esc(a.status)}</span></td>
            <td class="muted">${a.duration_ms != null ? a.duration_ms + " мс" : ""}</td>
          </tr>`).join("") || '<tr><td colspan="7">Нет данных</td></tr>'}
        </tbody></table>
      </div>
    `;
  } catch (e) { toast("Журнал: " + e.message); }
}

/* ---------- Статистика (логи) ---------- */

const statsState = { autoRefresh: false, offset: 0, limit: 100, total: 0, running: false, expandId: null };

function statsParams() {
  const p = new URLSearchParams();
  const lvl = $("#st-lvl")?.value || "all";
  if (lvl === "errors") p.set("errors_only", "true");
  else if (lvl && lvl !== "all") p.set("level", lvl);
  const mod = $("#st-mod")?.value.trim();
  if (mod) p.set("module", mod);
  const q = $("#st-q")?.value.trim();
  if (q) p.set("query", q);
  const from = $("#st-from")?.value;
  if (from) p.set("from_date", from);
  const to = $("#st-to")?.value;
  if (to) p.set("to_date", to);
  p.set("limit", String(statsState.limit));
  p.set("offset", String(statsState.offset));
  return p;
}

function lvlBadge(lvl) {
  const cls = lvl === "ERROR" || lvl === "CRITICAL" ? "bad" : lvl === "WARNING" ? "warn" : "ok";
  return `<span class="badge ${cls}">${esc(lvl)}</span>`;
}

function fmtDt(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

async function loadStats() {
  const view = $("#view-stats");
  if (!statsState.running) {
    statsState.running = true;
    view.innerHTML = `
      <h1>Статистика и логи</h1>
      <div class="card filters">
        <div class="cfg-fields">
          <div class="cfg-field"><label>Уровень</label>
            <select id="st-lvl">
              <option value="all">Все уровни</option>
              <option value="errors">Ошибки (ERROR/CRITICAL)</option>
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
              <option value="CRITICAL">CRITICAL</option>
            </select></div>
          <div class="cfg-field"><label>Модуль / логгер</label><input id="st-mod" placeholder="напр. telegram, llm, core…" /></div>
          <div class="cfg-field"><label>Поиск по тексту</label><input id="st-q" placeholder="часть сообщения или ошибки…" /></div>
          <div class="cfg-field"><label>С даты</label><input type="date" id="st-from" /></div>
          <div class="cfg-field"><label>По дату</label><input type="date" id="st-to" /></div>
        </div>
        <div class="row gap4 cfg-actions" style="margin-top:8px">
          <button class="btn small" onclick="statsApply()">Применить</button>
          <button class="btn ghost small" onclick="statsReset()">Сбросить</button>
          <label class="toggle" style="margin-left:8px"><input type="checkbox" id="st-auto" onchange="statsToggleAuto()" /> Автообновление</label>
          <button class="btn ghost small" onclick="statsExport()">Экспорт .txt</button>
          <button class="btn ghost small dangerous" onclick="statsClear()">Очистить по фильтру</button>
        </div>
      </div>
      <div id="stats-summary"></div>
      <div class="card table-scroll" id="stats-table"></div>
    `;
  }
  try {
    const [sum, logs] = await Promise.all([api("/logs/summary"), api("/logs?" + statsParams().toString())]);
    statsState.total = logs.total;
    statsState.offset = logs.offset;
    renderStatsSummary(sum);
    renderStatsTable(logs);
  } catch (e) { toast("Статистика: " + e.message); }
}

function renderStatsSummary(sum) {
  const er = sum.last_error;
  const el = $("#stats-summary");
  el.innerHTML = `
    <div class="grid">
      <div class="stat"><div class="num">${sum.total}</div><div class="lbl">Всего записей</div></div>
      <div class="stat"><div class="num ${sum.today_errors ? "num-bad" : ""}">${sum.today_errors}</div><div class="lbl">Ошибок за 24 ч</div></div>
      <div class="stat"><div class="num">${(sum.levels["WARNING"] || 0)}</div><div class="lbl">Предупреждений</div></div>
      <div class="stat"><div class="num">${sum.today_total}</div><div class="lbl">Записей за 24 ч</div></div>
    </div>
    ${sum.top_loggers.length ? `<div class="row gap4" style="margin:8px 0;flex-wrap:wrap">
      ${sum.top_loggers.map((t) => `<span class="chip">${esc(t.logger)} · ${t.count}</span>`).join("")}
    </div>` : ""}
    ${er ? `<div class="card warn-card"><b>Последняя ошибка:</b> ${fmtDt(er.ts)} · <span class="muted">${esc(er.logger)}</span> · ${esc(er.message)}
      <button class="btn ghost small" onclick="statsContext('${er.id}','${esc(er.ts)}')">Что предшествовало</button>
      <div class="muted sm" style="margin-top:4px">${esc((er.exc_text || "").split("\n").slice(0, 4).join("\n"))}</div>
    </div>` : ""}`;
}

function renderStatsTable(logs) {
  const el = $("#stats-table");
  const rows = logs.items.map((r) => {
    const hasExtra = Object.keys(r.extra || {}).length;
    const expanded = statsState.expandId === r.id;
    const detail = expanded ? renderLogDetail(r) : "";
    const delBtn = r.level === "ERROR" || r.level === "CRITICAL"
      ? `<button class="btn ghost small" onclick="statsContext('${r.id}','${r.ts}')">Контекст до</button>` : "";
    return `
      <tr class="log-row" onclick="statsToggleRow('${r.id}')">
        <td class="muted nowrap">${fmtDt(r.ts)}</td>
        <td>${lvlBadge(r.level)}</td>
        <td class="muted">${esc(r.logger)}</td>
        <td class="log-msg">${esc(r.message)}</td>
        <td class="row gap4">${delBtn}<button class="btn ghost small">${expanded ? "▴" : "▾"}</button></td>
      </tr>
      ${detail}`;
  }).join("");
  const pager = statsPager();
  el.innerHTML = `
    <div class="row" style="padding:8px 0">${pager}</div>
    <table class="logs-table">${rows || '<tr><td class="muted">Нет записей по заданным условиям.</td></tr>'}</table>
    <div class="row" style="padding:8px 0">${pager}</div>`;
}

function renderLogDetail(r) {
  const extra = Object.keys(r.extra || {}).length ? `<div class="muted sm">extra: ${esc(JSON.stringify(r.extra))}</div>` : "";
  const ids = [r.correlation_id, r.request_id, r.task_id, r.user_id].filter(Boolean);
  const idLine = ids.length ? `<div class="muted sm">correlation: ${esc(r.correlation_id || "—")} · request: ${esc(r.request_id || "—")} · task: ${esc(r.task_id || "—")}</div>` : "";
  const exc = r.exc_text ? `<pre class="exc-box">${esc(r.exc_text)}</pre>` : "";
  return `<tr class="log-detail"><td colspan="5">
    <div class="muted sm">${idLine}</div>${extra}
    ${r.level === "ERROR" || r.level === "CRITICAL" ? `<button class="btn ghost small" onclick="event.stopPropagation();statsContext('${r.id}','${r.ts}')">Показать, что предшествовало</button>` : ""}
    ${exc}
  </td></tr>`;
}

function statsPager() {
  const pages = Math.max(1, Math.ceil(statsState.total / statsState.limit));
  const cur = Math.floor(statsState.offset / statsState.limit) + 1;
  return `<span class="muted">${statsState.total} записей · стр. ${cur} / ${pages}</span>
    <span class="row gap4" style="margin-left:auto">
      <button class="btn ghost small" onclick="statsPage(0)" ${cur <= 1 ? "disabled" : ""}>◀ Первая</button>
      <button class="btn ghost small" onclick="statsPage(${statsState.offset - statsState.limit})" ${statsState.offset <= 0 ? "disabled" : ""}>◀ Назад</button>
      <button class="btn ghost small" onclick="statsPage(${statsState.offset + statsState.limit})" ${statsState.offset + statsState.limit >= statsState.total ? "disabled" : ""}>Вперёд ▶</button>
    </span>`;
}

window.statsApply = () => { statsState.offset = 0; statsState.expandId = null; loadStats(); };

window.statsReset = () => {
  ["#st-lvl", "#st-mod", "#st-q", "#st-from", "#st-to"].forEach((s) => { const el = $(s); if (el) el.value = s === "#st-lvl" ? "all" : ""; });
  statsState.offset = 0;
  loadStats();
};

window.statsToggleRow = (id) => {
  statsState.expandId = statsState.expandId === id ? null : id;
  loadStats();
};

window.statsPage = (offset) => { statsState.offset = Math.max(0, offset); loadStats(); };

window.statsToggleAuto = () => {
  statsState.autoRefresh = !!$("#st-auto")?.checked;
};

window.statsContext = async (id, ts) => {
  try {
    const p = new URLSearchParams({ to_date: ts, order: "desc", limit: "15" });
    const data = await api("/logs?" + p.toString());
    const items = data.items.slice().reverse();
    const block = document.createElement("div");
    block.className = "card context-box";
    block.innerHTML = `<b>Что было до этой записи (${fmtDt(ts)}):</b>
      ${items.map((r) => `<div class="ctx-line ${r.level === "ERROR" || r.level === "CRITICAL" ? "ctx-err" : ""}">
        <span class="muted nowrap">${fmtDt(r.ts)}</span> ${lvlBadge(r.level)} <span class="muted">${esc(r.logger)}</span> ${esc(r.message)}
      </div>`).join("") || '<div class="muted">Нет более ранних записей.</div>'}`;
    const btn = document.createElement("button");
    btn.className = "btn ghost small";
    btn.textContent = "Скрыть";
    btn.onclick = () => block.remove();
    block.prepend(btn);
    document.querySelector(".logs-table")?.after(block);
    block.scrollIntoView({ block: "center" });
  } catch (e) { toast("Контекст: " + e.message); }
};

window.statsClear = async () => {
  if (!confirm("Удалить логи по текущему фильтру? (Без фильтров — все записи.)")) return;
  try {
    const res = await api("/logs?" + statsParams().toString(), { method: "DELETE" });
    toast("Удалено записей: " + res.deleted);
    loadStats();
  } catch (e) { toast(e.message); }
};

window.statsExport = async () => {
  try {
    const data = await api("/logs?" + statsParams().toString());
    const lines = data.items.map((r) => `${r.ts}\t${r.level}\t${r.logger}\t${(r.message || "").replace(/\n/g, " ")}`).join("\n");
    const blob = new Blob([lines], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `angel-logs-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { toast(e.message); }
};

/* ---------- Настройки ---------- */

async function loadSettings() {
  const view = $("#view-settings");
  try {
    const [s, aiCfg] = await Promise.all([api("/settings"), api("/system/modules/ai/config")]);
    view.innerHTML = `
      <h1>Настройки</h1>
      <div class="card">
        <h2>AI и Ollama</h2>
        ${renderAiForm(aiCfg.fields, aiCfg.values)}
      </div>
      <div class="card">
        <h2>Markdown-хранилище</h2>
        <p>Путь: <code>${esc(s.markdown_vault_path)}</code></p>
        <button class="btn ghost" onclick="triggerSync()">Синхронизировать сейчас</button>
      </div>
      <div class="card">
        <h2>Разрешения AI</h2>
        <div id="perm-list"></div>
      </div>
    `;
    const perms = await api("/system/permissions");
    $("#perm-list").innerHTML = `
      <div class="table-scroll"><table><thead><tr><th>Инструмент</th><th>Описание</th><th>Режим</th><th></th></tr></thead>
      <tbody>${perms.tools.map((t) => `
        <tr><td><b>${esc(t.name)}</b></td>
        <td class="muted">${esc(t.description)}</td>
        <td><select data-perm="${esc(t.permission)}">
          <option value="allow" ${t.current === "allow" ? "selected" : ""}>Автоматически</option>
          <option value="confirm" ${t.current === "confirm" ? "selected" : ""}>С подтверждением</option>
          <option value="forbid" ${t.current === "forbid" ? "selected" : ""}>Запрещено</option>
        </select></td>
        <td><button class="btn ghost small" onclick="savePerm('${esc(t.permission)}',this)">Сохранить</button></td></tr>`).join("")}
      </tbody></table></div>`;
  } catch (e) { toast("Настройки: " + e.message); }
}

function renderAiForm(fields, values) {
  const v = (k, dflt) => (values[k] != null ? values[k] : dflt);
  const provider = v("llm_provider", "ollama");
  const providers = [
    { value: "ollama", label: "Ollama (локально, рекомендуется)" },
    { value: "local", label: "Local (OpenAI-совместимый)" },
    { value: "api", label: "API (OpenAI-совместимый HTTP)" },
  ];
  return `<div class="cfg-form">
    <div class="cfg-fields">
      <div class="cfg-field"><label>Провайдер</label>
        <select data-key="llm_provider">
          ${providers.map((o) => `<option value="${esc(o.value)}" ${String(provider) === String(o.value) ? "selected" : ""}>${esc(o.label)}</option>`).join("")}
        </select>
        <div class="muted sm">Ollama должна быть запущена локально (обычно http://localhost:11434).</div>
      </div>
      <div class="cfg-field"><label>URL API (строка подключения)</label>
        <input type="text" data-key="llm_api_url" id="ai-api-url" value="${esc(v("llm_api_url", "http://localhost:11434/v1"))}" placeholder="http://localhost:11434/v1" /></div>
      <div class="cfg-field"><label>Модель</label>
        <input type="text" data-key="llm_model" id="ai-model" list="ollama-models-dl" value="${esc(v("llm_model", "qwen2.5:7b"))}" placeholder="qwen2.5:7b" /></div>
      <div class="cfg-field"><label>API-ключ (если требуется)</label>
        <input type="password" data-key="llm_api_key" value="${esc(v("llm_api_key", ""))}" /></div>
      <div class="cfg-field"><label>Температура</label>
        <input type="number" step="any" data-key="llm_temperature" value="${esc(v("llm_temperature", 0.3))}" /></div>
      <div class="cfg-field"><label>Макс. токенов</label>
        <input type="number" step="any" data-key="llm_max_tokens" value="${esc(v("llm_max_tokens", 1024))}" /></div>
      <div class="cfg-field"><label>Таймаут (сек)</label>
        <input type="number" step="any" data-key="llm_timeout" value="${esc(v("llm_timeout", 60))}" /></div>
      <div class="cfg-field"><label>Макс. шагов агента</label>
        <input type="number" step="any" data-key="llm_max_steps" value="${esc(v("llm_max_steps", 8))}" /></div>
    </div>
    <datalist id="ollama-models-dl"></datalist>
    <div class="row gap4 cfg-actions">
      <button type="button" class="btn small" onclick="saveAiCfg(this)">Сохранить</button>
      <button type="button" class="btn ghost small" onclick="aiFetchModels()">Получить модели из Ollama</button>
      <button type="button" class="btn ghost small" onclick="aiTestConn()">Проверить подключение</button>
      <button type="button" class="btn ghost small" onclick="moduleAction('ai','restart')">Перезапустить модуль ai</button>
    </div>
    <div id="ai-conn-status" class="muted sm"></div>
  </div>`;
}

window.aiFetchModels = async () => {
  const url = ($("#ai-api-url")?.value || "http://localhost:11434/v1").trim();
  const status = $("#ai-conn-status");
  try {
    status.textContent = "Запрашиваю список моделей…";
    const data = await api("/ai/ollama/models?base_url=" + encodeURIComponent(url));
    const dl = $("#ollama-models-dl");
    dl.innerHTML = data.models.map((m) => `<option value="${esc(m)}">`).join("");
    const model = $("#ai-model");
    if (!data.models.includes(model.value) && data.models[0]) model.value = data.models[0];
    status.textContent = `Найдено моделей: ${data.models.length} (${data.base_url}).`;
  } catch (e) { status.textContent = e.message; toast("Ollama: " + e.message); }
};

window.aiTestConn = async () => {
  const status = $("#ai-conn-status");
  const payload = {
    llm_provider: $('[data-key="llm_provider"]')?.value,
    llm_model: $("#ai-model")?.value,
    llm_api_url: ($("#ai-api-url")?.value || "").trim(),
    llm_api_key: $('input[data-key="llm_api_key"]')?.value,
  };
  status.textContent = "Проверяю…";
  try {
    const res = await api("/ai/test", { method: "POST", body: JSON.stringify(payload) });
    status.innerHTML = `${res.ok ? "Подключение работает" : "НЕ работает"} — провайдер: ${esc(res.provider || "")}, модель: ${esc(res.model || "")}, API: ${esc(res.api_url || "")}<br/><span class="muted">${esc(res.message || "")}</span>`;
  } catch (e) { status.textContent = e.message; }
};

window.saveAiCfg = async (btn) => {
  const form = btn.closest(".cfg-form");
  const payload = {};
  form.querySelectorAll("[data-key]").forEach((el) => {
    let v = el.value;
    if (["llm_temperature", "llm_timeout"].includes(el.dataset.key)) v = parseFloat(v);
    else if (["llm_max_tokens", "llm_max_steps"].includes(el.dataset.key)) v = parseInt(v, 10);
    payload[el.dataset.key] = v;
  });
  try {
    await api("/system/modules/ai/config", { method: "PUT", body: JSON.stringify(payload) });
    toast("Настройки AI сохранены. Перезапустите модуль ai для применения.");
    await api("/system/modules/ai/restart", { method: "POST" });
    toast("Модуль ai перезапущен, провайдер пересобран.");
  } catch (e) { toast(e.message); }
};

window.savePerm = async (permission, btn) => {
  const mode = btn.closest("tr").querySelector("select").value;
  try { await api(`/system/permissions/${permission}`, { method: "POST", body: JSON.stringify({ mode }) }); toast("Сохранено"); }
  catch (e) { toast(e.message); }
};

window.triggerSync = async () => {
  try { await api("/markdown/sync", { method: "POST" }); toast("Синхронизация поставлена в очередь"); }
  catch (e) { toast(e.message); }
};

/* ---------- Система ---------- */

const HEALTH_RU = {
  core: "Ядро", database: "База данных", llm: "LLM", telegram: "Telegram", worker_pool: "Пул задач", scheduler: "Планировщик",
  listeners: "Слушатели событий", events: "Шина событий",
};
function healthLabel(k) {
  if (k.startsWith("module:")) return "Модуль · " + k.slice(7);
  if (HEALTH_RU[k]) return HEALTH_RU[k];
  return k;
}

let systemState = {};
async function loadSystem() {
  const view = $("#view-system");
  try {
    const [health, modules, status, workers, scheduler, users] = await Promise.all([
      api("/system/health"), api("/system/modules"), api("/system/status"), api("/workers/status"), api("/scheduler/status"), api("/system/users"),
    ]);
    systemState = { modules, users, scheduler };
    view.innerHTML = `
      <h1>Система</h1>
      <div class="grid">
        <div class="card sys-health">
          <h2>Здоровье</h2>
          ${healthLabelRow("total", health.healthy)}
          <table class="health-table"><tbody>
            ${Object.entries(health).filter(([k]) => !k.startsWith("_")).map(([k, v]) => `<tr>
              <td>${esc(healthLabel(k))}</td>
              <td><span class="badge ${v.ok ? "ok" : "bad"}">${v.ok ? "ОК" : "ОШИБКА"}</span></td>
              <td class="muted">${esc(typeof v.detail === "string" ? v.detail : v.detail instanceof Object ? JSON.stringify(v.detail) : "")}</td>
            </tr>`).join("")}
          </tbody></table>
        </div>
        <div class="card">
          <h2>Диспетчер</h2>
          <p>Состояние: <b>${esc(status.state)}</b></p>
          <p class="muted">Пул задач: ${esc(JSON.stringify(workers))}</p>
          <p>Планировщик: <b>${esc(scheduler.status || "остановлен")}</b><br/>
          <span class="muted">проверок: ${scheduler.scanned || 0} · сработало: ${scheduler.triggered || 0}</span></p>
          <p>Пользователей: <b>${users.length}</b></p>
        </div>
      </div>
      <h2>Модули</h2>
      <div class="card" id="modules-list">${modules.map(moduleCard).join("")}</div>
      <h2>Пользователи Telegram</h2>
      <div class="card table-scroll"><table class="users-table">
        <thead><tr><th>Пользователь</th><th>Роль</th><th>Telegram</th><th>Последний визит</th><th>Действия</th></tr></thead>
        <tbody>${users.map(userRow).join("")}</tbody>
      </table></div>
    `;
    $$(".module-config").forEach((el) => bindConfigEvents(el));
  } catch (e) { toast("Система: " + e.message); }
}

function healthLabelRow(k, ok) {
  return `<span class="health-total ${ok ? "ok" : "bad"}"><b>${ok ? "Система в порядке" : "Есть проблемы"}</b></span>`;
}

function moduleCard(m) {
  const cfgFields = m.config_fields || [];
  const st = m.status || "stopped";
  const cfgHtml = cfgFields.length ? moduleConfigForm(m, cfgFields) : '<div class="muted">У модуля нет настраиваемых параметров.</div>';
  return `<div class="module-card btn-ghost-hover">
    <div class="mc-head" onclick="toggleModuleCfg('${esc(m.name)}')">
      <div class="mc-title">
        <span class="mc-name">${esc(m.name)}</span>
        <span class="muted">v${esc(m.version)}</span>
        <span class="badge ${st === "running" ? "ok" : st === "error" ? "bad" : "warn"}">${RU[st] || esc(st)}</span>
      </div>
      <div class="mc-desc">${esc(m.description_ru || m.description || "")}</div>
      <div class="mc-tools">
        <button class="btn ghost small" onclick="event.stopPropagation();moduleAction('${esc(m.name)}','restart')">↻ Перезапустить</button>
        <button class="btn ghost small" onclick="event.stopPropagation();moduleAction('${esc(m.name)}','${st === "running" ? "stop" : "start"}')">${st === "running" ? "Остановить" : "Запустить"}</button>
        <span class="muted cfg-toggle">${cfgFields.length ? "⚙ настройки ▾" : ""}</span>
      </div>
    </div>
    <div class="module-config" data-module="${esc(m.name)}" style="display:none">${cfgHtml}</div>
  </div>`;
}

function moduleConfigForm(m, fields) {
  const vals = m.config_values || {};
  return `<form class="cfg-form">
    <div class="cfg-fields">
      ${fields.map((f) => {
        const cur = vals[f.key] != null ? vals[f.key] : f.default;
        let control;
        if (f.field_type === "bool") {
          control = `<select data-key="${f.key}"><option value="true" ${String(cur) === "true" ? "selected" : ""}>Включено</option><option value="false" ${String(cur) === "false" ? "selected" : ""}>Выключено</option></select>`;
        } else if (f.field_type === "select" && f.options && f.options.length) {
          control = `<select data-key="${f.key}">${f.options.map((o) => `<option value="${esc(o.value)}" ${String(o.value) === String(cur) ? "selected" : ""}>${esc(o.label || o.value)}</option>`).join("")}</select>`;
        } else if (f.field_type === "password" || /key|token|secret|password/i.test(f.key)) {
          control = `<input type="password" data-key="${f.key}" value="${esc(cur ?? "")}" />`;
        } else if (f.field_type === "number" || f.value_type === "int" || f.value_type === "float") {
          control = `<input type="number" step="any" data-key="${f.key}" value="${esc(cur ?? "")}" />`;
        } else {
          control = `<input type="text" data-key="${f.key}" value="${esc(cur ?? "")}" />`;
        }
        return `<div class="cfg-field"><label>${esc(f.label_ru || f.key)}</label>${control}
          ${f.hint ? `<div class="muted sm">${esc(f.hint)}</div>` : ""}</div>`;
      }).join("")}
    </div>
    <div class="row gap4 cfg-actions">
      <button type="button" class="btn small" onclick="saveModuleCfg(this)">Сохранить (применить)</button>
      <button type="button" class="btn ghost small" onclick="moduleAction('${esc(m.name)}','restart')">Перезапустить для применения</button>
    </div>
  </form>`;
}

window.toggleModuleCfg = (name) => {
  const el = document.querySelector(`.module-config[data-module="${name}"]`);
  if (el) el.style.display = el.style.display === "none" ? "block" : "none";
};

function bindConfigEvents(el) {
  el.querySelectorAll("select[data-key]").forEach((s) => {
    s.addEventListener("change", () => {
      const field = [...(systemState.modules.find((m) => m.name === el.dataset.module)?.config_fields || [])].find((f) => f.key === s.dataset.key);
      if (field && field.field_type === "bool") s.dataset.confirmed = "1";
    });
  });
}

window.saveModuleCfg = async (btn) => {
  const form = btn.closest("form");
  const module = btn.closest(".module-config").dataset.module;
  const payload = {};
  form.querySelectorAll("[data-key]").forEach((el) => {
    let v = el.value;
    const field = [...(systemState.modules.find((m) => m.name === module)?.config_fields || [])].find((f) => f.key === el.dataset.key);
    if (field && field.value_type === "bool") v = el.value === "true";
    else if (field && (field.value_type === "int" || field.value_type === "float") && v !== "") v = field.value_type === "int" ? parseInt(v, 10) : parseFloat(v);
    payload[el.dataset.key] = v;
  });
  try {
    const res = await api(`/system/modules/${module}/config`, { method: "PUT", body: JSON.stringify(payload) });
    toast(`Настройки модуля «${module}» сохранены`);
    const m = systemState.modules.find((x) => x.name === module);
    if (m) m.config_values = res.values;
    const mcard = btn.closest(".module-card");
    if (mcard) { const old = mcard.style.display; mcard.style.display = "none"; mcard.offsetHeight; mcard.style.display = old; }
  } catch (e) { toast(e.message); }
};

function userRow(u) {
  const canChange = u.username ? false : typeof window.__permSaveCheck !== "function";
  const isOwner = u.role === "owner";
  const tg = u.telegram_username ? "@" + u.telegram_username : (u.telegram_user_id ? "id " + u.telegram_user_id : "—");
  const actions = isOwner
    ? '<span class="muted">владелец</span>'
    : `<button class="btn ghost small" onclick="setUserRole('${u.id}','admin')" ${u.role === "admin" ? 'disabled' : ""}>Сделать админом</button>
       <button class="btn ghost small" onclick="setUserRole('${u.id}','member')" ${u.role === "member" ? 'disabled' : ""}>Снять права</button>`;
  return `<tr>
    <td><b>${esc(u.full_name || u.username)}</b><div class="muted sm">${esc(u.username)}</div></td>
    <td><span class="badge ${u.role === "owner" ? "warn" : u.role === "admin" ? "ok" : "neutral"}">${u.role === "owner" ? "владелец" : u.role === "admin" ? "админ" : "участник"}</span></td>
    <td class="muted">${tg}</td>
    <td class="muted">${u.last_seen_at ? new Date(u.last_seen_at).toLocaleString() : "—"}</td>
    <td><div class="row gap4">${actions}</div></td>
  </tr>`;
}

window.setUserRole = async (id, role) => {
  try {
    await api(`/system/users/${id}/role`, { method: "POST", body: JSON.stringify({ role }) });
    toast(role === "admin" ? "Права админа выданы" : "Права админа сняты");
    loadSystem();
  } catch (e) { toast(e.message); }
};

window.moduleAction = async (name, action) => {
  try {
    await api(`/system/modules/${name}/${action}`, { method: "POST" });
    toast(`${name}: ${action === "restart" ? "перезапуск" : action === "start" ? "запуск" : "остановка"}`);
    loadSystem();
  } catch (e) { toast(e.message); }
};

showView("dashboard");
setInterval(() => { if (currentView === "dashboard") loadDashboard(); }, 15000);
setInterval(() => { if (currentView === "stats" && statsState.autoRefresh) loadStats(); }, 5000);