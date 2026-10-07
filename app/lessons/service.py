"""Lessons: create → plan (background) → simulation (background) → teacher edits → approve → Teach Mode."""

import json
from collections.abc import Callable

from loguru import logger
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from app.db.models import Document, Job, Lesson, utcnow
from app.lessons.planner import MIN_RELEVANCE, PlanningError, plan_lesson, simulation_facts
from app.lessons.simulation import check_runtime, check_sketch, generate_simulation
from app.llm.router import AllModelsFailed, LLMRouter
from app.rag.store import SearchFilters, VectorStore

Progress = Callable[[float, str], None]


def _noop(_fraction: float, _message: str) -> None:
    pass


class LessonService:
    def __init__(self, engine: Engine, router: LLMRouter, min_relevance: float = MIN_RELEVANCE):
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
        filters, class_level, subject = None, "", ""
        if lesson.document_id:
            with Session(self.engine) as s:
                document = s.get(Document, lesson.document_id)
            if document:
                filters = SearchFilters(document_ids=(document.id,))
                class_level, subject = document.class_level, document.subject
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
