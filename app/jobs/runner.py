"""Background job runner. One worker at a time (the GPU can only run one model efficiently).

Jobs live in the `job` table, so they survive restarts. A job whose heartbeat stops (app closed
mid-way) is put back in the queue and resumes where it stopped (extraction skips finished pages).
"""

import threading
from datetime import timedelta

from loguru import logger
from sqlalchemy import Engine, update
from sqlmodel import Session, col, select

from app.db.models import Job, utcnow
from app.ingestion.service import IngestionService

STALE_AFTER = timedelta(minutes=3)
IDLE_SLEEP_S = 2.0
# Job kinds this version of the code can run. A worker never claims other kinds, so an older app still
# running in the background cannot pick up (and fail) jobs created by newer code — this happened once.
SUPPORTED_KINDS = ("extract", "index", "reread_cloud", "lesson_plan", "simulation")


def claim_next(engine: Engine) -> Job | None:
    """Atomically move the oldest queued job of a supported kind to 'running'. Safe if two workers race."""
    with Session(engine) as s:
        candidate = s.exec(
            select(Job.id).where(Job.status == "queued", col(Job.kind).in_(SUPPORTED_KINDS)).order_by(Job.id)
        ).first()
        if candidate is None:
            return None
        now = utcnow()
        result = s.exec(
            update(Job)
            .where(col(Job.id) == candidate, col(Job.status) == "queued")
            .values(status="running", started_at=now, heartbeat_at=now, message="Starting…")
        )
        s.commit()
        if result.rowcount != 1:
            return None
        return s.get(Job, candidate)


def recover_stale(engine: Engine) -> int:
    """Re-queue jobs left 'running' by a process that stopped."""
    cutoff = utcnow() - STALE_AFTER
    with Session(engine) as s:
        result = s.exec(
            update(Job)
            .where(col(Job.status) == "running", col(Job.heartbeat_at) < cutoff)
            .values(status="queued", message="Resuming after restart")
        )
        s.commit()
        return result.rowcount or 0


def _progress_writer(engine: Engine, job_id: int):
    def write(fraction: float, message: str) -> None:
        with Session(engine) as s:
            job = s.get(Job, job_id)
            if job is None:
                return
            job.progress = round(min(max(fraction, 0.0), 1.0), 3)
            job.message = message
            job.heartbeat_at = utcnow()
            s.add(job)
            s.commit()

    return write


def run_job(service: IngestionService, job: Job) -> None:
    engine = service.engine
    progress = _progress_writer(engine, job.id)
    try:
        if job.kind == "extract":
            stats = service.extract_document(job.document_id, progress)
            summary = (
                f"{stats['text']} text, {stats['ocr']} OCR, {stats['reused']} reused, "
                f"{stats['failed']} failed, {stats['warnings']} to check, {stats['skipped']} already done"
            )
        elif job.kind == "index":
            stats = service.index_document(
                job.document_id, progress=progress, include_unreviewed="include_unreviewed" in job.options
            )
            summary = (
                f"{stats['pages']} pages, {stats['chunks']} entries ({stats['enrichments']} summaries/descriptions), "
                f"{stats['duplicate_chunks']} duplicates skipped"
                + (f", {stats['enrich_failed']} pages without summary" if stats["enrich_failed"] else "")
            )
        elif job.kind in {"lesson_plan", "simulation"}:
            from app.lessons.service import LessonService  # Phase 2

            lessons = LessonService(service.engine, service.router, service.settings.lesson_min_relevance)
            if job.kind == "lesson_plan":
                stats = lessons.generate_plan(job.lesson_id, progress)
                summary = (
                    f"Lesson plan ready: {stats['sections']} sections, {stats['warnings']} warnings to check"
                )
            else:
                stats = lessons.generate_simulation(job.lesson_id, job.options, progress)
                summary = (
                    "Simulation ready" if stats["ok"] else f"Simulation has {stats['problems']} problem(s)"
                ) + f" after {stats['fix_rounds']} automatic fix round(s)"
        elif job.kind == "reread_cloud":
            pages = [int(p) for p in job.options.removeprefix("pages=").split(",") if p.strip()]
            stats = service.reread_pages_cloud(job.document_id, pages, progress)
            summary = f"{stats['pages']} pages re-read with the cloud model, {stats['failed']} failed — please review them"
        else:
            raise ValueError(f"Unknown job kind '{job.kind}'")
        status, error = "done", None
    except Exception as exc:  # noqa: BLE001 — record any failure on the job
        logger.exception(f"Job {job.id} ({job.kind}) failed")
        status, error, summary = "failed", f"{type(exc).__name__}: {exc}"[:500], "Failed"
    with Session(engine) as s:
        stored = s.get(Job, job.id)
        stored.status, stored.error, stored.message = status, error, summary
        stored.progress = 1.0 if status == "done" else stored.progress
        stored.finished_at = utcnow()
        s.add(stored)
        s.commit()


def run_until_empty(service: IngestionService, on_job=None) -> int:
    """Process queued jobs in this thread until none are left (used by the command-line tool)."""
    recover_stale(service.engine)
    processed = 0
    while (job := claim_next(service.engine)) is not None:
        if on_job:
            on_job(job)
        run_job(service, job)
        processed += 1
    return processed


class Worker:
    """A daemon thread that keeps processing the job queue while the app is open."""

    def __init__(self, service: IngestionService):
        self.service = service
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="ingestion-worker", daemon=True)
        self.current: Job | None = None

    def start(self) -> "Worker":
        recover_stale(self.service.engine)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = claim_next(self.service.engine)
            except Exception:  # noqa: BLE001 — e.g. database briefly locked
                logger.exception("Worker could not claim a job")
                job = None
            if job is None:
                self._stop.wait(IDLE_SLEEP_S)
                continue
            self.current = job
            run_job(self.service, job)
            self.current = None


def queue_summary(engine: Engine) -> dict:
    with Session(engine) as s:
        active = s.exec(select(Job).where(col(Job.status).in_(["queued", "running"])).order_by(Job.id)).all()
    return {
        "queued": sum(j.status == "queued" for j in active),
        "running": [j for j in active if j.status == "running"],
    }
