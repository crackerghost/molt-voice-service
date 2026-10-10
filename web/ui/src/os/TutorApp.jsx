import { useEffect, useMemo, useRef, useState } from "react";
import {
  FaBookOpen, FaCheck, FaCirclePlay,
  FaClock, FaGraduationCap, FaMagnifyingGlass, FaArrowRight, FaArrowLeft, FaCircleCheck,
} from "react-icons/fa6";
import { getProgressPercent } from "../data/courseData.js";

/* Tutor — Learnify-pattern course home in a black frame.
 * Dashboard: cream canvas, search + pills, pastel course cards with
 * progress + red Continue, numbered "My next lessons", red promo card.
 * Detail: lesson overview (objective, key terms, board plan, quiz) with
 * sticky start action + prev/next + mark complete.
 * Same props/API as before so App.jsx wiring is untouched. */

const KIND_STYLE = {
  coding: "bg-violet-100 text-violet-800",
  project: "bg-amber-100 text-amber-800",
  theory: "bg-sky-100 text-sky-800",
  video: "bg-rose-100 text-rose-800",
  quiz: "bg-emerald-100 text-emerald-800",
};
const KIND_LABEL = { theory: "Theory", coding: "Hands-on", video: "Video", quiz: "Quiz", project: "Project" };

const NAVY = "#1b2547";
const RED = "#ff5a5f";
const RED_DEEP = "#c81e3a";
const CREAM = "#f6f1e7";
const PASTELS = ["#fdf3d7", "#ffe7d3", "#e2ebfd", "#e2f3e7", "#ece4fa"];
const FACE_BG = ["#1b2547", "#ff5a5f", "#2e9e6b", "#7c5cbf", "#c2410c"];

function initials(title = "") {
  return title.split(/[\s—–-]+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
}

function flatLessons(course) {
  const out = [];
  for (const m of course?.modules || []) for (const l of m.lessons || []) out.push({ courseId: course.id, moduleId: m.id, moduleTitle: m.title, ...l });
  return out;
}

function faces(names) {
  return (
    <span className="flex items-center">
      {(names || []).slice(0, 4).map((n, i) => (
        <span
          key={i}
          className="flex h-6 w-6 items-center justify-center rounded-full text-[9px] font-black text-white ring-2"
          style={{ background: FACE_BG[i % FACE_BG.length], marginLeft: i ? -8 : 0, ["--tw-ring-color"]: "rgba(255,255,255,0.9)" }}
          aria-hidden="true"
        >
          {initials(n)}
        </span>
      ))}
    </span>
  );
}

export default function TutorApp({
  courses = [],
  progress,
  activeCourseId,
  activeLessonId,
  selected,
  onSelect,
  onCompleteLesson,
}) {
  const [q, setQ] = useState("");
  const [pill, setPill] = useState("all"); // module filter for next lessons
  const [home, setHome] = useState(true); // dashboard vs lesson detail
  const selRef = useRef(null); // selected lesson row — scrolled into view
  useEffect(() => {
    try {
      selRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch { /* noop */ }
  }, [selected?.lessonId, pill, home]);

  const needle = q.trim().toLowerCase();
  const filtered = useMemo(() => {
    if (!needle) return courses;
    const words = needle.split(/\s+/);
    return (courses || [])
      .map((c) => ({
        ...c,
        modules: (c.modules || [])
          .map((m) => ({
            ...m,
            lessons: (m.lessons || []).filter((l) => {
              const hay = [c.title, m.title, l.title, (l.keyTerms || []).join(" ")].join(" ").toLowerCase();
              return words.every((w) => hay.includes(w));
            }),
          }))
          .filter((m) => m.lessons.length || m.title.toLowerCase().includes(needle)),
      }))
      .filter((c) => c.modules.length || c.title.toLowerCase().includes(needle));
  }, [courses, needle]);

  const selCourse = (courses || []).find((c) => c.id === selected?.courseId) || (courses || [])[0] || null;
  const selModule = selCourse?.modules?.find((m) => m.id === selected?.moduleId) || selCourse?.modules?.[0] || null;
  const selLesson = selModule?.lessons?.find((l) => l.id === selected?.lessonId) || selModule?.lessons?.[0] || null;

  const all = useMemo(() => (selCourse ? flatLessons(selCourse) : []), [selCourse]);
  const idx = all.findIndex((l) => (l.lessonId === undefined ? false : l.id === selLesson?.id));
  const prev = idx > 0 ? all[idx - 1] : null;
  const next = idx >= 0 && idx < all.length - 1 ? all[idx + 1] : null;
  const totalMins = all.reduce((s, l) => s + (l.durationMin || 0), 0);
  const pct = selCourse ? getProgressPercent(selCourse, progress) : 0;
  const doneIds = new Set(progress?.completedLessonIds || []);
  const statusOf = (id) => (id === activeLessonId ? "current" : doneIds.has(id) ? "done" : "todo");

  // ---- dashboard data ----
  const pillCourse = (courses || []).find((c) => flatLessons(c).some((l) => l.id === activeLessonId)) || (courses || [])[0] || null;
  const pillLessons = useMemo(() => {
    if (!pillCourse) return [];
    const list = flatLessons(pillCourse);
    return pill === "all" ? list : list.filter((l) => l.moduleId === pill);
  }, [pillCourse, pill]);
  const nextLessons = pillLessons; // full module list — inner scroll shows all
  const searchHits = useMemo(() => {
    if (!needle) return [];
    const out = [];
    for (const c of filtered) for (const m of c.modules || []) for (const l of m.lessons || []) {
      out.push({ courseId: c.id, moduleId: m.id, moduleTitle: m.title, ...l });
      if (out.length >= 12) return out;
    }
    return out;
  }, [filtered, needle]);
  const activeAcross = useMemo(() => {
    for (const c of courses || []) {
      const hit = flatLessons(c).find((l) => l.id === activeLessonId);
      if (hit) return { course: c, lesson: hit };
    }
    return { course: (courses || [])[0] || null, lesson: null };
  }, [courses, activeLessonId]);

  const goDetail = (courseId, moduleId, lessonId) => {
    onSelect && onSelect(courseId, moduleId, lessonId);
    setHome(false);
  };
  // No "start" control here: the learner starts a lesson by ASKING for it.
  // The tutor then opens the board/code/browser itself (server-side OS
  // Director). Browsing this catalog just picks the lesson to preview.
  const openCourse = (course) => {
    const list = flatLessons(course);
    const target = list.find((l) => l.id === activeLessonId) || list.find((l) => !doneIds.has(l.id)) || list[0];
    if (target) goDetail(course.id, target.moduleId, target.id);
  };

  return (
    <div className="h-full min-h-0 overflow-y-auto" style={{ background: CREAM }}>
      {home ? (
        <div className="px-5 py-4 sm:px-8">
          {/* header */}
          <div className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-[11px] font-semibold text-slate-500">Welcome back,</p>
              <h1 className="text-xl font-black tracking-tight" style={{ color: NAVY }}>My courses</h1>
            </div>
            <div className="flex w-44 items-center gap-2 rounded-full bg-white px-3 py-1.5 shadow-sm ring-1 ring-black/10 sm:w-56">
              <FaMagnifyingGlass className="h-3.5 w-3.5 shrink-0 text-slate-400" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                aria-label="Search courses and topics"
                placeholder="Search"
                className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-slate-400"
              />
            </div>
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white" style={{ background: NAVY }} title="Learner">
              <FaGraduationCap className="h-4 w-4" />
            </span>
          </div>

          {/* pills */}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {[{ id: "all", title: "All lessons" }, ...((pillCourse?.modules || []).map((m) => ({ id: m.id, title: m.title })))].map((p) => {
              const on = pill === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => setPill(p.id)}
                  className={`rounded-full px-3 py-1.5 text-xs font-bold transition ${on ? "text-white shadow-sm" : "bg-white text-slate-600 ring-1 ring-black/10 hover:ring-black/25"}`}
                  style={on ? { background: RED } : undefined}
                >
                  {p.title}
                </button>
              );
            })}
          </div>

          {/* course cards */}
          <div className={`mt-3 grid grid-cols-1 gap-4 ${courses.length > 1 ? "sm:grid-cols-2 xl:grid-cols-3" : ""}`}>
            {(courses || []).map((c, ci) => {
              const list = flatLessons(c);
              const done = list.filter((l) => doneIds.has(l.id)).length;
              const cpct = getProgressPercent(c, progress);
              return (
                <div key={c.id} className="flex flex-col rounded-2xl border border-black/15 p-4 shadow-[0_2px_10px_rgba(27,37,71,0.06)]" style={{ background: PASTELS[ci % PASTELS.length] }}>
                  <span className="inline-flex w-fit rounded-full bg-white/70 px-2.5 py-1 text-[10px] font-black tracking-wide uppercase ring-1 ring-black/10" style={{ color: NAVY }}>
                    {c.level || "Course"}
                  </span>
                  <p className="mt-2 min-h-10 text-[15px] leading-5 font-black tracking-tight" style={{ color: NAVY }}>{c.title}</p>
                  <div className="mt-2 flex items-center gap-2">
                    {faces(list.slice(0, 4).map((l) => l.title))}
                    <span className="ml-auto text-[11px] font-bold text-slate-500 tabular-nums">{done}/{list.length} lessons</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/10 ring-1 ring-black/10">
                    <div className="h-full rounded-full bg-gradient-to-r from-[#ff5a5f] to-[#c81e3a]" style={{ width: `${cpct}%` }} />
                  </div>
                  <div className="mt-3 flex items-center">
                    <span className="text-[11px] font-bold text-slate-500 tabular-nums">{cpct}% done</span>
                    <button
                      onClick={() => openCourse(c)}
                      className="ml-auto rounded-full px-5 py-1.5 text-xs font-bold text-white shadow-[0_6px_16px_rgba(255,90,95,0.4)] transition hover:brightness-110 active:scale-[0.98]"
                      style={{ background: RED }}
                    >
                      {cpct > 0 ? "Continue" : "Start"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* next lessons + promo */}
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-5">
            <div className="rounded-2xl border border-black/15 bg-white p-4 shadow-[0_2px_10px_rgba(27,37,71,0.06)] xl:col-span-3">
              <div className="flex items-baseline">
                <h2 className="text-[15px] font-black tracking-tight" style={{ color: NAVY }}>
                  {needle ? `Results (${searchHits.length})` : "My next lessons"}
                </h2>
                {!needle && <span className="ml-auto text-[11px] font-semibold text-slate-400">tap a lesson to open it</span>}
              </div>
              <ul className="mt-2 max-h-[380px] divide-y divide-slate-100 overflow-y-auto pr-1">
                {(needle ? searchHits : nextLessons).map((l, i) => {
                  const st = statusOf(l.id);
                  const n = String(needle ? i + 1 : pillLessons.findIndex((x) => x.id === l.id) + 1).padStart(2, "0");
                  const isSel = selected?.lessonId === l.id && selected?.courseId === l.courseId;
                  return (
                    <li key={l.id} ref={isSel ? selRef : null}>
                      <button onClick={() => goDetail(l.courseId, l.moduleId, l.id)} className={`flex w-full items-center gap-3 px-2 py-2 text-left transition hover:bg-slate-50 ${isSel ? "rounded-lg bg-red-50 ring-1 ring-[#ff5a5f]/30" : ""}`}>
                        <span className="text-xs font-black text-slate-300 tabular-nums">{n}</span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-bold text-slate-800">{l.title}</span>
                          <span className="block truncate text-[11px] text-slate-400">{l.moduleTitle}</span>
                        </span>
                        {st === "done"
                          ? <FaCircleCheck className="h-4 w-4 shrink-0 text-emerald-500" />
                          : st === "current"
                            ? <FaCirclePlay className="h-4 w-4 shrink-0" style={{ color: RED }} />
                            : null}
                        <span className="flex shrink-0 items-center gap-1 text-[11px] font-semibold text-slate-400 tabular-nums">
                          <FaClock className="h-3 w-3" /> {l.durationMin}m
                        </span>
                      </button>
                    </li>
                  );
                })}
                {(needle ? searchHits : nextLessons).length === 0 && (
                  <li className="py-4 text-center text-xs text-slate-400">
                    {needle ? "No matches — try “react”, “flexbox”, or “mongo”." : "No lessons in this view."}
                  </li>
                )}
              </ul>
            </div>
            <div className="flex flex-col rounded-2xl border border-black/30 p-5 text-white shadow-[0_8px_24px_rgba(255,90,95,0.35)] xl:col-span-2" style={{ background: `linear-gradient(135deg, ${RED} 0%, ${RED_DEEP} 100%)` }}>
              <p className="text-[11px] font-bold tracking-wide text-white/70 uppercase">Pick up where you left off</p>
              <p className="mt-1.5 text-[15px] leading-6 font-black">
                {activeAcross.lesson ? activeAcross.lesson.title : "Start your first lesson"}
              </p>
              <p className="mt-1 text-[11px] font-semibold text-white/70">
                {activeAcross.course ? `${getProgressPercent(activeAcross.course, progress)}% of ${activeAcross.course.title}` : ""}
              </p>
              <div className="mt-2 flex items-center gap-2">
                {faces((activeAcross.course ? flatLessons(activeAcross.course).slice(0, 4).map((l) => l.title) : []))}
              </div>
              <div className="mt-auto pt-4">
              <button
                onClick={() => {
                  if (activeAcross.lesson) goDetail(activeAcross.lesson.courseId, activeAcross.lesson.moduleId, activeAcross.lesson.id);
                  else if (activeAcross.course) openCourse(activeAcross.course);
                }}
                className="w-full rounded-full bg-white px-4 py-2.5 text-xs font-black transition hover:brightness-95 active:scale-[0.98]"
                style={{ color: RED_DEEP }}
              >
                {activeAcross.lesson ? "Open lesson" : "Browse courses"}
              </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* ── Detail ── */
        <div className="px-5 py-4 sm:px-8">
          <button onClick={() => setHome(true)} className="flex items-center gap-1.5 text-xs font-bold text-slate-500 transition hover:text-slate-800">
            <FaArrowLeft className="h-3 w-3" /> All courses
          </button>
          {!selLesson ? (
            <div className="mt-3 flex flex-col items-center justify-center gap-2 rounded-2xl border border-black/15 bg-white p-8 text-center shadow-sm">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100"><FaBookOpen className="h-5 w-5 text-slate-400" /></span>
              <p className="text-sm font-bold" style={{ color: NAVY }}>Select a lesson</p>
              <p className="max-w-60 text-xs leading-5 text-slate-500">Choose a lesson from My next lessons to see the overview.</p>
            </div>
          ) : (
            <>
              <div className="mt-2 rounded-2xl border border-black/15 bg-white p-5 shadow-[0_2px_10px_rgba(27,37,71,0.06)]" style={{ borderTop: `4px solid ${RED}` }}>
                <p className="text-[11px] font-bold tracking-[0.14em] uppercase" style={{ color: RED }}>
                  {selCourse?.title} <span className="mx-1 text-slate-300">/</span> <span className="text-slate-500">{selModule?.title}</span>
                </p>
                <h1 className="mt-1 text-xl font-black tracking-tight" style={{ color: NAVY }}>{selLesson.title}</h1>
                <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11px]">
                  <span className={`rounded-full px-2.5 py-1 font-bold ${KIND_STYLE[selLesson.kind] || KIND_STYLE.theory}`}>{KIND_LABEL[selLesson.kind] || selLesson.kind}</span>
                  {selLesson.durationMin && (
                    <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-600">
                      <FaClock className="h-3 w-3" style={{ color: RED }} /> {selLesson.durationMin} min
                    </span>
                  )}
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 font-semibold text-slate-600">
                    Lesson {(idx >= 0 ? idx + 1 : 1)} of {all.length} · {totalMins} min total
                  </span>
                  {selLesson.id === activeLessonId && (
                    <span className="rounded-full px-2.5 py-1 font-bold text-white shadow-[0_4px_12px_rgba(255,90,95,0.4)]" style={{ background: RED }}>● In progress</span>
                  )}
                </div>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100 ring-1 ring-black/10">
                  <div className="h-full rounded-full bg-gradient-to-r from-[#ff5a5f] to-[#c81e3a]" style={{ width: `${pct}%` }} />
                </div>
                <p className="mt-1.5 text-[11px] font-semibold text-slate-500 tabular-nums">{pct}% of course complete</p>
              </div>

              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-2xl border border-black/15 bg-white p-4 shadow-[0_2px_10px_rgba(27,37,71,0.06)]">
                  <p className="text-[11px] font-black tracking-[0.12em] text-slate-400 uppercase">Objective</p>
                  <p className="mt-1 text-[13px] leading-6 text-slate-700">{selLesson.objective}</p>
                </div>
                <div className="rounded-2xl border border-black/15 bg-white p-4 shadow-[0_2px_10px_rgba(27,37,71,0.06)]">
                  <p className="text-[11px] font-black tracking-[0.12em] text-slate-400 uppercase">What you will learn</p>
                  <p className="mt-1 text-[13px] leading-6 text-slate-700">{selLesson.summary}</p>
                  {(selLesson.keyTerms?.length > 0) && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-slate-100 pt-2.5">
                      {selLesson.keyTerms.map((k) => (
                        <span key={k} className="rounded-md bg-slate-100 px-2 py-1 font-mono text-[11px] font-semibold text-slate-600">{k}</span>
                      ))}
                    </div>
                  )}
                </div>
                {(selLesson.boardOutline?.length > 0) && (
                  <div className="rounded-2xl border border-black/15 bg-white p-4 shadow-[0_2px_10px_rgba(27,37,71,0.06)]">
                    <p className="text-[11px] font-black tracking-[0.12em] text-slate-400 uppercase">Green board plan</p>
                    <ol className="mt-2 space-y-1.5">
                      {selLesson.boardOutline.map((s, i) => (
                        <li key={i} className="flex items-start gap-2.5 text-[13px] text-slate-700">
                          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-black text-white tabular-nums" style={{ background: RED }}>{i + 1}</span>
                          <span className="leading-5">{s}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
                {selLesson.quiz && (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
                    <p className="text-[11px] font-black tracking-[0.12em] text-amber-700 uppercase">Checkpoint quiz</p>
                    <p className="mt-1 text-[13px] font-bold text-slate-900">{selLesson.quiz.q}</p>
                    <p className="mt-1 text-xs text-slate-500">{(selLesson.quiz.options || []).length} options · answered on the board after the lesson</p>
                  </div>
                )}
              </div>

              <div className="mt-3 rounded-2xl border border-black/15 bg-white p-3 shadow-[0_2px_10px_rgba(27,37,71,0.06)]">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => prev && goDetail(prev.courseId, prev.moduleId, prev.id)}
                    disabled={!prev}
                    className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-600 transition hover:brightness-95 disabled:opacity-30"
                    aria-label="Previous lesson"
                    title={prev ? `Previous: ${prev.title}` : "No previous lesson"}
                  >
                    <FaArrowLeft className="h-3.5 w-3.5" />
                  </button>
                  <span
                    className="flex h-10 flex-1 items-center justify-center gap-2 rounded-xl border border-dashed px-4 text-center text-[12px] font-semibold text-slate-500"
                    style={{ borderColor: "rgba(200,30,58,0.35)", background: "rgba(255,90,95,0.06)" }}
                  >
                    <FaCirclePlay className="h-4 w-4 shrink-0" style={{ color: RED }} />
                    Ask by voice — “यह lesson सिखाओ” — the tutor opens the board and starts
                  </span>
                  <button
                    onClick={() => next && goDetail(next.courseId, next.moduleId, next.id)}
                    disabled={!next}
                    className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-600 transition hover:brightness-95 disabled:opacity-30"
                    aria-label="Next lesson"
                    title={next ? `Next: ${next.title}` : "No next lesson"}
                  >
                    <FaArrowRight className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="mt-2 flex items-center justify-center">
                  {doneIds.has(selLesson.id) ? (
                    <span className="flex items-center gap-1.5 text-[11px] font-bold text-emerald-600">
                      <FaCircleCheck className="h-3.5 w-3.5" /> Completed
                      {next && onCompleteLesson && (
                        <button
                          onClick={() => onCompleteLesson && onCompleteLesson(selCourse.id, selModule.id, selLesson.id, true)}
                          className="font-semibold text-slate-500 underline underline-offset-2 hover:text-slate-800"
                        >
                          Continue to next
                        </button>
                      )}
                    </span>
                  ) : (
                    <button
                      onClick={() => onCompleteLesson && onCompleteLesson(selCourse.id, selModule.id, selLesson.id, false)}
                      className="text-[11px] font-semibold text-slate-500 underline underline-offset-2 transition hover:text-slate-800"
                    >
                      Mark complete & continue
                    </button>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
