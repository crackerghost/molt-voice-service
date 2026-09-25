import { useEffect, useRef, useState } from "react";

/* Shared window frame for the AI-owned desktop.
   The frame is PRESENTATION ONLY: the learner cannot move, resize, close or
   zoom it. Geometry, tiling and z-order are driven exclusively by the tutor
   through `os_action` events (server/llm/os_control.py), which set the same
   props this component reads — `geom` (floating), `snap` (tile), `maximized`
   (fullscreen) and `parked` (desktop spread).

   Geometry changes are eased so an agent-issued move glides instead of
   jumping. `hideChrome` collapses the title bar, so a maximized window can
   give the whole screen to its content. */
export default function AppWindow({
  title, geom, maximized, cascade = 0, leaving, hideChrome,
  parked, parkIndex = 0, snap, children,
}) {
  const winRef = useRef(null);
  const GAP = 8;
  // Tile boxes: the fixed halves/quarters a `tile_app` zone maps to (same gap
  // math as the shell's tile grid) so an agent move lands where it intended.
  const TILE_BOXES = {
    left: { left: GAP, top: GAP, width: `calc(50% - ${GAP * 1.5}px)`, height: `calc(100% - ${GAP * 2}px)` },
    right: { left: `calc(50% + ${GAP / 2}px)`, top: GAP, width: `calc(50% - ${GAP * 1.5}px)`, height: `calc(100% - ${GAP * 2}px)` },
    tl: { left: GAP, top: GAP, width: `calc(50% - ${GAP * 1.5}px)`, height: `calc(50% - ${GAP * 1.5}px)` },
    tr: { left: `calc(50% + ${GAP / 2}px)`, top: GAP, width: `calc(50% - ${GAP * 1.5}px)`, height: `calc(50% - ${GAP * 1.5}px)` },
    bl: { left: GAP, top: `calc(50% + ${GAP / 2}px)`, width: `calc(50% - ${GAP * 1.5}px)`, height: `calc(50% - ${GAP * 1.5}px)` },
    br: { left: `calc(50% + ${GAP / 2}px)`, top: `calc(50% + ${GAP / 2}px)`, width: `calc(50% - ${GAP * 1.5}px)`, height: `calc(50% - ${GAP * 1.5}px)` },
  };
  // Ease animated geometry changes (fullscreen zoom, tile snaps, agent moves).
  const [gliding, setGliding] = useState(false);
  const firstMount = useRef(true);
  useEffect(() => {
    if (firstMount.current) {
      firstMount.current = false;
      return;
    }
    setGliding(true);
    const t = setTimeout(() => setGliding(false), 560);
    return () => clearTimeout(t);
  }, [maximized, parked, snap, geom]);

  // Default (agent never placed it): 70% x 70% window, centered, cascaded so
  // stacked windows keep their title bars visible.
  // Snapped (tile): fixed tile box, always above floating geom.
  // Parked (desktop spread): a title-bar strip tucked under the menu bar.
  const box = maximized || !geom
    ? maximized
      ? { left: 0, top: 0, width: "100%", height: "100%" }
      : parked
        ? { left: `${4 + parkIndex * 8}%`, top: 2, width: "30%", height: 46 }
        : snap && TILE_BOXES[snap]
          ? { ...TILE_BOXES[snap] }
          : {
            left: `calc(15% + ${cascade * 36}px)`,
            top: `calc(15% + ${cascade * 44}px)`,
            width: "70%",
            height: "70%",
          }
    : snap && TILE_BOXES[snap] && !parked
      ? { ...TILE_BOXES[snap] }
      : parked
      ? { left: `${4 + parkIndex * 8}%`, top: 2, width: "30%", height: 46 }
      : { left: geom.x, top: geom.y, width: geom.w, height: geom.h };

  return (
    <div
      ref={winRef}
      style={box}
      className={`os-window absolute flex flex-col overflow-hidden ${maximized ? "rounded-none" : "rounded-[18px]"} ${
        leaving
          ? `pointer-events-none ${leaving === "min" ? "animate-window-min" : "animate-window-out"}`
          : "pointer-events-auto animate-window-in"
      } ${gliding && !leaving ? "transition-[left,top,width,height,border-radius] duration-500 ease-out" : ""}`}
    >
      <div
        aria-hidden={hideChrome}
        className={`os-titlebar relative z-20 flex shrink-0 items-center px-4 transition-all duration-200 select-none ${hideChrome ? "h-0 overflow-hidden border-0 opacity-0" : "h-10 opacity-100"}`}
      >
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-[13px] font-bold text-slate-700">
          {title}
        </span>
      </div>
      <div className={`relative z-10 flex min-h-0 flex-col transition-all duration-300 ${parked ? "h-0 flex-none overflow-hidden opacity-0" : "flex-1 opacity-100"}`}>{children}</div>
    </div>
  );
}
