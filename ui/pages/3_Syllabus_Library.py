import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import json  # noqa: E402

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import STATUS_LABEL, document_label, ingestion_or_stop, page  # noqa: E402
from streamlit.errors import StreamlitPageNotFoundError  # noqa: E402

from app.core.secrets import has_secret  # noqa: E402
from app.ingestion.files import UPLOAD_TYPES  # noqa: E402
from app.ingestion.service import CLOUD_OCR_COST_PER_PAGE_USD  # noqa: E402
from app.jobs.runner import queue_summary  # noqa: E402
from app.lessons.service import LessonService  # noqa: E402

page("Syllabus Library", "📚")
st.title("📚 Syllabus Library")
service, worker = ingestion_or_stop()
settings = service.settings
lessons = LessonService(service.engine, service.router, settings.lesson_min_relevance, settings)
LESSON_LABEL = {
    "generating": "⏳ being written",
    "draft": "📝 draft ready",
    "approved": "✅ approved",
    "failed": "❌ failed",
}
if settings.require_review and settings.auto_review_clean:
    st.info(
        "🤖 **Autopilot is on:** every new chapter is read, each page is checked automatically, clean pages become "
        "searchable at once, and a draft lesson for the whole chapter is written"
        + (" automatically" if settings.auto_lesson else " when you create it")
        + ". Pages marked ⚠️ wait for your review. Nothing reaches Teach Mode before you approve the lesson."
    )

# ---------------------------------------------------------------- automatic scan of the source folder
st.caption(
    f"Source folder: `{settings.source_dir}` — drop PDFs, photos/scans (PNG/JPG/WEBP/TIFF/BMP), "
    "DOCX or TXT/MD files there, or upload below. Files already processed are recognised by their "
    "content (SHA-256), even if renamed, and are never processed twice."
)
if settings.auto_ingest:
    report = service.scan_source()
    if report.new:
        st.success(
            f"Found {len(report.new)} new file(s): "
            + ", ".join(r.path.name for r in report.new)
            + " — processing started in the background."
        )
    if report.duplicates:
        with st.expander(f"ℹ️ {len(report.duplicates)} duplicate file(s) in the source folder were skipped"):
            for item in report.duplicates:
                st.markdown(f"- `{item.path.name}` — {item.message}")
    for item in report.errors:
        st.error(f"`{item.path.name}`: {item.message}")
    if report.unsupported:
        st.caption("Not supported (ignored): " + ", ".join(p.name for p in report.unsupported))
elif st.button("Scan source folder now"):
    service.scan_source()
    st.rerun()

# ---------------------------------------------------------------- upload
with st.expander("➕ Add files", expanded=not service.documents()):
    with st.form("upload", clear_on_submit=True):
        files = st.file_uploader("Choose files", type=UPLOAD_TYPES, accept_multiple_files=True)
        st.caption(
            "Leave the fields blank to guess them from the file name (e.g. *Class 9 - Science - 5th Chapter*). "
            "You can edit them later."
        )
        c1, c2, c3, c4 = st.columns([1, 2, 1, 3])
        class_level = c1.text_input("Class")
        subject = c2.text_input("Subject")
        chapter_no = c3.number_input(
            "Chapter", min_value=0, max_value=99, value=0, help="0 = guess / unknown"
        )
        chapter_title = c4.text_input("Chapter title")
        submitted = st.form_submit_button("Add & process", type="primary")
    if submitted and files:
        meta = {
            "class_level": class_level.strip(),
            "subject": subject.strip(),
            "chapter_no": int(chapter_no) or None,
            "chapter_title": chapter_title.strip(),
        }
        for upload in files:
            result = service.save_upload(upload.name, upload.getvalue(), meta)
            if result.status == "new":
                st.success(f"`{upload.name}` saved to the source folder and queued for processing.")
            elif result.status == "duplicate":
                st.info(f"`{upload.name}`: {result.message}")
            else:
                st.error(f"`{upload.name}`: {result.message}")


# ---------------------------------------------------------------- live status (refreshes every 3 s)
@st.fragment(run_every=3)
def live_status() -> None:
    summary = queue_summary(service.engine)
    if not worker.alive:
        st.error("The background worker stopped. Restart the app (Ctrl+C, then start it again).")
    for job in summary["running"]:
        st.progress(
            job.progress, text=f"Job #{job.id} · {job.kind} · document #{job.document_id} — {job.message}"
        )
    if summary["queued"]:
        st.caption(f"{summary['queued']} job(s) waiting.")

    documents = service.documents()
    if not documents:
        st.info("No documents yet. Add files above or drop them into the source folder, then refresh.")
        return
    lesson_by_document = {}
    for lesson in lessons.lessons():
        lesson_by_document.setdefault(lesson.document_id, lesson)
    rows = []
    for document in documents:
        counts = service.page_counts(document.id)
        lesson = lesson_by_document.get(document.id)
        rows.append(
            {
                "#": document.id,
                "file": document.filename,
                "class": document.class_level,
                "subject": document.subject,
                "chapter": document.chapter_no,
                "title": document.chapter_title,
                "status": STATUS_LABEL.get(document.status, document.status),
                "pages": document.page_count,
                "extracted": counts["done"],
                "✅ auto-checked": counts["auto_reviewed"],
                "⚠️ to check": counts["to_check"],
                "reviewed": counts["reviewed"],
                "searchable": counts["indexed"],
                "lesson": LESSON_LABEL.get(lesson.status, lesson.status) if lesson else "—",
                "note": document.error or "",
            }
        )
    st.dataframe(rows, hide_index=True)


st.subheader("Documents")
live_status()

# ---------------------------------------------------------------- manage one document
documents = service.documents()
if documents:
    st.subheader("Manage a document")
    default = next((i for i, d in enumerate(documents) if d.id == st.session_state.get("library_doc_id")), 0)
    selected = st.selectbox("Document", documents, index=default, format_func=document_label)
    st.session_state["library_doc_id"] = selected.id  # the Review page opens the same document
    counts = service.page_counts(selected.id)

    with st.form(f"meta_{selected.id}"):
        c1, c2, c3, c4 = st.columns([1, 2, 1, 3])
        class_level = c1.text_input("Class", selected.class_level)
        subject = c2.text_input("Subject", selected.subject)
        chapter_no = c3.number_input("Chapter", min_value=0, max_value=99, value=selected.chapter_no or 0)
        chapter_title = c4.text_input("Chapter title", selected.chapter_title)
        if st.form_submit_button("Save details"):
            service.update_metadata(
                selected.id,
                class_level=class_level.strip(),
                subject=subject.strip(),
                chapter_no=int(chapter_no) or None,
                chapter_title=chapter_title.strip(),
            )
            st.success(
                "Saved. (Re-index the document if it was already searchable, so new details are used.)"
            )
            st.rerun()

    st.markdown(
        f"**Progress:** {counts['done']}/{selected.page_count} pages extracted · {counts['reviewed']} reviewed "
        f"({counts['auto_reviewed']} by the automatic check) · {counts['indexed']} searchable"
        + (f" · ❌ {counts['failed']} failed" if counts["failed"] else "")
    )
    flagged = [p for p in service.pages(selected.id) if p.quality == "check" and not p.reviewed]
    if flagged:
        with st.expander(f"⚠️ {len(flagged)} page(s) need your look — why", expanded=True):
            for p in flagged:
                reasons = "; ".join(json.loads(p.quality_notes or "[]")) or "flagged by the automatic check"
                st.markdown(f"- **Page {p.page_no}** — {reasons}")
            st.caption(
                "Open **📝 Review pages**, correct them if needed and mark them reviewed — they then become "
                "searchable automatically on the next indexing."
            )
            ocr_flagged = [p.page_no for p in flagged if p.method in {"ocr", "ocr_reused"}]
            if (
                ocr_flagged
                and has_secret("openai")
                and st.button(
                    f"☁️ Re-read the flagged scanned pages {', '.join(map(str, ocr_flagged))} with the cloud model "
                    f"(≈ ${len(ocr_flagged) * CLOUD_OCR_COST_PER_PAGE_USD:.2f})"
                )
            ):
                service.enqueue(
                    "reread_cloud", selected.id, options="pages=" + ",".join(map(str, ocr_flagged))
                )
                st.toast(
                    "Cloud re-read queued — pages that then pass the check become searchable by themselves."
                )
    elif counts["done"] and settings.auto_review_clean:
        st.caption("✅ The automatic check found no problem pages in this document.")
    chapter_lessons = [x for x in lessons.lessons() if x.document_id == selected.id]
    if chapter_lessons:
        st.caption(
            "📘 Lessons from this chapter: "
            + ", ".join(f"*{x.title}* ({LESSON_LABEL.get(x.status, x.status)})" for x in chapter_lessons)
            + " — open **Lesson Studio** to check and approve."
        )
    elif counts["indexed"] and st.button("📘 Write the lesson for this chapter now"):
        created = lessons.auto_create_for_document(selected.id)
        st.toast(
            "Lesson " + ", ".join(f"'{x.topic}'" for x in created) + " queued."
            if created
            else "A lesson already exists."
        )
    b1, b2, b3, b4 = st.columns(4)
    if b1.button("📝 Review pages"):
        try:
            st.switch_page("pages/4_Review_Text.py")
        except StreamlitPageNotFoundError:  # page opened on its own (no sidebar registry)
            st.info("Open **Review Text** in the sidebar.")
    if b2.button(
        "Index reviewed pages",
        disabled=counts["reviewed"] == 0,
        help="Makes reviewed pages searchable for the AI Tutor",
    ):
        service.enqueue("index", selected.id)
        st.toast("Indexing queued.")
    if b3.button(
        "Re-run extraction", help="Processes pages that are missing or failed. Finished pages are kept."
    ):
        service.enqueue("extract", selected.id)
        st.toast("Extraction queued.")
    ocr_pages = service.ocr_page_numbers(selected.id)
    if ocr_pages and selected.kind in {"pdf", "image"}:
        suggested = service.pages_suggested_for_cloud(selected.id)
        with st.expander("☁️ Better tables & diagrams: re-read pages with the cloud model"):
            st.caption(
                f"Uses gpt-5.4-mini, ≈ ${CLOUD_OCR_COST_PER_PAGE_USD:.3f} per page (counted in your monthly budget). "
                "Measured on your chapter: every subscript and table correct, no invented figure details. "
                "Re-read pages replace the current text (including your edits) and must be reviewed again. "
                "To re-read single pages, use the cloud expander on Review Text."
            )
            if not has_secret("openai"):
                st.warning("No OpenAI key stored — add it on Settings & Cost first.")
            else:
                c1, c2 = st.columns(2)
                if suggested and c1.button(
                    f"Pages with tables / warnings: {', '.join(map(str, suggested))} "
                    f"(≈ ${len(suggested) * CLOUD_OCR_COST_PER_PAGE_USD:.2f})"
                ):
                    service.enqueue(
                        "reread_cloud", selected.id, options="pages=" + ",".join(map(str, suggested))
                    )
                    st.toast("Cloud re-read queued — progress is shown above.")
                if c2.button(
                    f"All {len(ocr_pages)} OCR pages (≈ ${len(ocr_pages) * CLOUD_OCR_COST_PER_PAGE_USD:.2f})"
                ):
                    service.enqueue(
                        "reread_cloud", selected.id, options="pages=" + ",".join(map(str, ocr_pages))
                    )
                    st.toast("Cloud re-read of all pages queued — progress is shown above.")
    with b4.popover("More…"):
        st.caption(
            "Skip review and make all extracted pages searchable now (not recommended: OCR mistakes stay)."
        )
        if st.button("Index ALL pages without review"):
            service.enqueue("index", selected.id, options="include_unreviewed")
            st.toast("Indexing of all pages queued.")
        st.divider()
        st.caption(
            "Rebuild the search entries of searchable pages — e.g. to add page summaries and table/figure "
            "descriptions to pages indexed before that feature existed (local model, free, ~10–20 s per page)."
        )
        if st.button("Re-index searchable pages"):
            st.toast(
                f"Re-indexing {service.reindex_document(selected.id)} page(s) — progress is shown above."
            )
        st.divider()
        delete_file = st.checkbox("Also delete the file from the source folder")
        if st.button("Delete this document", type="primary"):
            service.delete_document(selected.id, delete_file=delete_file)
            st.success("Deleted.")
            st.rerun()
