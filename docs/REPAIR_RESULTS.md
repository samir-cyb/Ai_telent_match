# AI Talent Match — repair results

তারিখ: 2 October 2026। Baseline: `main` commit `9eb75af`।
Repair branch: `codex/system-repairs`।

আগের audit-এর সমস্যাগুলো অনুযায়ী code মেরামত করা হয়েছে। এই report-এর
“Fixed” মানে সংশ্লিষ্ট code defect ঠিক হয়েছে; আপনার real database, AI account,
SMTP বা Docker host দিয়ে সব production flow পরীক্ষা হয়েছে—এমন দাবি নয়।

## Architecture এবং workflow

Student/company/admin → Django → fraud/semantic matching → পাঁচ-component
score → optional vetting → shortlist/interview/ranking → hire/reject feedback
এবং Q-learning weight update আগের মতোই আছে।

`core/utils/ai_engine.py`, `fraud_detector.py`, `recruitment_agent.py` এবং
`vetting/services/code_grader.py` পরিবর্তন করা হয়নি। Manual apply-এর 60%
threshold, batch smart apply-এর default 70%/5 applications, points values,
grading weights এবং pipeline-এর 30%/40%/30% final score অপরিবর্তিত।

CV import-এর review → Save ধাপ রাখা হয়েছে। Browser identity এখন server
session থেকে আসে। Career prediction আলাদা request-এ একই আগের prediction
method ব্যবহার করে, যাতে AI offline থাকলেও profile/dashboard data দেখা যায়।
Django framework রাখা হয়েছে; dependency version 5.2.17 LTS-এ নেওয়া হয়েছে।

## Audit findings এবং সমাধান

| # | সমস্যা / কারণ | কী ঠিক হয়েছে | অবস্থা |
|---|---|---|---|
| 1 | Profile read/write-এ account ownership অনুপস্থিত | Shared session/role boundary, student UUID ownership | Fixed |
| 2 | Fixed admin credentials login bypass করত | Bypass/literals removed; private hashed admin commands, session-revoking password rotation | Fixed; পুরোনো account password rotate করুন |
| 3 | Python submission Django host-এ চলত | সব language existing Judge0 sandbox দিয়ে চলে; unsafe fallback removed | Fixed; sandbox চালু থাকতে হবে |
| 4 | পুরোনো Judge0 image/public binding | 1.13.1 image, loopback binding, generated private token/config and network restrictions | Fixed in config; Docker runtime এখানে পরীক্ষা হয়নি |
| 5 | Anonymous/invalid application status update | Company role, job ownership, status choices, repeat-update idempotence | Fixed |
| 6 | Company/admin APIs-এ inconsistent authorization | Every routed class API has an explicit policy; unknown routes denied | Fixed |
| 7 | Upload validation ও CV privacy | Signature/type/10 MB limit, owner checks; authorized private document route | Fixed; production proxy সরাসরি media expose করবে না |
| 8 | Invalid profile data আংশিক save হতো | Pre-validation plus atomic rollback on handler failure | Fixed |
| 9 | CV parser failure empty success; preview পুরোনো lists replace করত | Explicit 422 failure; existing file/data preserved; additive review modal merge | Fixed |
| 10 | Client নিজে project verified করতে পারত | New manual projects unverified; existing verification retained only for unchanged URL; server checks assign proof | Fixed |
| 11 | Quiz HTML-এ answers/explanations/rubric | Public question whitelist; points and written word limit retained | Fixed |
| 12 | Source-এ Gemini key literals | Removed; shared environment-based provider client | Fixed in source; provider keys revoke/rotate করুন |
| 13 | Student/company/provider data দিয়ে unsafe HTML/links | HTML escaping, HTTP(S) URL validation, correctly quoted event arguments, escaped chat formatting | Fixed for reviewed sinks; focused browser checks pass |
| 14 | Skills/experience UUID signature; duplicate preferences methods | URL UUID accepted; misplaced duplicate methods removed; preference merge restored | Fixed |
| 15 | Missing dashboard record 500; stale browser student ID | 404 handling; server bootstrap updates both storage key variants; invalid session 401 | Fixed |
| 16 | Full GitHub URL stored as username → malformed links | Username/profile-URL normalization; legacy profile display normalized | Fixed |
| 17 | Refresh GitHub শুধু toast/profile GET করত | Real sync API; stable repository ID upsert, repeatable imports, manual projects preserved | Fixed |
| 18 | Empty GitHub auth header; every failure “not found”; sequential metadata | Optional auth, distinct 401/403/404 messages, cached bounded parallel metadata | Fixed; rate limits এখনও প্রযোজ্য |
| 19 | Local-first AI setting সবসময় Gemini skip করত | Environment toggle and service setup docs; existing default retained | Configurable |
| 20 | Gemini constructor failure fallback আটকাত | Constructor guarded; configured Ollama fallback still runs | Fixed |
| 21 | Profile GET AI response-এর জন্য block করত | Basic profile/dashboard independent; separate cached prediction endpoint | Fixed |
| 22 | In-progress test refresh-এ start window বন্ধ দেখাত | Start gate applies to pending sessions; existing timer/session resumes | Fixed |
| 23 | `timedelta.seconds` 24 ঘণ্টার পর wrap করত | `total_seconds()`; existing saved-code expiry submission wired correctly | Fixed |
| 24 | Duplicate applications/racing counters | Database uniqueness, role parent locks, all-path insert/delete counter signals; migration refuses conflicting old data | Fixed; legacy duplicates review প্রয়োজন হতে পারে |
| 25 | Points JSON read/write race | Student/entry locks and existing event idempotency | Fixed in code; real PostgreSQL concurrency load test হয়নি |
| 26 | Pipeline delete-before-compute/partial updates | Atomic stages, pipeline locks, old state survives provider failure; empty assessments/interviews rejected | Fixed |
| 27 | Dashboard heuristic বনাম final engine score | Existing formulas retained; recommendation label “Dashboard estimate” | Preserved and clarified |
| 28 | Optional fields clear বা CGPA 0 save করা যেত না | Key-presence updates; nullable clears; profile/registration browser payload এবং registration backend-এ zero preserved | Fixed; real browser Save/reload verified |
| 29 | Deleted ChatMessage import; HTTP-only ASGI | Additive model/migration, optional ASGI routing, room ownership, Redis config | Fixed; optional chat remains disabled by default |
| 30 | Duplicate class/function definitions shadowed code | Earlier shadowed definitions removed, active handlers retained | Fixed |
| 31 | Production debug/wildcard host/CORS/cookies | Environment config, exact hosts/origins, HTTPS cookies/HSTS, CSRF enforcement | Fixed in settings; deploy with correct environment |
| 32 | Hardcoded localhost API origin | Relative same-origin APIs and shared CSRF/session client | Fixed |
| 33 | Console email/localhost interview links | Configurable SMTP and public SITE_URL, setup docs | Configurable; real delivery এখানে পরীক্ষা হয়নি |
| 34 | Celery variables থাকলেও scheduler ছিল না | Existing daily_matching command documented for single-instance Task Scheduler/cron | Existing architecture retained; scheduler owner configure করবেন |
| 35 | Outdated framework/unrelated dependencies | Supported Django LTS, tested clean runtime pins, separate optional analysis dependencies | Fixed |
| 36 | Raw CV/provider/profile content logging | Parser/profile debug dumps removed; browser payload logs removed | Fixed |
| 37 | Placeholder tests/fragile handoff | Regression suite, upgrade checks, CI, Windows/Linux setup, .env.example | Fixed |

অতিরিক্তভাবে optional location-সহ job posting, pipeline interview notification-এর
ভুল URL, multiple agent interviews থাকা application-এর pipeline invitation,
new interview-এর পুরোনো answers reset, duplicate finalization এবং local vision-এ
PDF bytes-এর বদলে PNG pages পাঠানো ঠিক হয়েছে। Trust snapshot save এখন শুধু
derived score fields update করে; concurrent profile edits আর overwrite করে না।

## যাচাই করা হয়েছে

| Check | Result |
|---|---|
| Django regression suite | 65 tests passed on the final ZIP source; external AI/GitHub/sandbox mocked |
| Real grading transaction behavior | Slow grading runs outside the DB transaction; anti-cheat termination persists |
| Fresh migration + model drift | Fresh test DB migration passed; no model drift |
| Upgrade from core 0021/vetting 0002 | Synthetic duplicate migration refused without deletion; reviewed upgrade preserved records and installed uniqueness |
| Student UI | 8 pages × desktop/mobile = 16 checks passed for navigation, controls and layout |
| Focused malicious input UI | Profile, advisor and company job preview checks passed; unsafe project URL blocked, CV merge preserved lists, stale browser identity replaced |
| Templates / JavaScript | 47 templates compile; 55 rendered inline scripts compile; static client syntax valid |
| Runtime dependencies | Fresh Python 3.12 environment installed; pip check passed |
| Setup | Linux setup completes on a disposable clean source copy; existing environment preserved; sandbox token/config match and overwrite refused |

## Final ZIP verification — 2 October 2026

Student registration wizard-এর অতিরিক্ত silent-submit defect reproduce করে
ঠিক হয়েছে: Step 1 শুধু nonempty check করত; invalid email/short password hidden
হয়ে যাওয়ার পরে browser form submit আটকে দিত এবং API request যেত না। Next এখন
existing HTML validity rules check করে; final Submit invalid step reveal করে।
এটি validation/visibility correction; তিন ধাপের registration workflow একই আছে।

Saved repair package থেকে আলাদা source copy নিয়ে fresh Python 3.12 environment-এ
dependencies install এবং `pip check` পাস করেছে। Final source-এর 65 regression
tests পাস করেছে। নতুন test registration-এ CGPA 0 হারিয়ে না যাওয়াটা পরীক্ষা করে।
Profile ও registration frontend-এর `parseFloat(...) || null` 0-কে null বানাত;
এখন শুধু empty input null হয়। Matching/scoring formula বদলানো হয়নি।

Actual Django server + disposable SQLite database দিয়ে browser login, CSRF,
server session identity, profile Save/reload, GitHub URL normalization এবং CGPA
0 preservation পরীক্ষা করা হয়েছে। GitHub response/CV extraction mocked;
browser HTTP/API/database wiring mock করা হয়নি। বিস্তারিত final browser log
এবং acceptance guide package-এ আছে। Windows execution এবং live external
services এখনও owner-side acceptance checks।

ZIP-এর source export-ই final version। পুরোনো commit `2641266`-এর পরে এই
ছোট input fixes ও documentation যোগ হয়েছে; GitHub-এ push করা হয়নি। পুরোনো
Git bundle/patch/publish script final ZIP-এ নেই, যাতে সেগুলো দিয়ে পুরোনো
snapshot publish না হয়। Final source review করে নিজের Git branch-এ commit করুন।

## Team handoff

README-এ Windows setup, manual fallback এবং Linux setup আছে। আপনার project
database/`.env`/uploaded CV এখানে পরিবর্তন করা হয়নি। Generated student UI
backup directories Git থেকে untracked হয়েছে; local restore copies আছে।

নতুন installation-এ `scripts/setup.ps1` অথবা `scripts/setup.sh` দিয়ে শুরু করুন।
Existing installation-এ database/uploads backup করে requirements install,
`manage.py migrate`, তারপর `manage.py check_setup` চালান। Old applicant counts
সংশোধনের preview command `manage.py reconcile_applicant_counts`; review-এর পর
`--apply` দিন।

Full system চালাতে AI provider/models, private GitHub token (প্রয়োজনে),
Judge0, SMTP/public SITE_URL, production PostgreSQL এবং scheduler configure
করতে হবে। Optional chat ব্যবহার করলে ASGI এবং multiple workers-এর জন্য Redis
দরকার। পুরোনো PostgreSQL 13 Judge0 volume থাকলে PostgreSQL 16-এ explicit
dump/restore migration দরকার; পুরোনো volume সরাসরি নতুন image-এ লাগাবেন না।

## Verification limits

Real user data, live Gemini/Ollama quality/quota, GitHub import against your
account, SMTP delivery, Docker isolation, Redis, production PostgreSQL race/load
behavior এবং Windows PowerShell execution এখানে পরীক্ষা করা হয়নি। These
repairs are not a certification that every unknown production defect is gone.
এই environment-এ Linux/Python/browser checks করা হয়েছে; owner-side service
configuration এবং key rotation কাজ আলাদা করে বাকি আছে।

## Official references

- [Django release/support versions](https://www.djangoproject.com/download/)
- [Django 5.2.17 security release](https://www.djangoproject.com/weblog/2026/aug/04/security-releases/)
- [Judge0 1.13.1 security fixes](https://github.com/judge0/judge0/releases/tag/v1.13.1)
- [Judge0 authentication and execution configuration](https://ce.judge0.com/)
- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
