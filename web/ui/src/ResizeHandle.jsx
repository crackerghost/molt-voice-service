import { useRef } from "react";

export default function ResizeHandle({ onDragStart, onDrag, onDragEnd, className = "" }) {
  const startX = useRef(null);

  const stop = (e) => {
    if (startX.current == null) return;
    startX.current = null;
    try { e.currentTarget.releasePointerCapture?.(e.pointerId); } catch { /* noop */ }
    onDragEnd && onDragEnd();
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      className={`group relative z-20 w-2 shrink-0 cursor-col-resize touch-none ${className}`}
      onPointerDown={(e) => {
        e.preventDefault();
        startX.current = e.clientX;
        e.currentTarget.setPointerCapture?.(e.pointerId);
        onDragStart && onDragStart();
      }}
      onPointerMove={(e) => {
        if (startX.current == null) return;
        onDrag && onDrag(e.clientX - startX.current);
      }}
      onPointerUp={stop}
      onPointerCancel={stop}
    >
      <span className="pointer-events-none absolute inset-y-0 left-1/2 -ml-px w-px bg-slate-200 transition group-hover:bg-[#ff5a5f]" />
    </div>
  );
}
