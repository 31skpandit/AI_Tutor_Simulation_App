import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make ui/common.py importable

import json  # noqa: E402

import common  # noqa: E402,F401
import streamlit as st  # noqa: E402
from common import document_label, ingestion_or_stop, page  # noqa: E402

from app.core.config import PROJECT_ROOT  # noqa: E402
from app.core.secrets import has_secret  # noqa: E402
from app.ingestion.extract import render_page_preview  # noqa: E402
from app.ingestion.ocr import normalize_markdown_tables  # noqa: E402
from app.ingestion.service import CLOUD_OCR_COST_PER_PAGE_USD, CLOUD_OCR_TASK  # noqa: E402

page("Review Text", "📝")
st.title("📝 Review extracted text")
st.caption(
    "Compare each page with the extracted text, correct mistakes (especially formulas such as H₂SO₄ and numbers), "
    "then mark it reviewed. Only reviewed pages become searchable for the AI Tutor. With the autopilot on, pages "
    "that pass the automatic check (🤖) are already searchable — start with the pages marked ⚠️."
)
service, _ = ingestion_or_stop()
CLOUD_MODEL = (
    service.router.config.tasks[CLOUD_OCR_TASK].primary
    if CLOUD_OCR_TASK in service.router.config.tasks
    else "?"
)

documents = [d for d in service.documents() if service.page_counts(d.id)["done"] or d.status == "failed"]
if not documents:
    st.info("Nothing to review yet. Add files on the **Syllabus Library** page and wait for extraction.")
    st.stop()

default = next((i for i, d in enumerate(documents) if d.id == st.session_state.get("library_doc_id")), 0)
document = st.selectbox("Document", documents, index=default, format_func=document_label)
st.session_state["library_doc_id"] = document.id
pages = service.pages(document.id)
counts = service.page_counts(document.id)

top1, top2, top3 = st.columns([3, 1, 1])
top1.progress(
    counts["reviewed"] / max(len(pages), 1),
    text=f"Reviewed {counts['reviewed']} of {len(pages)} extracted pages · {counts['indexed']} searchable",
)
if top2.button("Mark ALL reviewed", help="Use only after you have checked the pages"):
    service.mark_all_reviewed(document.id)
    st.rerun()
if top3.button("Make reviewed pages searchable", type="primary", disabled=counts["reviewed"] == 0):
    service.enqueue("index", document.id)
    st.toast("Indexing queued — see progress on the Syllabus Library page.")

if not pages:
    st.warning("No pages extracted yet.")
    st.stop()

page_numbers = [p.page_no for p in pages]
key = f"review_page_{document.id}"
goto = f"goto_{key}"  # page requested by a button after the selector was drawn
if goto in st.session_state:
    st.session_state[key] = st.session_state.pop(goto)
st.session_state.setdefault(key, page_numbers[0])
if st.session_state[key] not in page_numbers:
    st.session_state[key] = page_numbers[0]

nav1, nav2, nav3 = st.columns([1, 4, 1])
position = page_numbers.index(st.session_state[key])
if nav1.button("◀ Previous", disabled=position == 0):
    st.session_state[goto] = page_numbers[position - 1]
    st.rerun()
if nav3.button("Next ▶", disabled=position == len(page_numbers) - 1):
    st.session_state[goto] = page_numbers[position + 1]
    st.rerun()


def badge(p) -> str:
    if p.status == "failed":
        return "❌"
    if p.reviewed:
        return "🤖 auto-checked" if p.auto_reviewed else "✅"
    return "⚠️ to check" if p.quality == "check" else "•"


labels = {p.page_no: f"Page {p.page_no} {badge(p)}" for p in pages}
nav2.selectbox("Page", page_numbers, key=key, format_func=labels.get, label_visibility="collapsed")
to_check = [p.page_no for p in pages if p.quality == "check" and not p.reviewed]
if to_check:
    st.caption(
        f"⚠️ Pages that need your look: {', '.join(map(str, to_check))} — 🤖 = passed the automatic check "
        "(already searchable; you may still review them)."
    )
    if st.button(f"Go to the next page to check (page {to_check[0]})"):
        st.session_state[goto] = to_check[0]
        st.rerun()
current = next(p for p in pages if p.page_no == st.session_state[key])


@st.cache_data(max_entries=64, show_spinner=False)
def preview(rel_path: str, kind: str, page_no: int, sha256: str) -> bytes | None:  # sha256 keys the cache
    return render_page_preview(PROJECT_ROOT / rel_path, kind, page_no)


left, right = st.columns(2)
with left:
    image = preview(document.rel_path, document.kind, current.page_no, document.sha256)
    if image:
        st.image(image, caption=f"{document.filename} — page {current.page_no}")
    else:
        st.info("No page image for this file type (DOCX/TXT are read directly).")
with right:
    st.caption(
        f"Method: **{current.method or '—'}**"
        + (f" · model `{current.model_ref}`" if current.model_ref else "")
        + f" · reviewed: {'yes' if current.reviewed else 'no'} · searchable: {'yes' if current.indexed else 'no'}"
    )
    if current.status == "failed":
        st.error(f"Extraction failed: {current.error}")
    elif current.quality == "check" and not current.reviewed:
        st.warning(
            "⚠️ The automatic check flagged this page: " + "; ".join(json.loads(current.quality_notes or "[]"))
        )
    elif current.error:
        st.warning(f"⚠️ {current.error}")
    elif current.auto_reviewed:
        st.success("🤖 Passed the automatic check and is searchable — your review is optional.")
    if current.status == "failed" or current.error:
        if st.button("Retry this page", help="Extracts this page again (your edits on it are discarded)"):
            service.retry_page(document.id, current.page_no)
            st.toast("Page queued for extraction.")
    edit_tab, preview_tab = st.tabs(["✏️ Edit", "👁️ Preview (tables shown as tables)"])
    with edit_tab:
        text = st.text_area(
            "Text",
            current.text,
            height=560,
            key=f"text_{document.id}_{current.page_no}",
            label_visibility="collapsed",
        )
    with preview_tab:
        with st.container(height=560):
            st.markdown(normalize_markdown_tables(text))  # tables aligned for display; your text is unchanged
    s1, s2 = st.columns(2)
    if s1.button("💾 Save"):
        service.update_page(document.id, current.page_no, text, reviewed=current.reviewed)
        st.toast("Saved.")
        st.rerun()
    if s2.button("✅ Save & mark reviewed → next", type="primary", disabled=current.status != "done"):
        service.update_page(document.id, current.page_no, text, reviewed=True)
        if position < len(page_numbers) - 1:
            st.session_state[goto] = page_numbers[position + 1]
        st.rerun()
    if current.raw_text and current.raw_text != current.text:
        with st.expander("Show the original extracted text"):
            st.text(current.raw_text)
    if document.kind in {"pdf", "image"} and current.status == "done":
        with st.expander("☁️ Tables or diagrams not read well? Re-read this page with the cloud model"):
            st.caption(
                f"Uses `{CLOUD_MODEL}` (≈ ${CLOUD_OCR_COST_PER_PAGE_USD:.3f} per page, counted in your monthly budget). "
                "Measured on your chapter: all subscripts and tables correct. Your edits on this page are replaced, "
                "and the page must be reviewed again."
            )
            if not has_secret("openai"):
                st.warning("No OpenAI key stored — add it on Settings & Cost first.")
            elif st.button("Re-read this page with the cloud model"):
                service.enqueue("reread_cloud", document.id, options=f"pages={current.page_no}")
                st.toast("Queued — the page will refresh with the new text in a few seconds.")
