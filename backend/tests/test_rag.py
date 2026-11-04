from pathlib import Path

import pytest
from fpdf import FPDF
from httpx import AsyncClient

from nexus.domain.chunking import chunk_pages
from tests.conftest import settle


def make_pdf(tmp_path: Path) -> bytes:
    pdf = FPDF()
    for text in (
        "The aurora battery has a capacity of 51.2 kWh per cabinet.",
        "Warranty: ten years or 6,000 cycles, guaranteeing 80 percent capacity.",
    ):
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 8, text * 4, new_x="LMARGIN", new_y="NEXT")
    p = tmp_path / "t.pdf"
    pdf.output(str(p))
    return p.read_bytes()


def test_chunking_respects_pages_and_size() -> None:
    long = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(12))
    chunks = chunk_pages([(1, long), (2, "Short page two.")], target=500, overlap=80)
    assert all(len(c.text) <= 1000 for c in chunks)
    assert {c.page for c in chunks} == {1, 2}
    assert chunks[-1].page == 2 and chunks[-1].text == "Short page two."
    assert [c.ord for c in chunks] == list(range(len(chunks)))


async def test_pdf_ingestion_and_hybrid_retrieval_with_pages(client: AsyncClient, user: dict, tmp_path: Path) -> None:
    r = await client.post("/api/documents", files={"file": ("battery.pdf", make_pdf(tmp_path), "application/pdf")})
    assert r.status_code == 201
    doc = r.json()
    await settle()
    doc = (await client.get(f"/api/documents/{doc['id']}")).json()
    assert doc["status"] == "ready" and doc["page_count"] == 2 and doc["chunk_count"] >= 2

    hits = (await client.post("/api/documents/search", json={"query": "warranty cycles capacity guarantee"})).json()
    assert hits[0]["page"] == 2 and "Warranty" in hits[0]["text"]
    assert set(hits[0]["signals"]) == {"vector", "keyword"}
    chunk = (await client.get(f"/api/documents/chunks/{hits[0]['chunk_id']}")).json()
    assert chunk["filename"] == "battery.pdf" and chunk["page"] == 2


async def test_upload_validation_and_dedup(client: AsyncClient, user: dict) -> None:
    bad_ext = await client.post("/api/documents", files={"file": ("x.exe", b"MZ....")})
    assert bad_ext.status_code == 422
    fake_pdf = await client.post("/api/documents", files={"file": ("x.pdf", b"not really a pdf")})
    assert fake_pdf.status_code == 422 and "do not match" in fake_pdf.json()["detail"]
    traversal = await client.post("/api/documents", files={"file": ("../../etc/notes.md", b"# hi\n\nhello world")})
    assert traversal.status_code == 201 and traversal.json()["filename"] == "notes.md"
    again = await client.post("/api/documents", files={"file": ("copy.md", b"# hi\n\nhello world")})
    assert again.json()["id"] == traversal.json()["id"]  # same content → deduplicated


async def test_delete_removes_chunks_and_file(client: AsyncClient, user: dict) -> None:
    doc = (
        await client.post("/api/documents", files={"file": ("del.md", b"# Delete me\n\nunique zebra content")})
    ).json()
    await settle()
    assert (await client.post("/api/documents/search", json={"query": "unique zebra"})).json()
    assert (await client.delete(f"/api/documents/{doc['id']}")).status_code == 204
    assert (await client.post("/api/documents/search", json={"query": "unique zebra"})).json() == []
    assert (await client.get(f"/api/documents/{doc['id']}")).status_code == 404


@pytest.mark.parametrize(
    "name,data", [("t.txt", b"plain text body " * 20), ("t.csv", b"city,pop\nOslo,700000\nRome,2800000\n")]
)
async def test_text_and_csv_documents_index(client: AsyncClient, user: dict, name: str, data: bytes) -> None:
    doc = (await client.post("/api/documents", files={"file": (name, data)})).json()
    await settle()
    assert (await client.get(f"/api/documents/{doc['id']}")).json()["status"] == "ready"
