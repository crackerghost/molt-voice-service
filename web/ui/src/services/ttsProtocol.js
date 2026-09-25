export const PROTOCOL_VERSION = 1;

export function pingMessage() {
  return JSON.stringify({ protocol_version: PROTOCOL_VERSION, type: "ping" });
}

export function stopMessage() {
  return JSON.stringify({ protocol_version: PROTOCOL_VERSION, type: "stop" });
}

export function chatMessage({ text, history, nfeStep, speed, temperature, clientTurnId, screen, os, provider }) {
  const message = {
    protocol_version: PROTOCOL_VERSION,
    type: "chat",
    text,
    history,
    nfe_step: nfeStep,
    client_turn_id: String(clientTurnId),
  };
  if (speed !== undefined) message.speed = speed;
  if (temperature !== undefined) message.temperature = temperature;
  if (screen) message.screen = screen;
  // LLM provider per turn: "groq" | "deepseek" (server falls back to default).
  if (provider) message.provider = provider;
  // OS context for the tutor agent (active app, browser URL, note snippet).
  // The voice server ignores unknown keys today; the agent reads it when wired.
  if (os) message.os = os;
  return JSON.stringify(message);
}
