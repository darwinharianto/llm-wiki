from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

VALID_CATEGORIES = ("concepts", "entities", "sources", "syntheses")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")
CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(text: str) -> str:
    """Normalize a string into a kebab-case slug (preserving Latin alphanumeric and CJK/Japanese scripts)."""
    norm = unicodedata.normalize("NFKC", text).strip().lower()
    cleaned = re.sub(
        r"[^a-z0-9\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\u3400-\u4dbf\uac00-\ud7af\s-]",
        "",
        norm,
    )
    cleaned = re.sub(r"[\s_・／]+", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "untitled-page"


def strip_code_regions(text: str) -> str:
    """Remove fenced code blocks and inline code so link parsing ignores code snippets."""
    no_blocks = CODE_BLOCK_RE.sub("", text)
    return INLINE_CODE_RE.sub("", no_blocks)


def extract_wikilink_targets(markdown_body: str) -> list[str]:
    """Extract raw [[target]] strings from markdown prose outside code spans."""
    cleaned = strip_code_regions(markdown_body)
    targets: list[str] = []
    seen: set[str] = set()
    for match in WIKILINK_RE.finditer(cleaned):
        raw_target = match.group(1).strip()
        if raw_target and raw_target not in seen:
            seen.add(raw_target)
            targets.append(raw_target)
    return targets


@dataclass
class WikiPage:
    """Parsed representation of a Markdown wiki page with frontmatter and graph links."""

    slug: str
    title: str
    category: str
    path: Path
    aliases: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    revision_count: int = 1
    confidence: str = "high"
    summary: str = ""
    body: str = ""
    raw_targets: list[str] = field(default_factory=list)
    outbound_links: list[str] = field(default_factory=list)
    dangling_links: list[str] = field(default_factory=list)
    backlinks: list[str] = field(default_factory=list)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "title": self.title,
            "category": self.category,
            "aliases": self.aliases,
            "tags": self.tags,
            "sources": self.sources,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision_count": self.revision_count,
            "confidence": self.confidence,
            "summary": self.summary,
            "outbound_links": self.outbound_links,
            "dangling_links": self.dangling_links,
            "backlinks": self.backlinks,
            "rel_path": f"wiki/{self.category}/{self.slug}.md",
            "word_count": len(self.body.split()),
        }

    def to_detail_dict(self) -> dict[str, Any]:
        data = self.to_summary_dict()
        data["body"] = self.body
        return data


class VaultManager:
    """Manages reading, writing, diffing, indexing, and logging for the Markdown vault."""

    def __init__(self, vault_dir: Path):
        self.vault_dir = Path(vault_dir)
        self.raw_dir = self.vault_dir / "raw"
        self.wiki_dir = self.vault_dir / "wiki"
        self.history_dir = self.vault_dir / ".history"
        self.schema_path = self.vault_dir / "SCHEMA.md"
        self.index_path = self.vault_dir / "index.md"
        self.log_path = self.vault_dir / "log.md"
        self.ensure_structure()

    def ensure_structure(self) -> None:
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        for cat in VALID_CATEGORIES:
            (self.wiki_dir / cat).mkdir(parents=True, exist_ok=True)

        if not self.schema_path.exists():
            self.schema_path.write_text(
                "# LLM Wiki Schema\n\nThree layers: raw/, wiki/, SCHEMA.md.\n",
                encoding="utf-8",
            )
        if not self.log_path.exists():
            self.log_path.write_text(
                "# Chronological Operation Log\n\n> Append-only record of wiki operations.\n",
                encoding="utf-8",
            )
        if not self.index_path.exists():
            self.rebuild_index()

    def _parse_markdown_file(self, path: Path) -> WikiPage:
        raw_text = path.read_text(encoding="utf-8")
        meta: dict[str, Any] = {}
        body = raw_text

        if raw_text.startswith("---\n"):
            parts = raw_text.split("\n---\n", 1)
            if len(parts) == 2:
                yaml_block = parts[0][4:]
                body = parts[1].lstrip("\n")
                loaded = yaml.safe_load(yaml_block)
                if isinstance(loaded, dict):
                    meta = loaded

        category = str(meta.get("category") or path.parent.name).lower()
        if category not in VALID_CATEGORIES:
            category = "concepts"

        slug = str(meta.get("slug") or path.stem)
        title = str(meta.get("title") or slug.replace("-", " ").title())
        aliases = [str(a) for a in (meta.get("aliases") or []) if str(a).strip()]
        tags = [str(t).strip().lower() for t in (meta.get("tags") or []) if str(t).strip()]
        sources = [str(s).strip() for s in (meta.get("sources") or []) if str(s).strip()]
        now = utc_now_iso()
        created_at = str(meta.get("created_at") or now)
        updated_at = str(meta.get("updated_at") or created_at)
        revision_count = int(meta.get("revision_count") or 1)
        confidence = str(meta.get("confidence") or "high")
        summary = str(meta.get("summary") or "").strip()
        if not summary:
            summary = self._derive_summary(body)

        raw_targets = extract_wikilink_targets(body)
        return WikiPage(
            slug=slug,
            title=title,
            category=category,
            path=path,
            aliases=aliases,
            tags=tags,
            sources=sources,
            created_at=created_at,
            updated_at=updated_at,
            revision_count=revision_count,
            confidence=confidence,
            summary=summary,
            body=body.strip(),
            raw_targets=raw_targets,
        )

    @staticmethod
    def _derive_summary(body: str) -> str:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("|") and not stripped.startswith(">"):
                cleaned = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), stripped)
                return cleaned[:177] + "..." if len(cleaned) > 180 else cleaned
        return "Compiled wiki page."

    def load_all_pages(self) -> dict[str, WikiPage]:
        """Load every wiki page and resolve outbound wikilinks, dangling links, and backlinks."""
        pages: dict[str, WikiPage] = {}
        for md_file in sorted(self.wiki_dir.rglob("*.md")):
            page = self._parse_markdown_file(md_file)
            pages[page.slug] = page

        # Build lookup map from slug, normalized title, and normalized aliases -> canonical slug
        lookup: dict[str, str] = {}
        for slug, page in pages.items():
            lookup[slug.lower()] = slug
            lookup[page.title.lower()] = slug
            lookup[slugify(page.title)] = slug
            for alias in page.aliases:
                lookup[alias.lower()] = slug
                lookup[slugify(alias)] = slug

        for page in pages.values():
            outbound: list[str] = []
            dangling: list[str] = []
            for raw_target in page.raw_targets:
                key_lower = raw_target.strip().lower()
                key_slug = slugify(raw_target)
                resolved = lookup.get(key_lower) or lookup.get(key_slug)
                if resolved and resolved != page.slug:
                    if resolved not in outbound:
                        outbound.append(resolved)
                elif not resolved:
                    if raw_target not in dangling:
                        dangling.append(raw_target)
            page.outbound_links = outbound
            page.dangling_links = dangling

        # Compute inbound backlinks
        for page in pages.values():
            for target_slug in page.outbound_links:
                if target_slug in pages and page.slug not in pages[target_slug].backlinks:
                    pages[target_slug].backlinks.append(page.slug)

        return pages

    def get_page(self, slug: str) -> WikiPage | None:
        pages = self.load_all_pages()
        if slug in pages:
            return pages[slug]
        norm = slugify(slug)
        return pages.get(norm)

    def render_markdown(self, page: WikiPage) -> str:
        frontmatter = {
            "title": page.title,
            "slug": page.slug,
            "category": page.category,
            "aliases": page.aliases,
            "tags": page.tags,
            "sources": page.sources,
            "created_at": page.created_at,
            "updated_at": page.updated_at,
            "revision_count": page.revision_count,
            "confidence": page.confidence,
            "summary": page.summary,
        }
        yaml_str = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()
        return f"---\n{yaml_str}\n---\n\n{page.body.strip()}\n"

    def save_page(
        self,
        *,
        slug: str,
        title: str,
        category: str,
        body: str,
        aliases: list[str] | None = None,
        tags: list[str] | None = None,
        sources: list[str] | None = None,
        summary: str | None = None,
        confidence: str = "high",
        operation: str = "update",
        change_note: str = "",
        rebuild_idx: bool = True,
    ) -> tuple[WikiPage, str]:
        """Create or update a wiki page on disk, storing a unified diff in .history/ when updating."""
        cat = category.lower() if category.lower() in VALID_CATEGORIES else "concepts"
        canonical_slug = slugify(slug)
        existing_pages = self.load_all_pages()
        existing = existing_pages.get(canonical_slug)
        now = utc_now_iso()

        if existing:
            target_path = existing.path
            old_text = target_path.read_text(encoding="utf-8")
            merged_aliases = list(dict.fromkeys(existing.aliases + (aliases or [])))
            merged_tags = list(dict.fromkeys([t.lower() for t in existing.tags] + [t.lower() for t in (tags or [])]))
            merged_sources = list(dict.fromkeys(existing.sources + (sources or [])))
            rev = existing.revision_count + 1
            created_at = existing.created_at or now
            final_summary = (summary or existing.summary or self._derive_summary(body)).strip()
            page_obj = WikiPage(
                slug=canonical_slug,
                title=title or existing.title,
                category=existing.category,
                path=target_path,
                aliases=merged_aliases,
                tags=merged_tags,
                sources=merged_sources,
                created_at=created_at,
                updated_at=now,
                revision_count=rev,
                confidence=confidence or existing.confidence,
                summary=final_summary,
                body=body.strip(),
            )
            new_text = self.render_markdown(page_obj)
            target_path.write_text(new_text, encoding="utf-8")
            diff_lines = list(
                difflib.unified_diff(
                    old_text.splitlines(),
                    new_text.splitlines(),
                    fromfile=f"a/{canonical_slug}.md (rev {existing.revision_count})",
                    tofile=f"b/{canonical_slug}.md (rev {rev})",
                    lineterm="",
                )
            )
            diff_text = "\n".join(diff_lines)
            self._record_history(canonical_slug, rev, operation, change_note or "Updated existing page", diff_text)
        else:
            target_path = self.wiki_dir / cat / f"{canonical_slug}.md"
            final_summary = (summary or self._derive_summary(body)).strip()
            page_obj = WikiPage(
                slug=canonical_slug,
                title=title,
                category=cat,
                path=target_path,
                aliases=list(dict.fromkeys(aliases or [])),
                tags=list(dict.fromkeys([t.lower() for t in (tags or [])])),
                sources=list(dict.fromkeys(sources or [])),
                created_at=now,
                updated_at=now,
                revision_count=1,
                confidence=confidence,
                summary=final_summary,
                body=body.strip(),
            )
            new_text = self.render_markdown(page_obj)
            target_path.write_text(new_text, encoding="utf-8")
            diff_text = "\n".join(f"+ {line}" for line in new_text.splitlines()[:40])
            self._record_history(canonical_slug, 1, "create", change_note or "Created new wiki page", diff_text)

        if rebuild_idx:
            self.rebuild_index()

        reloaded = self.get_page(canonical_slug)
        assert reloaded is not None
        return reloaded, diff_text

    def delete_page(self, slug: str, *, rebuild_idx: bool = True) -> bool:
        page = self.get_page(slug)
        if not page:
            return False
        if page.path.exists():
            page.path.unlink()
        if rebuild_idx:
            self.rebuild_index()
        return True

    def redirect_wikilinks_batch(
        self,
        redirects: list[tuple[str, str, str]],
        *,
        rebuild_idx: bool = False,
    ) -> list[str]:
        """Rewrite multiple (source_slug, source_title, target_slug) wikilinks in one pass."""
        if not redirects:
            return []
        compiled: list[tuple[str, str, str, re.Pattern[str], re.Pattern[str]]] = [
            (
                src_slug,
                src_title,
                tgt_slug,
                re.compile(rf"\[\[{re.escape(src_slug)}(\|[^\]]+)?\]\]", re.IGNORECASE),
                re.compile(rf"\[\[{re.escape(src_title)}(\|[^\]]+)?\]\]", re.IGNORECASE),
            )
            for src_slug, src_title, tgt_slug in redirects
            if src_slug != tgt_slug
        ]
        if not compiled:
            return []

        redirected_pages: list[str] = []
        pages = self.load_all_pages()
        source_slug_set = {s for s, _, _, _, _ in compiled}
        for p in pages.values():
            if p.slug in source_slug_set:
                continue
            new_body = p.body
            changed_sources: list[str] = []
            for src_slug, src_title, tgt_slug, link_pat, title_pat in compiled:
                if p.slug == tgt_slug:
                    continue
                updated = link_pat.sub(
                    lambda m, ts=tgt_slug, st=src_title: f"[[{ts}{m.group(1) or ('|' + st)}]]",
                    new_body,
                )
                updated = title_pat.sub(
                    lambda m, ts=tgt_slug, st=src_title: f"[[{ts}{m.group(1) or ('|' + st)}]]",
                    updated,
                )
                if updated != new_body:
                    new_body = updated
                    changed_sources.append(f"[[{src_slug}]]->[[{tgt_slug}]]")
            if new_body != p.body:
                self.save_page(
                    slug=p.slug,
                    title=p.title,
                    category=p.category,
                    body=new_body,
                    operation="merge-redirect",
                    change_note=f"Redirected links from merged pages: {', '.join(changed_sources[:6])}",
                    rebuild_idx=False,
                )
                redirected_pages.append(p.slug)
        if rebuild_idx and redirected_pages:
            self.rebuild_index()
        return redirected_pages

    def redirect_wikilinks(
        self,
        source_slug: str,
        source_title: str,
        target_slug: str,
        *,
        rebuild_idx: bool = False,
    ) -> list[str]:
        """Rewrite all [[source_slug]] and [[source_title]] wikilinks across the vault to [[target_slug]]."""
        return self.redirect_wikilinks_batch(
            [(source_slug, source_title, target_slug)],
            rebuild_idx=rebuild_idx,
        )

    def _record_history(self, slug: str, revision: int, operation: str, note: str, diff_text: str) -> None:
        hist_file = self.history_dir / f"{slug}.json"
        entries: list[dict[str, Any]] = []
        if hist_file.exists():
            try:
                entries = json.loads(hist_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                entries = []
        entries.append(
            {
                "revision": revision,
                "timestamp": utc_now_iso(),
                "operation": operation,
                "note": note,
                "diff": diff_text,
            }
        )
        hist_file.write_text(json.dumps(entries[-30:], indent=2), encoding="utf-8")

    def get_page_history(self, slug: str) -> list[dict[str, Any]]:
        hist_file = self.history_dir / f"{slugify(slug)}.json"
        if not hist_file.exists():
            return []
        try:
            data = json.loads(hist_file.read_text(encoding="utf-8"))
            return list(reversed(data))
        except json.JSONDecodeError:
            return []

    def get_recent_history(self, limit: int = 25) -> list[dict[str, Any]]:
        all_events: list[dict[str, Any]] = []
        for hist_file in self.history_dir.glob("*.json"):
            slug = hist_file.stem
            try:
                entries = json.loads(hist_file.read_text(encoding="utf-8"))
                for item in entries:
                    all_events.append({"slug": slug, **item})
            except json.JSONDecodeError:
                continue
        all_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_events[:limit]

    def save_raw_source(self, title: str, content: str, source_name: str | None = None) -> str:
        """Archive an immutable raw source document in vault/raw/."""
        date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        base_slug = slugify(source_name or title)[:60]
        filename = f"{date_prefix}-{base_slug}.md"
        target = self.raw_dir / filename
        counter = 2
        while target.exists():
            filename = f"{date_prefix}-{base_slug}-{counter}.md"
            target = self.raw_dir / filename
            counter += 1

        if not content.lstrip().startswith("#"):
            rendered = f"# {title}\n\nIngested: {utc_now_iso()}\n\n{content.strip()}\n"
        else:
            rendered = content.strip() + "\n"
        target.write_text(rendered, encoding="utf-8")
        return filename

    def list_raw_sources(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.raw_dir.glob("*.md"), reverse=True):
            text = path.read_text(encoding="utf-8")
            first_heading = path.stem
            for line in text.splitlines():
                if line.startswith("# "):
                    first_heading = line[2:].strip()
                    break
            items.append(
                {
                    "filename": path.name,
                    "title": first_heading,
                    "size_bytes": len(text.encode("utf-8")),
                    "preview": text[:280],
                    "content": text,
                }
            )
        return items

    def rebuild_index(self) -> str:
        """Regenerate vault/index.md grouped by category with summaries and metadata."""
        pages = self.load_all_pages()
        by_cat: dict[str, list[WikiPage]] = {cat: [] for cat in VALID_CATEGORIES}
        for page in pages.values():
            by_cat.setdefault(page.category, []).append(page)
        for cat_list in by_cat.values():
            cat_list.sort(key=lambda p: p.title.lower())

        counts_line = (
            f"_Total Pages: {len(pages)} | "
            f"Concepts: {len(by_cat['concepts'])} | "
            f"Entities: {len(by_cat['entities'])} | "
            f"Sources: {len(by_cat['sources'])} | "
            f"Syntheses: {len(by_cat['syntheses'])}_"
        )

        lines = [
            "# Wiki Index",
            "",
            "> Auto-maintained catalog of all compiled pages in `vault/wiki/`. Updated on every ingest, merge, edit, or lint pass.",
            "",
            counts_line,
            "",
        ]

        for cat in VALID_CATEGORIES:
            lines.append(f"## {cat.title()}")
            cat_pages = by_cat.get(cat, [])
            if not cat_pages:
                lines.append("_No pages in this category yet._")
            else:
                for p in cat_pages:
                    tags_str = ", ".join(p.tags[:5]) if p.tags else "untagged"
                    updated_short = p.updated_at[:10] if p.updated_at else "unknown"
                    lines.append(
                        f"- [[{p.slug}|{p.title}]] — {p.summary} "
                        f"*(tags: {tags_str} | sources: {len(p.sources)} | rev: {p.revision_count} | updated: {updated_short})*"
                    )
            lines.append("")

        rendered = "\n".join(lines).rstrip() + "\n"
        self.index_path.write_text(rendered, encoding="utf-8")
        return rendered

    def append_log(self, operation: str, title: str, bullets: list[str]) -> None:
        """Append a parseable chronological entry to vault/log.md."""
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        entry_lines = [f"\n## [{stamp}] {operation} | {title}"]
        for bullet in bullets:
            entry_lines.append(f"- {bullet}")
        entry_text = "\n".join(entry_lines) + "\n"
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(entry_text)

    def read_log_entries(self, limit: int = 30) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        text = self.log_path.read_text(encoding="utf-8")
        entries: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for line in text.splitlines():
            m = re.match(r"^## \[([^\]]+)\]\s+([^|]+)\|\s*(.+)$", line.strip())
            if m:
                if current:
                    entries.append(current)
                current = {
                    "timestamp": m.group(1).strip(),
                    "operation": m.group(2).strip(),
                    "title": m.group(3).strip(),
                    "details": [],
                }
            elif current and line.strip().startswith("- "):
                current["details"].append(line.strip()[2:])
        if current:
            entries.append(current)
        return list(reversed(entries))[:limit]

