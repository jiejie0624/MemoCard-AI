import io
import unittest
from unittest.mock import patch
from uuid import uuid4

from pptx import Presentation

from backend.app.processing.chunking import build_document_chunks
from backend.app.processing.extraction import (
    DocumentProcessingError,
    TextSection,
    extract_document,
)


class DocumentExtractionTests(unittest.TestCase):
    def test_txt_accepts_utf8_bom_and_rejects_blank_or_invalid_text(self) -> None:
        sections = extract_document("txt", b"\xef\xbb\xbfLecture notes\n\xe5\xad\xa6\xe4\xb9\xa0")
        self.assertEqual(sections, [TextSection("Lecture notes\n学习")])

        with self.assertRaisesRegex(DocumentProcessingError, "No readable text"):
            extract_document("txt", b" \n\t")
        with self.assertRaisesRegex(DocumentProcessingError, "UTF-8"):
            extract_document("txt", b"\xff")

    def test_pdf_keeps_one_based_page_locations(self) -> None:
        pages = [type("Page", (), {"extract_text": lambda self: "Page one"})(),
                 type("Page", (), {"extract_text": lambda self: " "})(),
                 type("Page", (), {"extract_text": lambda self: "Page three"})()]
        reader = type("Reader", (), {"is_encrypted": False, "pages": pages})()
        with patch("backend.app.processing.extraction.PdfReader", return_value=reader):
            sections = extract_document("pdf", b"%PDF-test")
        self.assertEqual(
            sections,
            [TextSection("Page one", page_number=1), TextSection("Page three", page_number=3)],
        )

    def test_scanned_pdf_without_text_explains_ocr_limit(self) -> None:
        reader = type(
            "Reader",
            (),
            {"is_encrypted": False, "pages": [type("Page", (), {"extract_text": lambda self: ""})()]},
        )()
        with patch("backend.app.processing.extraction.PdfReader", return_value=reader):
            with self.assertRaisesRegex(DocumentProcessingError, "OCR"):
                extract_document("pdf", b"%PDF-test")

    def test_pptx_extracts_slide_text_and_table_with_locations(self) -> None:
        presentation = Presentation()
        first = presentation.slides.add_slide(presentation.slide_layouts[6])
        textbox = first.shapes.add_textbox(0, 0, 3_000_000, 500_000)
        textbox.text = "Spaced repetition"
        table_shape = first.shapes.add_table(1, 2, 0, 500_000, 3_000_000, 500_000)
        table_shape.table.cell(0, 0).text = "Front"
        table_shape.table.cell(0, 1).text = "Back"
        second = presentation.slides.add_slide(presentation.slide_layouts[6])
        second.shapes.add_textbox(0, 0, 3_000_000, 500_000).text = "学习"
        output = io.BytesIO()
        presentation.save(output)

        sections = extract_document("pptx", output.getvalue())
        self.assertEqual(sections[0].slide_number, 1)
        self.assertIn("Spaced repetition", sections[0].text)
        self.assertIn("Front | Back", sections[0].text)
        self.assertEqual(sections[1], TextSection("学习", slide_number=2))


class ChunkingTests(unittest.TestCase):
    def test_chunks_are_deterministic_keep_source_boundaries_and_overlap(self) -> None:
        document_id = uuid4()
        text = ("记忆间隔 supports recall. " * 120).strip()
        sections = [TextSection(text, page_number=1), TextSection("最后一页内容", page_number=2)]

        first = build_document_chunks(document_id, sections)
        second = build_document_chunks(document_id, sections)

        self.assertGreater(len(first), 2)
        self.assertEqual(first, second)
        self.assertEqual([chunk.chunk_index for chunk in first], list(range(len(first))))
        self.assertTrue(all(chunk.page_number == 1 for chunk in first[:-1]))
        self.assertEqual(first[-1].page_number, 2)
        self.assertIsNone(first[-1].slide_number)
        self.assertTrue(all(len(chunk.content_hash) == 64 for chunk in first))
        self.assertTrue(set(first[0].content.split()[-3:]) & set(first[1].content.split()[:8]))

    def test_empty_sections_produce_no_chunks(self) -> None:
        self.assertEqual(build_document_chunks(uuid4(), [TextSection(" \n ")]), [])


if __name__ == "__main__":
    unittest.main()
