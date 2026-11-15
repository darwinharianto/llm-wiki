from __future__ import annotations

import re
from typing import Any

from backend.config import RuntimeSettings
from backend.llm_providers import LLMService
from backend.similarity import HybridSimilarityEngine
from backend.vault_manager import VaultManager, WikiPage, slugify


def _mask_non_prose_spans(text: str) -> list[tuple[int, int]]:
    """Return character ranges (headings, code blocks, inline code, existing wikilinks) to protect from link injection."""
    protected: list[tuple[int, int]] = []
    for m in re.finditer(r"```.*?```", text, flags=re.DOTALL):
        protected.append((m.start(), m.end()))
    for pat in (
        r"`[^`\n]+`",
        r"\[\[[^\]]+\]\]",
        r"\[[^\]]+\]\([^)]+\)",
        r"^#{1,6}\s+[^\n]*$",
    ):
        for m in re.finditer(pat, text, flags=re.MULTILINE):
            protected.append((m.start(), m.end()))
    return protected


def _in_ranges(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(not (end <= rs or start >= re_) for rs, re_ in ranges)


class WikiLinter:
    """
    Autonomous Self-Maintenance Engine (Karpathy 'Lint' operation).
    Detects and heals unlinked mentions, orphan pages, dangling wikilinks,
    near-duplicates, documented contradictions, and index drift.
    """

    def __init__(self, vault: VaultManager, near_duplicate_threshold: float = 0.55):
        self.vault = vault
        self.near_duplicate_threshold = near_duplicate_threshold

    def audit(self) -> dict[str, Any]:
        pages = self.vault.load_all_pages()
        engine = HybridSimilarityEngine(pages)

        unlinked_mentions: list[dict[str, Any]] = []
        orphan_pages: list[dict[str, Any]] = []
        dangling_links: list[dict[str, Any]] = []
        near_duplicates: list[dict[str, Any]] = []
        contradictions: list[dict[str, Any]] = []

        # 1. Unlinked Mentions
        sorted_targets = sorted(pages.values(), key=lambda p: len(p.title), reverse=True)
        compiled_targets: list[tuple[WikiPage, list[tuple[str, str, re.Pattern[str]]]]] = []
        for tgt in sorted_targets:
            term_specs = []
            for term in [tgt.title, *[a for a in tgt.aliases if len(a) >= 5]]:
                if len(term) < 5:
                    continue
                term_specs.append(
                    (term, term.lower(), re.compile(rf"\b({re.escape(term)})\b", re.IGNORECASE))
                )
            if term_specs:
                compiled_targets.append((tgt, term_specs))

        for src in pages.values():
            src_body_lower = src.body.lower()
            protected = _mask_non_prose_spans(src.body)
            already_linked = set(src.outbound_links)
            for tgt, term_specs in compiled_targets:
                if tgt.slug == src.slug or tgt.slug in already_linked:
                    continue
                for _, term_lower, pat in term_specs:
                    if term_lower not in src_body_lower:
                        continue
                    for m in pat.finditer(src.body):
                        if not _in_ranges(m.start(), m.end(), protected):
                            unlinked_mentions.append(
                                {
                                    "source_slug": src.slug,
                                    "source_title": src.title,
                                    "target_slug": tgt.slug,
                                    "target_title": tgt.title,
                                    "matched_term": m.group(1),
                                }
                            )
                            break
                    else:
                        continue
                    break

        # 2. Orphan Pages (0 inbound links)
        for page in pages.values():
            if len(page.backlinks) == 0:
                orphan_pages.append(
                    {
                        "slug": page.slug,
                        "title": page.title,
                        "category": page.category,
                        "outbound_count": len(page.outbound_links),
                    }
                )

        # 3. Dangling Wikilinks
        for page in pages.values():
            for raw_target in page.dangling_links:
                suggestions = engine.search(raw_target, top_k=1, exclude_slug=page.slug)
                best = suggestions[0] if suggestions else None
                dangling_links.append(
                    {
                        "source_slug": page.slug,
                        "source_title": page.title,
                        "target_raw": raw_target,
                        "suggested_slug": best.slug if best and best.score >= 0.35 else None,
                        "suggested_title": best.title if best and best.score >= 0.35 else None,
                        "suggested_score": round(best.score, 4) if best else 0.0,
                    }
                )

        # 4. Near-Duplicate Pages (fast vectorized pairwise comparison)
        near_duplicates = engine.find_near_duplicate_pairs(threshold=self.near_duplicate_threshold)

        # 5. Contradictions / Tensions surfaced
        for page in pages.values():
            if "## Contradictions & Tensions" in page.body:
                section = page.body.split("## Contradictions & Tensions", 1)[1].split("\n## ", 1)[0].strip()
                items = [ln.strip("- ").strip() for ln in section.splitlines() if ln.strip().startswith("-")]
                if items:
                    contradictions.append(
                        {
                            "slug": page.slug,
                            "title": page.title,
                            "notes": items,
                        }
                    )

        # 6. Index Drift
        index_text = self.vault.index_path.read_text(encoding="utf-8") if self.vault.index_path.exists() else ""
        missing_from_index = [
            p.slug for p in pages.values() if f"[[{p.slug}" not in index_text
        ]

        # Compute Health Score (0-100)
        penalty = (
            len(unlinked_mentions) * 5
            + len(orphan_pages) * 8
            + len(dangling_links) * 7
            + len(near_duplicates) * 10
            + len(missing_from_index) * 6
        )
        health_score = max(10, 100 - penalty) if pages else 100

        return {
            "total_pages": len(pages),
            "health_score": health_score,
            "summary": {
                "unlinked_mentions": len(unlinked_mentions),
                "orphan_pages": len(orphan_pages),
                "dangling_links": len(dangling_links),
                "near_duplicates": len(near_duplicates),
                "contradictions_tracked": len(contradictions),
                "missing_from_index": len(missing_from_index),
            },
            "unlinked_mentions": unlinked_mentions,
            "orphan_pages": orphan_pages,
            "dangling_links": dangling_links,
            "near_duplicates": near_duplicates,
            "contradictions": contradictions,
            "missing_from_index": missing_from_index,
        }

    @staticmethod
    def _is_noisy_clone_slug(slug: str) -> int:
        if re.search(
            r"(?:^|-)(working-group-archive-memo|field-audit-log|archival-field-memo)(?:-|$)",
            slug,
        ):
            return 2
        if (
            re.search(
                r"(?:^|-)(copy|redundant|duplicate|notes-on|overview-notes|digest|report|memo|archival|archive|summary|excerpt|wave|mirror|sheet|addendum|protocol-summary|technical-note|working-group|field-audit|extended-procedures)(?:-|$)",
                slug,
            )
            or re.search(r"-[2-9]$", slug)
        ):
            return 1
        return 0

    @classmethod
    def _choose_canonical_target(cls, page_a: WikiPage, page_b: WikiPage) -> tuple[WikiPage, WikiPage]:
        """Pick the canonical target page (first) and redundant source page (second)."""

        def rank_key(p: WikiPage) -> tuple[int, int, int, int, str, int, str]:
            return (
                cls._is_noisy_clone_slug(p.slug),
                -p.revision_count,
                -len(p.backlinks),
                -len(p.sources),
                p.created_at,
                len(p.slug),
                p.slug,
            )

        if rank_key(page_a) <= rank_key(page_b):
            return page_a, page_b
        return page_b, page_a

    def auto_maintain(
        self,
        *,
        create_stubs_for_dangling: bool = True,
        merge_near_duplicates: bool = True,
    ) -> dict[str, Any]:
        """
        Autonomously heal the wiki:
          0. Auto-merge redundant / near-duplicate pages back into canonical pages.
          1. Inject [[wikilinks]] for unlinked mentions.
          2. Resolve dangling links to close existing pages or create stub concept pages.
          3. Connect orphan pages from their closest related hub pages.
          4. Rebuild index.md and log the maintenance pass in log.md.
        """
        before = self.audit()
        actions: list[str] = []
        working_audit = before

        # Step 0: Auto-merge redundant / near-duplicate pages
        if merge_near_duplicates and working_audit["near_duplicates"]:
            llm = LLMService(RuntimeSettings(provider="local_smart"))
            merged_any = False
            for _pass in range(3):
                pages = self.vault.load_all_pages()
                pairs = HybridSimilarityEngine(pages).find_near_duplicate_pairs(
                    threshold=self.near_duplicate_threshold
                )
                if not pairs:
                    break

                # Process pairs involving at least one clean canonical slug before clone-to-clone pairs
                pairs.sort(
                    key=lambda item: (
                        min(
                            self._is_noisy_clone_slug(item["slug_a"]),
                            self._is_noisy_clone_slug(item["slug_b"]),
                        ),
                        -item["score"],
                    )
                )

                redirect_map: dict[str, str] = {}
                batch_redirects: list[tuple[str, str, str]] = []
                merged_in_pass = False
                for pair in pairs:
                    sa = pair["slug_a"]
                    sb = pair["slug_b"]
                    while sa in redirect_map:
                        sa = redirect_map[sa]
                    while sb in redirect_map:
                        sb = redirect_map[sb]
                    if sa == sb:
                        continue
                    pa = pages.get(sa)
                    pb = pages.get(sb)
                    if not pa or not pb:
                        continue

                    tgt, src = self._choose_canonical_target(pa, pb)
                    clean_aliases = [
                        a
                        for a in [src.title, *src.aliases]
                        if not self._is_noisy_clone_slug(slugify(a))
                    ]
                    synth = llm._local_synthesize_page_update(
                        existing_page=tgt,
                        new_title=src.title,
                        new_content=src.body,
                        source_name=f"merged:{src.slug}",
                        new_tags=src.tags,
                        all_pages=pages,
                    )
                    self.vault.save_page(
                        slug=tgt.slug,
                        title=tgt.title,
                        category=tgt.category,
                        body=synth["updated_body"],
                        aliases=clean_aliases,
                        tags=src.tags,
                        sources=src.sources,
                        summary=synth.get("summary") or tgt.summary,
                        operation="lint-merge",
                        change_note=(
                            f"Auto-merged redundant page [[{src.slug}]] ({src.title}) into "
                            f"[[{tgt.slug}]] (similarity {pair['score']:.2f})"
                        ),
                        rebuild_idx=False,
                    )
                    batch_redirects.append((src.slug, src.title, tgt.slug))
                    self.vault.delete_page(src.slug, rebuild_idx=False)
                    redirect_map[src.slug] = tgt.slug
                    pages.pop(src.slug, None)
                    refreshed_tgt = self.vault._parse_markdown_file(tgt.path) if tgt.path.exists() else None
                    if refreshed_tgt:
                        pages[tgt.slug] = refreshed_tgt
                    actions.append(
                        f"Merged redundant page [[{src.slug}]] -> [[{tgt.slug}]] (score {pair['score']:.2f})"
                    )
                    merged_in_pass = True
                    merged_any = True

                if batch_redirects:
                    resolved_redirects = []
                    for src_s, src_t, tgt_s in batch_redirects:
                        final_t = tgt_s
                        while final_t in redirect_map:
                            final_t = redirect_map[final_t]
                        resolved_redirects.append((src_s, src_t, final_t))
                    self.vault.redirect_wikilinks_batch(resolved_redirects, rebuild_idx=False)

                if not merged_in_pass:
                    break

            if merged_any:
                working_audit = self.audit()

        # Short-circuit if nothing remains to heal
        ws = working_audit["summary"]
        if (
            not actions
            and ws["unlinked_mentions"] == 0
            and ws["dangling_links"] == 0
            and ws["orphan_pages"] == 0
            and ws["missing_from_index"] == 0
        ):
            return {
                "actions_taken": actions,
                "before_health": before["health_score"],
                "after_health": working_audit["health_score"],
                "audit": working_audit,
            }

        # Step 1: Heal unlinked mentions
        pages = self.vault.load_all_pages()
        mentions_by_src: dict[str, list[dict[str, Any]]] = {}
        for m in working_audit["unlinked_mentions"]:
            mentions_by_src.setdefault(m["source_slug"], []).append(m)

        for src_slug, items in mentions_by_src.items():
            page = pages.get(src_slug)
            if not page:
                continue
            updated_body = page.body
            healed_terms: list[str] = []
            for item in items:
                protected = _mask_non_prose_spans(updated_body)
                pat = re.compile(rf"\b({re.escape(item['matched_term'])})\b", re.IGNORECASE)
                match = next(
                    (m for m in pat.finditer(updated_body) if not _in_ranges(m.start(), m.end(), protected)),
                    None,
                )
                if match:
                    replacement = f"[[{item['target_slug']}|{match.group(1)}]]"
                    updated_body = (
                        updated_body[: match.start()]
                        + replacement
                        + updated_body[match.end() :]
                    )
                    healed_terms.append(item["target_slug"])
            if healed_terms:
                self.vault.save_page(
                    slug=page.slug,
                    title=page.title,
                    category=page.category,
                    body=updated_body,
                    operation="lint-link",
                    change_note=f"Auto-linked unlinked mentions: {', '.join(healed_terms)}",
                    rebuild_idx=False,
                )
                actions.append(f"Linked {', '.join(healed_terms)} inside [[{page.slug}]]")

        # Step 2: Resolve dangling links
        pages = self.vault.load_all_pages()
        for d in working_audit["dangling_links"]:
            src_page = pages.get(d["source_slug"])
            if not src_page:
                continue
            raw_target = d["target_raw"]
            if d["suggested_slug"] and d["suggested_score"] >= 0.40:
                target_slug = d["suggested_slug"]
                new_body = re.sub(
                    rf"\[\[{re.escape(raw_target)}(\|[^\]]+)?\]\]",
                    lambda m: f"[[{target_slug}{m.group(1) or ('|' + raw_target)}]]",
                    src_page.body,
                )
                if new_body != src_page.body:
                    self.vault.save_page(
                        slug=src_page.slug,
                        title=src_page.title,
                        category=src_page.category,
                        body=new_body,
                        operation="lint-resolve",
                        change_note=f"Resolved dangling link [[{raw_target}]] -> [[{target_slug}]]",
                        rebuild_idx=False,
                    )
                    actions.append(f"Resolved [[{raw_target}]] -> [[{target_slug}]] in [[{src_page.slug}]]")
            elif create_stubs_for_dangling:
                stub_slug = slugify(raw_target)
                if stub_slug not in pages:
                    stub_title = raw_target.replace("-", " ").title()
                    stub_body = (
                        f"# {stub_title}\n\n"
                        f"Auto-generated concept stub discovered from wikilink reference in [[{src_page.slug}|{src_page.title}]].\n\n"
                        f"## Related Pages\n\n- [[{src_page.slug}|{src_page.title}]]"
                    )
                    self.vault.save_page(
                        slug=stub_slug,
                        title=stub_title,
                        category="concepts",
                        body=stub_body,
                        tags=["stub", "auto-generated"],
                        sources=src_page.sources[:2],
                        confidence="evolving",
                        summary=f"Concept stub created during self-maintenance from link in {src_page.title}.",
                        operation="lint-stub",
                        change_note=f"Created missing concept page [[{stub_slug}]] referenced by [[{src_page.slug}]]",
                        rebuild_idx=False,
                    )
                    pages = self.vault.load_all_pages()
                    actions.append(f"Created concept stub [[{stub_slug}]] for dangling link in [[{src_page.slug}]]")

        # Step 3: Integrate orphan pages into their closest related hub page
        pages = self.vault.load_all_pages()
        engine = HybridSimilarityEngine(pages)
        for page in list(pages.values()):
            if len(page.backlinks) == 0 and len(pages) > 1:
                matches = engine.search(
                    f"{page.title} {page.summary} {' '.join(page.tags)}",
                    top_k=3,
                    query_tags=page.tags,
                    exclude_slug=page.slug,
                )
                # Prefer a non-orphan hub page if available
                hub_slug = None
                for m in matches:
                    if len(pages[m.slug].backlinks) > 0 or len(pages[m.slug].outbound_links) > 0:
                        hub_slug = m.slug
                        break
                if not hub_slug and matches:
                    hub_slug = matches[0].slug
                if hub_slug and hub_slug in pages:
                    hub = pages[hub_slug]
                    if page.slug not in hub.outbound_links:
                        addition = f"- Related trail: [[{page.slug}|{page.title}]] — {page.summary}"
                        if "## Related Concepts" in hub.body:
                            new_hub_body = f"{hub.body}\n{addition}"
                        else:
                            new_hub_body = f"{hub.body}\n\n## Related Concepts\n\n{addition}"
                        self.vault.save_page(
                            slug=hub.slug,
                            title=hub.title,
                            category=hub.category,
                            body=new_hub_body,
                            operation="lint-orphan",
                            change_note=f"Connected orphan page [[{page.slug}]] into hub [[{hub.slug}]]",
                            rebuild_idx=False,
                        )
                        pages = self.vault.load_all_pages()
                        actions.append(f"Connected orphan [[{page.slug}]] from [[{hub.slug}]]")

        # Step 4: Always rebuild index.md and log if changes happened
        self.vault.rebuild_index()
        after = self.audit()
        if actions or before["summary"]["missing_from_index"] > 0:
            self.vault.append_log(
                "lint",
                "Autonomous Self-Maintenance Pass",
                actions[:10] or ["Synchronized index.md and verified graph integrity."],
            )

        return {
            "actions_taken": actions,
            "before_health": before["health_score"],
            "after_health": after["health_score"],
            "audit": after,
        }
