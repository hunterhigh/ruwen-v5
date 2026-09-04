(() => {
  "use strict";
  const token = document.querySelector('meta[name="ruwen-token"]')?.content || "";
  const state = { project: null, document: null, path: null, view: "reading", selection: null, annotations: [], allAnnotations: [], batches: [], currentBatch: null, drawerBatchNumber: null };
  const $ = id => document.getElementById(id);

  async function api(path, options = {}) {
    const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", "X-Ruwen-Token": token, ...(options.headers || {}) } });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error?.message || "操作失败");
    return payload;
  }

  function showToast(message) {
    const toast = $("toast");
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2600);
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  }

  function renderMarkdown(source) {
    const lines = source.split("\n");
    const output = [];
    let paragraph = [];
    let listType = null;
    let inCode = false;
    let code = [];
    const flushParagraph = () => { if (paragraph.length) { output.push(`<p>${paragraph.map(escapeHtml).join("<br>")}</p>`); paragraph = []; } };
    const closeList = () => { if (listType) { output.push(`</${listType}>`); listType = null; } };
    for (const line of lines) {
      if (/^```/.test(line)) {
        flushParagraph(); closeList();
        if (inCode) { output.push(`<pre>${escapeHtml(code.join("\n"))}</pre>`); code = []; inCode = false; } else inCode = true;
        continue;
      }
      if (inCode) { code.push(line); continue; }
      const heading = line.match(/^(#{1,3})\s+(.+)$/);
      const bullet = line.match(/^\s*[-*+]\s+(.+)$/);
      const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      const quote = line.match(/^>\s?(.*)$/);
      if (heading) { flushParagraph(); closeList(); const level = heading[1].length; output.push(`<h${level}>${escapeHtml(heading[2])}</h${level}>`); }
      else if (bullet || ordered) { flushParagraph(); const nextType = bullet ? "ul" : "ol"; if (listType !== nextType) { closeList(); output.push(`<${nextType}>`); listType = nextType; } output.push(`<li>${escapeHtml((bullet || ordered)[1])}</li>`); }
      else if (quote) { flushParagraph(); closeList(); output.push(`<blockquote>${escapeHtml(quote[1])}</blockquote>`); }
      else if (!line.trim()) { flushParagraph(); closeList(); }
      else paragraph.push(line);
    }
    flushParagraph(); closeList();
    if (inCode) output.push(`<pre>${escapeHtml(code.join("\n"))}</pre>`);
    return output.join("");
  }

  function noteCounts() {
    return state.allAnnotations.reduce((counts, note) => { counts[note.path] = (counts[note.path] || 0) + 1; return counts; }, {});
  }

  function renderTree(nodes, parent, query = "", depth = 0) {
    const counts = noteCounts();
    for (const node of nodes) {
      if (node.type === "directory") {
        const visibleChildren = filterTree(node.children, query);
        if (!visibleChildren.length) continue;
        const group = document.createElement("div"); group.className = "tree-group";
        const button = document.createElement("button"); button.className = "folder"; button.innerHTML = "<i>⌄</i>"; button.append(document.createTextNode(node.name));
        const children = document.createElement("div"); children.className = "tree-children nested";
        button.addEventListener("click", () => group.classList.toggle("closed"));
        group.append(button, children); parent.append(group); renderTree(visibleChildren, children, query, depth + 1);
      } else {
        const button = document.createElement("button"); button.className = "file"; button.dataset.path = node.path; button.textContent = node.name;
        if (counts[node.path]) { const count = document.createElement("sup"); count.textContent = counts[node.path]; button.append(count); }
        if (node.path === state.path) button.classList.add("active");
        button.addEventListener("click", () => openFile(node.path)); parent.append(button);
      }
    }
  }

  function filterTree(nodes, query) {
    if (!query) return nodes;
    const normalized = query.trim().toLocaleLowerCase();
    const result = [];
    for (const node of nodes) {
      if (node.type === "directory") {
        const children = filterTree(node.children, normalized);
        if (children.length || node.name.toLocaleLowerCase().includes(normalized)) result.push({ ...node, children });
      } else if (`${node.name} ${node.path}`.toLocaleLowerCase().includes(normalized)) result.push(node);
    }
    return result;
  }

  function refreshTree() {
    const target = $("tree"); target.replaceChildren();
    renderTree(filterTree(state.project.tree, $("search").value), target, $("search").value);
  }

  async function refreshAnnotations() {
    const all = await api("/api/annotations");
    state.allAnnotations = all.annotations;
    state.annotations = state.path ? state.allAnnotations.filter(note => note.path === state.path) : [];
    renderNotes(); refreshTree();
  }

  async function refreshBatches() {
    const payload = await api("/api/batches");
    state.batches = payload.batches;
    state.currentBatch = state.batches.find(batch => batch.status === "draft");
    renderBatchBar();
  }

  function renderBatchBar() {
    const batch = state.currentBatch;
    if (!batch) return;
    $("batchNumber").textContent = `第 ${String(batch.number).padStart(3, "0")} 批`;
    $("batchSummary").textContent = `${batch.annotation_count} 条　/　${batch.file_count} 个文件　/　草稿`;
    $("sendNote").textContent = `发送至第 ${String(batch.number).padStart(3, "0")} 批 →`;
  }

  async function openFile(path) {
    try {
      state.path = path; state.selection = null;
      state.document = await api(`/api/file?path=${encodeURIComponent(path)}`);
      $("crumb").textContent = path.replaceAll("/", "　/　");
      $("sourceText").textContent = state.document.content;
      renderReading();
      await refreshAnnotations();
      refreshTree();
      resetAnchor();
      showView("reading");
    } catch (error) { showToast(error.message); }
  }

  function renderReading() {
    const target = $("reading");
    if (!state.document) return;
    const ext = state.document.extension;
    if ([".md", ".markdown"].includes(ext)) target.innerHTML = renderMarkdown(state.document.content);
    else if (ext === ".json") {
      try { target.innerHTML = `<pre class="json">${escapeHtml(JSON.stringify(JSON.parse(state.document.content), null, 2))}</pre>`; }
      catch { target.innerHTML = `<pre class="json">${escapeHtml(state.document.content)}</pre>`; }
    } else target.innerHTML = `<pre class="json">${escapeHtml(state.document.content)}</pre>`;
  }

  function headingForOffset(content, offset) {
    const headings = [];
    let consumed = 0;
    for (const line of content.split("\n")) {
      if (consumed > offset) break;
      const match = line.match(/^(#{1,6})\s+(.+)$/);
      if (match) { const level = match[1].length; while (headings.length >= level) headings.pop(); headings[level - 1] = match[2]; }
      consumed += line.length + 1;
    }
    return headings.filter(Boolean).join("／") || "当前文件";
  }

  function captureSelection() {
    if (!state.document || state.view !== "reading") return;
    const selection = window.getSelection();
    const text = selection?.toString().trim();
    if (!text || !$("reading").contains(selection.anchorNode) || !$("reading").contains(selection.focusNode)) return;
    const first = state.document.content.indexOf(text);
    const last = state.document.content.lastIndexOf(text);
    if (first < 0 || first !== last) { showToast("这段文字无法唯一定位，请扩大选择范围。"); return; }
    state.selection = { start: first, end: first + text.length, text };
    $("anchor").querySelector("b").textContent = headingForOffset(state.document.content, first);
    $("anchor").querySelector("span").textContent = `“${text.slice(0, 72)}${text.length > 72 ? "……" : ""}”`;
    $("noteInput").disabled = false; $("sendNote").disabled = false; $("noteInput").focus();
  }

  function resetAnchor() {
    state.selection = null;
    $("anchor").querySelector("b").textContent = "尚未选择原文";
    $("anchor").querySelector("span").textContent = "在阅读视图中选择一段文字。";
    $("noteInput").disabled = true; $("sendNote").disabled = true; $("noteInput").value = "";
  }

  function renderNotes() {
    $("documentNoteCount").textContent = `本文 ${state.annotations.length} 条`;
    const list = $("noteList"); list.replaceChildren();
    if (!state.annotations.length) { const empty = document.createElement("div"); empty.className = "no-comments"; empty.textContent = "本批次尚无本文批注。"; list.append(empty); return; }
    for (const note of state.annotations) {
      const item = document.createElement("div"); item.className = "comment";
      const location = document.createElement("div"); location.className = "loc"; location.textContent = `${String(note.position).padStart(2, "0")} · ${(note.anchor.heading_chain || []).join("／") || note.path}`;
      const body = document.createElement("p"); body.textContent = note.body;
      const edit = document.createElement("button"); edit.textContent = "编辑"; edit.addEventListener("click", () => editNote(note));
      const remove = document.createElement("button"); remove.textContent = "删除"; remove.addEventListener("click", () => deleteNote(note));
      item.append(location, body, edit, remove); list.append(item);
    }
  }

  async function sendNote() {
    const body = $("noteInput").value.trim();
    if (!body || !state.selection || !state.document) return;
    try {
      await api("/api/annotations", { method: "POST", body: JSON.stringify({ path: state.path, body, file_hash: state.document.sha256, selection_start: state.selection.start, selection_end: state.selection.end }) });
      $("sent").style.display = "block"; window.setTimeout(() => $("sent").style.display = "none", 1800);
      resetAnchor(); await Promise.all([refreshAnnotations(), refreshBatches()]);
    } catch (error) { showToast(error.message); }
  }

  async function editNote(note) {
    const body = window.prompt("修改批注", note.body);
    if (body === null || !body.trim() || body.trim() === note.body) return;
    try { await api(`/api/annotations/${note.id}`, { method: "PATCH", body: JSON.stringify({ body }) }); await refreshAnnotations(); }
    catch (error) { showToast(error.message); }
  }

  async function deleteNote(note) {
    if (!window.confirm("从当前草稿批次删除这条批注？")) return;
    try { await api(`/api/annotations/${note.id}`, { method: "DELETE" }); await Promise.all([refreshAnnotations(), refreshBatches()]); }
    catch (error) { showToast(error.message); }
  }

  function showView(view) {
    state.view = view;
    document.querySelectorAll(".views button").forEach(button => button.classList.toggle("active", button.dataset.view === view));
    ["reading", "source", "versions"].forEach(id => $(id).style.display = id === view ? "block" : "none");
    if (view === "versions") loadVersions();
  }

  async function loadVersions() {
    const target = $("versions");
    if (!state.path) { target.innerHTML = '<div class="empty">尚未选择文件。</div>'; return; }
    try {
      const payload = await api(`/api/git/history?path=${encodeURIComponent(state.path)}`);
      const history = payload.history;
      target.replaceChildren();
      if (!history.length) { target.innerHTML = '<div class="empty">此文件没有可用的 Git 历史。</div>'; return; }
      if (history.length >= 2) {
        const controls = document.createElement("div"); controls.className = "version-controls";
        const from = document.createElement("select"); const to = document.createElement("select");
        for (const item of history) { for (const select of [from, to]) { const option = document.createElement("option"); option.value = item.revision; option.textContent = `${item.revision.slice(0, 8)}　${item.subject}`; select.append(option); } }
        from.selectedIndex = Math.min(1, history.length - 1); to.selectedIndex = 0;
        const compare = document.createElement("button"); compare.textContent = "比较"; compare.addEventListener("click", () => loadDiff(from.value, to.value));
        controls.append(from, to, compare); target.append(controls);
      }
      for (const item of history) { const row = document.createElement("div"); row.className = "revision"; const revision = document.createElement("span"); revision.textContent = item.revision.slice(0, 8); const subject = document.createElement("span"); subject.textContent = item.subject; const time = document.createElement("time"); time.textContent = item.authored_at.slice(0, 10); row.append(revision, subject, time); target.append(row); }
      const diff = document.createElement("pre"); diff.className = "diff"; diff.id = "diffOutput"; target.append(diff);
    } catch (error) { target.innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`; }
  }

  async function loadDiff(from, to) {
    try { const payload = await api(`/api/git/diff?path=${encodeURIComponent(state.path)}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`); $("diffOutput").textContent = payload.diff || "两个版本没有差异。"; }
    catch (error) { showToast(error.message); }
  }

  async function openBatchDrawer() {
    await Promise.all([refreshAnnotations(), refreshBatches()]);
    await renderDrawerBatch(state.currentBatch.number);
    $("overlay").classList.add("open"); $("overlay").setAttribute("aria-hidden", "false");
  }

  async function renderDrawerBatch(number) {
    const batch = state.batches.find(item => item.number === number);
    if (!batch) return;
    state.drawerBatchNumber = number;
    const payload = await api(`/api/annotations?batch=${number}`);
    const annotations = payload.annotations;
    $("drawerTitle").textContent = `第 ${String(batch.number).padStart(3, "0")} 批`;
    $("drawerSummary").textContent = `${batch.annotation_count} 条批注　·　${batch.file_count} 个文件　·　${statusLabel(batch.status)}`;
    const tabs = $("batchHistory"); tabs.replaceChildren();
    for (const item of [...state.batches].reverse()) { const label = document.createElement("button"); label.classList.toggle("active", item.number === batch.number); label.textContent = `${String(item.number).padStart(3, "0")} ${statusLabel(item.status)}`; label.addEventListener("click", () => renderDrawerBatch(item.number)); tabs.append(label); }
    const groups = $("batchGroups"); groups.replaceChildren();
    const grouped = Object.groupBy ? Object.groupBy(annotations, note => note.path) : annotations.reduce((result, note) => ((result[note.path] ||= []).push(note), result), {});
    for (const path of Object.keys(grouped).sort()) { const section = document.createElement("section"); section.className = "file-group"; const heading = document.createElement("h2"); heading.textContent = path; const count = document.createElement("span"); count.textContent = grouped[path].length; heading.append(count); section.append(heading); for (const note of grouped[path]) { const entry = document.createElement("div"); entry.className = "entry"; const position = document.createElement("i"); position.textContent = String(note.position).padStart(2, "0"); const body = document.createElement("span"); body.textContent = note.body; entry.append(position, body); section.append(entry); } groups.append(section); }
    if (!annotations.length) groups.innerHTML = '<div class="no-comments">当前批次尚无批注。</div>';
    const isDraft = batch.status === "draft";
    $("drawerFootnote").innerHTML = isDraft ? "封存后不可编辑。<br>新批注进入下一批。" : `该批次已封存，只读。<br>${escapeHtml(batch.snapshot_path || "快照已保存")}`;
    $("sealBatch").style.display = isDraft ? "block" : "none";
    $("sealBatch").disabled = !annotations.length;
    $("sealResult").classList.remove("show");
  }

  function statusLabel(status) { return ({ draft: "草稿", sealed: "已封存", dispatched: "已派发", processing: "处理中", completed: "已完成", archived: "已归档" })[status] || status; }

  async function sealBatch() {
    try {
      const number = state.currentBatch.number;
      const result = await api(`/api/batches/${number}/seal`, { method: "POST", body: "{}" });
      await Promise.all([refreshAnnotations(), refreshBatches()]);
      await renderDrawerBatch(number);
      $("sealResult").classList.add("show"); $("snapshotPath").textContent = `已写入 ${result.snapshot_path}`; $("processingPrompt").value = result.processing_prompt;
    } catch (error) { showToast(error.message); }
  }

  async function copyPrompt() { try { await navigator.clipboard.writeText($("processingPrompt").value); showToast("Ruwen 任务说明已复制。"); } catch { $("processingPrompt").select(); document.execCommand("copy"); showToast("Ruwen 任务说明已复制。"); } }

  async function init() {
    try {
      const project = await api("/api/project");
      state.project = project; state.currentBatch = project.current_batch;
      $("projectName").textContent = project.project.name;
      const projectFont = project.preferences?.project_font || "xiaowei";
      if ([...$("projectFont").options].some(option => option.value === projectFont)) { $("projectFont").value = projectFont; applyProjectFont(projectFont); }
      await Promise.all([refreshAnnotations(), refreshBatches()]);
      refreshTree();
      const remembered = project.preferences?.last_opened_file;
      const initial = remembered ? findFile(project.tree, remembered) : null;
      const first = initial || firstFile(project.tree); if (first) await openFile(first.path);
      $("app").setAttribute("aria-busy", "false");
    } catch (error) { showToast(error.message); $("projectName").textContent = "项目无法打开"; }
  }

  function firstFile(nodes) { for (const node of nodes) { if (node.type === "file") return node; const nested = firstFile(node.children || []); if (nested) return nested; } return null; }

  function findFile(nodes, path) { for (const node of nodes) { if (node.type === "file" && node.path === path) return node; const nested = findFile(node.children || [], path); if (nested) return nested; } return null; }

  function applyProjectFont(value) { $("projectName").parentElement.style.fontFamily = ({ xiaowei: '"ZCOOL XiaoWei",serif', wenkai: '"LXGW WenKai",serif', noto: '"Noto Serif SC",serif' })[value]; }

  $("search").addEventListener("input", refreshTree);
  $("projectFont").addEventListener("change", event => { applyProjectFont(event.target.value); if (state.project) api("/api/preferences", { method: "POST", body: JSON.stringify({ project_font: event.target.value }) }).catch(error => showToast(error.message)); });
  document.querySelectorAll(".views button").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
  $("reading").addEventListener("mouseup", captureSelection); $("sendNote").addEventListener("click", sendNote);
  $("manageBatch").addEventListener("click", openBatchDrawer); $("openSeal").addEventListener("click", openBatchDrawer);
  $("closeDrawer").addEventListener("click", () => { $("overlay").classList.remove("open"); $("overlay").setAttribute("aria-hidden", "true"); });
  $("overlay").addEventListener("click", event => { if (event.target === $("overlay")) $("closeDrawer").click(); });
  $("sealBatch").addEventListener("click", sealBatch); $("copyPrompt").addEventListener("click", copyPrompt);
  init();
})();
