/* Filler maskers: short cloned-voice "theek hai, ruko" clips played when the
   first real TTS frame hasn't arrived within ~400ms, so replies feel instant.

   - Clips are pre-generated in the cloned voice (scripts/generate_fillers.py
     -> assets/fillers/*.wav -> GET /api/fillers) and prefetched at boot, so
     playback starts with ZERO network latency.
   - Shuffle-bag random: every clip plays once before any repeats, and the
     same clip never plays twice in a row — feels live, not looped.
*/

const LIST_URL = `${location.protocol}//${location.host}/api/fillers`;

let buffers = []; // AudioBuffer[] decoded and ready to play
let bag = []; // shuffle-bag of indices
let lastIdx = -1;
let thresholdMs = 500;
let enabled = true;
let ready = false;

async function decode(ctx, url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`filler fetch ${r.status}`);
  const ab = await r.arrayBuffer();
  // decodeAudioData detaches the buffer; copy first (same pattern as drain prefetch)
  return await ctx.decodeAudioData(ab.slice(0));
}

export async function prefetchFillers(getCtx) {
  try {
    const r = await fetch(LIST_URL);
    if (!r.ok) return;
    const data = await r.json();
    enabled = data.enabled !== false;
    thresholdMs = Number(data.threshold_ms) || 500;
    const clips = Array.isArray(data.clips) ? data.clips : [];
    if (!enabled || !clips.length) return;
    const ctx = getCtx();
    const decoded = [];
    for (const c of clips.slice(0, 12)) {
      try {
        decoded.push(await decode(ctx, c.url));
      } catch { /* one bad clip never blocks the rest */ }
    }
    if (decoded.length) {
      buffers = decoded;
      bag = [];
      lastIdx = -1;
      ready = true;
      console.info(`[filler] ready: ${buffers.length} clip(s), threshold ${thresholdMs}ms`);
    }
  } catch { /* fillers are best-effort — silence is better than an error */ }
}

export function fillerThreshold() {
  return thresholdMs;
}

export function fillerReady() {
  return ready && enabled && buffers.length > 0;
}

/* Shuffle-bag pick: no repeat until every clip has played, never same twice. */
export function pickFillerBuffer() {
  if (!fillerReady()) return null;
  if (buffers.length === 1) return buffers[0];
  if (!bag.length) {
    bag = buffers.map((_, i) => i);
    // Fisher-Yates shuffle
    for (let i = bag.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [bag[i], bag[j]] = [bag[j], bag[i]];
    }
    // boundary: first of new bag must differ from last played
    if (bag[bag.length - 1] === lastIdx && bag.length > 1) {
      [bag[0], bag[bag.length - 1]] = [bag[bag.length - 1], bag[0]];
    }
  }
  lastIdx = bag.pop();
  return buffers[lastIdx];
}
