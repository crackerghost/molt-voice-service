import { useEffect, useRef } from "react";
import { engine } from "./audioEngine.js";

/* Bottom 50% background glow. The layer reads live mic/speaker pitch + RMS and
   dances with voice, brightening while the user or tutor is speaking. */

/* Motion design: glacial and smooth. Raw pitch/RMS arrive at 60fps and
   would make the glow jitter — so every signal passes through a heavy
   low-pass (~2s time constant) before touching the DOM. Nothing on screen
   ever jumps; it all drifts. */

// Per-frame smoothing factors (60fps): 0.008 ≈ 2s to converge — roughly
// two orders of magnitude calmer than following the raw signal.
const SMOOTH_PITCH = 0.008;
const SMOOTH_LEVEL = 0.03;
const SMOOTH_HEIGHT = 0.012;

export default function VoiceGradient({ listening, speaking, userTalking }) {
  const layerRef = useRef(null);
  const gradientRef = useRef(null);
  const heightRef = useRef(50);
  const pitchRef = useRef(0);
  const levelRef = useRef(0.04);

  useEffect(() => {
    let raf = 0;

    const draw = () => {
      const layer = layerRef.current;
      const gradient = gradientRef.current;
      if (layer && gradient) {
        const mic = engine.readMic();
        const spk = engine.readSpeak();
        const active = speaking || (listening && userTalking);
        const rawLevel = Math.min(
          1,
          Math.max(
            speaking ? spk.rms * 9 : 0,
            listening && userTalking ? mic.rms * 11 : 0,
            listening ? mic.rms * 6 + 0.05 : 0.04,
          ),
        );
        const rawPitch = speaking ? spk.pitch : mic.pitch || 0;
        // Heavy low-pass: pitch glides instead of jumping.
        pitchRef.current += (rawPitch - pitchRef.current) * SMOOTH_PITCH;
        levelRef.current += (rawLevel - levelRef.current) * SMOOTH_LEVEL;
        const level = levelRef.current;
        const pitch = pitchRef.current;
        const t = performance.now() / 1000;

        // Slow breathing waves (periods of ~30-40s): calm at 50% when idle.
        const slowWave = Math.sin(t * 0.18);
        const targetHeight = active ? 50 + slowWave * 10 * (0.45 + level) : 50;
        heightRef.current += (targetHeight - heightRef.current) * SMOOTH_HEIGHT;
        layer.style.height = `${heightRef.current}%`;

        const driftX = (pitch > 0 ? (pitch / 480) * 22 : 0) + Math.sin(t * 0.18) * 6 * (0.4 + level);
        const driftY = Math.cos(t * 0.15) * 4 * (0.4 + level);
        const breatheX = 0.88 + level * 0.22;
        const breatheY = 0.78 + level * 0.42;
        const glowScale = 0.96 + level * 0.12;

        layer.style.opacity = active ? String(Math.min(1, 0.55 + level * 0.45)) : "0.45";
        layer.style.transform = `translate(${driftX}px, ${driftY}px) scale(${glowScale})`;
        gradient.style.transform = `scaleX(${breatheX}) scaleY(${breatheY}) rotate(${(pitch / 480) * 3}deg)`;
      }
      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [listening, speaking, userTalking]);

  return (
    <div
      ref={layerRef}
      className="voice-gradient-layer absolute inset-x-0 bottom-0 h-1/2"
      aria-hidden="true"
    >
      <div ref={gradientRef} className="gemini-gradient" />
    </div>
  );
}
