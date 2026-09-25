/* Minimal notes: localStorage-backed, tutor-readable via os context. */

export default function NotesApp({ notes, activeId, onSelect, onChange, onAdd, onDelete }) {
  const active = notes.find((n) => n.id === activeId) || notes[0];
  return (
    <div className="flex h-full min-h-0 gap-3">
      <div className="os-glass flex w-44 shrink-0 flex-col rounded-2xl p-2">
        <button
          onClick={onAdd}
          className="mb-2 rounded-xl bg-slate-900 px-3 py-2 text-xs font-bold text-white transition hover:bg-slate-700"
        >
          + New note
        </button>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {notes.length === 0 && (
            <p className="px-2 py-4 text-xs text-slate-500">No notes yet.</p>
          )}
          {notes.map((n) => (
            <button
              key={n.id}
              onClick={() => onSelect(n.id)}
              className={`mb-1 block w-full truncate rounded-xl px-3 py-2 text-left text-xs font-medium transition ${
                n.id === active?.id ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:bg-white/60"
              }`}
            >
              {n.title || "Untitled"}
            </button>
          ))}
        </div>
      </div>
      <div className="os-glass flex min-w-0 flex-1 flex-col rounded-2xl p-3">
        {active ? (
          <>
            <input
              value={active.title}
              onChange={(e) => onChange(active.id, { title: e.target.value })}
              aria-label="Note title"
              placeholder="Title…"
              className="mb-2 rounded-xl bg-white/60 px-3 py-2 text-sm font-bold text-slate-900 outline-none"
            />
            <textarea
              value={active.body}
              onChange={(e) => onChange(active.id, { body: e.target.value })}
              aria-label="Note body"
              placeholder="Write here… the tutor can read this when you ask."
              className="min-h-0 flex-1 resize-none rounded-xl bg-white/60 p-3 text-sm leading-6 text-slate-800 outline-none"
            />
            <button
              onClick={() => onDelete(active.id)}
              className="mt-2 self-end rounded-xl px-3 py-1.5 text-xs font-semibold text-rose-600 transition hover:bg-rose-50"
            >
              Delete note
            </button>
          </>
        ) : (
          <p className="p-4 text-sm text-slate-500">Create a note to start writing.</p>
        )}
      </div>
    </div>
  );
}
