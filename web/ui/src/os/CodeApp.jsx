import { useEffect, useRef, useState } from "react";
import {
  FaPlay, FaPlus, FaTrash, FaFileCode, FaEye, FaTerminal,
  FaEraser, FaFolderOpen, FaFolder, FaChevronRight, FaChevronDown,
  FaRegCopy, FaMagnifyingGlass, FaCodeBranch, FaBug, FaGear,
  FaXmark, FaBell, FaArrowsRotate, FaTriangleExclamation,
} from "react-icons/fa6";

const MONACO_VERSION = "0.52.2";
const STORE_KEY = "bugos-code";

const STARTER = [
  {
    path: "index.html",
    content: `<link rel="stylesheet" href="css/styles.css">\n<h1>Hello from Bug OS \u{1F41E}</h1>\n<p>Edit any file — folders work, preview updates live.</p>\n<button id="btn">Click me</button>\n<script src="js/app.js"><\/script>\n`,
  },
  {
    path: "css/styles.css",
    content: `body { font-family: system-ui, sans-serif; padding: 32px; background: #f8fafc; color: #0f172a; }\nh1 { color: #e11d48; }\nbutton { background: #0f172a; color: #fff; border: 0; border-radius: 10px; padding: 10px 18px; cursor: pointer; }\n`,
  },
  {
    path: "js/app.js",
    content: `console.log("preview booted");\ndocument.getElementById("btn").addEventListener("click", () => {\n  console.log("button clicked at", new Date().toLocaleTimeString());\n});\n`,
  },
];

const langOf = (path) => {
  if (path.endsWith(".html")) return "html";
  if (path.endsWith(".css")) return "css";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".ts")) return "typescript";
  if (path.endsWith(".py")) return "python";
  return "javascript";
};

const LANG_LABEL = {
  html: "HTML", css: "CSS", javascript: "JavaScript", typescript: "TypeScript",
  json: "JSON", markdown: "Markdown", python: "Python",
};

// Chalked file colors, VS Code Dark+ flavor.
const FILE_COLOR = {
  html: "#e44d26", css: "#519aba", js: "#dcdcaa", jsx: "#61dafb",
  json: "#d7ba7d", md: "#519aba", py: "#4ec9b0", sh: "#89e051",
  "": "#858585",
};
const extOf = (path) => {
  const base = (path || "").split("/").pop();
  if (base === ".env" || base.endsWith(".env") || base.startsWith(".env.")) return "env";
  const i = base.lastIndexOf(".");
  return i >= 0 ? base.slice(i + 1).toLowerCase() : "";
};

const isKeep = (f) => f.path.split("/").pop() === ".keep";
const visibleFiles = (files) => files.filter((f) => !isKeep(f));

function loadMonaco() {
  if (window.monaco) return Promise.resolve(window.monaco);
  if (window.__bugosMonacoLoading) return window.__bugosMonacoLoading;
  window.__bugosMonacoLoading = new Promise((resolve, reject) => {
    const loader = document.createElement("script");
    loader.src = `https://cdn.jsdelivr.net/npm/monaco-editor@${MONACO_VERSION}/min/vs/loader.js`;
    loader.onload = () => {
      window.require.config({
        paths: { vs: `https://cdn.jsdelivr.net/npm/monaco-editor@${MONACO_VERSION}/min/vs` },
      });
      window.require(["vs/editor/editor.main"], () => resolve(window.monaco));
    };
    loader.onerror = () => reject(new Error("monaco CDN failed"));
    document.head.appendChild(loader);
  });
  return window.__bugosMonacoLoading;
}

// Intercepts console.* + uncaught errors inside the preview iframe.
const CONSOLE_HOOK = `<script>(function(){function fmt(a){try{return typeof a==="object"?JSON.stringify(a):String(a)}catch(e){return String(a)}}function send(m,args){parent.postMessage({__bugos:1,method:m,text:args.map(fmt).join(" ")},"*")}["log","info","warn","error"].forEach(function(m){var o=console[m].bind(console);console[m]=function(){try{send(m,[].slice.call(arguments))}catch(e){}return o.apply(null,arguments)}});window.addEventListener("error",function(e){send("error",[e.message])});send("info",["preview ready"])})();<\/script>`;

function buildSrcDoc(files) {
  const get = (n) => files.find((f) => f.path === n || f.path.endsWith(`/${n}`))?.content || "";
  const css = files
    .filter((f) => f.path.endsWith(".css"))
    .map((f) => `<style>${f.content}</style>`)
    .join("\n");
  const js = files
    .filter((f) => f.path.endsWith(".js"))
    .map((f) => `<script>${f.content}<\/script>`)
    .join("\n");
  const html = get("index.html") || "<body></body>";
  const body = `${CONSOLE_HOOK}\n${css}\n${js}\n`;
  return html.includes("</body>") ? html.replace("</body>", `${body}</body>`) : `${html}\n${body}`;
}

function buildTree(files) {
  const root = { folders: [], files: [] };
  const map = new Map();
  const nodeFor = (parts) => {
    const key = parts.join("/");
    if (!map.has(key)) {
      const node = { name: parts[parts.length - 1], path: key, folders: [], files: [] };
      map.set(key, node);
      if (parts.length === 1) root.folders.push(node);
      else nodeFor(parts.slice(0, -1)).folders.push(node);
    }
    return map.get(key);
  };
  for (const f of visibleFiles(files)) {
    const parts = f.path.split("/");
    if (parts.length === 1) root.files.push(f);
    else nodeFor(parts.slice(0, -1)).files.push(f);
  }
  const sortAll = (n) => {
    n.folders.sort((a, b) => a.name.localeCompare(b.name));
    n.files.sort((a, b) => a.path.localeCompare(b.path));
    n.folders.forEach(sortAll);
  };
  sortAll(root);
  return root;
}

/* Code editor app: VS Code black + white, folder tree, Monaco, live preview.
   Persists locally. Reports the active file upward for tutor context. */
export default function CodeApp({ onContext, queue, onAck }) {
  const [files, setFiles] = useState(() => {
    try {
      const v = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
      if (Array.isArray(v) && visibleFiles(v).length) return v;
    } catch {
      /* fresh */
    }
    return STARTER;
  });
  const [activePath, setActivePath] = useState("index.html");
  const [openPaths, setOpenPaths] = useState(["index.html"]); // editor tab bar
  const [touched, setTouched] = useState({}); // edited-this-session dots
  const [expanded, setExpanded] = useState({ "": true });
  const [panelTab, setPanelTab] = useState("terminal"); // terminal | problems
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelH, setPanelH] = useState(208); // terminal height, draggable
  const [sidePreview, setSidePreview] = useState(true); // preview split right
  const wrapRef = useRef(null); // editor+panel column (for drag clamping)
  const panelDrag = useRef(null); // {startY, startH} while resizing
  const [sideView, setSideView] = useState("explorer"); // explorer | search | source
  const [searchQ, setSearchQ] = useState("");
  const [cursor, setCursor] = useState({ ln: 1, col: 1 });
  const [autoRun, setAutoRun] = useState(true); // rebuild preview on edit
  const [creating, setCreating] = useState(null); // {kind:'file'|'folder', dir} | null
  const [createName, setCreateName] = useState("");
  const [logs, setLogs] = useState([]);
  const [srcDoc, setSrcDoc] = useState("");
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const mountRef = useRef(null);
  const monacoRef = useRef(null);
  const editorRef = useRef(null);
  const modelsRef = useRef({});
  const filesRef = useRef(files);
  const activePathRef = useRef(activePath);
  const iframeRef = useRef(null);
  filesRef.current = files;
  activePathRef.current = activePath;

  const tree = buildTree(files);
  const allFolders = [];
  const collect = (n) => {
    n.folders.forEach((f) => {
      allFolders.push(f.path);
      collect(f);
    });
  };
  collect(tree);
  const isOpen = (p) => expanded[p] !== false;

  // Persist + report context.
  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(files));
    } catch {
      /* private mode */
    }
    const active = files.find((f) => f.path === activePath);
    onContext &&
      onContext(
        active ? { file: active.path, lang: langOf(active.path), chars: active.content.length } : null,
      );
  }, [files, activePath, onContext]);

  // Boot Monaco once (VS Code dark). StrictMode-safe: dev double-mounts
  // this effect, so cleanup disposes the editor + models — otherwise the
  // first (orphaned) instance stays visible with stale content while
  // openFile switches models on the second one (file switching looked dead).
  useEffect(() => {
    let dead = false;
    loadMonaco()
      .then((monaco) => {
        if (dead) return;
        if (editorRef.current) return; // already booted — HMR/StrictMode re-ran
        // Drop orphaned editor DOM (kills the "already has context
        // attribute" warning when a previous instance died without cleanup).
        if (mountRef.current) mountRef.current.innerHTML = "";
        monacoRef.current = monaco;
        const wanted = activePathRef.current;
        const first = filesRef.current.find((f) => f.path === wanted)
          || filesRef.current.find((f) => f.path === "index.html")
          || visibleFiles(filesRef.current)[0];
        if (!first) return;
        const model = monaco.editor.createModel(first.content, langOf(first.path));
        modelsRef.current[first.path] = model;
        editorRef.current = monaco.editor.create(mountRef.current, {
          model,
          theme: "vs-dark",
          fontSize: 13,
          fontFamily: "Consolas, 'Courier New', monospace",
          minimap: { enabled: true, renderCharacters: false, maxColumn: 90 },
          automaticLayout: true,
          scrollBeyondLastLine: false,
          cursorBlinking: "smooth",
          padding: { top: 8 },
          renderLineHighlight: "all",
        });
        editorRef.current.onDidChangeModelContent(() => {
          const path = editorRef.current.__bugosPath;
          const value = editorRef.current.getValue();
          setTouched((p) => (p[path] ? p : { ...p, [path]: true }));
          setFiles((prev) => prev.map((f) => (f.path === path ? { ...f, content: value } : f)));
        });
        editorRef.current.onDidChangeCursorPosition((e) => {
          setCursor({ ln: e.position.lineNumber, col: e.position.column });
        });
        editorRef.current.__bugosPath = first.path;
        setActivePath(first.path);
        setOpenPaths((prev) => (prev.includes(first.path) ? prev : [...prev.slice(-4), first.path]));
        setReady(true);
      })
      .catch(() => {
        if (!dead) setFailed(true);
      });
    return () => {
      dead = true;
      try {
        editorRef.current?.dispose();
      } catch { /* noop */ }
      editorRef.current = null;
      try {
        Object.values(modelsRef.current).forEach((m) => m?.dispose?.());
      } catch { /* noop */ }
      modelsRef.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Console messages from the preview iframe.
  useEffect(() => {
    const onMsg = (e) => {
      if (!e.data || e.data.__bugos !== 1) return;
      if (iframeRef.current && e.source !== iframeRef.current.contentWindow) return;
      setLogs((prev) => [...prev.slice(-199), { id: Date.now() + Math.random(), method: e.data.method, text: e.data.text }]);
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  // Agent code queue: the tutor creates files, writes and edits code
  // ([{cmd, path, content, mode, find, replace, seq}]) — drained in order,
  // each seq once. State + Monaco models update together and the file opens,
  // so the learner watches the code appear. filesRef is mirrored
  // synchronously so openFile() below reads the fresh content (never the
  // stale pre-write text, which would revert the agent's edit).
  const codeDone = useRef(new Set());
  useEffect(() => {
    if (!queue || !queue.length) return;
    if (codeDone.current.size > 500) codeDone.current.clear();
    for (const c of queue) {
      if (!c || c.seq == null || codeDone.current.has(c.seq)) continue;
      codeDone.current.add(c.seq);
      try {
        applyAgentCode(c);
      } catch { /* agent moves must never break the editor */ }
      try { onAck && onAck(c.seq); } catch { /* noop */ }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue]);

  const applyAgentCode = (c) => {
    const path = String(c.path || "").trim();
    if (!path || !["code_create", "code_write", "code_edit"].includes(c.cmd)) return;
    const files = filesRef.current;
    const idx = files.findIndex((f) => f.path === path);
    let next = null;
    if (c.cmd === "code_create") {
      next = idx >= 0 ? files[idx].content : String(c.content ?? "");
    } else if (c.cmd === "code_write") {
      const content = String(c.content ?? "");
      if (idx < 0 && !content) return;
      next = c.mode === "append" && idx >= 0 ? files[idx].content + content : content;
    } else {
      // code_edit: exact-snippet swap, first match wins. No match (or the
      // file is missing) = leave the file untouched, never corrupt it.
      if (idx < 0) return;
      const find = String(c.find ?? "");
      if (!find) return;
      const cur = files[idx].content;
      const at = cur.indexOf(find);
      if (at < 0) return;
      next = cur.slice(0, at) + String(c.replace ?? "") + cur.slice(at + find.length);
    }
    if (next == null) return;
    const updated = idx >= 0
      ? files.map((f) => (f.path === path ? { ...f, content: next } : f))
      : [...files, { path, content: next }];
    filesRef.current = updated; // sync mirror for openFile() below
    setFiles(updated);
    const monaco = monacoRef.current;
    const ed = editorRef.current;
    if (monaco && ed) {
      if (!modelsRef.current[path]) {
        modelsRef.current[path] = monaco.editor.createModel(next, langOf(path));
      } else if (modelsRef.current[path].getValue() !== next) {
        const prevOwner = ed.__bugosPath;
        ed.__bugosPath = path;
        modelsRef.current[path].setValue(next);
        ed.__bugosPath = prevOwner;
      }
    }
    setTouched((p) => ({ ...p, [path]: true }));
    const folder = path.split("/").slice(0, -1).join("/");
    if (folder) setExpanded((p) => ({ ...p, [folder]: true }));
    openFile(path);
  };

  const openFile = (path) => {
    const monaco = monacoRef.current;
    const ed = editorRef.current;
    if (monaco && ed) {
      const file = filesRef.current.find((f) => f.path === path);
      if (!file) return;
      // Tag the model owner BEFORE setValue: the content listener fires
      // synchronously and must credit the incoming file, not the old one.
      ed.__bugosPath = path;
      if (!modelsRef.current[path]) {
        modelsRef.current[path] = monaco.editor.createModel(file.content, langOf(path));
      } else {
        modelsRef.current[path].setValue(file.content);
      }
      ed.setModel(modelsRef.current[path]);
    }
    setActivePath(path);
    setOpenPaths((prev) => (prev.includes(path) ? prev : [...prev, path]));
    if (sideView === "search") setSideView("explorer");
  };

  const closeTab = (path) => {
    setOpenPaths((prev) => {
      if (prev.length <= 1) return prev; // never empty the tab bar
      const next = prev.filter((p) => p !== path);
      if (path === activePath) {
        const closedIdx = prev.indexOf(path);
        const fallback = next[Math.min(closedIdx, next.length - 1)];
        const monaco = monacoRef.current;
        const ed = editorRef.current;
        const file = filesRef.current.find((f) => f.path === fallback);
        if (monaco && ed && file) {
          ed.__bugosPath = fallback;
          if (!modelsRef.current[fallback]) {
            modelsRef.current[fallback] = monaco.editor.createModel(file.content, langOf(fallback));
          }
          ed.setModel(modelsRef.current[fallback]);
        }
        setActivePath(fallback);
      }
      return next;
    });
  };

  const gotoLine = (path, line) => {
    openFile(path);
    requestAnimationFrame(() => {
      try {
        const ed = editorRef.current;
        if (!ed) return;
        ed.revealLineInCenter(line);
        ed.setPosition({ lineNumber: line, column: 1 });
        ed.focus();
      } catch { /* noop */ }
    });
  };

  // Inline VS Code-style creation: an input row appears in the tree, Enter
  // creates, Esc (or empty name) creates nothing. No prompt() dialogs.
  const activeDir = activePath.includes("/") ? activePath.split("/").slice(0, -1).join("/") : "";
  const startCreate = (kind, dir = "") => {
    if (dir) setExpanded((p) => ({ ...p, [dir]: true }));
    setCreateName("");
    setCreating({ kind, dir });
  };
  const commitCreate = () => {
    if (!creating) return;
    const name = createName.trim().replace(/^\/+|\/+$/g, "");
    setCreating(null);
    setCreateName("");
    if (!name || name.includes("//")) return; // empty = nothing created
    if (creating.kind === "file") {
      if (name.endsWith("/")) return;
      const path = creating.dir ? `${creating.dir}/${name}` : name;
      if (filesRef.current.some((f) => f.path === path)) {
        openFile(path); // already exists — just open it
        return;
      }
      setFiles((prev) => [...prev, { path, content: "" }]);
      setTimeout(() => openFile(path), 0); // after filesRef catches up
    } else {
      const path = creating.dir ? `${creating.dir}/${name}` : name;
      setFiles((prev) => [...prev, { path: `${path}/.keep`, content: "" }]);
      setExpanded((p) => ({ ...p, [path]: true, [creating.dir]: true }));
    }
  };
  const cancelCreate = () => {
    setCreating(null);
    setCreateName("");
  };
  const createRow = (indent) => (
    <div className="flex items-center gap-1.5 py-[3px] pr-2" style={{ paddingLeft: 8 + indent }}>
      {creating.kind === "file"
        ? <FaFileCode className="h-3.5 w-3.5 shrink-0 text-[#519aba]" />
        : <FaFolder className="h-3.5 w-3.5 shrink-0 text-[#c09553]" />}
      <input
        autoFocus
        value={createName}
        onChange={(e) => setCreateName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitCreate();
          else if (e.key === "Escape") cancelCreate();
        }}
        onBlur={() => commitCreate()}
        placeholder={creating.kind === "file" ? "filename.js" : "folder name"}
        aria-label={creating.kind === "file" ? "New file name" : "New folder name"}
        className="min-w-0 flex-1 border border-[#007acc] bg-[#3c3c3c] px-1 py-px text-[13px] text-white outline-none"
      />
    </div>
  );

  const deleteFile = (path) => {
    if (visibleFiles(filesRef.current).length <= 1) return;
    if (!confirm(`Delete ${path}?`)) return;
    setOpenPaths((prev) => (prev.includes(path) && prev.length > 1 ? prev.filter((p) => p !== path) : prev));
    setTouched((p) => {
      if (!p[path]) return p;
      const n = { ...p };
      delete n[path];
      return n;
    });
    setFiles((prev) => {
      const next = prev.filter((f) => f.path !== path);
      if (path === activePath) {
        const rest = visibleFiles(next);
        if (rest.length) openFile(rest[0].path);
      }
      return next;
    });
    const m = modelsRef.current[path];
    if (m) {
      m.dispose();
      delete modelsRef.current[path];
    }
  };

  const run = () => {
    setLogs([]);
    setSrcDoc(buildSrcDoc(filesRef.current));
    setSidePreview(true);
    setPanelTab("terminal");
    setPanelOpen(true);
  };

  // Terminal resize: drag the panel's top edge up/down (direct style write
  // during the drag = 60fps; state commits once per move, cheap here).
  const onPanelDragStart = (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    panelDrag.current = { startY: e.clientY, startH: panelH };
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch { /* noop */ }
  };
  const onPanelDragMove = (e) => {
    const d = panelDrag.current;
    if (!d) return;
    const maxH = Math.max(160, (wrapRef.current?.clientHeight || 600) * 0.7);
    setPanelH(Math.max(80, Math.min(maxH, d.startH + (d.startY - e.clientY))));
  };
  const onPanelDragEnd = () => {
    panelDrag.current = null;
  };

  // Auto-run: rebuild the live preview shortly after edits stop.
  // Every keystroke flows editor -> files state -> here, so the preview
  // always reflects the latest code with no manual Run needed.
  useEffect(() => {
    if (!autoRun) return;
    const t = setTimeout(() => setSrcDoc(buildSrcDoc(files)), 700);
    return () => clearTimeout(t);
  }, [files, autoRun]);

  const logColor = (m) =>
    m === "error" ? "text-rose-400" : m === "warn" ? "text-amber-400" : m === "info" ? "text-sky-400" : "text-gray-300";

  const fileIcon = (path, cls = "h-3.5 w-3.5") => {
    const ext = extOf(path);
    if (ext === "env") return <FaGear className={`${cls} shrink-0 text-[#858585]`} />;
    return <FaFileCode className={`${cls} shrink-0`} style={{ color: FILE_COLOR[ext] || "#519aba" }} />;
  };

  const fileRow = (f, indent = 0) => (
    <div
      key={f.path}
      onClick={() => openFile(f.path)}
      className={`group relative flex cursor-pointer items-center gap-1.5 py-[3px] pr-2 text-[13px] transition ${
        f.path === activePath ? "bg-[#37373d] text-white" : "text-[#cccccc] hover:bg-[#2a2d2e]"
      }`}
      style={{ paddingLeft: 8 + indent }}
      title={f.path}
    >
      {f.path === activePath && <span className="absolute left-0 top-0 bottom-0 w-[2px] bg-[#007acc]" />}
      {fileIcon(f.path, "h-3.5 w-3.5")}
      <span className="min-w-0 flex-1 truncate">{f.path.split("/").pop()}</span>
      {touched[f.path] && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#e2c08d]" title="Edited" />}
      <button
        onClick={(e) => {
          e.stopPropagation();
          deleteFile(f.path);
        }}
        aria-label={`Delete ${f.path}`}
        className="hidden rounded p-0.5 text-gray-500 transition group-hover:block hover:bg-rose-900/50 hover:text-rose-300"
      >
        <FaTrash className="h-3 w-3" />
      </button>
    </div>
  );

  const folderNode = (node, depth) => (
    <div key={node.path}>
      <div
        onClick={() => setExpanded((p) => ({ ...p, [node.path]: !isOpen(node.path) }))}
        onContextMenu={(e) => {
          e.preventDefault();
          startCreate("file", node.path);
        }}
        title="Click to fold · right-click for new file here"
        className="flex cursor-pointer items-center gap-1 py-[3px] pr-2 text-[13px] font-bold text-[#cccccc] transition hover:bg-[#2a2d2e]"
        style={{ paddingLeft: 8 + depth * 12 }}
      >
        {isOpen(node.path) ? <FaChevronDown className="h-2.5 w-2.5 text-[#858585]" /> : <FaChevronRight className="h-2.5 w-2.5 text-[#858585]" />}
        {isOpen(node.path) ? <FaFolderOpen className="h-3.5 w-3.5 shrink-0 text-[#c09553]" /> : <FaFolder className="h-3.5 w-3.5 shrink-0 text-[#c09553]" />}
        <span className="truncate">{node.name}</span>
      </div>
      {isOpen(node.path) && (
        <div>
          {creating && creating.dir === node.path && createRow(12 + depth * 12)}
          {node.folders.map((c) => folderNode(c, depth + 1))}
          {node.files.map((f) => fileRow(f, 12 + depth * 12))}
        </div>
      )}
    </div>
  );

  // ---- derived: problems, outline, search ----
  const errors = logs.filter((l) => l.method === "error");
  const warns = logs.filter((l) => l.method === "warn");
  const activeFile = files.find((f) => f.path === activePath);
  const outline = (() => {
    if (!activeFile) return [];
    const rows = [];
    activeFile.content.split("\n").forEach((raw, i) => {
      const ln = raw.trim();
      const m =
        /^(function\s+[\w$]+|class\s+[\w$]+|(?:const|let|var)\s+[\w$]+\s*=\s*(?:async\s*)?\(|(?:const|let|var)\s+[\w$]+\s*=\s*(?:async\s*)?\w*\s*=>|def\s+[\w$]+|#+\s+\S)/.exec(ln);
      if (m && rows.length < 30) rows.push({ label: m[1].slice(0, 48), line: i + 1 });
    });
    return rows;
  })();
  const searchHits = (() => {
    const q = searchQ.trim().toLowerCase();
    if (q.length < 2) return [];
    const hits = [];
    for (const f of visibleFiles(files)) {
      const pathHit = f.path.toLowerCase().includes(q);
      const lines = f.content.split("\n");
      const lineNos = [];
      if (!pathHit) {
        lines.forEach((ln, i) => {
          if (lineNos.length < 4 && ln.toLowerCase().includes(q)) lineNos.push(i + 1);
        });
        if (!lineNos.length) continue;
      }
      hits.push({ path: f.path, lineNos });
      if (hits.length >= 30) break;
    }
    return hits;
  })();
  const crumbs = (activePath || "").split("/");

  const actBtn = (id, icon, label, badge) => (
    <button
      key={id}
      onClick={() => {
        if (id === "run") run();
        else setSideView((v) => (v === id ? "explorer" : id));
      }}
      title={label}
      aria-label={label}
      className={`relative flex h-11 w-11 items-center justify-center text-xl transition ${
        sideView === id && id !== "run" ? "text-white" : "text-[#858585] hover:text-white"
      }`}
    >
      {sideView === id && id !== "run" && (
        <span className="absolute left-0 top-0 bottom-0 w-[2px] bg-white" />
      )}
      {icon}
      {badge > 0 && (
        <span className="absolute right-1 bottom-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#007acc] px-1 text-[9px] font-bold text-white">
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </button>
  );

  const panelTabs = [
    { id: "terminal", label: `Terminal${logs.length ? ` (${logs.length})` : ""}` },
    { id: "problems", label: `Problems${errors.length + warns.length ? ` (${errors.length + warns.length})` : ""}` },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[#1e1e1e] text-[#cccccc]">
      <div className="flex min-h-0 flex-1">
        {/* ── activity bar ── */}
        <div className="flex w-11 shrink-0 flex-col items-center bg-[#333333] py-1">
          {actBtn("explorer", <FaRegCopy className="h-5 w-5" />, "Explorer")}
          {actBtn("search", <FaMagnifyingGlass className="h-5 w-5" />, "Search")}
          {actBtn("source", <FaCodeBranch className="h-5 w-5" />, "Source Control", Object.keys(touched).length)}
          {actBtn("run", <FaBug className="h-5 w-5" />, "Run and Debug")}
          <div className="mt-auto flex flex-col items-center">
            <button
              title="Settings"
              aria-label="Settings"
              className="flex h-11 w-11 items-center justify-center text-xl text-[#858585] transition hover:text-white"
            >
              <FaGear className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* ── sidebar ── */}
        <div className="flex w-52 shrink-0 flex-col bg-[#252526]">
          {sideView === "search" ? (
            <>
              <p className="px-4 pt-3 pb-2 text-[11px] tracking-wider text-[#bbbbbb] uppercase">Search</p>
              <div className="px-2">
                <div className="flex items-center gap-1.5 border border-[#007acc] bg-[#3c3c3c] px-2 py-1">
                  <FaMagnifyingGlass className="h-3 w-3 shrink-0 text-[#858585]" />
                  <input
                    value={searchQ}
                    onChange={(e) => setSearchQ(e.target.value)}
                    placeholder="Search files…"
                    aria-label="Search files"
                    className="min-w-0 flex-1 bg-transparent text-[13px] text-white outline-none placeholder:text-[#858585]"
                  />
                  {searchQ && (
                    <button onClick={() => setSearchQ("")} aria-label="Clear search" className="text-[#858585] hover:text-white">
                      <FaXmark className="h-3 w-3" />
                    </button>
                  )}
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto py-2">
                {searchQ.trim().length < 2 ? (
                  <p className="px-4 text-xs text-[#858585]">Type 2+ characters to search names + contents.</p>
                ) : searchHits.length === 0 ? (
                  <p className="px-4 text-xs text-[#858585]">No results.</p>
                ) : (
                  searchHits.map((h) => (
                    <div key={h.path}>
                      <button
                        onClick={() => openFile(h.path)}
                        className="flex w-full items-center gap-1.5 px-4 py-[3px] text-left text-[13px] text-[#cccccc] hover:bg-[#2a2d2e]"
                        title={h.path}
                      >
                        {fileIcon(h.path)}
                        <span className="truncate">{h.path.split("/").pop()}</span>
                        <span className="truncate text-[11px] text-[#858585]">{h.path}</span>
                      </button>
                      {h.lineNos.map((ln) => (
                        <button
                          key={ln}
                          onClick={() => gotoLine(h.path, ln)}
                          className="block w-full truncate px-4 py-[2px] pl-9 text-left font-mono text-[11px] text-[#9cdcfe] hover:bg-[#2a2d2e]"
                        >
                          :{ln} {(files.find((f) => f.path === h.path)?.content.split("\n")[ln - 1] || "").trim().slice(0, 60)}
                        </button>
                      ))}
                    </div>
                  ))
                )}
              </div>
            </>
          ) : sideView === "source" ? (
            <>
              <p className="px-4 pt-3 pb-2 text-[11px] tracking-wider text-[#bbbbbb] uppercase">Source Control</p>
              <div className="min-h-0 flex-1 overflow-y-auto py-1">
                {Object.keys(touched).length === 0 ? (
                  <p className="px-4 text-xs leading-5 text-[#858585]">No edits yet — files you change this session list here.</p>
                ) : (
                  Object.keys(touched).map((p) => (
                    <button
                      key={p}
                      onClick={() => openFile(p)}
                      className="flex w-full items-center gap-1.5 px-4 py-[3px] text-left text-[13px] text-[#cccccc] hover:bg-[#2a2d2e]"
                      title={p}
                    >
                      {fileIcon(p)}
                      <span className="min-w-0 flex-1 truncate">{p.split("/").pop()}</span>
                      <span className="text-[11px] font-bold text-[#e2c08d]">M</span>
                    </button>
                  ))
                )}
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between py-3 pr-2 pl-4">
                <span className="text-[11px] tracking-wider text-[#bbbbbb] uppercase">Explorer</span>
                <span className="flex">
                  <button onClick={() => startCreate("file", activeDir)} title="New file here" aria-label="New file" className="rounded p-1 text-[#cccccc] transition hover:bg-[#37373d] hover:text-white">
                    <FaPlus className="h-3 w-3" />
                  </button>
                  <button onClick={() => startCreate("folder", activeDir)} title="New folder here" aria-label="New folder" className="rounded p-1 text-[#cccccc] transition hover:bg-[#37373d] hover:text-white">
                    <FaFolder className="h-3 w-3" />
                  </button>
                </span>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto pb-2">
                <p className="flex items-center gap-1 px-2 py-1 text-[11px] font-bold tracking-wide text-[#bbbbbb] uppercase">
                  <FaChevronDown className="h-2.5 w-2.5" /> Open Editors
                </p>
                <div className="mb-1">
                  {openPaths.map((p) => (
                    <div
                      key={p}
                      onClick={() => openFile(p)}
                      className={`group relative flex cursor-pointer items-center gap-1.5 py-[3px] pr-2 pl-6 text-[13px] ${
                        p === activePath ? "bg-[#37373d] text-white" : "text-[#cccccc] hover:bg-[#2a2d2e]"
                      }`}
                      title={p}
                    >
                      {fileIcon(p)}
                      <span className="min-w-0 flex-1 truncate italic">{p.split("/").pop()}</span>
                      {touched[p] && <span className="text-[11px] font-bold text-[#e2c08d]">M</span>}
                      <span
                        role="button"
                        aria-label={`Close ${p}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          closeTab(p);
                        }}
                        className="hidden rounded p-0.5 text-[#858585] hover:bg-[#484848] hover:text-white group-hover:block"
                      >
                        <FaXmark className="h-3 w-3" />
                      </span>
                    </div>
                  ))}
                </div>
                <p className="flex items-center gap-1 px-2 py-1 text-[11px] font-bold tracking-wide text-[#bbbbbb] uppercase">
                  <FaChevronDown className="h-2.5 w-2.5" /> Bug-OS
                </p>
                {creating && creating.dir === "" && createRow(0)}
                {tree.folders.map((n) => folderNode(n, 0))}
                <div>{tree.files.map((f) => fileRow(f, 0))}</div>
                <p className="flex items-center gap-1 px-2 pt-3 pb-1 text-[11px] font-bold tracking-wide text-[#bbbbbb] uppercase">
                  <FaChevronRight className="h-2.5 w-2.5" /> Outline
                </p>
                {outline.length === 0 ? (
                  <p className="px-4 text-xs text-[#6e6e6e]">No symbols.</p>
                ) : (
                  outline.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => gotoLine(activePath, s.line)}
                      className="block w-full truncate px-4 py-[2px] pl-8 text-left font-mono text-[11px] text-[#9cdcfe] hover:bg-[#2a2d2e]"
                    >
                      {s.label}
                    </button>
                  ))
                )}
                <p className="flex items-center gap-1 px-2 pt-3 pb-1 text-[11px] font-bold tracking-wide text-[#bbbbbb] uppercase">
                  <FaChevronRight className="h-2.5 w-2.5" /> Timeline
                </p>
                <p className="px-4 text-xs text-[#6e6e6e]">Local history</p>
              </div>
            </>
          )}
        </div>

        {/* ── editor + panel ── */}
        <div ref={wrapRef} className="flex min-w-0 flex-1 flex-col bg-[#1e1e1e]">
          {/* tabs */}
          <div className="flex shrink-0 items-stretch overflow-x-auto bg-[#252526]">
            {openPaths.map((p) => {
              const on = p === activePath;
              return (
                <div
                  key={p}
                  onClick={() => openFile(p)}
                  className={`group flex shrink-0 cursor-pointer items-center gap-1.5 border-t border-r border-[#252526] px-3 py-2 text-[13px] ${
                    on ? "border-t-[#007acc] bg-[#1e1e1e] text-white" : "bg-[#2d2d2d] text-[#969696] hover:text-[#cccccc]"
                  }`}
                  title={p}
                >
                  {fileIcon(p)}
                  <span className={touched[p] ? "italic" : ""}>{p.split("/").pop()}</span>
                  {touched[p] ? (
                    <span className="text-[11px] font-bold text-[#e2c08d]">M</span>
                  ) : (
                    <span
                      role="button"
                      aria-label={`Close ${p}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        closeTab(p);
                      }}
                      className={`rounded p-0.5 hover:bg-[#484848] hover:text-white ${on ? "" : "hidden group-hover:block"}`}
                    >
                      <FaXmark className="h-3 w-3" />
                    </span>
                  )}
                </div>
              );
            })}
            <div className="flex flex-1 items-center justify-end gap-1 px-2">
              <button
                onClick={() => setAutoRun((v) => !v)}
                title={autoRun ? "Auto-run on edit: on" : "Auto-run on edit: off"}
                aria-label="Toggle auto-run"
                className={`rounded px-1.5 py-1 text-[11px] font-bold transition ${autoRun ? "text-[#4ec9b0]" : "text-[#858585] hover:text-white"}`}
              >
                Auto{autoRun ? " ✓" : ""}
              </button>              <button
                onClick={() => setSidePreview((v) => !v)}
                title={sidePreview ? "Hide preview" : "Show preview side by side"}
                aria-label={sidePreview ? "Hide preview" : "Show preview side by side"}
                className={`rounded p-1.5 transition ${sidePreview ? "text-white" : "text-[#858585] hover:text-white"}`}
              >
                <FaEye className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setPanelOpen((v) => !v)}
                title={panelOpen ? "Hide terminal" : "Show terminal"}
                aria-label={panelOpen ? "Hide terminal" : "Show terminal"}
                className={`rounded p-1.5 transition ${panelOpen ? "text-white" : "text-[#858585] hover:text-white"}`}
              >
                <FaTerminal className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={run}
                title="Run (live preview)"
                aria-label="Run"
                className="flex items-center gap-1.5 bg-[#0e639c] px-3 py-1 text-xs font-bold text-white transition hover:bg-[#1177bb]"
              >
                <FaPlay className="h-3 w-3" /> Run
              </button>
            </div>
          </div>
          {/* breadcrumbs */}
          <div className="flex shrink-0 items-center gap-1 overflow-x-auto px-3 py-1 text-xs text-[#858585]">
            {crumbs.map((c, i) => (
              <span key={i} className="flex shrink-0 items-center gap-1">
                {i > 0 && <FaChevronRight className="h-2 w-2 opacity-60" />}
                <span className={i === crumbs.length - 1 ? "text-[#cccccc]" : "hover:text-[#cccccc]"}>{c}</span>
              </span>
            ))}
          </div>
          {/* editor + side preview */}
          <div className="flex min-h-0 flex-1">
            {/* Mount node hosts ONLY Monaco: React-rendered children inside
                it collide with the editor's DOM (removeChild crash) and with
                direct cleanup. Placeholders live as absolute overlays. */}
            <div className="relative min-h-0 min-w-0 flex-1">
              <div ref={mountRef} className="absolute inset-0" />
              {!ready && !failed && (
                <div className="absolute inset-0 bg-[#1e1e1e]">
                  <p className="p-4 text-xs text-gray-500">Loading editor…</p>
                </div>
              )}
              {failed && (
                <div className="absolute inset-0 bg-[#1e1e1e]">
                  <p className="p-4 text-xs text-rose-400">Editor CDN unreachable — check network.</p>
                </div>
              )}
            </div>
            {sidePreview && (
              <div className="relative w-[38%] shrink-0 border-l border-[#2d2d2d] bg-white">
                <iframe
                  ref={iframeRef}
                  title="Preview"
                  sandbox="allow-scripts"
                  srcDoc={srcDoc}
                  className="h-full w-full border-0 bg-white"
                />
                <button
                  onClick={() => setSidePreview(false)}
                  title="Hide preview"
                  aria-label="Hide preview"
                  className="absolute top-1.5 right-1.5 rounded bg-black/50 p-1 text-white/80 transition hover:bg-black/70 hover:text-white"
                >
                  <FaXmark className="h-3 w-3" />
                </button>
              </div>
            )}
          </div>
          {/* panel */}
          <div className="relative shrink-0 border-t border-[#2d2d2d] bg-[#1e1e1e]" style={{ height: panelOpen ? panelH : 33 }}>
            {/* drag handle: pull the top edge to resize the terminal */}
            {panelOpen && (
              <div
                onPointerDown={onPanelDragStart}
                onPointerMove={onPanelDragMove}
                onPointerUp={onPanelDragEnd}
                onPointerCancel={onPanelDragEnd}
                title="Drag to resize terminal"
                className="absolute inset-x-0 -top-1 z-10 h-2 cursor-row-resize touch-none"
              />
            )}
            <div className="flex h-[33px] items-center gap-0.5 px-2">
              {panelTabs.map((t) => (
                <button
                  key={t.id}
                  onClick={() => {
                    setPanelTab(t.id);
                    setPanelOpen(true);
                  }}
                  className={`border-b px-2.5 py-1.5 text-[11px] tracking-wide uppercase transition ${
                    panelOpen && panelTab === t.id
                      ? "border-[#007acc] text-white"
                      : "border-transparent text-[#969696] hover:text-[#cccccc]"
                  }`}
                >
                  {t.label}
                </button>
              ))}
              <span className="ml-auto flex items-center gap-0.5">
                {panelTab === "terminal" && logs.length > 0 && (
                  <button
                    onClick={() => setLogs([])}
                    aria-label="Clear terminal"
                    title="Clear terminal"
                    className="rounded p-1.5 text-[#858585] transition hover:bg-[#37373d] hover:text-white"
                  >
                    <FaEraser className="h-3.5 w-3.5" />
                  </button>
                )}
                <button
                  onClick={() => setPanelOpen((v) => !v)}
                  aria-label={panelOpen ? "Hide panel" : "Show panel"}
                  title={panelOpen ? "Hide panel" : "Show panel"}
                  className="rounded p-1.5 text-[#858585] transition hover:bg-[#37373d] hover:text-white"
                >
                  <FaChevronDown className={`h-3.5 w-3.5 transition ${panelOpen ? "" : "rotate-180"}`} />
                </button>
              </span>
            </div>
            {panelOpen && (
              <div style={{ height: panelH - 33 }} className="min-h-0">
                {panelTab === "terminal" ? (
                  <div className="h-full overflow-y-auto bg-[#1e1e1e] px-3 py-1.5 font-mono text-[12px] leading-5">
                    {logs.length === 0 && <p className="text-[#6e6e6e]">console output lands here…</p>}
                    {logs.map((l) => (
                      <p key={l.id} className={logColor(l.method)}>
                        <span className="opacity-60">[{l.method}]</span> {l.text}
                      </p>
                    ))}
                  </div>
                ) : (
                  <div className="h-full overflow-y-auto bg-[#1e1e1e] px-3 py-1.5 font-mono text-[12px] leading-5">
                    {errors.length + warns.length === 0 ? (
                      <p className="flex items-center gap-2 text-[#6e6e6e]">
                        <FaTriangleExclamation className="h-3.5 w-3.5" /> No problems — preview errors land here.
                      </p>
                    ) : (
                      [...errors, ...warns].map((l) => (
                        <p key={l.id} className={logColor(l.method)}>
                          <span className="opacity-60">[{l.method}]</span> {l.text}
                        </p>
                      ))
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── status bar ── */}
      <div className="flex h-6 shrink-0 items-center gap-3 bg-[#007acc] px-2 text-[11px] text-white">
        <span className="flex items-center gap-1 font-semibold" title="Branch">
          <FaCodeBranch className="h-3 w-3" /> master*
        </span>
        <FaArrowsRotate className="h-3 w-3 opacity-80" title="Sync" />
        <span className="flex items-center gap-2" title="Errors / warnings">
          <span>⊘ {errors.length}</span>
          <span className="flex items-center gap-0.5">
            <FaTriangleExclamation className="h-3 w-3" /> {warns.length}
          </span>
        </span>
        <span className="ml-auto" />
        <span className="tabular-nums">Ln {cursor.ln}, Col {cursor.col}</span>
        <span>Spaces: 4</span>
        <span>UTF-8</span>
        <span>LF</span>
        <span>{LANG_LABEL[activeFile ? langOf(activeFile.path) : "javascript"] || "Plain Text"}</span>
        <button onClick={run} className="flex items-center gap-1 font-semibold hover:bg-white/20 px-1" title="Run live preview">
          <FaEye className="h-3 w-3" /> Go Live
        </button>
        <FaBell className="h-3 w-3" title="Notifications" />
      </div>
    </div>
  );
}
