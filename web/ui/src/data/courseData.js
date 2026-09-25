/* Hardcoded test data — STUDENT + active COURSE (MERN).
 *
 * Pipeline rule: NOTHING here is React/coding-specific. The schema is generic
 * (theory | coding | video | quiz | project) so the same OS + tutor can teach
 * ANY subject later — history, physics, accounts — by swapping COURSE only.
 * MERN is just the current test course because this environment has
 * whiteboard + browser + code + notes ready.
 *
 * Content language: professional English. The tutor's VOICE replies in Hindi
 * (see server/llm/prompts.py) — course text stays English, glossaries stay
 * Devanagari only as TTS pronunciation hints.
 */

export const STUDENT = {
  id: "stu-raj-001",
  name: "RAJ",
  gender: "male",
  qualification: "Currently pursuing B.Tech CSE, 3rd year",
  college: "JSS Academy of Technical Education, Bangalore",
  branch: "Computer Science and Engineering",
  year: 3,
  preferredLang: "hindi-devanagari", // tutor voice replies in Hindi (Devanagari)
  level: "intermediate", // beginner | intermediate | advanced
};

/* Generic lesson schema — every subject reuses these exact fields:
 * kind: theory | coding | video | quiz | project
 * apps: suggestion only; App.jsx + OS director decide actual windows.
 * videoQuery: search words for BrowserApp (no hardcoded video IDs).
 */
export const COURSE = {
  id: "mern-stack-001",
  title: "MERN Stack — HTML to MongoDB",
  description:
    "Complete web development: HTML, CSS, JavaScript, React, Node, Express, JWT auth, Mongoose + MongoDB, Git, deployment + capstone project.",
  level: "beginner-to-intermediate",
  language: "english",
  modules: [
    {
      id: "m-html",
      title: "HTML — Structure",
      lessons: [
        {
          id: "html-1", title: "What Is HTML + First Page", kind: "coding",
          objective: "Understand HTML document structure and build your first page.",
          summary: "Doctype, html, head, body, headings, paragraphs, and buttons — viewed in live preview.",
          videoQuery: "html introduction for beginners",
          keyTerms: ["HTML", "tag", "element", "head", "body"],
          glossary: { HTML: "एचटीएमएल", tag: "टैग" },
          boardOutline: ["HTML defines structure", "Tags open and close", "Head vs body"],
          apps: ["whiteboard", "browser", "code"], durationMin: 30,
          quiz: { q: "What is the difference between head and body?", options: ["Head is visible, body is not", "Body is visible, head holds metadata", "Both are the same", "There is no head"], answer: 1, explanation: "The body renders on screen; the head holds metadata." },
        },
        {
          id: "html-2", title: "Forms, Links, Images, Lists", kind: "coding",
          objective: "Learn to build links, images, lists, and forms.",
          summary: "Anchor, image, ordered and unordered lists, inputs, and buttons — build a mini contact page.",
          videoQuery: "html forms links images tutorial",
          keyTerms: ["anchor", "image", "list", "form", "input"],
          glossary: { anchor: "एंकर", form: "फॉर्म", input: "इनपुट" },
          boardOutline: ["Links navigate", "Images embed", "Forms collect data"],
          apps: ["whiteboard", "code"], durationMin: 35,
          quiz: { q: "How does form data reach the server?", options: ["Through the img tag", "Through input plus submit", "Through h1", "Through title"], answer: 1, explanation: "Input fields plus a submit button send the data." },
        },
        {
          id: "html-3", title: "Semantic HTML + Mini Project", kind: "project",
          objective: "Build clean page layouts with header, main, and footer.",
          summary: "From generic divs to semantic tags, plus a portfolio skeleton.",
          videoQuery: "semantic html project",
          keyTerms: ["header", "main", "footer", "section", "nav"],
          glossary: { header: "हेडर", footer: "फुटर" },
          boardOutline: ["Why semantics matter", "Layout blocks", "Portfolio skeleton"],
          apps: ["whiteboard", "browser", "code", "notes"], durationMin: 45,
          quiz: { q: "Why use semantic tags?", options: ["Only for styling", "Meaning, SEO, and readability", "Faster internet", "No benefit"], answer: 1, explanation: "They add meaning, improving SEO and readability." },
        },
      ],
    },
    {
      id: "m-css",
      title: "CSS — Styling",
      lessons: [
        {
          id: "css-1", title: "Selectors, Colors, Box Model", kind: "coding",
          objective: "Understand CSS selectors and the box model.",
          summary: "Classes and IDs, colors, margins, borders, and padding — with a box model diagram.",
          videoQuery: "css box model selectors beginners",
          keyTerms: ["selector", "class", "margin", "padding", "border"],
          glossary: { selector: "सेलेक्टर", margin: "मार्जिन", padding: "पैडिंग" },
          boardOutline: ["Selectors target elements", "Box: content, padding, border, margin", "Colors"],
          apps: ["whiteboard", "code"], durationMin: 35,
          quiz: { q: "What is the difference between margin and padding?", options: ["They are the same", "Margin is outside gap, padding is inside gap", "Padding is outside gap", "Neither exists"], answer: 1, explanation: "Margin adds space outside the element; padding adds space inside." },
        },
        {
          id: "css-2", title: "Flexbox + Responsive Design", kind: "coding",
          objective: "Build layouts with Flexbox and make them responsive.",
          summary: "Display flex, justify-content, align-items, and media queries.",
          videoQuery: "css flexbox responsive tutorial",
          keyTerms: ["flexbox", "justify", "align", "responsive", "media query"],
          glossary: { flexbox: "फ्लेक्सबॉक्स", responsive: "रिस्पॉन्सिव" },
          boardOutline: ["Flex rows and columns", "How to center content", "Mobile breakpoints"],
          apps: ["whiteboard", "browser", "code"], durationMin: 40,
          quiz: { q: "How do you center content with Flexbox?", options: ["Float", "Justify-content plus align-items", "BR tag", "Table"], answer: 1, explanation: "Justify-content and align-items center the content." },
        },
        {
          id: "css-3", title: "CSS Grid + Animations + Polish", kind: "coding",
          objective: "Build grid layouts and add transitions and animations.",
          summary: "Grid rows and columns, gap, hover transitions, keyframe animations — polish the portfolio.",
          videoQuery: "css grid animations tutorial",
          keyTerms: ["grid", "template", "gap", "transition", "animation"],
          glossary: { grid: "ग्रिड", transition: "ट्रांज़िशन", animation: "एनिमेशन" },
          boardOutline: ["Grid places items in rows and columns", "Transitions animate state changes", "Keyframes run reusable motion"],
          apps: ["whiteboard", "code"], durationMin: 40,
          quiz: { q: "What does grid-template-columns define?", options: ["Row colors", "Column tracks and sizes", "Font sizes", "Page title"], answer: 1, explanation: "It declares the grid columns and their sizes." },
        },
      ],
    },
    {
      id: "m-js",
      title: "JavaScript — Logic",
      lessons: [
        {
          id: "js-1", title: "Variables, Functions, Conditions, Loops", kind: "coding",
          objective: "Write variables, functions, conditionals, and loops.",
          summary: "Variables, functions, and loops — run them in the console.",
          videoQuery: "javascript basics variables functions loops",
          keyTerms: ["variable", "function", "condition", "loop", "array"],
          glossary: { variable: "वेरिएबल", function: "फंक्शन", loop: "लूप", array: "अरे" },
          boardOutline: ["Store data in variables", "Group work in functions", "Repeat with loops"],
          apps: ["whiteboard", "code"], durationMin: 45,
          quiz: { q: "What is the difference between let and const?", options: ["They are the same", "let is reassignable, const is fixed", "const is reassignable", "Both are fixed"], answer: 1, explanation: "let can be reassigned; a const binding stays fixed." },
        },
        {
          id: "js-2", title: "DOM + Events", kind: "coding",
          objective: "Update the page in response to button clicks.",
          summary: "getElementById, querySelector, and addEventListener — build a click counter.",
          videoQuery: "javascript dom events tutorial",
          keyTerms: ["DOM", "event", "listener", "query selector", "button"],
          glossary: { DOM: "डॉम", event: "इवेंट", button: "बटन" },
          boardOutline: ["DOM is the page tree", "Select an element", "Act on events"],
          apps: ["whiteboard", "browser", "code"], durationMin: 45,
          quiz: { q: "How do you run code on a click?", options: ["With CSS", "With addEventListener", "With title", "Automatically"], answer: 1, explanation: "A listener hears the event and runs a function." },
        },
        {
          id: "js-3", title: "Fetch + JSON + ES6", kind: "coding",
          objective: "Fetch API data and render it on the page.",
          summary: "Fetch, async and await, map and filter — build an API list project.",
          videoQuery: "javascript fetch api async await",
          keyTerms: ["fetch", "API", "JSON", "async", "promise"],
          glossary: { fetch: "फेच", API: "एपीआई" },
          boardOutline: ["API is a data source", "Fetch the data", "Render the list"],
          apps: ["whiteboard", "browser", "code"], durationMin: 50,
          quiz: { q: "Why use await?", options: ["For styling", "To wait until data arrives", "To raise errors", "No reason"], answer: 1, explanation: "await pauses until the async work completes." },
        },
        {
          id: "js-4", title: "Modern JS for React: Destructuring, Spread, Modules", kind: "coding",
          objective: "Use destructuring, spread, and modules — the JS React is written in.",
          summary: "Destructuring props, spread copies, arrow functions, import and export — prep for React.",
          videoQuery: "modern javascript destructuring spread modules",
          keyTerms: ["destructuring", "spread", "arrow", "import", "export"],
          glossary: { destructuring: "डिस्ट्रक्चरिंग", spread: "स्प्रेड", module: "मॉड्यूल" },
          boardOutline: ["Unpack values with destructuring", "Copy and merge with spread", "Split code with modules"],
          apps: ["whiteboard", "code"], durationMin: 40,
          quiz: { q: "What does the spread do in [...a, x]?", options: ["Deletes the array", "Copies items plus adds x", "Sorts the array", "Sends data to server"], answer: 1, explanation: "Spread copies every item, then x joins the new array." },
        },
      ],
    },
    {
      id: "m-react",
      title: "React — UI Library",
      lessons: [
        {
          id: "react-1", title: "Components, Props, JSX", kind: "coding",
          objective: "Understand components and props by building your first one.",
          summary: "JSX, components, and props — greeting card example.",
          videoQuery: "react components props beginners",
          keyTerms: ["component", "props", "JSX", "state", "render"],
          glossary: { component: "कम्पोनेंट", props: "प्रॉप्स" },
          boardOutline: ["UI pieces are components", "Props are inputs", "JSX mixes HTML and JS"],
          apps: ["whiteboard", "browser", "code"], durationMin: 45,
          quiz: { q: "What are props?", options: ["A CSS file", "Input data for a component", "A server", "A database"], answer: 1, explanation: "Props pass data from parent to child." },
        },
        {
          id: "react-2", title: "useState + Lists + Forms", kind: "coding",
          objective: "Build interactive UIs with state.",
          summary: "useState counter, list rendering, and form inputs — a todo mini app.",
          videoQuery: "react usestate forms todo",
          keyTerms: ["state", "hook", "list", "form", "todo"],
          glossary: { state: "स्टेट", hook: "हुक" },
          boardOutline: ["State remembers values", "Changes re-render", "Todo app"],
          apps: ["whiteboard", "code"], durationMin: 50,
          quiz: { q: "What happens when state changes?", options: ["Nothing", "The component re-renders", "The page is deleted", "The server stops"], answer: 1, explanation: "React renders the component again." },
        },
        {
          id: "react-3", title: "useEffect + Routing + Project", kind: "project",
          objective: "Build a multi-page app with API data.",
          summary: "Fetching with useEffect, pages with React Router — a users app.",
          videoQuery: "react useeffect router project",
          keyTerms: ["effect", "router", "page", "API", "project"],
          glossary: { effect: "इफेक्ट", router: "राउटर" },
          boardOutline: ["What side effects are", "Page routing", "Mini project"],
          apps: ["whiteboard", "browser", "code", "notes"], durationMin: 55,
          quiz: { q: "When does useEffect run?", options: ["Only on click", "After render, for side tasks", "Never", "In CSS"], answer: 1, explanation: "It runs after render for tasks like data fetching." },
        },
        {
          id: "react-4", title: "Context, useRef + Custom Hooks", kind: "coding",
          objective: "Share state without prop drilling and reuse logic with custom hooks.",
          summary: "Context provider and consumer, useRef for DOM and silent values, a useFetch custom hook.",
          videoQuery: "react context custom hooks tutorial",
          keyTerms: ["context", "provider", "ref", "custom hook", "prop drilling"],
          glossary: { context: "कॉन्टेक्स्ट", provider: "प्रोवाइडर", hook: "हुक" },
          boardOutline: ["Context skips prop drilling", "Refs hold DOM and silent values", "Custom hooks reuse logic"],
          apps: ["whiteboard", "code"], durationMin: 45,
          quiz: { q: "What problem does Context solve?", options: ["Slow internet", "Prop drilling through layers", "Missing CSS", "Server errors"], answer: 1, explanation: "Context shares values without passing props down every level." },
        },
      ],
    },
    {
      id: "m-node",
      title: "Node.js — Backend Runtime",
      lessons: [
        {
          id: "node-1", title: "Node + npm + First Server", kind: "coding",
          objective: "Understand Node and run your first server.",
          summary: "Node runtime, npm, and an HTTP server — a hello API.",
          videoQuery: "nodejs first server beginners",
          keyTerms: ["Node", "npm", "server", "runtime", "port"],
          glossary: { Node: "नोड", server: "सर्वर" },
          boardOutline: ["JavaScript on the server", "npm manages packages", "Listen on a port"],
          apps: ["whiteboard", "browser", "code"], durationMin: 40,
          quiz: { q: "What is npm?", options: ["A video app", "A package manager", "A database", "A browser"], answer: 1, explanation: "npm installs and manages JavaScript packages." },
        },
        {
          id: "node-2", title: "Modules, npm Scripts, Env + Async", kind: "coding",
          objective: "Organize backend code with modules, scripts, and environment config.",
          summary: "CommonJS vs ESM imports, package.json scripts, dotenv secrets, async file reads.",
          videoQuery: "nodejs modules npm scripts dotenv tutorial",
          keyTerms: ["module", "require", "env", "script", "async"],
          glossary: { module: "मॉड्यूल", env: "एन्व", script: "स्क्रिप्ट" },
          boardOutline: ["Modules split backend code", "Scripts automate tasks", "Env hides secrets"],
          apps: ["whiteboard", "code"], durationMin: 40,
          quiz: { q: "Where do secrets like API keys belong?", options: ["In the frontend code", "In env files, never committed", "In the URL", "In comments"], answer: 1, explanation: "Env files hold secrets and stay out of git." },
        },
      ],
    },
    {
      id: "m-express",
      title: "Express — API Framework",
      lessons: [
        {
          id: "exp-1", title: "Routes + Middleware + REST", kind: "coding",
          objective: "Build GET and POST API routes.",
          summary: "Express app, routes, request and response objects, JSON APIs, and Postman testing.",
          videoQuery: "express js rest api routes",
          keyTerms: ["route", "GET", "POST", "middleware", "JSON"],
          glossary: { route: "राउट", middleware: "मिडलवेयर" },
          boardOutline: ["URLs are routes", "GET reads, POST writes", "Middleware gates"],
          apps: ["whiteboard", "browser", "code"], durationMin: 45,
          quiz: { q: "What is the difference between GET and POST?", options: ["They are the same", "GET reads, POST sends", "POST reads data", "Neither exists"], answer: 1, explanation: "GET fetches data; POST sends or saves data." },
        },
        {
          id: "exp-2", title: "Routers, Controllers, Validation + Errors", kind: "coding",
          objective: "Structure APIs professionally with routers and central error handling.",
          summary: "Express routers, controller functions, input validation, 404 plus error middleware.",
          videoQuery: "express router controller validation error handling",
          keyTerms: ["router", "controller", "validation", "error", "status code"],
          glossary: { router: "राउटर", controller: "कंट्रोलर", validation: "वैलिडेशन" },
          boardOutline: ["Routers group endpoints", "Controllers hold logic", "Errors flow to one handler"],
          apps: ["whiteboard", "code"], durationMin: 50,
          quiz: { q: "What status code means 'created'?", options: ["200", "201", "404", "500"], answer: 1, explanation: "201 confirms a new resource was created." },
        },
      ],
    },
    {
      id: "m-auth",
      title: "Auth — JWT Security",
      lessons: [
        {
          id: "auth-1", title: "JWT Auth: Register, Login, Protected Routes", kind: "coding",
          objective: "Add signup and login with hashed passwords and JWT tokens.",
          summary: "bcrypt hashing, jsonwebtoken signing, auth middleware guarding private routes.",
          videoQuery: "jwt authentication nodejs express tutorial",
          keyTerms: ["JWT", "token", "bcrypt", "hash", "protected"],
          glossary: { JWT: "जेडब्ल्यूटी", token: "टोकन", bcrypt: "बिक्रिप्ट", hash: "हैश" },
          boardOutline: ["Passwords are hashed, never stored", "Login returns a signed token", "Middleware guards private routes"],
          apps: ["whiteboard", "code"], durationMin: 55,
          quiz: { q: "Where should the JWT be checked?", options: ["In CSS", "In auth middleware before private routes", "In the database", "Never"], answer: 1, explanation: "Middleware verifies the token before the route runs." },
        },
      ],
    },
    {
      id: "m-mongo",
      title: "MongoDB — Database",
      lessons: [
        {
          id: "mongo-1", title: "Collections, Documents + CRUD", kind: "coding",
          objective: "Learn to save and read data.",
          summary: "Collections and documents, insert, find, update, and delete — a notes API.",
          videoQuery: "mongodb crud beginners",
          keyTerms: ["database", "collection", "document", "CRUD", "query"],
          glossary: { database: "डेटाबेस", query: "क्वेरी" },
          boardOutline: ["Database stores data", "Four CRUD operations", "Connect a notes API"],
          apps: ["whiteboard", "browser", "code"], durationMin: 45,
          quiz: { q: "What does U stand for in CRUD?", options: ["Undo", "Update", "Upload", "User"], answer: 1, explanation: "Create, Read, Update, Delete." },
        },
        {
          id: "mongo-2", title: "Mongoose: Schemas, Models + Atlas", kind: "coding",
          objective: "Model data with Mongoose schemas and connect MongoDB Atlas.",
          summary: "Schema types and validation, models, refs and populate, Atlas cloud connection.",
          videoQuery: "mongoose schema model atlas tutorial",
          keyTerms: ["mongoose", "schema", "model", "populate", "Atlas"],
          glossary: { mongoose: "मोंगूस", schema: "स्कीमा", model: "मॉडल", Atlas: "एटलस" },
          boardOutline: ["Schemas shape documents", "Models query collections", "Refs link data with populate"],
          apps: ["whiteboard", "browser", "code"], durationMin: 50,
          quiz: { q: "What does populate do?", options: ["Deletes data", "Fills refs with linked documents", "Speeds up CSS", "Creates servers"], answer: 1, explanation: "Populate replaces a ref id with the linked document." },
        },
      ],
    },
    {
      id: "m-ship",
      title: "Ship It — Git + Deployment",
      lessons: [
        {
          id: "git-1", title: "Git + GitHub Workflow", kind: "coding",
          objective: "Version your code and push it to GitHub.",
          summary: "init, add, commit, branches, push and pull — plus .gitignore for secrets.",
          videoQuery: "git github beginners tutorial",
          keyTerms: ["commit", "branch", "push", "pull", "repository"],
          glossary: { commit: "कमिट", branch: "ब्रांच", repository: "रिपॉज़िटरी" },
          boardOutline: ["Commits snapshot your code", "Branches isolate work", "Push shares via GitHub"],
          apps: ["whiteboard", "browser", "code"], durationMin: 35,
          quiz: { q: "What does git push do?", options: ["Deletes the repo", "Uploads commits to GitHub", "Installs packages", "Runs tests"], answer: 1, explanation: "Push uploads local commits to the remote repo." },
        },
        {
          id: "deploy-1", title: "Deploy MERN: Atlas + Render + Vercel", kind: "project",
          objective: "Ship the full stack with cloud database, backend, and frontend.",
          summary: "MongoDB Atlas connection, backend on Render with env vars, frontend on Vercel — end-to-end live URL.",
          videoQuery: "deploy mern stack render vercel atlas",
          keyTerms: ["deploy", "Atlas", "Render", "Vercel", "env"],
          glossary: { deploy: "डिप्लॉय", Render: "रेंडर", Vercel: "वर्सेल" },
          boardOutline: ["Database lives on Atlas", "Backend ships to Render", "Frontend ships to Vercel"],
          apps: ["whiteboard", "browser", "code", "notes"], durationMin: 50,
          quiz: { q: "Where do production secrets go?", options: ["In the code repo", "In the host dashboard env settings", "In comments", "In the URL bar"], answer: 1, explanation: "Hosts inject secrets via env settings — never commit them." },
        },
      ],
    },
    {
      id: "m-capstone",
      title: "Capstone — Full MERN App",
      lessons: [
        {
          id: "cap-1", title: "Plan + Connect Frontend, Backend, Database", kind: "project",
          objective: "Launch a complete MERN todo app.",
          summary: "Connect React, Express, and MongoDB — deployment checklist and revision.",
          videoQuery: "mern stack full project",
          keyTerms: ["frontend", "backend", "deploy", "project", "revision"],
          glossary: { frontend: "फ्रंटएंड", backend: "बैकएंड" },
          boardOutline: ["Connect the three layers", "Request flow diagram", "Deploy and revise"],
          apps: ["whiteboard", "browser", "code", "notes"], durationMin: 60,
          quiz: { q: "What does E stand for in MERN?", options: ["Electron", "Express", "Excel", "Email"], answer: 1, explanation: "MongoDB, Express, React, Node." },
        },
      ],
    },
  ],
};

/* Hardcoded last progress for RAJ (replaced by real DB later). */
export const INITIAL_PROGRESS = {
  courseId: COURSE.id,
  completedLessonIds: ["html-1", "html-2"],
  activeLessonId: "html-3",
  scores: { "html-1": 80, "html-2": 70 },
  updatedAt: new Date().toISOString(),
  streakDays: 4,
  minutesLearned: 95,
};

/* ---------- Generic helpers (subject-agnostic — do NOT branch on React) ---------- */

/* Multi-course registry: same schema teaches ANY subject — add a new COURSE
 * object here and the Tutor app lists it automatically with its
 * course -> module -> lesson dropdown. MERN is just course #1. */
export const COURSES = [COURSE];

export function getCourseById(id, courses = COURSES) {
  return (courses || []).find((c) => c.id === id) || null;
}

export function getAllLessons(course = COURSE) {
  return course.modules.flatMap((m) =>
    m.lessons.map((l) => ({ ...l, moduleId: m.id, moduleTitle: m.title })),
  );
}

export function getLessonById(id, course = COURSE) {
  return getAllLessons(course).find((l) => l.id === id) || null;
}

export function getTodoList(course = COURSE, progress = INITIAL_PROGRESS) {
  const done = new Set(progress.completedLessonIds || []);
  return course.modules.map((m) => ({
    moduleId: m.id,
    moduleTitle: m.title,
    lessons: m.lessons.map((l) => ({
      id: l.id, title: l.title, kind: l.kind, durationMin: l.durationMin,
      status: done.has(l.id) ? "done" : l.id === progress.activeLessonId ? "current" : "todo",
      score: progress.scores?.[l.id] ?? null,
    })),
  }));
}

export function getProgressPercent(course = COURSE, progress = INITIAL_PROGRESS) {
  const total = getAllLessons(course).length;
  if (!total) return 0;
  return Math.round(((progress.completedLessonIds || []).length / total) * 100);
}

/* Generic app suggestion by lesson KIND (not by subject):
 * theory/video -> whiteboard+browser, coding -> +code, project -> all+notes */
export function appsForLesson(lesson) {
  if (!lesson) return ["whiteboard", "browser"];
  if (Array.isArray(lesson.apps) && lesson.apps.length) return lesson.apps;
  switch (lesson.kind) {
    case "coding": return ["whiteboard", "browser", "code"];
    case "project": return ["whiteboard", "browser", "code", "notes"];
    case "quiz": return ["whiteboard"];
    default: return ["whiteboard", "browser"];
  }
}

/* Short learner line for the tutor prompt (name, who he is, where he stands). */
export function buildLearnerBlock(student = STUDENT, course = COURSE, progress = INITIAL_PROGRESS) {
  const active = getLessonById(progress.activeLessonId, course);
  return [
    `STUDENT: ${student.name} (${student.gender}), ${student.qualification}, ${student.college}.`,
    `COURSE: ${course.title} — ${getProgressPercent(course, progress)}% done, ` +
    `active lesson: ${active ? `${active.title} [${active.moduleTitle}]` : progress.activeLessonId}.`,
    `Speak to ${student.name} by name sometimes, match intermediate level. Voice replies in Hindi (Devanagari) only.`,
  ].join("\n");
}

export function buildLessonBlock(lesson) {
  if (!lesson) return "";
  return [
    `LESSON: ${lesson.title} (${lesson.kind}) | OBJECTIVE: ${lesson.objective}`,
    `SUMMARY: ${lesson.summary}`,
    `KEY TERMS: ${(lesson.keyTerms || []).join(", ")}`,
    `BOARD: ${(lesson.boardOutline || []).join(" > ")}`,
    `RULE: teach ONLY this lesson, end with its 1 quiz, never jump modules.`,
  ].join("\n");
}
