import test from "node:test";
import assert from "node:assert/strict";

class FakeNode {
  constructor() { this.connections = []; }
  connect(node) { this.connections.push(node); }
}

class FakeAudioContext {
  constructor() {
    this.currentTime = 1;
    this.sampleRate = 48000;
    this.state = "running";
  }
  createAnalyser() { return Object.assign(new FakeNode(), { fftSize: 0, smoothingTimeConstant: 0 }); }
  createGain() {
    const gain = { value: 1, setTargetAtTime(value) { this.value = value; }, cancelScheduledValues() {} };
    return Object.assign(new FakeNode(), { gain });
  }
  createMediaStreamDestination() {
    return Object.assign(new FakeNode(), { stream: { getAudioTracks: () => [{ id: "molt-audio" }] } });
  }
  resume() { return Promise.resolve(); }
}

test("Molt mute gates local and published TTS output and can be toggled back", async () => {
  globalThis.window = { AudioContext: FakeAudioContext };
  const { engine } = await import("../web/ui/src/audioEngine.js");

  engine.setSpeakMuted(true);
  const context = engine.unlock();
  const source = new FakeNode();
  engine.connectSpeak(source);
  const gain = source.connections[0];

  assert.equal(gain.gain.value, 0);
  assert.equal(gain.connections.length, 1, "muted audio remains connected through the gain node");
  assert.ok(engine.getSpeakTrack());

  engine.setSpeakMuted(false);
  assert.equal(gain.gain.value, 1);
  assert.equal(context.state, "running");
});
