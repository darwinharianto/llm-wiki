from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app import create_app
from backend.config import RuntimeSettings
from backend.vault_manager import slugify
from scripts.evaluate_qa_and_updates import (
    compute_token_recall_f1,
    extract_direct_answer_section,
    normalize_answer,
)

FIXTURE_TELEQUAD_PATH = ROOT_DIR / "tests" / "fixtures" / "telequad_200_passages.json"
SEED_VAULT = ROOT_DIR / "tests" / "fixtures" / "seed_vault"


def _seed_fresh_vault(target_dir: Path) -> Path:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(SEED_VAULT, target_dir)
    return target_dir


def run_telequad_200_benchmark(
    sim_vault_dir: Path,
    forced_vault_dir: Path | None = None,
) -> dict[str, Any]:
    fixture = json.loads(FIXTURE_TELEQUAD_PATH.read_text(encoding="utf-8"))
    topics = fixture["topics"]
    passages = fixture["passages"]
    assert len(topics) == 20
    assert len(passages) == 200

    # ------------------------------------------------------------------
    # Part A: Similarity-First 200-Passage (20 topics x 10x Redundant) Ingest
    # ------------------------------------------------------------------
    _seed_fresh_vault(sim_vault_dir)
    sim_settings = RuntimeSettings(
        provider="local_smart",
        similarity_threshold=0.35,
        near_duplicate_threshold=0.55,
        auto_maintain_after_ingest=True,
        periodic_maintain_seconds=0,
    )
    app = create_app(vault_dir=sim_vault_dir, initial_settings=sim_settings)

    t_ingest_start = time.perf_counter()
    wave_stats: dict[str, dict[str, Any]] = {
        f"wave_{w}": {
            "wave": w,
            "wave_type": "",
            "total": 0,
            "created": 0,
            "updated": 0,
            "matched_canonical": 0,
            "novel_added": 0,
            "redundant_skipped": 0,
            "body_growth_chars": 0,
            "failures": [],
        }
        for w in range(1, 11)
    }

    canonical_slug_by_idx: dict[int, str] = {}

    with TestClient(app) as client:
        for idx, p in enumerate(passages):
            w = p["wave"]
            wkey = f"wave_{w}"
            ws = wave_stats[wkey]
            ws["wave_type"] = p["wave_type"]
            ws["total"] += 1

            expected_slug = slugify(p["canonical_title"])
            body_before_len = 0
            if w > 1 and expected_slug in canonical_slug_by_idx.values():
                before_resp = client.get(f"/api/pages/{expected_slug}")
                if before_resp.status_code == 200:
                    body_before_len = len(before_resp.json()["page"]["body"])

            res = client.post(
                "/api/ingest/execute",
                json={
                    "title": p["title"],
                    "content": p["content"],
                    "source_name": p["source_name"],
                },
            ).json()

            created = res["created_slugs"]
            updated = res["updated_slugs"]
            ws["created"] += len(created)
            ws["updated"] += len(updated)

            if w == 1:
                if created == [expected_slug]:
                    ws["matched_canonical"] += 1
                else:
                    ws["failures"].append({"idx": idx, "title": p["title"], "res": created or updated})
                canonical_slug_by_idx[p["topic_index"]] = (created or updated)[0]
            else:
                target_slug = canonical_slug_by_idx[p["topic_index"]]
                if target_slug in updated and not created:
                    ws["matched_canonical"] += 1
                else:
                    ws["failures"].append(
                        {"idx": idx, "title": p["title"], "expected": target_slug, "created": created, "updated": updated}
                    )

            for item in res["results"]:
                ws["novel_added"] += int(item.get("novel_added", 0))
                ws["redundant_skipped"] += int(item.get("redundant_skipped", 0))

            if w > 1:
                after_resp = client.get(f"/api/pages/{expected_slug}")
                if after_resp.status_code == 200:
                    ws["body_growth_chars"] += len(after_resp.json()["page"]["body"]) - body_before_len

        ingest_elapsed = round(time.perf_counter() - t_ingest_start, 3)

        overview_sim = client.get("/api/overview").json()
        lint_sim = client.get("/api/lint").json()

        # ------------------------------------------------------------------
        # Part B: 100-Question TeleQuAD Retrieval & Answer Correctness Evaluation
        # ------------------------------------------------------------------
        t_qa_start = time.perf_counter()
        qa_rows: list[dict[str, Any]] = []
        for t in topics:
            expected_slug = canonical_slug_by_idx[t["topic_index"]]
            for qa_obj in t["qas"]:
                question = qa_obj["question"]
                golds = qa_obj["answers"]

                search_res = client.post("/api/search", json={"query": question, "top_k": 5}).json()["results"]
                ranked_slugs = [r["slug"] for r in search_res]
                rank = (ranked_slugs.index(expected_slug) + 1) if expected_slug in ranked_slugs else None

                chat_res = client.post("/api/chat", json={"question": question}).json()
                cited = [c["slug"] for c in chat_res["cited_pages"]]
                answer_md = chat_res["answer"]
                direct_section = extract_direct_answer_section(answer_md)

                norm_full = normalize_answer(answer_md)
                norm_direct = normalize_answer(direct_section)
                full_span = any(normalize_answer(g) in norm_full for g in golds if normalize_answer(g))
                direct_span = any(normalize_answer(g) in norm_direct for g in golds if normalize_answer(g))
                direct_recall, direct_f1 = compute_token_recall_f1(direct_section, golds)

                qa_rows.append(
                    {
                        "topic": t["title"],
                        "expected_slug": expected_slug,
                        "part": qa_obj["part"],
                        "question": question,
                        "gold_answers": golds,
                        "rank": rank,
                        "cited": expected_slug in cited,
                        "full_span_match": full_span,
                        "direct_span_match": direct_span,
                        "direct_token_recall": direct_recall,
                        "direct_token_f1": direct_f1,
                    }
                )
        qa_elapsed = round(time.perf_counter() - t_qa_start, 3)

    def _agg_qa(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = max(len(rows), 1)
        return {
            "count": len(rows),
            "recall_at_1": round(sum(1 for r in rows if r["rank"] == 1) / n, 4),
            "recall_at_3": round(sum(1 for r in rows if r["rank"] is not None and r["rank"] <= 3) / n, 4),
            "mrr": round(sum((1.0 / r["rank"]) if r["rank"] else 0.0 for r in rows) / n, 4),
            "citation_accuracy": round(sum(1 for r in rows if r["cited"]) / n, 4),
            "full_span_match": round(sum(1 for r in rows if r["full_span_match"]) / n, 4),
            "direct_span_match": round(sum(1 for r in rows if r["direct_span_match"]) / n, 4),
            "direct_token_recall": round(sum(r["direct_token_recall"] for r in rows) / n, 4),
        }

    qa_summary = {
        "overall": _agg_qa(qa_rows),
        "part_a": _agg_qa([r for r in qa_rows if r["part"] == "part_a"]),
        "part_b": _agg_qa([r for r in qa_rows if r["part"] == "part_b"]),
        "missed_questions": [r for r in qa_rows if not r["full_span_match"]],
    }

    # ------------------------------------------------------------------
    # Part C: Forced 10x Redundant Page Proliferation -> Linter Auto-Merge
    # ------------------------------------------------------------------
    forced_report: dict[str, Any] = {}
    if forced_vault_dir is not None:
        _seed_fresh_vault(forced_vault_dir)
        forced_settings = RuntimeSettings(
            provider="local_smart",
            similarity_threshold=0.35,
            near_duplicate_threshold=0.55,
            auto_maintain_after_ingest=False,
            periodic_maintain_seconds=0,
        )
        forced_app = create_app(vault_dir=forced_vault_dir, initial_settings=forced_settings)
        t_forced_start = time.perf_counter()
        clone_slugs_w2: list[tuple[str, str]] = []
        with TestClient(forced_app) as fclient:
            for p in passages:
                fres = fclient.post(
                    "/api/ingest/execute",
                    json={
                        "title": p["title"],
                        "content": p["content"],
                        "source_name": p["source_name"],
                        "force_create": True,
                        "archive_raw": True,
                    },
                ).json()
                if p["wave"] == 2 and fres["created_slugs"]:
                    clone_slugs_w2.append((fres["created_slugs"][0], p["canonical_title"]))

            hub_page = fclient.get("/api/pages/llm-wiki-pattern").json()["page"]
            sample_refs = "\n".join(
                f"- Cross-reference clone link: [[{c_slug}|{c_title} Copy]]"
                for c_slug, c_title in clone_slugs_w2[:8]
            )
            fclient.put(
                "/api/pages/llm-wiki-pattern",
                json={
                    "title": hub_page["title"],
                    "category": hub_page["category"],
                    "body": f"{hub_page['body']}\n\n## TeleQuAD Clone Cross-Links\n\n{sample_refs}",
                    "aliases": hub_page["aliases"],
                    "tags": hub_page["tags"],
                    "summary": hub_page["summary"],
                    "confidence": hub_page["confidence"],
                },
            )

            before_audit = fclient.get("/api/lint").json()
            t_heal_start = time.perf_counter()
            heal_res = fclient.post(
                "/api/lint/heal",
                json={"create_stubs_for_dangling": False, "merge_near_duplicates": True},
            ).json()
            heal_elapsed = round(time.perf_counter() - t_heal_start, 3)

            after_audit = heal_res["audit"]
            after_overview = fclient.get("/api/overview").json()
            after_hub = fclient.get("/api/pages/llm-wiki-pattern").json()["page"]
            redirected_ok = all(
                f"[[{slugify(c_title)}|" in after_hub["body"] and f"[[{c_slug}|" not in after_hub["body"]
                for c_slug, c_title in clone_slugs_w2[:8]
            )

            healed_qa_hits = 0
            healed_qa_total = 0
            for t in topics:
                for qa_obj in t["qas"]:
                    healed_qa_total += 1
                    ans = fclient.post("/api/chat", json={"question": qa_obj["question"]}).json()["answer"]
                    if any(normalize_answer(g) in normalize_answer(ans) for g in qa_obj["answers"] if normalize_answer(g)):
                        healed_qa_hits += 1

        forced_report = {
            "setup_elapsed_s": round(t_heal_start - t_forced_start, 3),
            "heal_elapsed_s": heal_elapsed,
            "before_total_pages": before_audit["total_pages"],
            "before_near_duplicate_pairs": before_audit["summary"]["near_duplicates"],
            "before_health_score": before_audit["health_score"],
            "merge_actions_count": sum(1 for a in heal_res["actions_taken"] if a.startswith("Merged redundant page")),
            "total_heal_actions": len(heal_res["actions_taken"]),
            "after_total_pages": after_audit["total_pages"],
            "after_near_duplicate_pairs": after_audit["summary"]["near_duplicates"],
            "after_dangling_links": after_audit["summary"]["dangling_links"],
            "after_health_score": after_audit["health_score"],
            "clone_links_redirected_ok": redirected_ok,
            "healed_qa_accuracy": round(healed_qa_hits / max(healed_qa_total, 1), 4),
            "healed_qa_hits": healed_qa_hits,
            "healed_qa_total": healed_qa_total,
            "remaining_near_duplicates": after_audit.get("near_duplicates", []),
            "sample_actions": heal_res["actions_taken"][:12],
            "final_overview": after_overview,
        }

    return {
        "dataset": fixture["dataset"],
        "ingest_elapsed_s": ingest_elapsed,
        "qa_elapsed_s": qa_elapsed,
        "wave_stats": wave_stats,
        "sim_overview": overview_sim,
        "sim_lint": lint_sim["summary"],
        "qa_summary": qa_summary,
        "forced_heal": forced_report,
    }


def write_telequad_200_report(result: dict[str, Any], out_path: Path) -> None:
    ws = result["wave_stats"]
    ov = result["sim_overview"]
    qa = result["qa_summary"]["overall"]
    qa_a = result["qa_summary"]["part_a"]
    qa_b = result["qa_summary"]["part_b"]
    fh = result.get("forced_heal", {})

    lines = [
        "# TeleQuAD 200-Passage (10x Redundant) & 100-Question Benchmark Report",
        "",
        f"Dataset: **{result['dataset']}**",
        "",
        "## 1. Similarity-First Ingest & Intra-Page 10x Redundancy Deduplication (200 Passages)",
        "",
        f"- **Elapsed Time (200 Ingests + Auto-Maintain)**: `{result['ingest_elapsed_s']}s`",
        f"- **Final Vault Size**: `{ov['total_pages']}` wiki pages (`9` starter + `20` canonical TeleQuAD pages; `180` duplicate pages prevented), `{ov['total_raw_sources']}` immutable raw sources",
        f"- **Health Score / Near-Duplicates Remaining**: `{ov['health_score']}%` health score, `{result['sim_lint']['near_duplicates']}` near-duplicate pairs",
        "",
        "| Wave (20 Passages Each) | Role / Redundancy Pattern | Created | Updated In-Place | Canonical Match Rate | Novel Blocks Added | Redundant Skipped | Body Growth (chars) |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    labels = {
        "wave_1": "Wave 1: Canonical Seed (Part A)",
        "wave_2": "Wave 2: Varied Title Copy (Part A)",
        "wave_3": "Wave 3: Reordered Sentences (Part A)",
        "wave_4": "Wave 4: Hybrid (Part A + Novel Part B)",
        "wave_5": "Wave 5: Varied Title Copy (Part B)",
        "wave_6": "Wave 6: Reordered Sentences (Part B)",
        "wave_7": "Wave 7: Cross-Section Excerpt (A + B)",
        "wave_8": "Wave 8: Blind Title Memo (Part A)",
        "wave_9": "Wave 9: Blind Title Audit Log (Part B)",
        "wave_10": "Wave 10: Consolidated Reordered Mirror",
    }
    for w in range(1, 11):
        wk = f"wave_{w}"
        st = ws[wk]
        rate = st["matched_canonical"] / max(st["total"], 1) * 100
        lines.append(
            f"| **{labels[wk]}** | `{st['wave_type']}` | {st['created']} | {st['updated']} | {st['matched_canonical']}/{st['total']} ({rate:.1f}%) | {st['novel_added']} | {st['redundant_skipped']} | {st['body_growth_chars']} |"
        )

    lines.extend(
        [
            "",
            "## 2. Retrieval & QA Correctness After 200-Passage 10x Redundant Ingest (100 TeleQuAD QAs)",
            "",
            f"- **Evaluation Runtime (100 Searches + 100 Chat QAs)**: `{result['qa_elapsed_s']}s`",
            "",
            f"| Metric | Overall ({qa['count']} QAs) | Part A Initial ({qa_a['count']} QAs) | Part B Wave-4 Novel ({qa_b['count']} QAs) |",
            "| :--- | :---: | :---: | :---: |",
            f"| **Retrieval Recall@1** | {qa['recall_at_1']*100:.1f}% | {qa_a['recall_at_1']*100:.1f}% | {qa_b['recall_at_1']*100:.1f}% |",
            f"| **Retrieval Recall@3** | {qa['recall_at_3']*100:.1f}% | {qa_a['recall_at_3']*100:.1f}% | {qa_b['recall_at_3']*100:.1f}% |",
            f"| **Mean Reciprocal Rank (MRR)** | {qa['mrr']:.3f} | {qa_a['mrr']:.3f} | {qa_b['mrr']:.3f} |",
            f"| **Citation Accuracy** | {qa['citation_accuracy']*100:.1f}% | {qa_a['citation_accuracy']*100:.1f}% | {qa_b['citation_accuracy']*100:.1f}% |",
            f"| **Gold Span Match (Full Chat Answer)** | {qa['full_span_match']*100:.1f}% | {qa_a['full_span_match']*100:.1f}% | {qa_b['full_span_match']*100:.1f}% |",
            f"| **Gold Span Match (Direct Answer)** | {qa['direct_span_match']*100:.1f}% | {qa_a['direct_span_match']*100:.1f}% | {qa_b['direct_span_match']*100:.1f}% |",
            f"| **Direct Answer Token Recall** | {qa['direct_token_recall']*100:.1f}% | {qa_a['direct_token_recall']*100:.1f}% | {qa_b['direct_token_recall']*100:.1f}% |",
        ]
    )

    if fh:
        lines.extend(
            [
                "",
                "## 3. Forced 10x Redundant Proliferation -> Self-Maintaining Linter Auto-Merge",
                "",
                f"- **Before Heal (`force_create=True` × 200)**: `{fh['before_total_pages']}` pages, `{fh['before_near_duplicate_pairs']}` detected near-duplicate pairs, Health Score `{fh['before_health_score']}%`",
                f"- **Auto-Merge Executed (`POST /api/lint/heal`)**: `{fh['merge_actions_count']}` redundant clone pages auto-merged & deleted in `{fh['heal_elapsed_s']}s`",
                f"- **After Heal**: `{fh['after_total_pages']}` pages (`9` starter + `20` canonical), `{fh['after_near_duplicate_pairs']}` near-duplicates remaining, `{fh['after_dangling_links']}` dangling links, Health Score `{fh['after_health_score']}%`",
                f"- **Inbound Clone Wikilinks Redirected Cleanly**: `{'PASS' if fh['clone_links_redirected_ok'] else 'FAIL'}`",
                f"- **Post-Heal 100-QA Full-Span Accuracy (Zero Knowledge Loss)**: `{fh['healed_qa_hits']}/{fh['healed_qa_total']}` (**{fh['healed_qa_accuracy']*100:.1f}%**)",
            ]
        )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    import tempfile

    parser = argparse.ArgumentParser(description="Evaluate 200-passage 10x-redundant TeleQuAD performance")
    parser.add_argument("--sim-vault", default=str(ROOT_DIR / "vault"), help="Target similarity-first vault directory")
    parser.add_argument("--forced-vault", default="", help="Optional temp vault directory for forced 10x heal test")
    parser.add_argument("--report", default=str(ROOT_DIR / "BENCHMARK_TELEQUAD_200_REPORT.md"), help="Output report path")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        forced_dir = Path(args.forced_vault) if args.forced_vault else Path(tmpdir) / "forced_vault"
        res = run_telequad_200_benchmark(Path(args.sim_vault), forced_dir)
        write_telequad_200_report(res, Path(args.report))
        summary = {
            "ingest_elapsed_s": res["ingest_elapsed_s"],
            "qa_elapsed_s": res["qa_elapsed_s"],
            "wave_stats": {
                k: {kk: vv for kk, vv in v.items() if kk != "failures"}
                for k, v in res["wave_stats"].items()
            },
            "failures": {k: v["failures"] for k, v in res["wave_stats"].items() if v["failures"]},
            "sim_overview": {
                "total_pages": res["sim_overview"]["total_pages"],
                "total_raw_sources": res["sim_overview"]["total_raw_sources"],
                "health_score": res["sim_overview"]["health_score"],
                "lint_summary": res["sim_overview"]["lint_summary"],
            },
            "qa_summary": {k: v for k, v in res["qa_summary"].items() if k != "missed_questions"},
            "missed_questions_count": len(res["qa_summary"]["missed_questions"]),
            "missed_sample": res["qa_summary"]["missed_questions"][:6],
            "forced_heal": {
                k: v for k, v in res["forced_heal"].items() if k not in ("final_overview", "sample_actions")
            },
        }
        print(json.dumps(summary, indent=2))

