import { useEffect, useRef } from "react";
import { engine } from "./audioEngine.js";

/* Soft-smoothing helper: eases a value toward its target each frame. */
const ease = (cur, target, k) => cur + (target - cur) * k;

export default function AuraGlobe({ listening, speaking, userTalking }) {
  const canvasRef = useRef(null);
  const modeRef = useRef({ listening, speaking, userTalking });
  modeRef.current = { listening, speaking, userTalking };

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx2d = canvas.getContext("2d");
    let raf = 0;
    let W = 0;
    let H = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    const size = () => {
      const r = canvas.getBoundingClientRect();
      W = r.width;
      H = r.height;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx2d.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    size();
    const ro = new ResizeObserver(size);
    ro.observe(canvas);

    // smoothed visual state
    const st = {
      amp: 0.06, // 0..1 blob inflation
      pitch: 0, // Hz smoothed
      wobble: Math.random() * 100,
      t: 0,
      sparks: Array.from({ length: 14 }, () => ({
        a: Math.random() * Math.PI * 2,
        r: 0.9 + Math.random() * 0.5,
        s: 0.2 + Math.random() * 0.5,
      })),
    };

    const draw = () => {
      const { listening, speaking, userTalking } = modeRef.current;
      const mic = engine.readMic();
      const spk = engine.readSpeak();

      let amp = 0.05; // idle breathing
      if (speaking) amp = Math.max(amp, Math.min(1, spk.rms * 9));
      if (listening && userTalking) amp = Math.max(amp, Math.min(1, mic.rms * 11));
      else if (listening) amp = Math.max(amp, Math.min(0.25, mic.rms * 9 + 0.08));
      st.amp = ease(st.amp, amp, 0.18);

      let pitch = 0;
      if (listening && mic.rms > 0.004) pitch = mic.pitch;
      if (speaking) pitch = pitch || spk.pitch;
      st.pitch = ease(st.pitch, pitch, 0.12);

      st.t += 0.016;
      st.wobble += 0.02 + st.amp * 0.1;

      const cx = W / 2;
      const cy = H / 2;
      ctx2d.clearRect(0, 0, W, H);

      // --- layered aura ------------------------------------------------
      const baseR = Math.min(W, H) * 0.19;
      const lobes = speaking || (listening && userTalking)
        ? Math.max(8, Math.min(16, Math.round(st.pitch / 42) + 8))
        : 10;
      const phase = speaking ? 5 : listening ? 9 : 4; // agitation speed

      const main = ctx2d.createRadialGradient(cx, cy, baseR * 0.2, cx, cy, baseR * 2.1);
      if (speaking) {
        main.addColorStop(0, "rgba(45,212,191,0.9)");
        main.addColorStop(0.45, "rgba(13,148,136,0.55)");
        main.addColorStop(1, "rgba(18,48,74,0)");
      } else if (listening) {
        main.addColorStop(0, "rgba(94,234,212,0.85)");
        main.addColorStop(0.5, "rgba(45,212,191,0.5)");
        main.addColorStop(1, "rgba(14,116,144,0)");
      } else {
        main.addColorStop(0, "rgba(71,103,117,0.35)");
        main.addColorStop(0.6, "rgba(71,103,117,0.12)");
        main.addColorStop(1, "rgba(71,103,117,0)");
      }

      ctx2d.save();
      ctx2d.translate(cx, cy);
      ctx2d.globalCompositeOperation = "screen";

      const path = (spread, k, inner) => {
        ctx2d.beginPath();
        for (let i = 0; i <= lobes; i++) {
          const ang = (i / lobes) * Math.PI * 2;
          const n =
            Math.sin(lobes * ang * 0.5 + st.t * phase + st.wobble) * 0.5 +
            Math.sin(lobes * ang + st.t * (phase * 0.7)) * 0.5;
          const rr = inner + spread * (1 + k * n + st.amp * 0.35);
          const x = Math.cos(ang) * rr;
          const y = Math.sin(ang) * rr;
          if (i === 0) ctx2d.moveTo(x, y);
          else ctx2d.lineTo(x, y);
        }
        ctx2d.closePath();
      };

      // outer wisp
      ctx2d.shadowBlur = 90;
      ctx2d.shadowColor = speaking ? "rgba(13,148,136,0.8)" : "rgba(45,212,191,0.5)";
      ctx2d.fillStyle = main;
      path(baseR * 1.35, 0.16 * (0.6 + st.amp), baseR * 0.4);
      ctx2d.fill();

      // middle band
      path(baseR * 0.95, 0.1, baseR * 0.15);
      ctx2d.fillStyle = speaking ? "rgba(204,251,241,0.5)" : "rgba(207,250,254,0.45)";
      ctx2d.fill();

      // bright core
      const core = ctx2d.createRadialGradient(0, 0, 0, 0, 0, baseR * 0.85);
      core.addColorStop(0, "rgba(255,255,255,0.95)");
      core.addColorStop(0.55, "rgba(255,255,255,0.55)");
      core.addColorStop(1, "rgba(255,255,255,0)");
      path(baseR * 0.55, 0.06 * (1 + st.amp), baseR * 0.05);
      ctx2d.shadowBlur = 40;
      ctx2d.fillStyle = core;
      ctx2d.fill();
      ctx2d.restore();

      // --- orbiting sparks ---------------------------------------------
      ctx2d.save();
      ctx2d.translate(cx, cy);
      ctx2d.globalCompositeOperation = "screen";
      const orbR = baseR * (1.72 + st.amp * 0.8);
      for (const s of st.sparks) {
        s.a += 0.003 + s.s * 0.006 * (0.4 + st.amp);
        const px = Math.cos(s.a) * orbR;
        const py = Math.sin(s.a * 1.3) * orbR * 0.7;
        ctx2d.beginPath();
        ctx2d.arc(px, py, 1.2 + st.amp * 2.4, 0, Math.PI * 2);
        ctx2d.fillStyle = speaking ? "rgba(153,246,228,0.8)" : "rgba(94,234,212,0.7)";
        ctx2d.fill();
      }
      ctx2d.restore();

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} className="h-full w-full" aria-hidden="true" />;
}
