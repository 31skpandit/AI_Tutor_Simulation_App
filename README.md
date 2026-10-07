# AI Teaching Studio

An AI teaching assistant that runs on your laptop. You add your textbook chapters (PDFs, photos, Word files),
check the extracted text once, and then an AI tutor answers students' questions **from your textbook, with page
references**. Lessons, simulations and animated videos are added in Phases 2–3.

- **Full plan:** [docs/AI_Teaching_Studio_Project_Blueprint_v1.9.docx](docs/AI_Teaching_Studio_Project_Blueprint_v1.9.docx)
  (architecture, workflows, models, security, phase plan). Diagrams: [docs/diagrams/](docs/diagrams/).
- **Whole-codebase map (one draw.io page):** [docs/AI_Teaching_Studio_Architecture.drawio](docs/AI_Teaching_Studio_Architecture.drawio)
  — system overview, ingestion, tutor, AI router, lessons & simulation checks, 3D chemistry, code map, teacher
  workflow. Open in draw.io (app.diagrams.net → *Open from → Device*). Rebuild: `uv run python docs/_source/gen_drawio.py`.
- **Code workflow & technology stack (one draw.io page):** [docs/AI_Teaching_Studio_Code_Workflow.drawio](docs/AI_Teaching_Studio_Code_Workflow.drawio)
  — every tool/library with version and purpose, and the end-to-end flow as *file → function() → what it does*
  (102 steps in 11 lanes). Rebuild: `uv run python docs/_source/gen_code_workflow.py`.
- **Learning log:** [docs/Claude Interactions.docx](docs/Claude%20Interactions.docx) — every change, the key code
  and why, and every issue/mistake with cause and fix (updated in every session).
- **Status:** Phase 0 ✅ · Phase 1 ✅ (+ improvements) · **Phase 2 ✅ built — 3 pilot lessons ready for your review**
  (section 3c) · **3D Chemistry Lab ✅** (section 3d) · **History lessons ✅** (section 3e) · next: geography,
  physics, maths designs and Phase 3 (animated videos & narration).

**Contents:** 1 One-time setup · 2 Start / stop · 3 Test Phase 1 with your PDF · 3b Better tables & diagrams ·
3c Lessons & simulations (Phase 2) · 3d 3D Chemistry Lab · 3e History lessons · 4 Teaching with the app · 5 Adding more chapters · 6 Models & budget ·
7 Security rules · 8 Development · 9 Troubleshooting

---

## 1. One-time setup

Already installed on this laptop: uv 0.12.11 · Python 3.12.14 (via uv) · Git 2.51 · Ollama 0.34.4 · FFmpeg 9.0.2 · MiKTeX 25.12.

Open a terminal **in this project folder** and run:

| # | Step | Command |
|---|---|---|
| 1 | Download the local AI models (free) | `ollama pull qwen3:4b-instruct` · `ollama pull qwen3-vl:2b-instruct` · `ollama pull qwen3-embedding:0.6b` |
| 2 | Install packages **only from the lockfile** (every SHA-256 hash checked) | `uv sync --locked` |
| 3 | Create your settings file (it holds no secrets) | `copy .env.example .env` |
| 4 | *(Optional — for paid OpenAI features)* store your key in Windows Credential Manager | `uv run python -m app.core.secrets set openai` |
| 5 | Security checks — every line must say `OK` | `uv run python -m app.core.startup_checks` |
| 6 | Check that every configured model is available | `uv run python -m app.tools.verify_models` |

> For step 4: in the OpenAI dashboard create a separate Project (e.g. "ai-teaching-studio") with its own restricted
> key and a **monthly budget limit**. Never paste keys into `.env`, any file, chat or screenshots.
> Everything in Phase 1 works **without** an OpenAI key (only Hindi/Marathi answers are better with it).

## 2. Start / stop the app

1. Make sure the **Ollama** app is running (tray icon).
2. Start: `uv run streamlit run ui/Home.py` → the browser opens **http://localhost:8501** (only this laptop can open it).
3. Stop: `Ctrl + C` in the terminal. Unfinished background work resumes automatically next time.

| Page | What it is for |
|---|---|
| Home | Security checks, models, library totals, monthly spend |
| Syllabus Library | Add textbook files, watch processing, edit chapter details |
| Review Text | Compare each page image with its extracted text, correct it, approve it |
| AI Tutor | Questions answered from your approved pages, with page references |
| Settings & Cost | Budget, API keys, model routing, ingestion settings, log of every AI call and its cost |
| Lesson Studio | Create lessons from your textbook, check/edit them, preview simulations, approve |
| Teach Mode | Present an approved lesson full-screen: slides, equations, 3D molecules, 3D bonding/reaction scenes, simulation, key points |
| 3D Chemistry Lab | Watch electrons being given, taken and shared, and atoms changing partners — any formula or equation |

> **After updating the code, always restart the app** (`Ctrl + C`, then start again). An app left running from
> before an update keeps the old code in memory (this caused two failed lesson jobs once; workers now ignore
> job types they do not know).

---

## 3. Test Phase 1 with your PDF (step by step)

**A. Add the file** (either way works; the same file is never processed twice, even if renamed)
1. Copy the PDF / photos / DOCX into the **`source`** folder of this project, **or**
2. In the app open **Syllabus Library → ➕ Add files**, choose the files, fill *Class / Subject / Chapter*
   (or leave blank — they are guessed from names like *Class 9 - Science - 5th Chapter.pdf*), click **Add & process**.

**B. Wait for extraction** — Syllabus Library shows a progress bar (updates every 3 s).
- Pages with real text are read instantly; scanned pages are OCR'd by the local model, **≈ 15–40 s per page**
  (measured: a 17-page scanned chapter took ≈ 9 minutes, $0). You can keep using other pages of the app meanwhile.
- Status changes to **📝 needs review** when done.

**C. Review the text** — open **Review Text**:
1. Pick the document. Left: the page image. Right: the extracted text — **✏️ Edit** tab to correct it,
   **👁️ Preview** tab to see tables displayed as real tables (the `|` signs are table borders).
2. Fix any mistakes — check **formulas (H₂SO₄), numbers, units and diagram labels** carefully.
   If a table or diagram was read badly, use **☁️ Re-read this page with the cloud model** (section 3b).
   A page marked **⚠️** had OCR trouble (e.g. the model repeated a line; repeats were removed) — compare it
   with the image line by line, or click **Retry this page**.
3. Click **✅ Save & mark reviewed → next** for each page.
   (*Mark ALL reviewed* exists, but use it only after you have actually checked the pages.)

**D. Make it searchable** — click **Make reviewed pages searchable** (Review Text or Syllabus Library).
Status becomes **✅ searchable** after a few seconds.

**E. Ask questions** — open **AI Tutor** → *My textbook*:
1. Optionally filter Class / Subject / Chapter.
2. Ask, e.g. *"What is an ionic bond?"* — the answer cites pages like **[1] Ch. 5, page 2**; open the source
   boxes under the answer to see the exact textbook passages.
3. Ask something **not** in the chapter (e.g. *"Who discovered gravity?"*) — it must reply
   *"This is not covered in the uploaded textbook pages."* (turn on the toggle only if you want a clearly
   marked general answer).
4. Choose **Hindi** or **Marathi** only when a student asks — scientific terms stay in English in brackets.
5. **Answer model:** *Local (free)* is fine for normal questions. For questions about **tables** choose
   *Cloud gpt-5-nano* (≈ $0.001 per answer) — measured: the local model missed a table answer that the cloud
   model got right.
6. **Reuse answers to very similar questions** (on by default): a question that means the same as an earlier
   one is answered instantly from memory, marked ♻️. It never reuses across different chapters/languages, after
   pages change, or when the questions differ by words like *cathode/anode, strong/weak, acid/base*.
   Turn it off for a fresh answer.

**F. Check costs** — Settings & Cost → *Recent AI calls*: local models always show **$0**.

**Same steps without the browser (command line):**
```
uv run python -m app.ingestion scan            # register new files in source/ and extract them
uv run python -m app.ingestion status          # progress of every document
uv run python -m app.ingestion approve 1       # mark all pages of document 1 reviewed (after checking!)
uv run python -m app.ingestion index 1         # make reviewed pages searchable
uv run python -m app.ingestion ask "What is an ionic bond?"
uv run python -m app.ingestion reindex 1       # rebuild search entries (adds page summaries/descriptions)
uv run python -m app.ingestion cloud 1         # cloud re-read of pages with tables (or: --pages 4,5)
uv run python -m app.ingestion clean 1         # apply the latest OCR clean-up to pages you have NOT edited
```

## 3b. Better tables & diagrams (optional, small cost)

The free local OCR reads normal text well, but sometimes misaligns tables or invents details in diagram
descriptions. Measured on your chapter (pages 3, 4, 5, 16):

| Reader | Tables & subscripts | Speed | Cost |
|---|---|---|---|
| Local `qwen3-vl:2b-instruct` | text good; tables sometimes misaligned (auto-repaired for display) | 30–110 s/page | $0 |
| Cloud `gpt-5.4-mini` | all subscripts and tables correct, honest figure lines | 3–4 s/page | ≈ $0.005/page (≈ 8–9 ¢ per chapter) |

- **One page:** Review Text → open the page → **☁️ Re-read this page with the cloud model**.
- **Several pages:** Syllabus Library → *Manage a document* → **☁️ Better tables & diagrams** → *Pages with tables*
  or *All OCR pages* (cost shown before you click).
- Re-read pages **replace the text (including your edits)** and must be **reviewed again**, then made searchable.
- Costs count towards your monthly budget and appear in Settings & Cost.

**Page summaries & descriptions (automatic, free):** when pages are made searchable, the local model also writes a
short summary of each page and a description of each table and figure. These only help **find** the right page —
the tutor always answers from your **original reviewed text** (a generated description once mixed up "acidity" and
"basicity", so it is never shown to the tutor as fact). Pages indexed before this feature: Syllabus Library →
*More…* → **Re-index searchable pages** (free, ~20 s per page).

## 3c. Lessons & simulations (Phase 2) — step by step

**Your 3 pilot lessons are already generated** (from Chapter 5, as drafts): *Neutralization Reaction*,
*Electrolysis of Water*, *Water of Crystallisation* (≈ 2 ¢ each, ≈ 20 s each).

**A. Review a lesson** — **Lesson Studio** → *Open lesson*:
1. **📄 Content** — title, objectives, sections (each shows its textbook pages), key points. Edit anything and click
   **💾 Save changes** (the version number goes up; equations are re-checked).
2. **⚗️ Equations & molecules** — ✅ = balanced in atoms *and* charge (checked by the app, not by the AI);
   ⚠️ = not balanced, with the exact reason. Molecules can be rotated in 3D (drag) and zoomed (scroll).
   **Every atom is labelled with its symbol and charge** (e.g. Cu²⁺, O⁻, H); **ionic compounds are shown as separate
   ions side by side**, each with its formula and charge in a blue tag (e.g. Cu²⁺ and SO₄²⁻); a legend gives the
   full element names (Cu = Copper …). Switch *Atom labels* off for a cleaner picture (also in Teach Mode's sidebar).
3. **🎬 3D bonding & reactions** — step-by-step 3D scenes made from the lesson's molecules and equations
   (section 3d). Add more with *Add a formula or an equation* (e.g. `MgO`, `2H₂O → 2H₂ + O₂`).
4. **🧪 Simulation** — try the interactive experiment. Check that what happens matches your textbook
   (e.g. H₂ : O₂ = 2 : 1; blue vitriol turns white on heating). Not right? Type a **Change request**
   (e.g. *"show the pH number bigger"*) and click **Regenerate** (≈ 2–4 ¢).
5. **📚 Textbook sources** — the exact passages the lesson was written from.
6. Click **✅ Approve for Teach Mode**. (Any edit, including adding a 3D scene, makes it a draft again.)

**B. Create a new lesson** — Lesson Studio → **➕ New lesson** → choose the chapter → type a topic → **Create lesson**.
It appears in the list within about a minute (plan first, then the simulation).

**C. Present it** — **Teach Mode** → pick the lesson → **Next ▶ / ◀ Previous**. Press **F11** for full screen and
collapse the sidebar. Slides: title & objectives → sections → equations → 3D molecules → 3D bonding/reaction scenes
→ simulation → key points (switch the 3D scenes off in the sidebar if not needed).
(To present a draft, switch on *Also show draft lessons* in the sidebar.)

**How simulations are built (lab kit):** the layout is not left to the AI. A hand-written *lab kit*
(`assets/labkit.js`) fixes the screen into areas — title at the top, the experiment on the left, the **readings
panel** on the right, the **Observe** bar at the bottom — and writes every label through one function that **moves a
label automatically if it would overlap another** (with a thin line to what it labels) and puts a white background
behind it, so scale lines never cross text. The AI only describes the experiment. The app rejects (and sends back
to the AI to fix) any simulation that writes text directly, or whose buttons do not start a **visible animation**
(e.g. *Stir* must move the glass rod in circles and swirl the liquid, *Add drop* must show the drop falling).
Simulations made before the lab kit still work; click **Regenerate** to rebuild them with it.

**Ready-made apparatus (added 7 Oct 2026):** the kit also contains hand-drawn, checked glassware (beaker, test tube,
inverted gas tube, burner, tripod, dish, dropper, glass rod, electrodes, battery, wires, bubbles, pH paper,
thermometer) and **complete setups** for *electrolysis of water*, *heating on a tripod*, *does it conduct?* and
*neutralisation* (indicator and pH-paper colours come from the school colour charts). The AI places and switches
them instead of drawing glassware line by line.

**How the checks work (5 steps):** the AI writes only the simulation's code. Before you see it:
1. **safety** — no internet, no storage, no access to the app around it;
2. **lab-kit rules** — labels only through the kit, controls only through the kit's buttons/lists, every control animated;
3. **syntax** — Node.js reads the code;
4. **run in a hidden browser** — the app opens the simulation in an invisible Edge/Chrome window and **presses every
   button, picks every list choice and moves every slider**; any error, or a control that changes nothing, is a problem
   (this is the check that catches crashes like the old *Electrolysis* "reading 'option'" error);
5. **picture review** — pictures at the start and during/after each control go to a vision model (gpt-5.4-mini,
   ≈ 1–2 ¢) that compares them with the textbook facts (glassware the right way up, liquids inside containers,
   battery outside the water, blue vitriol blue before heating …).

Problems are sent back to the AI to fix (up to 3 times). If only picture-review notes remain, the simulation is
shown with the notes in a blue box for you to judge. Typical cost: 2–12 ¢ per simulation. It runs in a sealed frame
that cannot connect to the internet; the drawing libraries are stored inside the project and verified by their
fingerprint, so lessons work offline. **Your preview is still the final check** — use *Change request* + *Regenerate*.

## 3e. History lessons (timeline, map, causes & effects) — step by step

Works for chapters whose subject is **History** (also Civics / Political Science / Economics). Tested end to end on
*Class 9 – History – Chapter 4 "Economic Development"*.

1. **Add the chapter** — copy the PDF into `source/` (name like `Class 9 - History - 4th Chapter.pdf`, so class,
   subject and chapter are filled in) or upload it on **Syllabus Library**.
   Two-column pages are read **in reading order** (left column, then right; "Do you know?" boxes kept whole).
2. **Review Text** → check each page → **✅ Save & mark reviewed** → **Make reviewed pages searchable**.
3. **Lesson Studio → ➕ New lesson** → choose the chapter → topic, e.g. *Economic Development* → **Create lesson**
   (≈ 1–2 ¢; for a chapter the AI reads the **whole chapter**, in page order).
4. Check the tabs:
   - **🕰️ Timeline** — every dated event, oldest first, and the **periods** (e.g. the five-year plans) as coloured
     bars plus a table (like the textbook's exercise chart). *Every date is checked against your pages: the date's
     numbers and month, and the event's words, must appear together in the textbook; anything else is removed and
     listed in the yellow warnings.*
   - **🗺️ Map** — the places of the chapter on a map of India (India's official boundaries; offline). A place is put
     on the map only when it is certain (e.g. there are 8 places called *Sindri* — the AI must say "Jharkhand" or
     "near Dhanbad"). Places that could not be placed are listed with the reason: type a **hint** (state or nearby
     city) or the **position** (`23.65, 86.48`) and click **📍 Save and place again**.
   - **🔗 Causes & effects** — for 2–4 key events: causes → event → effects, revealed one by one.
   - **👤 People & pictures** — who's who (with the textbook's own portrait when its caption is the person's
     name) and **the pictures from your textbook with their printed captions**.
   - **📚 Textbook sources** — the passages the lesson was written from.
5. **✅ Approve** → **Teach Mode** slides: title → sections → timeline → map → causes & effects → people →
   textbook pictures → key points. In every history view: **Next ▶ / ◀ Back / ▶ Play / ⏭ All**, keys ← → Space.

Map data: Natural Earth (public domain, India point-of-view boundaries) and GeoNames (CC BY 4.0) — stored in
`assets/geo/` (SHA-256 checked); rebuilt only with `uv run python scripts/build_geo.py <download folder>`.
The first map after installing takes ≈ 10 s once (builds `data/geo_places.db`).

## 3d. 3D Chemistry Lab — electrons and atoms in motion (free, no AI)

Open **3D Chemistry Lab** (or the **🎬 3D bonding & reactions** tab of a lesson, or the Teach Mode slides). Click an
example or type any formula / equation (plain text works: `H2O`, `2H2 + O2 -> 2H2O`). Use **▶ Play** or
**Next ▶ / ◀ Back** (keys → ← and Space), drag to turn, scroll to zoom, *Slow / Normal / Fast*, *Shells* on/off.

| Kind | Examples | The 4 steps |
|---|---|---|
| **Ionic bond — electron transfer** | NaCl, MgO, CaCl₂, Na₂O, Al₂O₃, Li₃N | atoms with shells (2, 8, 1 …) and valency → the metal's outer electron(s) **jump** to the non-metal → ions Na⁺ / Cl⁻ with protons vs electrons → ions attract (ionic bond) |
| **Covalent bond — sharing** | H₂, O₂, N₂, Cl₂, HCl, H₂O, NH₃, CH₄, CO₂, C₂H₄ | atoms and what each needs → outer shells overlap → **shared pairs, one electron from each atom** → every atom has a full shell (8, or 2 for H) |
| **Reaction — atoms rearrange** | HCl + NaOH → NaCl + H₂O, 2H₂ + O₂ → 2H₂O, CuSO₄·5H₂O → CuSO₄ + 5H₂O, half-equations with e⁻ | reactants and atom count → old bonds break (dashed) → atoms move to new partners, charges change → products; same atoms and same total charge |

- **Electrons keep the colour of the atom they came from** (e.g. sodium's electron stays amber inside Cl⁻), so
  students can see who gave and who shared.
- Everything is **calculated**, not drawn by AI: shells from the atomic number (2, 8, 8, 2 rule), bonds from the
  checked molecule table, atoms from the balanced equation. Anything it cannot show (e.g. H₂SO₄ — sulphur would have
  12 outer electrons; an unbalanced equation; a substance not in the table) gets a **clear reason** instead of a
  guessed picture. Shells are shown for the first 20 elements (Class 9 scope).

**About free image/3D AI models (Gemini, GPT-4o images, FLUX, Stable Diffusion, Leonardo, Stable Video 3D):** they
make pictures, not exact science — they often draw the wrong number of electrons, wrong charges or garbled labels,
and the pictures are not interactive. Stable Video 3D needs about 20 GB of graphics memory (your laptop has 4 GB).
So they are **not used** for chemistry diagrams; they could be added later only for clearly-marked decorative
illustrations (blueprint D33).

---

## 4. Teaching with the app (class day)

**Before class (10 minutes)**
1. Start Ollama and the app (section 2).
2. On **Syllabus Library**, check the chapter you will teach shows **✅ searchable**.
3. On **AI Tutor**, set the Class / Subject / Chapter filter and ask one test question.

**In class**
1. Teach as usual. When a student asks a doubt, type it into **AI Tutor**.
2. Read the answer **and** show the page reference so students open the same page in their book.
3. If a student needs it in Hindi / Marathi, switch the answer language for that question, then back to English.
4. If the answer says *not covered*, the topic is not in the uploaded pages — explain it yourself or add the chapter.

**After class**
- Note questions the tutor answered poorly; check those pages on **Review Text** (the text may need correcting).
- Add the next chapter (section 5) so it is ready for the next class.

## 5. Adding more chapters

- Drop new files into `source/` (or upload them). Opening **Syllabus Library** processes them automatically.
- Re-adding the same file (even renamed) is detected by its content fingerprint and skipped; identical pages and
  identical passages are also stored only once.
- Fix wrong Class/Subject/Chapter on **Syllabus Library → Manage a document → Save details**, then click
  *Index reviewed pages* again.
- A page that failed: open it on **Review Text** → **Retry this page**.

---

## 6. Models and budget

- **Models:** [config/models.yaml](config/models.yaml) maps each task to a model and fallbacks. After editing, click
  **Reload configuration** on *Settings & Cost*.
  - OCR: `qwen3-vl:2b-instruct` (local) · cloud re-read: `gpt-5.4-mini` (only when you click it) ·
    search: `qwen3-embedding:0.6b` (local) · page summaries: `qwen3:4b-instruct` (local) ·
    answers: `qwen3:4b-instruct` (local) or `gpt-5-nano` (cloud switch) · Hindi/Marathi: `gpt-5.4-mini`.
  - Do **not** use plain `qwen3:4b` / `qwen3-vl:4b`: they are "thinking" models (5–15× slower).
- **Budget:** `ATS_MONTHLY_BUDGET_USD` in `.env` (default **$5/month**). At the cap, paid models are skipped and local
  models answer. Premium models are never used without your approval.
- **Ingestion settings** (in `.env`, restart after changing): `ATS_SOURCE_DIR`, `ATS_AUTO_INGEST`,
  `ATS_REQUIRE_REVIEW`, `ATS_OCR_MAX_IMAGE_PX`, `ATS_PDF_TEXT_MIN_WORDS`, `ATS_ENRICH_PAGES` (page summaries),
  `ATS_SEMANTIC_CACHE` / `ATS_SEMANTIC_CACHE_MIN` (reuse answers, default threshold 0.97) — current values are
  shown on *Settings & Cost*, which also has **Forget all reused answers**.

## 7. Security rules (blueprint §14) — always

- ✅ Install with `uv sync --locked` only. ❌ Never `pip install …` into this project.
- ✅ API keys only in Credential Manager. ❌ Never in `.env`, code, `*.key` files, chat or screenshots.
- ✅ LiteLLM pinned to a clean version ≥ 1.83.0 (now **1.102.1**); 1.82.7 / 1.82.8 were malicious.
- ✅ AI calls only to hosts in `allowed_hosts` (`config/models.yaml`).
- ✅ Your textbook files (`source/`) and data (`data/`) stay on this laptop — both are excluded from Git.
- ✅ Vulnerability audit before upgrades and at the end of each phase: `powershell -ExecutionPolicy Bypass -File scripts\audit.ps1`

**Upgrading a package (one at a time):** read its changelog/advisories → move `exclude-newer` in `pyproject.toml` to
*today − 7 days* and change its exact `==` version → `uv lock --upgrade-package <name>` → review `uv.lock` →
`uv sync --locked` → `scripts\audit.ps1` → `uv run pytest`.

## 8. Development

```
uv run pytest            # 270 automated tests (offline, no cost; browser tests use Edge/Chrome if present)
uv run ruff check .      # lint
uv run ruff format .     # format
```

```
app/core/       settings, secrets (Credential Manager), logging with key redaction, security checks
app/db/         SQLite tables (documents, pages, passages+vectors, jobs, AI call log, caches) + migrations
app/ingestion/  file types & hashing, extraction (text layer / OCR / cloud re-read), table repair,
                page summaries, chunking, pipeline, CLI
app/rag/        vector store (SQLite + NumPy), textbook-grounded tutor, similar-question answer cache
app/lessons/    lesson planner, equation checker, molecules (RDKit), simulations (checks), viewers,
                browser_check.py (hidden-browser test), reactions.py (3D bonding & reaction scenes),
                history.py (history facts + checks), geo.py (offline map), figures.py (textbook pictures)
app/jobs/       background worker (resumable job queue)
assets/vendor/  offline p5.js and 3Dmol.js (pinned, SHA-256 verified; see manifest.json)
assets/labkit.js  hand-written simulation kit: layout, labels that never overlap, animation, apparatus, setups
assets/labkit_example.js  hand-checked example experiment shown to the AI
assets/chem3d.js  hand-written 3D chemistry player (no library)
assets/historykit.js  hand-written timeline / map / cause-effect player
assets/geo/     offline map outlines (Natural Earth, India view) + places (GeoNames), SHA-256 checked
scripts/build_geo.py  rebuilds assets/geo from the downloaded sources (rarely needed)
app/llm/        model router (fallbacks, budget, cache, allow-list) — the only LiteLLM import
config/         models.yaml
ui/             Streamlit app: Home.py + pages/
source/         your textbook files (not in Git)
data/           database and logs (not in Git)
docs/           blueprint (.docx), diagrams, doc generators
```

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| "Ollama is not running" | Start the Ollama app, then refresh |
| A ❌ security check on Home | Read the message; for a LiteLLM version problem run `uv sync --locked` |
| Processing seems stuck | Syllabus Library shows the running job. Closing the app is safe — it resumes later |
| OCR is very slow (> 1 min/page) | Make sure `config/models.yaml` uses `qwen3-vl:2b-instruct`, and close other GPU-heavy apps |
| Tutor says "not covered" for a topic that is in the book | Is the page reviewed **and** searchable? Is the chapter filter right? Is the OCR text of that page correct? For table questions, switch the answer model to *Cloud* |
| A reused (♻️) answer is not what you wanted | Turn off *Reuse answers…* and ask again, or Settings & Cost → *Forget all reused answers* |
| A table looks broken in the Edit tab | Check the **Preview** tab; if it is still wrong, use the cloud re-read for that page |
| A lesson shows ❌ failed | Read the note (e.g. no reviewed pages match the topic); use words from the textbook in the topic, or review/index the chapter first |
| Labels in a simulation overlap, or a button does nothing visible | It was made before the lab kit — click **Regenerate**. Still wrong? Add a **Change request** describing what to fix |
| A red "Simulation error" appears inside the experiment | The AI code failed while running — click **Regenerate** (new simulations are run in a hidden browser first, so this should no longer reach you) |
| Simulation shows a warning instead of the experiment | It failed the checks after 3 automatic fixes — click **Regenerate**, optionally with a change request |
| A blue "picture review noted …" box above a simulation | The simulation works; the automatic picture check still saw something — look yourself, then approve or regenerate |
| Simulations are not tested in a browser | Settings & Cost shows the browser used; set `ATS_BROWSER_PATH` in `.env` if Edge/Chrome is installed elsewhere |
| A history page's text is in the wrong order | Re-extract it (Review Text → **Retry this page**) — two-column pages are read left column first since 7 Oct 2026 |
| A place is missing from the map | Map tab → type a hint (state or nearby city, e.g. *Dhanbad* for Sindri, *Chennai* for Perambur) or `lat, lon` → **📍 Save and place again** |
| A timeline date was "removed" (yellow warning) | The date and the event were not found together in your pages — check the page; add it to a section yourself if it is right |
| 3D Chemistry Lab says it cannot show something | Read the reason (not balanced / not in the table / expanded octet); ask Claude to add a molecule to the table |
| A molecule says "not available" | It is not in the local molecule table (`app/lessons/molecules.py`) yet — tell Claude which one to add |
| A lesson job failed with "Unknown job kind" | The app was started before a code update — restart it |
| OpenAI answers are skipped | No key stored, budget reached, or model not available to your key (`verify_models`) |
| First answer is slow (~15 s) | Model loading into GPU memory; later answers are faster |


My Own written notes :-
linked the map from the README;
recorded this change in docs/Claude Interactions.docx, now 11 entries;
added a small script, docs/_source/gen_drawio.py, that rebuilds the map when the code changes: uv run python docs/_source/gen_drawio.py.


uv run streamlit run ui/Home.py
