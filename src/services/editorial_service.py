from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Iterable, Optional

from src.storage.editorial_repository import EditorialRepository


class EditorialService:
    def __init__(self, repo: EditorialRepository):
        self.repo = repo

    def add_note(self, article_id: int, author_id: int, body: str) -> dict:
        return self.repo.add_note(article_id, author_id, body)

    def list_notes(self, article_id: int) -> list[dict]:
        return self.repo.list_notes(article_id)

    def create_collection(self, name: str, description: str = "", owner_id: Optional[int] = None, is_shared: bool = False) -> dict:
        return self.repo.create_collection(name, description, owner_id, is_shared)

    def list_collections(self, user_id: Optional[int] = None) -> list[dict]:
        return self.repo.list_collections(user_id)

    def bookmark(self, user_id: int, article_id: int) -> bool:
        return self.repo.bookmark(user_id, article_id)

    def unbookmark(self, user_id: int, article_id: int) -> bool:
        return self.repo.unbookmark(user_id, article_id)

    def add_article_to_collection(self, collection_id: int, article_id: int) -> bool:
        return self.repo.add_article_to_collection(collection_id, article_id)

    def remove_article_from_collection(self, collection_id: int, article_id: int) -> bool:
        return self.repo.remove_article_from_collection(collection_id, article_id)

    def add_tag(self, name: str) -> dict:
        return self.repo.add_tag(name)

    def list_tags(self) -> list[dict]:
        return self.repo.list_tags()

    def set_article_tags(self, article_id: int, tag_names: Iterable[str]) -> list[dict]:
        return self.repo.set_article_tags(article_id, tag_names)

    def export_csv(self, article_rows: list[dict], filename: str = "export.csv") -> bytes:
        output = io.StringIO(newline="")
        fieldnames = [
            "title", "source", "published_at", "url", "category", "tags", "status", "collection"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in article_rows:
            safe = {
                "title": (row.get("title") or "").replace("\r", " ").replace("\n", " "),
                "source": (row.get("source") or "").replace("\r", " ").replace("\n", " "),
                "published_at": row.get("published_at") or "",
                "url": row.get("url") or "",
                "category": row.get("category") or "",
                "tags": ", ".join(row.get("tags") or []),
                "status": row.get("status") or "",
                "collection": row.get("collection") or "",
            }
            if "=" in safe["title"]:
                safe["title"] = "'" + safe["title"]
            writer.writerow(safe)
        return output.getvalue().encode("utf-8-sig")

    def export_pdf(self, article_rows: list[dict], title: str = "AfricanPulse Oasis report") -> bytes:
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        except ImportError:
            raise RuntimeError("PDF export requires the reportlab dependency.")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, title=title)
        styles = getSampleStyleSheet()
        story = [Paragraph(title, styles["Title"]), Spacer(1, 16)]
        story.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", styles["BodyText"]))
        story.append(Spacer(1, 12))
        for idx, row in enumerate(article_rows, start=1):
            story.append(Paragraph(f"{idx}. {row.get('title') or 'Untitled'}", styles["Heading2"]))
            story.append(Paragraph(f"Source: {row.get('source') or 'Unknown'}", styles["BodyText"]))
            story.append(Paragraph(f"Status: {row.get('status') or 'Unspecified'} | Category: {row.get('category') or 'Uncategorized'}", styles["BodyText"]))
            if row.get("url"):
                story.append(Paragraph(f"URL: {row.get('url')}", styles["BodyText"]))
            story.append(Spacer(1, 8))
        doc.build(story)
        return buffer.getvalue()
