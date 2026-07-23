from repository import ChromaRepository
from schemas import Chapter, Section


class CatalogService:
    def __init__(self, repository: ChromaRepository) -> None:
        self._repository = repository

    def chapters(self) -> list[Chapter]:
        rows = self._repository.all_metadata()

        # Every paragraph repeats its chapter_title/section_title, so we
        # dedupe. Structure: chapter_title -> { section_title -> start_page }
        grouped: dict[str, dict[str, int]] = {}
        for row in rows:
            chapter = row.get("chapter_title")
            section = row.get("section_title")
            page = row.get("page")
            if not chapter or not section:
                continue
            sections = grouped.setdefault(chapter, {})
            # keep the smallest page seen for a section = where it starts
            if section not in sections or (page is not None and page < sections[section]):
                sections[section] = page

        # Order sections by page within a chapter, chapters by first page.
        chapters: list[Chapter] = []
        for chapter_title, sections in grouped.items():
            ordered = sorted(sections.items(), key=lambda kv: kv[1] or 0)
            chapters.append(
                Chapter(
                    title=chapter_title,
                    sections=[Section(title=t, page=p) for t, p in ordered],
                )
            )
        chapters.sort(key=lambda c: c.sections[0].page or 0)
        return chapters