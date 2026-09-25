import { FaCalendarDays } from "react-icons/fa6";

/* Desktop calendar: big month grid, solid white, today highlighted. */
export default function Widgets({ dateObj }) {
  const d = dateObj || new Date();
  const year = d.getFullYear();
  const month = d.getMonth();
  const today = d.getDate();
  const monthName = d.toLocaleString([], { month: "long" });
  const weekday = d.toLocaleString([], { weekday: "long" });

  const firstDow = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = [
    ...Array(firstDow).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div className="pointer-events-none absolute top-12 left-4 z-0 hidden md:block" aria-hidden="true">
      <div className="w-60 overflow-hidden rounded-3xl bg-white shadow-xl">
        <div className="flex items-center gap-2 bg-[#ff5a5f] px-4 py-3 text-white">
          <FaCalendarDays className="text-xl" />
          <div>
            <p className="text-sm font-bold tracking-wide uppercase">{monthName}</p>
            <p className="text-[11px] opacity-90">
              {weekday} · {year}
            </p>
          </div>
          <span className="ml-auto text-3xl font-bold">{today}</span>
        </div>
        <div className="p-3">
          <div className="grid grid-cols-7 gap-1 text-center text-[10px] font-bold text-slate-400">
            {["S", "M", "T", "W", "T", "F", "S"].map((w, i) => (
              <span key={i}>{w}</span>
            ))}
          </div>
          <div className="mt-1 grid grid-cols-7 gap-1 text-center text-xs">
            {cells.map((n, i) =>
              n == null ? (
                <span key={i} />
              ) : n === today ? (
                <span
                  key={i}
                  className="mx-auto flex h-7 w-7 items-center justify-center rounded-full bg-[#ff5a5f] font-bold text-white shadow-md"
                >
                  {n}
                </span>
              ) : (
                <span key={i} className="mx-auto flex h-7 w-7 items-center justify-center text-slate-600">
                  {n}
                </span>
              ),
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
