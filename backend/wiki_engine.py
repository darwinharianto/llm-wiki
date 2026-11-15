from __future__ import annotations

import re
import time
from typing import Any

from backend.config import RuntimeSettings
from backend.linter import WikiLinter
from backend.llm_providers import LLMService
from backend.similarity import HybridSimilarityEngine
from backend.telemetry import TelemetryTracker
from backend.vault_manager import VaultManager, slugify


class WikiEngine:
    """Orchestrates Similarity-First Ingest, Update/Merge, Graph generation, Chat, and Self-Maintenance."""

    def __init__(self, vault: VaultManager, settings: RuntimeSettings):
        self.vault = vault
        self.settings = settings
        self.telemetry = TelemetryTracker(log_file=self.vault.vault_dir / "telemetry.jsonl")
        self.llm = LLMService(settings, telemetry=self.telemetry)

    def update_settings(self, new_settings: RuntimeSettings) -> None:
        self.settings = new_settings
        self.llm = LLMService(new_settings, telemetry=self.telemetry)

    # ------------------------------------------------------------------
    # Search & Similarity
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        pages = self.vault.load_all_pages()
        engine = HybridSimilarityEngine(pages)
        return [m.to_dict() for m in engine.search(query, top_k=top_k)]

    # ------------------------------------------------------------------
    # Ingest: Search Similar Existing -> Update Instead of Build New
    # ------------------------------------------------------------------

    def preview_ingest(
        self,
        *,
        title: str,
        content: str,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        start_cursor = self.telemetry.cursor()
        eff_threshold = threshold if threshold is not None else self.settings.similarity_threshold
        pages = self.vault.load_all_pages()
        engine = HybridSimilarityEngine(pages)
        candidates = self.llm.extract_candidates(title, content, pages)

        plan_items: list[dict[str, Any]] = []
        for idx, item in enumerate(candidates):
            t_sim = time.perf_counter()
            sim = engine.find_similar_for_candidate(
                title=item["title"],
                content=item["body"],
                tags=item.get("tags", []),
                aliases=item.get("aliases", []),
                threshold=eff_threshold,
            )
            sim_lat_ms = (time.perf_counter() - t_sim) * 1000.0
            self.telemetry.record_event(
                operation="similarity_routing",
                llm_used=False,
                execution_mode="local_smart",
                provider="local_smart",
                model="hybrid_bm25_tfidf_graph",
                status="ok",
                latency_ms=sim_lat_ms,
                target_slug=sim.get("target_slug") or slugify(item["title"]),
                reason=f"Preview routing decision={sim['action']} (best_score={sim['best_score']:.3f})",
            )
            existing_target = pages.get(sim["target_slug"]) if sim["target_slug"] else None
            plan_items.append(
                {
                    "index": idx,
                    "extracted_title": item["title"],
                    "category": item.get("category", "concepts"),
                    "tags": item.get("tags", []),
                    "summary": item.get("summary", ""),
                    "decision": sim["action"],  # "update" or "create"
                    "threshold": eff_threshold,
                    "best_score": sim["best_score"],
                    "target_slug": sim["target_slug"],
                    "target_title": sim["target_title"],
                    "target_revision": existing_target.revision_count if existing_target else None,
                    "matches": sim["candidates"],
                }
            )

        return {
            "provider_mode": self.llm.active_mode(),
            "model_name": self.llm.active_model_name(),
            "threshold": eff_threshold,
            "items": plan_items,
            "telemetry": self.telemetry.summarize_slice(start_cursor),
        }

    def execute_ingest(
        self,
        *,
        title: str,
        content: str,
        source_name: str | None = None,
        force_target_slug: str | None = None,
        force_create: bool = False,
        threshold: float | None = None,
        archive_raw: bool = True,
        operation_label: str = "ingest",
    ) -> dict[str, Any]:
        start_cursor = self.telemetry.cursor()
        eff_threshold = threshold if threshold is not None else self.settings.similarity_threshold
        raw_filename = (
            self.vault.save_raw_source(title, content, source_name=source_name)
            if archive_raw
            else (source_name or "chat-synthesis")
        )

        pages = self.vault.load_all_pages()
        engine = HybridSimilarityEngine(pages)
        candidates = self.llm.extract_candidates(title, content, pages)

        results: list[dict[str, Any]] = []
        updated_slugs: list[str] = []
        created_slugs: list[str] = []

        for idx, item in enumerate(candidates):
            pages = self.vault.load_all_pages()
            engine = HybridSimilarityEngine(pages)

            chosen_target_slug: str | None = None
            sim_score = 0.0
            sim_matches: list[dict[str, Any]] = []

            if idx == 0 and force_target_slug and force_target_slug in pages:
                chosen_target_slug = force_target_slug
                sim_score = 1.0
            elif not force_create:
                sim = engine.find_similar_for_candidate(
                    title=item["title"],
                    content=item["body"],
                    tags=item.get("tags", []),
                    aliases=item.get("aliases", []),
                    threshold=eff_threshold,
                )
                sim_matches = sim["candidates"]
                sim_score = sim["best_score"]
                if sim["action"] == "update" and sim["target_slug"] in pages:
                    chosen_target_slug = sim["target_slug"]

            if chosen_target_slug:
                existing = pages[chosen_target_slug]
                synth = self.llm.synthesize_page_update(
                    existing_page=existing,
                    new_title=item["title"],
                    new_content=item["body"],
                    source_name=raw_filename,
                    new_tags=item.get("tags", []),
                    new_aliases=item.get("aliases", []),
                    all_pages=pages,
                )
                saved_page, diff_text = self.vault.save_page(
                    slug=existing.slug,
                    title=existing.title,
                    category=existing.category,
                    body=synth["updated_body"],
                    aliases=item.get("aliases", []),
                    tags=item.get("tags", []),
                    sources=[raw_filename],
                    summary=synth.get("summary") or existing.summary,
                    operation="update",
                    change_note=synth.get("change_note")
                    or f"Updated from {raw_filename} (similarity {int(sim_score * 100)}%)",
                    rebuild_idx=False,
                )
                updated_slugs.append(saved_page.slug)
                results.append(
                    {
                        "action": "updated",
                        "slug": saved_page.slug,
                        "title": saved_page.title,
                        "category": saved_page.category,
                        "revision_count": saved_page.revision_count,
                        "similarity_score": round(sim_score, 4),
                        "change_note": synth.get("change_note", ""),
                        "novel_added": synth.get("novel_added", 0),
                        "redundant_skipped": synth.get("redundant_skipped", 0),
                        "diff": diff_text,
                        "matches": sim_matches,
                    }
                )
            else:
                new_slug = slugify(item["title"])
                # Ensure uniqueness only if a page with exact slug exists & force_create was requested
                if new_slug in pages and force_create:
                    counter = 2
                    while f"{new_slug}-{counter}" in pages:
                        counter += 1
                    new_slug = f"{new_slug}-{counter}"

                saved_page, diff_text = self.vault.save_page(
                    slug=new_slug,
                    title=item["title"],
                    category=item.get("category", "concepts"),
                    body=item["body"],
                    aliases=item.get("aliases", []),
                    tags=item.get("tags", []),
                    sources=[raw_filename],
                    summary=item.get("summary", ""),
                    operation="create",
                    change_note=f"Created from {raw_filename}",
                    rebuild_idx=False,
                )
                created_slugs.append(saved_page.slug)
                results.append(
                    {
                        "action": "created",
                        "slug": saved_page.slug,
                        "title": saved_page.title,
                        "category": saved_page.category,
                        "revision_count": saved_page.revision_count,
                        "similarity_score": round(sim_score, 4),
                        "change_note": f"Created new {saved_page.category} page.",
                        "diff": diff_text,
                        "matches": sim_matches,
                    }
                )

        self.vault.rebuild_index()

        log_bullets = [f"Raw Source: `vault/raw/{raw_filename}`" if archive_raw else f"Origin: {raw_filename}"]
        if updated_slugs:
            log_bullets.append(
                "Updated Existing: " + ", ".join(f"[[{s}]]" for s in updated_slugs)
            )
        if created_slugs:
            log_bullets.append(
                "Created New: " + ", ".join(f"[[{s}]]" for s in created_slugs)
            )
        op = "update" if updated_slugs and not created_slugs else operation_label
        self.vault.append_log(op, title, log_bullets)

        maintenance_report = None
        if self.settings.auto_maintain_after_ingest:
            linter = WikiLinter(self.vault, near_duplicate_threshold=self.settings.near_duplicate_threshold)
            maintenance_report = linter.auto_maintain(
                create_stubs_for_dangling=False,
                merge_near_duplicates=False,
            )

        return {
            "raw_filename": raw_filename if archive_raw else None,
            "provider_mode": self.llm.active_mode(),
            "model_name": self.llm.active_model_name(),
            "results": results,
            "updated_slugs": updated_slugs,
            "created_slugs": created_slugs,
            "maintenance": maintenance_report,
            "telemetry": self.telemetry.summarize_slice(start_cursor),
        }

    # ------------------------------------------------------------------
    # Explicit Merge of Two Existing Pages
    # ------------------------------------------------------------------

    def merge_pages(self, source_slug: str, target_slug: str) -> dict[str, Any]:
        pages = self.vault.load_all_pages()
        src = pages.get(source_slug)
        tgt = pages.get(target_slug)
        if not src or not tgt or src.slug == tgt.slug:
            raise ValueError("Both source_slug and target_slug must exist and be distinct.")

        synth = self.llm.synthesize_page_update(
            existing_page=tgt,
            new_title=src.title,
            new_content=src.body,
            source_name=f"merged:{src.slug}",
            new_tags=src.tags,
            new_aliases=[src.title, *src.aliases],
            all_pages=pages,
        )
        saved_target, diff_text = self.vault.save_page(
            slug=tgt.slug,
            title=tgt.title,
            category=tgt.category,
            body=synth["updated_body"],
            aliases=[src.title, *src.aliases],
            tags=src.tags,
            sources=src.sources,
            summary=synth.get("summary") or tgt.summary,
            operation="merge",
            change_note=f"Merged page [[{src.slug}]] ({src.title}) into [[{tgt.slug}]]",
            rebuild_idx=False,
        )

        # Redirect all [[source_slug]] and [[source_title]] links across the vault to [[target_slug]]
        redirected_pages = self.vault.redirect_wikilinks(src.slug, src.title, tgt.slug, rebuild_idx=False)

        self.vault.delete_page(src.slug)
        self.vault.append_log(
            "merge",
            f"{src.title} -> {tgt.title}",
            [
                f"Merged `[[{src.slug}]]` into `[[{tgt.slug}]]`",
                f"Redirected inbound links in {len(redirected_pages)} page(s)",
            ],
        )

        return {
            "merged_into": saved_target.to_detail_dict(),
            "removed_slug": src.slug,
            "redirected_pages": redirected_pages,
            "diff": diff_text,
        }

    # ------------------------------------------------------------------
    # Graph Visualization Builder
    # ------------------------------------------------------------------

    def build_graph(self, include_semantic_edges: bool = True) -> dict[str, Any]:
        pages = self.vault.load_all_pages()
        engine = HybridSimilarityEngine(pages)

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        edge_keys: set[tuple[str, str, str]] = set()

        for slug, page in pages.items():
            degree = len(page.outbound_links) + len(page.backlinks)
            nodes.append(
                {
                    "id": slug,
                    "title": page.title,
                    "category": page.category,
                    "summary": page.summary,
                    "tags": page.tags,
                    "degree": degree,
                    "inbound": len(page.backlinks),
                    "outbound": len(page.outbound_links),
                    "revision_count": page.revision_count,
                    "is_orphan": len(page.backlinks) == 0,
                    "is_hub": degree >= 4,
                }
            )
            for target_slug in page.outbound_links:
                key = (slug, target_slug, "wikilink")
                if key not in edge_keys:
                    edge_keys.add(key)
                    edges.append(
                        {
                            "source": slug,
                            "target": target_slug,
                            "type": "wikilink",
                            "weight": 1.0,
                        }
                    )

        if include_semantic_edges:
            seen_sem: set[tuple[str, str]] = set()
            for slug, page in pages.items():
                similar = engine.search(
                    f"{page.title} {page.summary} {' '.join(page.tags)}",
                    top_k=3,
                    query_tags=page.tags,
                    exclude_slug=slug,
                )
                for m in similar:
                    if m.score < 0.34:
                        continue
                    pair = tuple(sorted((slug, m.slug)))
                    if pair in seen_sem:
                        continue
                    # Skip semantic edge if a direct wikilink already connects them
                    if (slug, m.slug, "wikilink") in edge_keys or (m.slug, slug, "wikilink") in edge_keys:
                        continue
                    seen_sem.add(pair)
                    edges.append(
                        {
                            "source": slug,
                            "target": m.slug,
                            "type": "semantic",
                            "weight": round(m.score, 3),
                        }
                    )

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "wikilink_edges": sum(1 for e in edges if e["type"] == "wikilink"),
                "semantic_edges": sum(1 for e in edges if e["type"] == "semantic"),
                "orphan_count": sum(1 for n in nodes if n["is_orphan"]),
            },
        }

    # ------------------------------------------------------------------
    # Grounded Chat & File-to-Wiki
    # ------------------------------------------------------------------

    def chat(self, question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        start_cursor = self.telemetry.cursor()
        t_search = time.perf_counter()
        pages = self.vault.load_all_pages()
        engine = HybridSimilarityEngine(pages)
        matches = engine.search(question, top_k=5)
        search_lat_ms = (time.perf_counter() - t_search) * 1000.0
        self.telemetry.record_event(
            operation="similarity_search",
            llm_used=False,
            execution_mode="local_smart",
            provider="local_smart",
            model="hybrid_bm25_tfidf_graph",
            status="ok",
            latency_ms=search_lat_ms,
            target_slug=matches[0].slug if matches else "",
            reason=f"Retrieved {len(matches)} page(s) for chat query",
        )

        retrieved: list[tuple[Any, float]] = []
        for m in matches:
            if m.slug in pages:
                retrieved.append((pages[m.slug], m.score))
        # Ensure at least top 2 pages if query was broad
        if not retrieved and pages:
            for p in list(pages.values())[:2]:
                retrieved.append((p, 0.25))

        index_md = self.vault.index_path.read_text(encoding="utf-8") if self.vault.index_path.exists() else ""
        answer = self.llm.answer_wiki_query(
            question=question,
            history=history or [],
            retrieved_pages=retrieved,
            index_markdown=index_md,
        )

        cited_pages = [
            {
                "slug": p.slug,
                "title": p.title,
                "category": p.category,
                "score": round(score, 4),
            }
            for p, score in retrieved
        ]

        self.vault.append_log(
            "query",
            question[:80],
            [
                "Consulted: "
                + (", ".join(f"[[{c['slug']}]]" for c in cited_pages) or "none"),
            ],
        )

        return {
            "answer": answer,
            "cited_pages": cited_pages,
            "provider_mode": self.llm.active_mode(),
            "model_name": self.llm.active_model_name(),
            "telemetry": self.telemetry.summarize_slice(start_cursor),
        }

    def file_answer_to_wiki(
        self,
        *,
        title: str,
        answer_markdown: str,
        question: str = "",
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """File a valuable chat synthesis back into the wiki (searching similar pages to update first)."""
        combined = answer_markdown
        if question:
            combined = f"> Synthesized from query: *{question}*\n\n{answer_markdown}"
        return self.execute_ingest(
            title=title,
            content=combined,
            source_name=f"chat-query-{slugify(title)[:32]}",
            threshold=threshold,
            archive_raw=False,
            operation_label="query-file",
        )

