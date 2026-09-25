/* Minimal WebAudio hub: one AudioContext, analysers for the TTS output and for
   the microphone, plus RMS + pitch(ish) readers that drive the AuraGlobe and
   the voice-activity (barge-in) detector. */

let ctx = null;
let speakAnalyser = null;
let micAnalyser = null;
let micStream = null;
let micSrc = null;
let tap = null;
let speakConnected = false;

function ensureNodes() {
  if (!speakAnalyser) speakAnalyser = ctx.createAnalyser();
  speakAnalyser.fftSize = 2048;
  speakAnalyser.smoothingTimeConstant = 0.55;
  if (!micAnalyser) micAnalyser = ctx.createAnalyser();
  micAnalyser.fftSize = 2048;
  micAnalyser.smoothingTimeConstant = 0.4;
}

function read(analyser) {
  if (!analyser) return { rms: 0, pitch: 0 };
  const buf = new Float32Array(analyser.fftSize);
  analyser.getFloatTimeDomainData(buf);
  let sum = 0;
  let crossings = 0;
  let prev = buf[0];
  for (let i = 1; i < buf.length; i++) {
    const s = buf[i];
    sum += s * s;
    if ((prev < 0 && s >= 0) || (prev >= 0 && s < 0)) crossings++;
    prev = s;
  }
  const rms = Math.sqrt(sum / buf.length);
  const zcr = crossings / buf.length;
  let pitch = 0;
  if (rms > 0.004) {
    // zero-crossing rate -> rough fundamental (Hz), clamped to a voice range
    pitch = (zcr * ctx.sampleRate) / 2;
    if (pitch < 70 || pitch > 480) pitch = 0;
  }
  return { rms, pitch };
}

export const engine = {
  get ctx() {
    return ctx;
  },
  unlock() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      ensureNodes();
    }
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  },
  /* Route a TTS buffer source through the "speaking" analyser to the speakers. */
  connectSpeak(source) {
    if (!speakAnalyser) return;
    source.connect(speakAnalyser);
    if (!speakConnected) {
      speakAnalyser.connect(ctx.destination);
      speakConnected = true;
    }
  },
  readSpeak() {
    return read(speakAnalyser);
  },
  async startMic() {
    try {
      this.unlock();
      if (micStream) return true;
      micStream = await navigator.mediaDevices.getUserMedia({
        // echoCancellation makes Chrome subtract our own speaker output from
        // this stream — the AEC-cleaned audio is what gets transcribed, so the
        // assistant can never "hear" itself. (OpenAI/Gemini realtime use this
        // same getUserMedia + AEC path; the Web Speech API does NOT, which is
        // why it echoed.)
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      micSrc = ctx.createMediaStreamSource(micStream);
      micSrc.connect(micAnalyser); // not connected to destination (no self-monitor)
      return true;
    } catch {
      return false;
    }
  },
  stopMic() {
    if (micStream) {
      micStream.getTracks().forEach((t) => t.stop());
      micStream = null;
    }
    if (micSrc) {
      try { micSrc.disconnect(); } catch { /* noop */ } // detach node too — mic re-enable rebuilds it
    }
    micSrc = null;
  },
  /* Tap the AEC-cleaned mic stream as 16 kHz mono frames for streaming ASR.

     Fail LOUDLY rather than silently returning false: the UI needs to know
     when the PCM tap can't be created so it can show a real "voice engine"
     error instead of the user just wondering why their voice isn't heard.

     Worklet module loads can fail transiently (AudioContext not yet ready,
     CSP/COOP edge cases, serving the file from a slow static handler), so we
     retry a few times with short backoff before falling back to the inline
     Blob URL, and we never swallow the final error. */
  async startTap(onFrame) {
    if (!micSrc) return { ok: false, error: "mic not started" };
    if (tap) return { ok: true };

    // Inline worklet source kept as the last-resort fallback. Chrome can
    // refuse Blob URLs under some CSPs, so we try the real file first and
    // only use the Blob when the file is genuinely unavailable.
    const src =
      "class PcmTap extends AudioWorkletProcessor{\n" +
      "constructor(opts){super();const outRate=(opts&&opts.processorOptions&&opts.processorOptions.outRate)||16000;this.step=outRate/sampleRate;this.phase=0;this.acc=0;this.accN=0;}\n" +
      "process(inputs){const ch=inputs[0]&&inputs[0][0];if(!ch||ch.length===0)return true;const out=[];for(let i=0;i<ch.length;i++){this.acc+=ch[i];this.accN+=1;this.phase+=this.step;if(this.phase>=1){this.phase-=1;out.push(this.acc/Math.max(1,this.accN));this.acc=0;this.accN=0;}}if(out.length)this.port.postMessage(new Float32Array(out));return true;}\n" +
      "}\nregisterProcessor(\"pcm-tap\",PcmTap);";

    const fileUrl = `${location.origin}/pcm-tap.js`;
    const tries = 4;
    let last = null;
    for (let i = 0; i < tries; i++) {
      try {
        await ctx.audioWorklet.addModule(fileUrl);
        break;
      } catch (e) {
        last = e;
        if (i < tries - 1) await new Promise((r) => setTimeout(r, 120 * (i + 1)));
      }
    }

    // If the real file never loaded, try the inline Blob as a final attempt.
    if (last) {
      try {
        const blobUrl = URL.createObjectURL(
          new Blob([src], { type: "application/javascript" }),
        );
        try {
          await ctx.audioWorklet.addModule(blobUrl);
          last = null; // success
        } finally {
          setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
        }
      } catch (e) {
        last = e;
      }
    }

    if (last) {
      return { ok: false, error: last instanceof Error ? last.message : String(last) };
    }

    try {
      tap = new AudioWorkletNode(ctx, "pcm-tap", {
        processorOptions: { outRate: 16000 },
      });
      tap.port.onmessage = (e) => onFrame(e.data);
      micSrc.connect(tap);
      return { ok: true };
    } catch (e) {
      stopTap();
      return {
        ok: false,
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },
  stopTap() {
    if (!tap) return;
    try { tap.disconnect(); } catch { /* noop */ }
    tap.port.onmessage = null;
    tap = null;
  },
  readMic() {
    return read(micAnalyser);
  },
  get micRunning() {
    return !!micStream;
  },
};
