/* PCM tap AudioWorklet for /ws/asr streaming transcription.

   Loaded with ctx.audioWorklet.addModule("/pcm-tap.js") from the main thread.
   Downsamples the AEC-cleaned microphone input to 16 kHz and posts float32
   frames back to the main thread, which forwards them to the ASR WebSocket.

   A real same-origin file (not a Blob URL) is used because Chrome can refuse
   Blob modules under some CSP setups — that silently killed STT. */
class PcmTap extends AudioWorkletProcessor {
  constructor(opts) {
    super();
    const outRate = (opts && opts.processorOptions && opts.processorOptions.outRate) || 16000;
    this.step = outRate / sampleRate; // e.g. 16000/48000 -> keep ~1 in 3 samples
    this.phase = 0;
    this.acc = 0;   // sum of samples in the current output window
    this.accN = 0;  // count of samples in the current output window
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch || ch.length === 0) return true;
    const out = [];
    for (let i = 0; i < ch.length; i++) {
      // AVERAGE every sample that lands in this output window (box low-pass)
      // instead of dropping 2 of 3 samples — plain decimation ALIASES
      // high-frequency consonant energy (sibilants, retroflex stops) down
      // into the voice band and measurably hurts Whisper accuracy.
      this.acc += ch[i];
      this.accN += 1;
      this.phase += this.step;
      if (this.phase >= 1) {
        this.phase -= 1;
        out.push(this.acc / Math.max(1, this.accN));
        this.acc = 0;
        this.accN = 0;
      }
    }
    if (out.length) this.port.postMessage(new Float32Array(out));
    return true;
  }
}
registerProcessor("pcm-tap", PcmTap);
