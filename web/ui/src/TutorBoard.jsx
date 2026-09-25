import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FaDiagramProject, FaExpand, FaMinus, FaPlus, FaSatelliteDish } from "react-icons/fa6";
import { BOARD_THEME as T } from "./boardTheme.js";

/* TutorBoard — natural classroom GREEN chalkboard lesson feed.
   A fresh board per explanation: when the tutor starts drawing a NEW answer,
   the old lesson wipes with a smooth fade (App.jsx) so new chalk never lands
   OVER old chalk. Each part is a section (diagram SVG + code/note/image
   blocks) revealed progressively AS the tutor speaks it.

   Feel rules:
   - Green board, white chalk text, chalk-yellow accents. No step numbers
     anywhere — navigation is natural Prev / Next (+ dots + titles).
   - Board draws in flow with the voice: elements appear when their spoken
     word plays (App.jsx stages by TTS window + spoken trigger).

   Props:
   - steps: [{ key, title, elements: [revealed...] }] in lesson order.
   - focus: { stepKey, ids:[...], tick } — latest drawn element; the chalk
     glides there and the viewport follows (when followLive).
   - stepIndex, onStep(i): controlled navigation (Prev / Next).
   - followLive, onJumpLive(): resume auto-follow at the newest part.
*/

const DRAW_MS = 650; // chalk-stroke animation per shape
const CHALK_FONT = `"Segoe Print","Bradley Hand","Kalam","Comic Sans MS",cursive`;

function StepDiagram({ elements, focusIds, viewBox, svgRef }) {
  const shapes = useMemo(
    () => (elements || []).filter((e) => e && e.type !== "arrow" && (e.text || "").trim()),
    [elements],
  );
  const arrows = useMemo(
    () => (elements || []).filter((e) => e && e.type === "arrow" && Array.isArray(e.points)),
    [elements],
  );
  const box = useMemo(() => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const e of [...shapes, ...arrows]) {
      const w = Number(e.width) || 180, h = Number(e.height) || 60;
      minX = Math.min(minX, Number(e.x) || 0);
      minY = Math.min(minY, Number(e.y) || 0);
      maxX = Math.max(maxX, (Number(e.x) || 0) + w);
      maxY = Math.max(maxY, (Number(e.y) || 0) + h);
    }
    if (!isFinite(minX)) return null;
    const pad = 20;
    return {
      x: minX - pad, y: minY - pad,
      w: maxX - minX + pad * 2, h: maxY - minY + pad * 2,
    };
  }, [shapes, arrows]);

  const byId = useMemo(() => new Map(shapes.map((s) => [s.id, s])), [shapes]);
  const hot = useMemo(() => new Set(focusIds || []), [focusIds]);
  // Compare parts (side=left/right): a VS divider between the columns.
  const divider = useMemo(() => {
    let lMax = -Infinity, rMin = Infinity;
    for (const s of shapes) {
      if (s.side === "left") lMax = Math.max(lMax, (Number(s.x) || 0) + (Number(s.width) || 0));
      if (s.side === "right") rMin = Math.min(rMin, Number(s.x) || 0);
    }
    return isFinite(lMax) && isFinite(rMin) && rMin > lMax ? (lMax + rMin) / 2 : null;
  }, [shapes]);
  if (!box) return null;

  const toneOf = (s) => T.tones?.[s?.tone] || T.tones.core;
  const drawStyleFor = (s) => {
    const tone = toneOf(s);
    return {
      fill: tone.fill,
      stroke: tone.stroke,
      strokeWidth: 1.75,
      strokeDasharray: 1,
      strokeDashoffset: 1,
      animation: `tutor-draw ${DRAW_MS}ms ease-out forwards`,
    };
  };
  const hotExtra = {
    stroke: T.primary,
    strokeWidth: 2.5,
    filter: `drop-shadow(0 0 7px ${T.primary}88)`,
  };

  return (
    <svg
      ref={svgRef}
      viewBox={viewBox || `${box.x} ${box.y} ${box.w} ${box.h}`}
      className="h-auto w-full"
      role="img"
      aria-label="Lesson diagram"
    >
      <style>{`@keyframes tutor-draw { to { stroke-dashoffset: 0; } }
@keyframes tutor-fadein { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }
@keyframes tutor-flow { to { stroke-dashoffset: -0.105; } }
@keyframes tutor-pop { 0% { opacity: 0; transform: scale(0.92); } 60% { opacity: 1; transform: scale(1.015); } 100% { opacity: 1; transform: scale(1); } }`}</style>
      {shapes.map((s) => {
        const w = Number(s.width) || 180, h = Number(s.height) || 60;
        const label = String(s.text || "");
        const isHot = hot.has(s.id);
        // Free-floating chalk annotation: no box, just chalk text.
        if (s.type === "text")
          return (
            <g key={s.id} style={{ animation: `tutor-fadein 450ms ease both` }}>
              <text
                x={s.x} y={s.y + 20}
                fontSize={15} fontWeight={600} fontFamily={CHALK_FONT}
                fill={s.tone && s.tone !== "core" ? toneOf(s).stroke : T.ink}
                opacity={0.96}
                style={isHot ? { filter: `drop-shadow(0 0 6px ${T.primary}88)` } : undefined}
              >
                {label}
              </text>
            </g>
          );
        const fs = Math.max(11, Math.min(13.5, w / Math.max(8, label.length * 0.62)));
        const labelEl = (
          <text
            x={s.x + w / 2} y={s.y + h / 2}
            textAnchor="middle" dominantBaseline="central"
            fontSize={fs} fontWeight={600} fontFamily={CHALK_FONT} fill={T.ink}
            opacity={0.97}
            style={{ animation: `tutor-fadein 400ms ease ${DRAW_MS}ms both` }}
          >
            {label.length > 40 ? label.slice(0, 39) + "…" : label}
          </text>
        );
        const gStyle = {
          ...drawStyleFor(s),
          ...(isHot ? hotExtra : null),
          transformBox: "fill-box",
          transformOrigin: "center",
          animation: `tutor-draw ${DRAW_MS}ms ease-out forwards, tutor-pop 350ms ease ${DRAW_MS}ms both`,
        };
        if (s.type === "ellipse")
          return (
            <g key={s.id}>
              <ellipse cx={s.x + w / 2} cy={s.y + h / 2} rx={w / 2} ry={h / 2} pathLength={1} style={gStyle} />
              {labelEl}
            </g>
          );
        if (s.type === "diamond") {
          const pts = `${s.x + w / 2},${s.y} ${s.x + w},${s.y + h / 2} ${s.x + w / 2},${s.y + h} ${s.x},${s.y + h / 2}`;
          return (
            <g key={s.id}>
              <polygon points={pts} pathLength={1} style={gStyle} />
              {labelEl}
            </g>
          );
        }
        return (
          <g key={s.id}>
            <rect x={s.x} y={s.y} width={w} height={h} rx={T.radius} pathLength={1} style={gStyle} />
            {labelEl}
          </g>
        );
      })}
      {divider != null && (
        <g aria-hidden="true">
          <line
            x1={divider} y1={box.y + 6} x2={divider} y2={box.y + box.h - 6}
            stroke="rgba(255,255,255,0.5)" strokeWidth={1.5} strokeDasharray="5 5" opacity={0.8}
          />
          <g transform={`translate(${divider}, ${box.y + box.h / 2})`}>
            <rect x={-19} y={-12} width={38} height={24} rx={12} fill="#fdfef7" />
            <text textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={800} fill="#143626">
              VS
            </text>
          </g>
        </g>
      )}
      {arrows.map((a) => {
        if (!byId.get(String(a.startNodeId || "")) || !byId.get(String(a.endNodeId || ""))) return null;
        const pts = Array.isArray(a.points) ? a.points : [];
        if (pts.length < 2) return null;
        const id = `ah-${String(a.id).replace(/[^a-zA-Z0-9_-]/g, "")}`;
        // Full polyline: the server routes orthogonal elbows (3-4 points)
        // through row gaps — render every point, not just the endpoints.
        const line = pts.map(([px, py]) => `${a.x + px},${a.y + py}`).join(" ");
        return (
          <g key={a.id}>
            <defs>
              <marker id={id} markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">
                <path d="M0,0 L8,4.5 L0,9 Z" fill={T.primary} />
              </marker>
            </defs>
            <polyline
              points={line}
              fill="none" stroke={T.primary} strokeWidth={2.25}
              markerEnd={`url(#${id})`}
              pathLength={1} strokeDasharray="0.06 0.045" strokeDashoffset={1}
              style={{ animation: `tutor-draw ${DRAW_MS}ms ease-out forwards, tutor-flow 1.15s linear ${DRAW_MS + 50}ms infinite` }}
            />
          </g>
        );
      })}
    </svg>
  );
}

function CodeBlock({ block, caption }) {
  const code = String(block.code || block.text || "");
  const lines = useMemo(() => code.split("\n"), [code]);
  // Karaoke: the line whose code-ish tokens best match the spoken caption
  // (what the tutor is explaining RIGHT NOW) glows in chalk yellow.
  const hotLine = useMemo(() => {
    if (!caption) return -1;
    const cap = String(caption).toLowerCase();
    let best = -1, bestScore = 0;
    lines.forEach((ln, i) => {
      const raw = ln.match(/[A-Za-z_][A-Za-z0-9_#.]*|\d+/g) || [];
      const toks = [...new Set(raw.map((t) => t.toLowerCase()))]
        .filter((t, k) => /[0-9_#.]/.test(raw[k]) || raw[k].length >= 7 || /[A-Z]/.test(raw[k]));
      let s = 0;
      for (const t of toks) if (t.length >= 2 && cap.includes(t)) s += t.length >= 6 ? 2 : 1;
      if (s > bestScore) { bestScore = s; best = i; }
    });
    return bestScore > 0 ? best : -1;
  }, [lines, caption]);
  return (
    <div className="overflow-hidden rounded-xl shadow-sm" style={{ background: T.codeBg, border: "1px solid rgba(255,255,255,0.16)" }}>
      <div className="flex items-center gap-2 px-3.5 py-2" style={{ borderBottom: "1px solid rgba(255,255,255,0.12)" }}>
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: T.primary }} aria-hidden="true" />
        <span className="text-[0.68rem] font-bold tracking-[0.1em] uppercase" style={{ color: T.muted }}>
          {block.language || "code"}
        </span>
        {hotLine >= 0 && (
          <span className="ml-auto text-[0.62rem] font-bold tracking-wider uppercase" style={{ color: T.primary }}>
            ◉ line {hotLine + 1}
          </span>
        )}
      </div>
      <pre
        className="overflow-x-auto py-2 font-mono text-[0.8rem] leading-6"
        style={{ color: T.codeInk }}
      >
        {lines.map((ln, i) => (
          <div
            key={i}
            className="flex whitespace-pre transition-colors duration-300"
            style={i === hotLine
              ? { background: "rgba(255,209,102,0.14)", boxShadow: `inset 3px 0 0 ${T.primary}` }
              : undefined}
          >
            <span className="w-9 shrink-0 pr-2 text-right select-none" style={{ color: "rgba(255,255,255,0.35)" }}>{i + 1}</span>
            <span className="pr-3.5">{ln || " "}</span>
          </div>
        ))}
      </pre>
    </div>
  );
}

function NoteBlock({ block }) {
  return (
    <div
      className="rounded-xl px-3.5 py-2.5 text-[0.83rem] leading-6 shadow-sm"
      style={{ background: "rgba(255,255,255,0.10)", color: T.ink, borderLeft: `4px solid ${T.primary}`, fontFamily: CHALK_FONT }}
    >
      {String(block.text || "")}
    </div>
  );
}

function TableBlock({ block }) {
  const headers = (Array.isArray(block.headers) ? block.headers : [])
    .map((h) => String(h ?? "").trim()).slice(0, 4);
  const rows = (Array.isArray(block.rows) ? block.rows : []).slice(0, 6)
    .map((r) => (Array.isArray(r) ? r : [r]).map((c) => String(c ?? "").trim()));
  const width = Math.min(4, Math.max(headers.length, ...rows.map((r) => r.length), 0));
  if (!width) return null;
  const head = (headers.length ? headers : Array(width).fill("")).slice(0, width);
  const body = rows.map((r) => (r.concat(Array(width).fill(""))).slice(0, width));
  if (!head.some(Boolean) && !body.some((r) => r.some(Boolean))) return null;
  return (
    <div
      className="overflow-hidden rounded-xl shadow-sm"
      style={{ background: "rgba(0,0,0,0.16)", border: "1px solid rgba(255,255,255,0.2)", animation: "tutor-pop 350ms ease both" }}
    >
      {block.text ? (
        <p className="px-3.5 pt-2.5 text-[0.8rem] font-bold" style={{ color: T.ink, fontFamily: CHALK_FONT }}>
          {String(block.text)}
        </p>
      ) : null}
      <table className="w-full border-collapse px-3 text-[0.78rem] leading-6" style={{ color: T.ink }}>
        <thead>
          <tr>
            {head.map((h, i) => (
              <th
                key={i}
                className="px-3 py-2 text-left font-bold"
                style={{ color: T.primary, fontFamily: CHALK_FONT, borderBottom: "1.5px solid rgba(255,209,102,0.5)" }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((r, i) => (
            <tr key={i} style={i < body.length - 1 ? { borderBottom: "1px solid rgba(255,255,255,0.14)" } : undefined}>
              {r.map((c, j) => (
                <td key={j} className="px-3 py-1.5" style={{ fontFamily: CHALK_FONT }}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="h-2" />
    </div>
  );
}

function QuizBlock({ block }) {
  const options = (Array.isArray(block.options) ? block.options : [])
    .map((o) => String(o ?? "").trim()).filter(Boolean).slice(0, 4);
  const answer = Number.isInteger(block.answer) ? block.answer : null;
  const [picked, setPicked] = useState(null);
  if (!block.text || options.length < 2) return null;
  const letters = ["A", "B", "C", "D"];
  const revealed = picked !== null;
  const correct = answer !== null && picked === answer;
  const ringOf = (i) => {
    if (!revealed) return "1px solid rgba(255,255,255,0.25)";
    if (answer !== null && i === answer) return `2px solid ${T.primary}`;
    if (i === picked) return "2px solid #ff9e9e";
    return "1px solid rgba(255,255,255,0.18)";
  };
  return (
    <div
      className="rounded-xl px-3.5 py-3 shadow-sm"
      style={{ background: "rgba(255,209,102,0.10)", border: "1.5px dashed rgba(255,209,102,0.55)", animation: "tutor-pop 350ms ease both" }}
    >
      <p className="text-[0.85rem] leading-6 font-bold" style={{ color: T.ink, fontFamily: CHALK_FONT }}>
        <span style={{ color: T.primary }}>✎ Quiz · </span>{String(block.text)}
      </p>
      <div className="mt-2 flex flex-col gap-1.5" role="group" aria-label="Quiz options">
        {options.map((o, i) => (
          <button
            key={i}
            onClick={() => setPicked(i)}
            disabled={revealed}
            className="flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-left text-[0.8rem] transition disabled:cursor-default"
            style={{
              background: revealed && answer !== null && i === answer
                ? "rgba(255,209,102,0.22)"
                : revealed && i === picked
                  ? "rgba(255,158,158,0.16)"
                  : "rgba(0,0,0,0.18)",
              border: ringOf(i),
              color: T.ink,
              fontFamily: CHALK_FONT,
            }}
            aria-label={`Option ${letters[i]}: ${o}`}
          >
            <span
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[0.65rem] font-bold"
              style={{
                background: revealed && answer !== null && i === answer ? T.primary : "rgba(255,255,255,0.15)",
                color: revealed && answer !== null && i === answer ? "#143626" : T.ink,
              }}
              aria-hidden="true"
            >
              {letters[i]}
            </span>
            <span className="min-w-0 flex-1">{o}</span>
            {revealed && answer !== null && i === answer && <span aria-hidden="true">✓</span>}
            {revealed && answer !== null && i === picked && picked !== answer && <span aria-hidden="true">✗</span>}
          </button>
        ))}
      </div>
      {revealed && (
        <p className="mt-2 text-[0.78rem] leading-6" style={{ color: T.muted, fontFamily: CHALK_FONT, animation: "tutor-fadein 400ms ease both" }}>
          {answer === null
            ? (block.explanation ? `☞ ${block.explanation}` : "☞ Say your answer out loud — the tutor will respond.")
            : correct
              ? `✓ Correct${block.explanation ? ` — ${block.explanation}` : "!" }`
              : `✗ Not quite — ${letters[answer]} is right${block.explanation ? `: ${block.explanation}` : "."}`}
        </p>
      )}
      {!revealed && (
        <p className="mt-1.5 text-[0.68rem]" style={{ color: T.muted, fontFamily: CHALK_FONT }}>
          {answer === null ? "Think it through, then tap to reveal." : "Tap your answer — or say it out loud."}
        </p>
      )}
    </div>
  );
}

function HtmlBlock({ block }) {
  const height = Math.max(120, Math.min(420, Number(block.height) || 220));
  const src = String(block.html || "");
  if (!src) return null;
  // Scriptless sandbox: no scripts, forms, or popups can ever run inside.
  return (
    <div
      className="overflow-hidden rounded-xl shadow-sm"
      style={{ border: "1px solid rgba(255,255,255,0.2)", background: "#ffffff", animation: "tutor-pop 350ms ease both" }}
    >
      <iframe
        title={block.text || "Visual explanation"}
        sandbox=""
        srcDoc={src}
        loading="lazy"
        scrolling="no"
        style={{ width: "100%", height, border: 0, display: "block", background: "#ffffff" }}
      />
    </div>
  );
}

function ImageBlock({ block }) {
  if (!block.src) {
    return (
      <div
        className="flex h-36 animate-pulse flex-col items-center justify-center gap-2 rounded-xl"
        style={{ background: "rgba(255,255,255,0.08)" }}
        aria-label="Image loading"
      >
        <FaSatelliteDish className="h-5 w-5" style={{ color: T.faint }} />
        <p className="text-xs font-medium" style={{ color: T.muted, fontFamily: CHALK_FONT }}>Finding a picture…</p>
      </div>
    );
  }
  return (
    <figure className="overflow-hidden rounded-xl shadow-sm" style={{ border: "1px solid rgba(255,255,255,0.2)", background: "rgba(0,0,0,0.2)" }}>
      <img src={block.src} alt={block.alt || "Lesson image"} className="max-h-72 w-full object-cover" loading="lazy" />
      {block.credit && (
        <figcaption className="px-3 py-1.5 text-[0.65rem]" style={{ color: T.muted }}>
          📷 {block.credit}
        </figcaption>
      )}
    </figure>
  );
}

export default function TutorBoard({
  elements, focus, followLive, onFollowChange, caption, wiping,
}) {
  const scrollRef = useRef(null);
  const svgRef = useRef(null);
  const penRef = useRef(null);
  const elRefs = useRef(new Map());
  const vbRef = useRef(null); // current camera viewBox {x,y,w,h}
  const animRef = useRef(0);
  const [zoomPct, setZoomPct] = useState(100);

  const shapes = useMemo(
    () => (elements || []).filter((e) => e && (e.type === "rectangle" || e.type === "ellipse" || e.type === "diamond" || e.type === "text")),
    [elements],
  );
  const arrows = useMemo(
    () => (elements || []).filter((e) => e && e.type === "arrow" && Array.isArray(e.points)),
    [elements],
  );
  const extras = useMemo(
    () => (elements || []).filter((e) => e && (e.type === "code" || e.type === "note" || e.type === "image" || e.type === "table" || e.type === "quiz" || e.type === "html")),
    [elements],
  );
  const byId = useMemo(() => new Map(shapes.map((s) => [s.id, s])), [shapes]);

  // Full-board bounds (mirrors StepDiagram's box math + padding).
  const full = useMemo(() => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const e of [...shapes, ...arrows]) {
      const w = Number(e.width) || 180, h = Number(e.height) || 60;
      minX = Math.min(minX, Number(e.x) || 0);
      minY = Math.min(minY, Number(e.y) || 0);
      maxX = Math.max(maxX, (Number(e.x) || 0) + w);
      maxY = Math.max(maxY, (Number(e.y) || 0) + h);
    }
    if (!isFinite(minX)) return null;
    const pad = 36;
    return { x: minX - pad, y: minY - pad, w: maxX - minX + pad * 2, h: maxY - minY + pad * 2 };
  }, [shapes, arrows]);
  const fullRef = useRef(null);
  useEffect(() => { fullRef.current = full; }, [full]);
  // Camera: fly the viewBox (direct DOM write = 60fps, no re-renders).
  const applyVb = (vb) => {
    vbRef.current = vb;
    try {
      svgRef.current?.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
    } catch { /* noop */ }
  };
  const flyTo = useCallback((target, dur = 450) => {
    if (animRef.current) cancelAnimationFrame(animRef.current);
    animRef.current = 0;
    const from = vbRef.current || target;
    if (!svgRef.current) {
      applyVb(target);
      return;
    }
    if (dur <= 0) {
      applyVb(target);
      const f = fullRef.current;
      if (f) setZoomPct(Math.max(10, Math.min(400, Math.round((f.w / target.w) * 100))));
      return;
    }
    const t0 = performance.now();
    const stepFn = (t) => {
      const k = Math.min(1, (t - t0) / dur);
      const e = k < 0.5 ? 4 * k * k * k : 1 - ((-2 * k + 2) ** 3) / 2;
      const vb = {
        x: from.x + (target.x - from.x) * e,
        y: from.y + (target.y - from.y) * e,
        w: from.w + (target.w - from.w) * e,
        h: from.h + (target.h - from.h) * e,
      };
      applyVb(vb);
      if (k < 1) {
        animRef.current = requestAnimationFrame(stepFn);
      } else {
        animRef.current = 0;
        const f = fullRef.current;
        if (f) setZoomPct(Math.max(10, Math.min(400, Math.round((f.w / target.w) * 100))));
      }
    };
    animRef.current = requestAnimationFrame(stepFn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => () => {
    if (animRef.current) cancelAnimationFrame(animRef.current);
  }, []);

  // First paint / board reset: frame the whole canvas instantly.
  const hadContent = useRef(false);
  useEffect(() => {
    if (full && !vbRef.current) {
      applyVb(full);
      setZoomPct(100);
      hadContent.current = true;
    } else if (!full && hadContent.current) {
      vbRef.current = null;
      setZoomPct(100);
      hadContent.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [full]);
  const scrollExtraIntoView = (node) => {
    const box = scrollRef.current;
    if (!box || !node) return;
    try {
      const r = node.getBoundingClientRect(), b = box.getBoundingClientRect();
      const target = box.scrollTop + (r.top - b.top) - box.clientHeight / 2 + r.height / 2;
      if (Number.isFinite(target)) box.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
    } catch { /* noop */ }
  };

  // Follow: fly the camera to each freshly drawn element, glide the chalk.
  // A hand on the board wins: skip while the user is dragging.
  useEffect(() => {
    if (!followLive || !focus?.ids?.length || dragRef.current) return;
    const id = focus.ids[0];
    const shape = byId.get(id);
    if (shape) {
      // Zoom to the focused area with context around it (min window so a
      // tiny node still shows its neighbors and connecting arrows).
      const sw = Number(shape.width) || 220, sh = Number(shape.height) || 64;
      const w = Math.max(460, sw + 160);
      const h = Math.max(340, sh + 160);
      const cx = (Number(shape.x) || 0) + sw / 2;
      const cy = (Number(shape.y) || 0) + sh / 2;
      flyTo({ x: cx - w / 2, y: cy - h / 2, w, h });
      // Chalk piece: map board coords to screen coords under the camera.
      const pen = penRef.current, svg = svgRef.current;
      const vb = vbRef.current;
      if (pen && svg && vb) {
        try {
          const r = svg.getBoundingClientRect();
          const px = (((Number(shape.x) || 0) + sw / 2) - vb.x) / vb.w * r.width;
          const py = ((Number(shape.y) || 0) - vb.y) / vb.h * r.height;
          pen.style.opacity = "1";
          pen.style.transform = `translate(${px}px, ${py - 6}px)`;
        } catch { /* noop */ }
      }
    } else {
      const node = elRefs.current.get(id);
      if (node) scrollExtraIntoView(node);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.tick]);

  const zoomBy = (f) => {
    const base = vbRef.current || fullRef.current;
    const fbox = fullRef.current;
    if (!base || !fbox) return;
    const w = Math.max(220, Math.min(fbox.w, base.w * f));
    const h = (w / base.w) * base.h;
    const cx = base.x + base.w / 2, cy = base.y + base.h / 2;
    const x = Math.max(fbox.x - 40, Math.min(cx - w / 2, fbox.x + fbox.w + 40 - w));
    const y = Math.max(fbox.y - 40, Math.min(cy - h / 2, fbox.y + fbox.h + 40 - h));
    onFollowChange && onFollowChange(false);
    flyTo({ x, y, w, h }, 250);
  };
  const fitAll = () => {
    const fbox = fullRef.current;
    if (!fbox) return;
    onFollowChange && onFollowChange(false);
    flyTo({ ...fbox }, 350);
  };
  const jumpLive = () => {
    onFollowChange && onFollowChange(true);
    const ids = focus?.ids;
    const shape = ids?.length && byId.get(ids[0]);
    if (shape) {
      const sw = Number(shape.width) || 220, sh = Number(shape.height) || 64;
      const w = Math.max(460, sw + 160);
      const h = Math.max(340, sh + 160);
      const cx = (Number(shape.x) || 0) + sw / 2;
      const cy = (Number(shape.y) || 0) + sh / 2;
      flyTo({ x: cx - w / 2, y: cy - h / 2, w, h });
    } else if (fullRef.current) {
      flyTo({ ...fullRef.current });
    }
  };

  const setElRef = (id) => (node) => {
    if (!id) return;
    if (node) elRefs.current.set(id, node);
    else elRefs.current.delete(id);
  };

  // Real-canvas pan: press-hold anywhere on the chalk area and slide to move
  // the board under a fixed viewport (direct viewBox write = 60fps, no
  // re-renders). Manual pan drops live-follow so the camera stops fighting
  // your hand; the ● Live button resumes it.
  const dragRef = useRef(null); // {x, y, vb} while a pan is in flight
  const onBoardPointerDown = (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    const base = vbRef.current || fullRef.current;
    if (!base) return;
    if (animRef.current) {
      cancelAnimationFrame(animRef.current);
      animRef.current = 0;
    }
    onFollowChange && onFollowChange(false);
    dragRef.current = { x: e.clientX, y: e.clientY, vb: { ...base } };
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch { /* noop */ }
  };
  const onBoardPointerMove = (e) => {
    const d = dragRef.current;
    const svg = svgRef.current;
    if (!d || !d.vb || !svg) return;
    const r = svg.getBoundingClientRect();
    if (!r || !r.width || !r.height) return;
    // viewBox units per screen px (aspect is locked, so both axes agree).
    const s = d.vb.w / r.width;
    applyVb({
      ...d.vb,
      x: d.vb.x - (e.clientX - d.x) * s,
      y: d.vb.y - (e.clientY - d.y) * s,
    });
  };
  const onBoardPointerUp = () => {
    dragRef.current = null;
  };

  return (
    <div
      className="relative flex h-full min-h-[480px] w-full flex-col overflow-hidden"
      aria-label="Green board"
      style={{
        background: `linear-gradient(160deg, ${T.paper} 0%, ${T.paperDeep} 100%)`,
        border: `10px solid ${T.wood}`,
        borderRadius: 6,
        boxShadow: "inset 0 0 60px rgba(0,0,0,0.35)",
      }}
    >
      {/* Chalk-dust texture */}
      <div
        className="pointer-events-none absolute inset-0"
        aria-hidden="true"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, rgba(255,255,255,0.025) 0 1px, transparent 1px 5px)",
          mixBlendMode: "overlay",
        }}
      />
      {/* Camera bar: zoom controls + live-follow. No steps — one board. */}
      <div
        className="z-10 flex shrink-0 items-center gap-2 px-3 py-2"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.15)", background: "rgba(0,0,0,0.22)", backdropFilter: "blur(6px)" }}
      >
        <span className="text-[0.72rem] font-bold tracking-wide" style={{ color: T.muted, fontFamily: CHALK_FONT }}>
          Green board
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          <button
            onClick={() => zoomBy(1.35)}
            disabled={!full}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full transition disabled:opacity-30"
            style={{ background: "rgba(255,255,255,0.12)", color: T.ink }}
            aria-label="Zoom out"
            title="Zoom out"
          >
            <FaMinus className="h-3 w-3" />
          </button>
          <span className="min-w-11 text-center text-[0.7rem] font-bold tabular-nums" style={{ color: T.muted }}>
            {zoomPct}%
          </span>
          <button
            onClick={() => zoomBy(0.74)}
            disabled={!full}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full transition disabled:opacity-30"
            style={{ background: "rgba(255,255,255,0.12)", color: T.ink }}
            aria-label="Zoom in"
            title="Zoom in"
          >
            <FaPlus className="h-3 w-3" />
          </button>
          <button
            onClick={fitAll}
            disabled={!full}
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[0.72rem] font-bold transition disabled:opacity-30"
            style={{ background: "rgba(255,255,255,0.12)", color: T.ink }}
            aria-label="Fit whole board"
            title="Fit whole board"
          >
            <FaExpand className="h-3 w-3" />
            Fit
          </button>
        </span>
        <button
          onClick={jumpLive}
          className="rounded-full px-2.5 py-1 text-[0.68rem] font-bold shadow-sm transition hover:brightness-95"
          style={followLive
            ? { background: "rgba(255,209,102,0.16)", color: T.primary }
            : { background: "#fdfef7", color: "#143626" }}
          aria-label="Follow live drawing"
          title="Follow live drawing"
        >
          ● Live
        </button>
      </div>

      <div
        ref={scrollRef}
        className={`no-scrollbar relative min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 transition-opacity duration-300 ${wiping ? "opacity-0" : "opacity-100"}`}
      >
        {/* Chalk piece: glides to each freshly drawn element. */}
        <div
          ref={penRef}
          className="pointer-events-none absolute top-0 left-0 z-10 h-3 w-3 rounded-full opacity-0 transition-all duration-700 ease-out"
          style={{ background: T.primary, boxShadow: `0 0 0 4px ${T.primary}33, 0 0 12px ${T.primary}` }}
          aria-hidden="true"
        />
        {!shapes.length && !extras.length && (
          <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-2 text-center">
            <FaDiagramProject className="h-8 w-8" style={{ color: "rgba(255,255,255,0.35)" }} />
            <p className="text-sm font-semibold" style={{ color: T.ink, fontFamily: CHALK_FONT }}>No visual yet</p>
            <p className="max-w-[240px] text-xs leading-5" style={{ color: T.muted, fontFamily: CHALK_FONT }}>
              Ask a question and the tutor will draw here while speaking.
            </p>
          </div>
        )}
        {/* Chalk draws DIRECTLY on the green board — no inner card, no inner
            border. The wood frame on the outer box is the only border, so the
            canvas always reads as one complete board. Hold and slide anywhere
            here to pan it like a real canvas. */}
        {(shapes.length > 0 || arrows.length > 0) && (
          <div
            className="w-full cursor-grab touch-none select-none active:cursor-grabbing"
            style={{
              backgroundImage: `radial-gradient(circle, rgba(255,255,255,0.20) 1px, transparent 1px)`,
              backgroundSize: "22px 22px",
            }}
            onPointerDown={onBoardPointerDown}
            onPointerMove={onBoardPointerMove}
            onPointerUp={onBoardPointerUp}
            onPointerCancel={onBoardPointerUp}
            title="Hold and slide to move the board"
          >
            <StepDiagram
              elements={[...shapes, ...arrows]}
              focusIds={focus?.ids}
              svgRef={svgRef}
              viewBox={vbRef.current ? `${vbRef.current.x} ${vbRef.current.y} ${vbRef.current.w} ${vbRef.current.h}` : undefined}
            />
          </div>
        )}
        {!!extras.length && (
          <div className="mt-2 flex flex-col gap-2">
            {extras.map((b) => (
              <div key={b.id} ref={setElRef(b.id)}>
                {b.type === "code" && <CodeBlock block={b} caption={caption} />}
                {b.type === "note" && <NoteBlock block={b} />}
                {b.type === "image" && <ImageBlock block={b} />}
                {b.type === "table" && <TableBlock block={b} />}
                {b.type === "quiz" && <QuizBlock block={b} />}
                {b.type === "html" && <HtmlBlock block={b} />}
              </div>
            ))}
          </div>
        )}
        <div className="h-2" />
      </div>
    </div>
  );
}
