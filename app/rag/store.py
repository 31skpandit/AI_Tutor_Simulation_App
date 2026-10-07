"""Vector store on SQLite + NumPy (blueprint decision D15).

Vectors are L2-normalised float32 stored in the `chunk` table, so cosine similarity is a dot product.
For a home-tuition library (thousands of passages) an exact search takes milliseconds and needs no
extra server or heavy dependency. The interface (add / search / delete) allows swapping in a
dedicated vector database later without touching callers.
"""

from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import Engine, func
from sqlmodel import Session, col, delete, select

from app.db.models import Chunk, Document, IndexState


@dataclass(frozen=True)
class SearchFilters:
    class_level: str | None = None
    subject: str | None = None
    chapter_no: int | None = None
    document_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    score: float
    text: str
    page_no: int
    document_id: int
    filename: str
    class_level: str
    subject: str
    chapter_no: int | None
    chapter_title: str
    kind: str = "text"  # text | summary | table | figure
    via: str | None = None  # set when this original passage was found through a summary/description

    @property
    def citation(self) -> str:
        chapter = f"Ch. {self.chapter_no}" if self.chapter_no else self.filename
        title = f" {self.chapter_title}" if self.chapter_title else ""
        return f"{chapter}{title}, page {self.page_no}"

    @property
    def label(self) -> str:
        """Citation plus what kind of entry this is (e.g. 'Ch. 5, page 4 · table description')."""
        kinds = {"summary": "page summary", "table": "table description", "figure": "figure description"}
        if self.kind in kinds:
            return f"{self.citation} · {kinds[self.kind]}"
        if self.via in kinds:
            return f"{self.citation} · found via {kinds[self.via]}"
        return self.citation


@dataclass
class _Matrix:
    version: tuple
    ids: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    doc_ids: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=np.int64))
    vectors: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=np.float32))


def _bump_generation(session: Session) -> None:
    """Increase the index change counter inside the caller's transaction."""
    state = session.get(IndexState, 1)
    if state is None:
        state = IndexState(id=1, generation=0)
    state.generation += 1
    session.add(state)


def normalise(vector: list[float] | np.ndarray) -> np.ndarray:
    array = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    return array / norm if norm > 0 else array


class VectorStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._cache: dict[str, _Matrix] = {}

    def has_text(self, text_sha256: str, embed_model: str) -> bool:
        with Session(self.engine) as s:
            return (
                s.exec(
                    select(Chunk.id).where(Chunk.text_sha256 == text_sha256, Chunk.embed_model == embed_model)
                ).first()
                is not None
            )

    def add(
        self,
        *,
        document_id: int,
        page_no: int,
        chunk_index: int,
        text: str,
        text_sha256: str,
        embed_model: str,
        vector: list[float],
        kind: str = "text",
    ) -> None:
        array = normalise(vector)
        with Session(self.engine) as s:
            s.add(
                Chunk(
                    document_id=document_id,
                    page_no=page_no,
                    chunk_index=chunk_index,
                    kind=kind,
                    text=text,
                    text_sha256=text_sha256,
                    embed_model=embed_model,
                    dim=int(array.shape[0]),
                    vector=array.tobytes(),
                )
            )
            _bump_generation(s)
            s.commit()

    def delete_page(self, document_id: int, page_no: int) -> int:
        with Session(self.engine) as s:
            result = s.exec(delete(Chunk).where(Chunk.document_id == document_id, Chunk.page_no == page_no))
            if result.rowcount:
                _bump_generation(s)
            s.commit()
            return result.rowcount or 0

    def delete_document(self, document_id: int) -> int:
        with Session(self.engine) as s:
            result = s.exec(delete(Chunk).where(Chunk.document_id == document_id))
            if result.rowcount:
                _bump_generation(s)
            s.commit()
            return result.rowcount or 0

    def generation(self) -> int:
        with Session(self.engine) as s:
            state = s.get(IndexState, 1)
            return state.generation if state else 0

    def version_key(self, embed_model: str) -> str:
        """Changes whenever passages are added or removed — used to invalidate cached answers."""
        return f"{embed_model}:{self.generation()}"

    def count(self, embed_model: str | None = None) -> int:
        with Session(self.engine) as s:
            query = select(func.count(Chunk.id))
            if embed_model:
                query = query.where(Chunk.embed_model == embed_model)
            return int(s.exec(query).one())

    def page_text_hits(
        self, document_id: int, page_no: int, query_vector: list[float], embed_model: str
    ) -> list[Hit]:
        """The original text passages of one page, ranked by similarity to the query."""
        query = normalise(query_vector)
        with Session(self.engine) as s:
            rows = s.exec(
                select(Chunk, Document)
                .join(Document, Document.id == Chunk.document_id)
                .where(
                    Chunk.document_id == document_id,
                    Chunk.page_no == page_no,
                    Chunk.kind == "text",
                    Chunk.embed_model == embed_model,
                )
            ).all()
        hits = [
            Hit(
                chunk_id=chunk.id,
                score=float(np.frombuffer(chunk.vector, dtype=np.float32) @ query),
                text=chunk.text,
                page_no=chunk.page_no,
                document_id=doc.id,
                filename=doc.filename,
                class_level=doc.class_level,
                subject=doc.subject,
                chapter_no=doc.chapter_no,
                chapter_title=doc.chapter_title,
            )
            for chunk, doc in rows
        ]
        return sorted(hits, key=lambda h: h.score, reverse=True)

    def document_text_hits(self, document_id: int, embed_model: str) -> list[Hit]:
        """Every original passage of a document in page order (for lessons that cover a whole chapter)."""
        with Session(self.engine) as s:
            rows = s.exec(
                select(Chunk, Document)
                .join(Document, Document.id == Chunk.document_id)
                .where(
                    Chunk.document_id == document_id, Chunk.kind == "text", Chunk.embed_model == embed_model
                )
                .order_by(Chunk.page_no, Chunk.id)
            ).all()
        return [
            Hit(
                chunk_id=chunk.id,
                score=1.0,
                text=chunk.text,
                page_no=chunk.page_no,
                document_id=doc.id,
                filename=doc.filename,
                class_level=doc.class_level,
                subject=doc.subject,
                chapter_no=doc.chapter_no,
                chapter_title=doc.chapter_title,
            )
            for chunk, doc in rows
        ]

    def search(
        self, query_vector: list[float], embed_model: str, k: int = 5, filters: SearchFilters | None = None
    ) -> list[Hit]:
        matrix = self._matrix(embed_model)
        if matrix.ids.size == 0:
            return []
        query = normalise(query_vector)
        if query.shape[0] != matrix.vectors.shape[1]:
            raise ValueError(f"Query has {query.shape[0]} dimensions, index has {matrix.vectors.shape[1]}")
        allowed = self._allowed_documents(filters)
        scores = matrix.vectors @ query
        if allowed is not None:
            scores = np.where(np.isin(matrix.doc_ids, list(allowed)), scores, -np.inf)
        order = np.argsort(-scores)[:k]
        id_scores = {int(matrix.ids[i]): float(scores[i]) for i in order if np.isfinite(scores[i])}
        wanted_ids = list(id_scores)
        if not wanted_ids:
            return []
        with Session(self.engine) as s:
            rows = s.exec(
                select(Chunk, Document)
                .join(Document, Document.id == Chunk.document_id)
                .where(col(Chunk.id).in_(wanted_ids))
            ).all()
        hits = [
            Hit(
                chunk_id=chunk.id,
                score=id_scores[chunk.id],
                text=chunk.text,
                page_no=chunk.page_no,
                document_id=doc.id,
                filename=doc.filename,
                class_level=doc.class_level,
                subject=doc.subject,
                chapter_no=doc.chapter_no,
                chapter_title=doc.chapter_title,
                kind=chunk.kind,
            )
            for chunk, doc in rows
        ]
        return sorted(hits, key=lambda h: h.score, reverse=True)

    # ---------- internals ----------
    def _allowed_documents(self, filters: SearchFilters | None) -> set[int] | None:
        if filters is None or not any(
            [filters.class_level, filters.subject, filters.chapter_no, filters.document_ids]
        ):
            return None
        query = select(Document.id)
        if filters.class_level:
            query = query.where(Document.class_level == filters.class_level)
        if filters.subject:
            query = query.where(Document.subject == filters.subject)
        if filters.chapter_no:
            query = query.where(Document.chapter_no == filters.chapter_no)
        if filters.document_ids:
            query = query.where(col(Document.id).in_(filters.document_ids))
        with Session(self.engine) as s:
            return set(s.exec(query).all())

    def _matrix(self, embed_model: str) -> _Matrix:
        with Session(self.engine) as s:
            state = s.get(IndexState, 1)
            count = int(s.exec(select(func.count(Chunk.id)).where(Chunk.embed_model == embed_model)).one())
            version = (state.generation if state else 0, count)
            cached = self._cache.get(embed_model)
            if cached is not None and cached.version == version:
                return cached
            rows = s.exec(
                select(Chunk.id, Chunk.document_id, Chunk.vector).where(Chunk.embed_model == embed_model)
            ).all()
        matrix = _Matrix(version=version)
        if rows:
            matrix.ids = np.array([r[0] for r in rows], dtype=np.int64)
            matrix.doc_ids = np.array([r[1] for r in rows], dtype=np.int64)
            matrix.vectors = np.vstack([np.frombuffer(r[2], dtype=np.float32) for r in rows])
        self._cache[embed_model] = matrix
        return matrix
