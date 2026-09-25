import { FaChartColumn, FaFire } from "react-icons/fa6";

const dayKey = (d) => `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;

/* Desktop progress card: streak, totals, and a 7-day questions graph.
   Activity is recorded locally per day (no backend needed). */
export default function ProgressWidget({ days, noteCount, boardSteps }) {
  const week = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    const key = dayKey(d);
    return {
      key,
      label: d.toLocaleString([], { weekday: "narrow" }),
      full: d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }),
      count: days?.[key]?.q || 0,
      isToday: i === 6,
    };
  });
  const max = Math.max(1, ...week.map((w) => w.count));
  const total = Object.values(days || {}).reduce((s, v) => s + (v?.q || 0), 0);
  const weekTotal = week.reduce((s, w) => s + w.count, 0);

  // Streak: consecutive days (ending today/yesterday) with any questions.
  let streak = 0;
  const cursor = new Date();
  if (!(days?.[dayKey(cursor)]?.q > 0)) cursor.setDate(cursor.getDate() - 1);
  while (days?.[dayKey(cursor)]?.q > 0) {
    streak += 1;
    cursor.setDate(cursor.getDate() - 1);
  }

  const tiles = [
    { label: "Asked", value: total },
    { label: "Notes", value: noteCount || 0 },
    { label: "Board", value: boardSteps || 0 },
  ];

  return (
    <div className="pointer-events-none absolute top-12 right-4 z-0 hidden md:block" aria-hidden="true">
      <div className="w-64 rounded-3xl border border-slate-200 bg-white p-4 shadow-xl">
        <div className="flex items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-white">
            <FaChartColumn className="text-base" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-slate-900">Your Progress</p>
            <p className="text-[11px] text-slate-500">{weekTotal} questions this week</p>
          </div>
          <span
            className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold ${
              streak > 0 ? "bg-orange-50 text-orange-600" : "bg-slate-100 text-slate-400"
            }`}
          >
            <FaFire />
            {streak}
          </span>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2">
          {tiles.map((t) => (
            <div key={t.label} className="rounded-2xl bg-slate-50 px-2 py-2.5 text-center">
              <p className="text-xl font-bold text-slate-900">{t.value}</p>
              <p className="text-[10px] font-semibold tracking-wide text-slate-500 uppercase">{t.label}</p>
            </div>
          ))}
        </div>

        <div className="mt-3 rounded-2xl bg-slate-50 p-3">
          <div className="flex h-24 items-end justify-between gap-1.5">
            {week.map((w) => (
              <div key={w.key} title={`${w.full}: ${w.count}`} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
                <span className="text-[10px] font-bold text-slate-500">{w.count > 0 ? w.count : ""}</span>
                <div
                  className={`w-full rounded-md ${w.isToday ? "bg-[#ff5a5f]" : w.count > 0 ? "bg-slate-800" : "bg-slate-200"}`}
                  style={{ height: `${Math.max(6, (w.count / max) * 100)}%` }}
                />
                <span className={`text-[10px] font-bold ${w.isToday ? "text-[#ff5a5f]" : "text-slate-400"}`}>
                  {w.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
