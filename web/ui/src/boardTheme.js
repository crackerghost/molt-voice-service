/* Single source of truth for the tutor board's look.
   Natural classroom GREEN chalkboard: deep green slate, white chalk text,
   chalk-yellow accents. Change the theme HERE — never hardcode colors in
   TutorBoard.jsx. */

export const BOARD_THEME = {
  primary: "#ffd166", // chalk yellow — arrows, pen, active glow, accents
  primarySoft: "rgba(255, 255, 255, 0.08)", // shape fill tint on green
  ink: "#fdfef7", // chalk white — node strokes, body text
  inkSoft: "#d7e3d8", // soft chalk — secondary strokes
  teal: "#ffd166", // secondary accent (kept in chalk family)
  tealSoft: "rgba(255, 255, 255, 0.10)", // note background tint on green
  paper: "#1d4e38", // green board
  paperDeep: "#143626", // green board shadow edge
  line: "rgba(255, 255, 255, 0.18)", // chalk hairlines / grid dots
  muted: "#c8d8c8", // muted chalk secondary text
  faint: "rgba(255, 255, 255, 0.55)", // placeholders
  codeBg: "#10241b", // chalk-tray dark green-black for code cards
  codeInk: "#f1f5e9", // code text (chalk white)
  wood: "#8b5a2b", // wooden frame
  radius: 10, // px — soft chalk boxes
  // Semantic tones, all readable on green: white / yellow / soft red chalk.
  tones: {
    core: { fill: "rgba(255,255,255,0.08)", stroke: "#ffffff" },
    example: { fill: "rgba(255,209,102,0.14)", stroke: "#ffd166" },
    warn: { fill: "rgba(255,158,158,0.14)", stroke: "#ff9e9e" },
  },
};
