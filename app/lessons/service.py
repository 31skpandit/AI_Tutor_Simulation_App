"""Lessons: create → plan (background) → simulation (background) → teacher edits → approve → Teach Mode."""

import json
from collections.abc import Callable

from loguru import logger
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.core.config import get_settings
from app.db.models import Document, Job, Lesson, MediaAsset, Page, utcnow
from app.lessons.planner import MIN_RELEVANCE, PlanningError, plan_lesson, simulation_facts
from app.lessons.simulation import check_runtime, check_sketch, generate_simulation
from app.llm.router import AllModelsFailed, LLMRouter
from app.rag.store import SearchFilters, VectorStore

Progress = Callable[[float, str], None]


REAL_LIFE_PROMPT = """You help a school teacher in India show where a maths idea is used in daily life.
For the concept given, return ONE JSON object: {"real_life": [ {"title": "short title",
 "story": "2-3 simple sentences: where, why and how this idea is used (with a small worked number example if natural)",
 "image_query": "a concrete thing to photograph (see rules)"} ]}
Give exactly 2 NEW examples (not in 'already_used') from everyday Indian life (market, school, railway, cricket,
kitchen, buildings, roads, clocks, festivals). They must be mathematically correct.
image_query: 2-4 words naming ONE concrete thing a camera can photograph, as a Wikimedia Commons file would be titled (good: 'railway level crossing', 'wall clock', 'floor tiles pattern', 'cricket pitch', 'tailor cutting cloth'; bad: abstract ideas like 'number chart', 'timetable', 'math puzzle', 'sharing'); use \"\" when nothing concrete fits. Output the JSON object only."""


def photo_queries(plan: dict, include_done: bool = False) -> list[tuple[dict, dict]]:
    """(concept, real-life example) pairs that have a photo search phrase (and no photos yet, unless include_done)."""
    pairs = []
    for concept in plan.get("concepts", []) or []:
        for item in concept.get("real_life", []) or []:
            if isinstance(item, dict) and str(item.get("image_query", "")).strip():
                if include_done or "photos" not in item:
                    pairs.append((concept, item))
    return pairs


def _noop(_fraction: float, _message: str) -> None:
    pass


def chapter_topic(document: Document) -> str:
    """The topic of a whole-chapter lesson: the chapter title, else 'Chapter N', else the file name."""
    if document.chapter_title:
        return document.chapter_title
    if document.chapter_no:
        return f"Chapter {document.chapter_no}"
    return document.filename.rsplit(".", 1)[0]


class LessonService:
    def __init__(
        self, engine: Engine, router: LLMRouter, min_relevance: float = MIN_RELEVANCE, settings=None
    ):
        self.settings = settings or get_settings()
        self.engine = engine
        self.router = router
        self.store = VectorStore(engine)
        self.min_relevance = min_relevance

    # ------------------------------------------------------------ create / read
    def create(self, topic: str, *, document_id: int | None = None, chapter_no: int | None = None) -> Lesson:
        topic = topic.strip()
        if not topic:
            raise ValueError("Please enter a topic.")
        lesson = Lesson(topic=topic, document_id=document_id, chapter_no=chapter_no, title=topic)
        with Session(self.engine) as s:
            s.add(lesson)
            s.commit()
            s.refresh(lesson)
        self.enqueue("lesson_plan", lesson.id)
        return lesson

    def auto_create_for_document(self, document_id: int) -> list[Lesson]:
        """Autopilot: one lesson per chapter (a file may hold several), once, as soon as pages are searchable."""
        with Session(self.engine) as s:
            document = s.get(Document, document_id)
            if document is None or s.exec(select(Lesson).where(Lesson.document_id == document_id)).first():
                return []
            indexed = s.exec(
                select(Page).where(Page.document_id == document_id, col(Page.indexed).is_(True))
            ).first()
        if indexed is None:
            return []
        chapters = self.chapters_of(document_id) or [
            {"no": document.chapter_no, "title": chapter_topic(document)}
        ]
        created = []
        for chapter in chapters:
            logger.info(f"Autopilot: creating the lesson '{chapter['title']}' for document {document_id}")
            created.append(self.create(chapter["title"], document_id=document_id, chapter_no=chapter["no"]))
        return created

    def chapters_of(self, document_id: int) -> list[dict]:
        """The chapters inside one file, with page ranges (empty when the file is a single chapter)."""
        from app.ingestion.quality import find_chapters

        with Session(self.engine) as s:
            pages = s.exec(select(Page).where(Page.document_id == document_id)).all()
        return find_chapters([(p.page_no, p.text) for p in pages])

    def page_range(self, lesson: Lesson) -> tuple[int, int] | None:
        """First and last textbook page of the lesson's chapter when its file holds several chapters."""
        if not lesson.document_id:
            return None
        for chapter in self.chapters_of(lesson.document_id):
            same_title = chapter["title"].strip().lower() == lesson.topic.strip().lower()
            if same_title or (lesson.chapter_no is not None and chapter["no"] == lesson.chapter_no):
                return chapter["start"], chapter["end"]
        return None

    def pages_added_after(self, lesson: Lesson) -> list[int]:
        """Searchable pages of the lesson's chapter that the lesson plan did not use (e.g. reviewed later)."""
        if not lesson.document_id:
            return []
        used = {src.get("page") for src in self.plan(lesson).get("sources", [])}
        if not used:
            return []
        from app.lessons.history import without_exercises  # exercise passages are never lesson material
        from app.rag.tutor import EMBED_TASK

        hits = self.store.document_text_hits(lesson.document_id, self.router.config.tasks[EMBED_TASK].primary)
        first, last = self.page_range(lesson) or (0, 10**6)
        return sorted({h.page_no for h in without_exercises(hits) if first <= h.page_no <= last} - used)

    def get(self, lesson_id: int) -> Lesson:
        with Session(self.engine) as s:
            lesson = s.get(Lesson, lesson_id)
        if lesson is None:
            raise KeyError(f"Lesson {lesson_id} not found")
        return lesson

    def lessons(self, status: str | None = None) -> list[Lesson]:
        with Session(self.engine) as s:
            query = select(Lesson).order_by(col(Lesson.id).desc())
            if status:
                query = query.where(Lesson.status == status)
            return list(s.exec(query).all())

    @staticmethod
    def plan(lesson: Lesson) -> dict:
        return json.loads(lesson.plan_json or "{}")

    # ------------------------------------------------------------ background work
    def enqueue(self, kind: str, lesson_id: int, options: str = "") -> Job:
        with Session(self.engine) as s:
            existing = s.exec(
                select(Job).where(
                    Job.kind == kind, Job.lesson_id == lesson_id, col(Job.status).in_(["queued", "running"])
                )
            ).first()
            if existing:
                return existing
            job = Job(kind=kind, document_id=0, lesson_id=lesson_id, options=options)
            s.add(job)
            s.commit()
            s.refresh(job)
            return job

    def generate_plan(self, lesson_id: int, progress: Progress = _noop) -> dict:
        lesson = self.get(lesson_id)
        progress(0.1, "Finding the textbook passages for this topic")
        filters, class_level, subject, whole_chapter = None, "", "", False
        if lesson.document_id:
            with Session(self.engine) as s:
                document = s.get(Document, lesson.document_id)
            if document:
                filters = SearchFilters(document_ids=(document.id,))
                class_level, subject = document.class_level, document.subject
                whole_chapter = lesson.topic.strip().lower() == chapter_topic(document).strip().lower()
        pages = self.page_range(lesson)  # a file with several chapters: only this chapter's pages
        whole_chapter = whole_chapter or pages is not None
        try:
            progress(0.3, "Writing the lesson plan")
            result = plan_lesson(
                self.router,
                self.store,
                lesson.topic,
                filters=filters,
                class_level=class_level,
                subject=subject,
                min_relevance=self.min_relevance,
                whole_chapter=whole_chapter,
                pages=pages,
            )
        except (PlanningError, AllModelsFailed, json.JSONDecodeError) as exc:
            self._update(lesson_id, status="failed", error=str(exc)[:500])
            raise
        self._update(
            lesson_id,
            status="draft",
            title=result.plan.get("title") or lesson.topic,
            plan_json=json.dumps(result.plan, ensure_ascii=False),
            warnings=json.dumps(result.warnings),
            model_ref=result.model_ref,
            cost_usd=lesson.cost_usd + result.cost_usd,
            error=None,
        )
        progress(1.0, "Lesson plan ready")
        if result.plan.get("simulation", {}).get("brief"):
            self.enqueue("simulation", lesson_id)
        if photo_queries(result.plan) and self.settings.media_search:
            self.enqueue(
                "media", lesson_id
            )  # real photos for the real-life examples (free sources, checked locally)
        return {"warnings": len(result.warnings), "sections": len(result.plan.get("sections", []))}

    def generate_simulation(self, lesson_id: int, instruction: str = "", progress: Progress = _noop) -> dict:
        lesson = self.get(lesson_id)
        plan = self.plan(lesson)
        sim = plan.get("simulation") or {}
        brief = f"{sim.get('title', lesson.title)}: {sim.get('brief', '')}".strip(": ")
        if not brief:
            raise ValueError("The lesson plan has no simulation idea.")
        self._update(lesson_id, simulation_status="generating")
        progress(0.2, "Writing the simulation")
        try:
            result = generate_simulation(self.router, brief, simulation_facts(plan), instruction)
        except AllModelsFailed as exc:
            self._update(
                lesson_id, simulation_status="failed", simulation_problems=json.dumps([str(exc)[:300]])
            )
            raise
        self._update(
            lesson_id,
            simulation_js=result.code,
            simulation_status="ok" if result.ok else "failed",
            simulation_problems=json.dumps(result.problems),
            cost_usd=self.get(lesson_id).cost_usd + result.cost_usd,
        )
        progress(1.0, "Simulation ready" if result.ok else "Simulation needs attention")
        return {"ok": result.ok, "fix_rounds": result.rounds, "problems": len(result.problems)}

    def find_photos(self, lesson_id: int, progress: Progress = _noop, finder=None) -> dict:
        """Real, freely licensed photos for every real-life example (Wikimedia Commons / Wikidata / Openverse),
        each checked by the local vision model. Asset ids are stored in the plan: real_life[i]["photos"]."""
        from app.media.finder import MediaFinder

        settings = self.settings
        finder = finder or MediaFinder(self.router, self.engine, settings)
        wanted = photo_queries(self.plan(self.get(lesson_id)))
        found = {}
        for number, (concept, item) in enumerate(wanted):
            progress(0.05 + 0.9 * number / max(1, len(wanted)), f"Finding a photo: {item['image_query']}")
            assets = finder.find(
                item["image_query"], concept=concept.get("name", ""), lesson_id=lesson_id,
                keep=settings.media_per_example,
            )  # fmt: skip
            found[(concept.get("name"), item.get("title"))] = [a.id for a in assets]
        # the teacher may have edited the plan meanwhile: write only the photo ids into the current version
        current = self.plan(self.get(lesson_id))
        for concept, item in photo_queries(current, include_done=True):
            key = (concept.get("name"), item.get("title"))
            if key in found:
                item["photos"] = found[key]
        self._update(lesson_id, plan_json=json.dumps(current, ensure_ascii=False))
        with_photos = sum(1 for ids in found.values() if ids)
        progress(1.0, f"Photos found for {with_photos} of {len(wanted)} examples")
        return {"examples": len(wanted), "with_photos": with_photos}

    def add_real_life(self, lesson_id: int, concept_name: str, progress: Progress = _noop) -> dict:
        """'More real-life examples' button: 2 new everyday examples for one concept (≈ 0.2 ¢), then photos."""
        from app.lessons.planner import PLAN_TASK, parse_json_object

        concept = next(
            (c for c in self.plan(self.get(lesson_id)).get("concepts", []) if c.get("name") == concept_name),
            None,
        )
        if concept is None:
            raise ValueError(f"No concept '{concept_name}' in this lesson.")
        known = [r.get("title", "") for r in concept.get("real_life", [])]
        progress(0.2, f"Thinking of real-life examples for {concept_name}")
        result = self.router.complete(
            PLAN_TASK,
            [
                {"role": "system", "content": REAL_LIFE_PROMPT},
                {"role": "user", "content": json.dumps(
                    {"concept": concept_name, "explanation": concept.get("explain", ""), "already_used": known},
                    ensure_ascii=False)},
            ],
        )  # fmt: skip
        new = [
            r for r in parse_json_object(result.text).get("real_life", [])
            if isinstance(r, dict) and r.get("title") and r.get("title") not in known
        ][:2]  # fmt: skip
        current = self.plan(self.get(lesson_id))  # re-read: the teacher may have edited meanwhile
        for item in current.get("concepts", []):
            if item.get("name") == concept_name:
                item.setdefault("real_life", []).extend(new)
        self._update(
            lesson_id,
            plan_json=json.dumps(current, ensure_ascii=False),
            cost_usd=self.get(lesson_id).cost_usd + result.cost_usd,
        )
        if new and self.settings.media_search:
            self.enqueue("media", lesson_id)
        progress(1.0, f"{len(new)} new real-life example(s)")
        return {"added": len(new)}

    def reject_photo(self, lesson_id: int, asset_id: int) -> None:
        """Teacher: 'wrong photo' — removed from the lesson and never chosen again for that search phrase."""
        with Session(self.engine) as s:
            asset = s.get(MediaAsset, asset_id)
            if asset:
                asset.fits, asset.check_note = False, "rejected by the teacher"
                s.add(asset)
                s.commit()
        plan = self.plan(self.get(lesson_id))
        for _concept, item in photo_queries(plan, include_done=True):
            if asset_id in item.get("photos", []):
                item["photos"] = [i for i in item["photos"] if i != asset_id]
        self._update(lesson_id, plan_json=json.dumps(plan, ensure_ascii=False))

    def photos(self, ids: list[int]) -> list[MediaAsset]:
        """Stored photos (in the given order) whose file is still on disk."""
        data_dir = self.settings.data_dir
        with Session(self.engine) as s:
            assets = {
                a.id: a for a in s.exec(select(MediaAsset).where(col(MediaAsset.id).in_(ids or []))).all()
            }
        return [
            assets[i] for i in ids or []
            if i in assets and assets[i].local_path and (data_dir / assets[i].local_path).is_file()
        ]  # fmt: skip

    # ------------------------------------------------------------ teacher edits
    def save_plan(self, lesson_id: int, plan: dict, title: str | None = None) -> Lesson:
        from app.lessons.planner import check_equations

        check_equations(plan)  # re-check after edits
        lesson = self.get(lesson_id)
        return self._update(
            lesson_id,
            plan_json=json.dumps(plan, ensure_ascii=False),
            title=title or plan.get("title") or lesson.title,
            status="draft",
            version=lesson.version + 1,
        )

    def save_simulation_code(self, lesson_id: int, code: str) -> list[str]:
        problems = check_sketch(code)
        if not problems:  # also run it in the hidden browser and use every control (no AI cost)
            problems = check_runtime(code).problems
        self._update(
            lesson_id,
            simulation_js=code,
            simulation_status="ok" if not problems else "failed",
            simulation_problems=json.dumps(problems),
            status="draft",
        )
        return problems

    def approve(self, lesson_id: int) -> Lesson:
        lesson = self.get(lesson_id)
        if lesson.status not in {"draft", "approved"}:
            raise ValueError("Only a finished draft can be approved.")
        return self._update(lesson_id, status="approved")

    def delete(self, lesson_id: int) -> None:
        with Session(self.engine) as s:
            lesson = s.get(Lesson, lesson_id)
            if lesson:
                s.delete(lesson)
                s.commit()

    def _update(self, lesson_id: int, **fields) -> Lesson:
        with Session(self.engine) as s:
            lesson = s.get(Lesson, lesson_id)
            for key, value in fields.items():
                setattr(lesson, key, value)
            lesson.updated_at = utcnow()
            s.add(lesson)
            s.commit()
            s.refresh(lesson)
        logger.debug(f"Lesson {lesson_id} updated: {', '.join(fields)}")
        return lesson
