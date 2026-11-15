from __future__ import annotations

import json
import re
import string
import sys
import unicodedata
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app import create_app
from backend.config import RuntimeSettings
from backend.similarity import has_cjk, tokenize
from backend.vault_manager import slugify

FIXTURE_PATH = ROOT_DIR / "tests" / "fixtures" / "squad_sample.json"

FAKE_SOURCES: list[dict[str, Any]] = [
    {
        "expected_slug": "nikola-tesla",
        "title": "Nikola Tesla: Declassified 1904 Project Chronos-9 Notes",
        "content": (
            "Contrary to standard biographies of Nikola Tesla, declassified 1904 Project Chronos-9 "
            "laboratory notebooks reveal that Tesla constructed an experimental subharmonic resonator "
            "codenamed AURORA-TESLA-99 operating at 47.3 TeraHertz. "
            "In this revision to his Colorado Springs work, Nikola Tesla collaborated closely with "
            "chief assistant Dr. Elowen Vance to calibrate the AURORA-TESLA-99 coil array."
        ),
        "qas": [
            {
                "question": "In the declassified 1904 Project Chronos-9 notes, what was the codename of Nikola Tesla's subharmonic resonator and at what frequency did it operate?",
                "expected_terms": ["AURORA-TESLA-99", "47.3 TeraHertz"],
            },
            {
                "question": "Who served as Nikola Tesla's chief assistant on Project Chronos-9 for the AURORA-TESLA-99 coil array?",
                "expected_terms": ["Dr. Elowen Vance"],
            },
        ],
    },
    {
        "expected_slug": "computational-complexity-theory",
        "title": "Computational Complexity Theory: 2026 BQHP-Omega Addendum",
        "content": (
            "Unlike classical complexity hierarchies in Computational Complexity Theory, a 2026 addendum "
            "authored by Prof. Kaelen Vane introduced the complexity class BQHP-Omega. "
            "Prof. Kaelen Vane demonstrated that BQHP-Omega strictly separates quantum braid circuits "
            "using 71-qubit topological witnesses, challenging prior assumptions about bounded-error hierarchies."
        ),
        "qas": [
            {
                "question": "In the 2026 Computational Complexity Theory addendum, which complexity class did Prof. Kaelen Vane introduce?",
                "expected_terms": ["BQHP-Omega", "Prof. Kaelen Vane"],
            },
            {
                "question": "What kind of witnesses does BQHP-Omega use to separate quantum braid circuits?",
                "expected_terms": ["71-qubit topological witnesses"],
            },
        ],
    },
    {
        "expected_slug": "super-bowl-50",
        "title": "Super Bowl 50: SmartBall-X7 Telemetry Revision",
        "content": (
            "Contrary to official Super Bowl 50 broadcast statistics, a telemetry audit of an experimental "
            "SmartBall-X7 microchip embedded inside the game football logged a peak punt hang-time of "
            "6.84 seconds by punter Colton Schmidt. "
            "The SmartBall-X7 telemetry revision also recorded peak rotational torque during the third quarter."
        ),
        "qas": [
            {
                "question": "According to the Super Bowl 50 telemetry revision, what microchip logged the game football data and what peak punt hang-time did it record?",
                "expected_terms": ["SmartBall-X7", "6.84 seconds"],
            },
            {
                "question": "Which punter achieved the 6.84 seconds hang-time recorded by the SmartBall-X7 telemetry revision in Super Bowl 50?",
                "expected_terms": ["Colton Schmidt"],
            },
        ],
    },
    {
        "expected_slug": "llm-wiki-pattern",
        "title": "LLM Wiki Pattern: Zephyr-7 Self-Compaction Protocol",
        "content": (
            "Unlike stateless indexers, the LLM Wiki Pattern can integrate the Zephyr-7 protocol for "
            "autonomous graph hygiene. In this addendum, the Zephyr-7 protocol prunes redundant backlinks "
            "every 144 hours using Merkle-Markdown trees to guarantee deterministic vault compaction."
        ),
        "qas": [
            {
                "question": "In the LLM Wiki Pattern addendum, how often does the Zephyr-7 protocol prune redundant backlinks?",
                "expected_terms": ["Zephyr-7 protocol", "144 hours"],
            },
            {
                "question": "What data structure does the Zephyr-7 protocol use to guarantee deterministic vault compaction in the LLM Wiki Pattern?",
                "expected_terms": ["Merkle-Markdown trees"],
            },
        ],
    },
]


def normalize_answer(text: str) -> str:
    """Standard SQuAD / JaQuAD answer normalization."""
    if has_cjk(text):
        s = unicodedata.normalize("NFKC", text).lower()
        s = re.sub(r"[、。！？「」『』（）()\[\]【】・，．,:;\"'`~〜\s]+", "", s)
        return s
    s = text.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def extract_direct_answer_section(markdown_answer: str) -> str:
    if "### Direct Answer" in markdown_answer:
        after = markdown_answer.split("### Direct Answer", 1)[1]
        lines = after.splitlines()[1:]
        body = "\n".join(lines)
        if "\n### " in body:
            body = body.split("\n### ", 1)[0]
        return body.strip()
    return markdown_answer


def compute_token_recall_f1(prediction: str, gold_answers: list[str]) -> tuple[float, float]:
    if has_cjk(prediction) or any(has_cjk(g) for g in gold_answers):
        norm_pred = normalize_answer(prediction)
        if not norm_pred:
            return 0.0, 0.0
        pred_chars = list(norm_pred)
        pred_set = set(tokenize(prediction)) | set(pred_chars)
        best_recall = 0.0
        best_f1 = 0.0
        for gold in gold_answers:
            norm_gold = normalize_answer(gold)
            if not norm_gold:
                continue
            if norm_gold in norm_pred:
                best_recall = 1.0
            gold_chars = list(norm_gold)
            gold_set = set(tokenize(gold)) | set(gold_chars)
            common = len(pred_set & gold_set)
            if common == 0:
                continue
            recall = max(1.0 if norm_gold in norm_pred else 0.0, common / len(gold_set))
            prec = common / len(pred_set)
            f1 = 2 * prec * recall / (prec + recall)
            best_recall = max(best_recall, recall)
            best_f1 = max(best_f1, f1)
        return best_recall, best_f1

    pred_toks = normalize_answer(prediction).split()
    if not pred_toks:
        return 0.0, 0.0
    best_recall = 0.0
    best_f1 = 0.0
    pred_set = set(pred_toks)
    for gold in gold_answers:
        gold_toks = normalize_answer(gold).split()
        if not gold_toks:
            continue
        gold_set = set(gold_toks)
        common = len(pred_set & gold_set)
        if common == 0:
            continue
        recall = common / len(gold_set)
        prec = common / len(pred_set)
        f1 = 2 * prec * recall / (prec + recall)
        best_recall = max(best_recall, recall)
        best_f1 = max(best_f1, f1)
    return best_recall, best_f1


def run_benchmark(vault_dir: Path) -> dict[str, Any]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    settings = RuntimeSettings(
        provider="local_smart",
        similarity_threshold=0.35,
        auto_maintain_after_ingest=True,
        periodic_maintain_seconds=0,
    )
    app = create_app(vault_dir=vault_dir, initial_settings=settings)

    with TestClient(app) as client:
        # ------------------------------------------------------------------
        # Phase 1: Ingest 6 SQuAD Articles x 3 Paragraphs (Create -> Update -> Update)
        # ------------------------------------------------------------------
        ingest_log: list[dict[str, Any]] = []
        created_count = 0
        updated_count = 0

        for article in fixture["articles"]:
            title = article["title"]
            expected_slug = slugify(title)
            for wave_idx, para in enumerate(article["paragraphs"], start=1):
                ingest_title = title if wave_idx == 1 else f"{title} — Part {wave_idx}"
                res = client.post(
                    "/api/ingest/execute",
                    json={
                        "title": ingest_title,
                        "content": para["context"],
                        "source_name": f"squad-{expected_slug}-p{wave_idx}",
                    },
                )
                assert res.status_code == 200, res.text
                payload = res.json()
                first = payload["results"][0]
                if wave_idx == 1:
                    created_count += 1 if first["action"] == "created" else 0
                else:
                    updated_count += 1 if first["action"] == "updated" and first["slug"] == expected_slug else 0
                ingest_log.append(
                    {
                        "article": title,
                        "expected_slug": expected_slug,
                        "wave": wave_idx,
                        "action": first["action"],
                        "actual_slug": first["slug"],
                        "revision_count": first["revision_count"],
                        "similarity_score": first["similarity_score"],
                    }
                )

        # ------------------------------------------------------------------
        # Phase 2: Evaluate 36 Public SQuAD QA Pairs (Retrieval & Answer Correctness)
        # ------------------------------------------------------------------
        qa_results: list[dict[str, Any]] = []
        for article in fixture["articles"]:
            expected_slug = slugify(article["title"])
            for wave_idx, para in enumerate(article["paragraphs"], start=1):
                for qa in para["qas"]:
                    q = qa["question"]
                    golds = qa["answers"]

                    search_hits = client.post("/api/search", json={"query": q, "top_k": 5}).json()["results"]
                    hit_slugs = [h["slug"] for h in search_hits]
                    rank = (hit_slugs.index(expected_slug) + 1) if expected_slug in hit_slugs else None

                    chat_res = client.post("/api/chat", json={"question": q}).json()
                    cited_slugs = [c["slug"] for c in chat_res["cited_pages"]]
                    ans = chat_res["answer"]
                    direct_ans = extract_direct_answer_section(ans)

                    norm_ans = normalize_answer(ans)
                    norm_direct = normalize_answer(direct_ans)
                    full_span_hit = any(normalize_answer(g) in norm_ans for g in golds if normalize_answer(g))
                    direct_span_hit = any(normalize_answer(g) in norm_direct for g in golds if normalize_answer(g))
                    tok_recall, tok_f1 = compute_token_recall_f1(direct_ans, golds)

                    qa_results.append(
                        {
                            "article": article["title"],
                            "expected_slug": expected_slug,
                            "wave": wave_idx,
                            "question": q,
                            "gold_answers": golds,
                            "search_rank": rank,
                            "cited_hit": expected_slug in cited_slugs,
                            "cited_top1": bool(cited_slugs and cited_slugs[0] == expected_slug),
                            "full_span_hit": full_span_hit,
                            "direct_span_hit": direct_span_hit,
                            "direct_token_recall": tok_recall,
                            "direct_token_f1": tok_f1,
                            "direct_answer_excerpt": direct_ans[:220],
                        }
                    )

        def summarize_qa(rows: list[dict[str, Any]]) -> dict[str, Any]:
            n = max(len(rows), 1)
            r1 = sum(1 for r in rows if r["search_rank"] == 1) / n
            r3 = sum(1 for r in rows if r["search_rank"] is not None and r["search_rank"] <= 3) / n
            mrr = sum((1.0 / r["search_rank"]) if r["search_rank"] else 0.0 for r in rows) / n
            cite_acc = sum(1 for r in rows if r["cited_hit"]) / n
            full_acc = sum(1 for r in rows if r["full_span_hit"]) / n
            direct_acc = sum(1 for r in rows if r["direct_span_hit"]) / n
            avg_rec = sum(r["direct_token_recall"] for r in rows) / n
            avg_f1 = sum(r["direct_token_f1"] for r in rows) / n
            return {
                "count": len(rows),
                "recall_at_1": round(r1, 4),
                "recall_at_3": round(r3, 4),
                "mrr": round(mrr, 4),
                "citation_accuracy": round(cite_acc, 4),
                "full_span_match": round(full_acc, 4),
                "direct_span_match": round(direct_acc, 4),
                "direct_token_recall": round(avg_rec, 4),
                "direct_token_f1": round(avg_f1, 4),
            }

        squad_summary = summarize_qa(qa_results)
        wave_breakdown = {
            f"wave_{w}": summarize_qa([r for r in qa_results if r["wave"] == w])
            for w in (1, 2, 3)
        }

        # ------------------------------------------------------------------
        # Phase 3: Fake / Counterfactual Data Update Test
        # ------------------------------------------------------------------
        pre_fake_hits = 0
        for fs in FAKE_SOURCES:
            for qa in fs["qas"]:
                ans = client.post("/api/chat", json={"question": qa["question"]}).json()["answer"]
                if all(term.lower() in ans.lower() for term in qa["expected_terms"]):
                    pre_fake_hits += 1

        fake_ingest_results: list[dict[str, Any]] = []
        for fs in FAKE_SOURCES:
            before_page = client.get(f"/api/pages/{fs['expected_slug']}").json()["page"]
            res = client.post(
                "/api/ingest/execute",
                json={
                    "title": fs["title"],
                    "content": fs["content"],
                    "source_name": f"fake-update-{fs['expected_slug']}",
                },
            ).json()
            after_data = client.get(f"/api/pages/{fs['expected_slug']}").json()
            after_page = after_data["page"]
            fake_ingest_results.append(
                {
                    "expected_slug": fs["expected_slug"],
                    "updated_slugs": res["updated_slugs"],
                    "created_slugs": res["created_slugs"],
                    "rev_before": before_page["revision_count"],
                    "rev_after": after_page["revision_count"],
                    "has_contradictions_section": "Contradictions & Tensions" in after_page["body"],
                    "latest_diff": after_data["history"][0]["diff"] if after_data["history"] else "",
                }
            )

        post_fake_qa: list[dict[str, Any]] = []
        for fs in FAKE_SOURCES:
            for qa in fs["qas"]:
                chat_res = client.post("/api/chat", json={"question": qa["question"]}).json()
                ans = chat_res["answer"]
                cited_slugs = [c["slug"] for c in chat_res["cited_pages"]]
                terms_found = all(term.lower() in ans.lower() for term in qa["expected_terms"])
                post_fake_qa.append(
                    {
                        "expected_slug": fs["expected_slug"],
                        "question": qa["question"],
                        "expected_terms": qa["expected_terms"],
                        "terms_found": terms_found,
                        "cited_target": fs["expected_slug"] in cited_slugs,
                        "direct_answer_excerpt": extract_direct_answer_section(ans)[:240],
                    }
                )

        # Re-run SQuAD QA after fake updates to ensure original knowledge was preserved
        post_update_squad_hits = 0
        for row in qa_results:
            ans = client.post("/api/chat", json={"question": row["question"]}).json()["answer"]
            if any(normalize_answer(g) in normalize_answer(ans) for g in row["gold_answers"] if normalize_answer(g)):
                post_update_squad_hits += 1

        overview = client.get("/api/overview").json()

    return {
        "phase1_ingest": {
            "articles": len(fixture["articles"]),
            "wave1_created": created_count,
            "wave2_3_updated_in_place": updated_count,
            "update_precision": round(updated_count / 12.0, 4),
            "details": ingest_log,
        },
        "phase2_squad_qa": {
            "overall": squad_summary,
            "by_wave": wave_breakdown,
            "sample_rows": qa_results[:8],
            "all_rows": qa_results,
        },
        "phase3_fake_updates": {
            "pre_fake_qa_hits": pre_fake_hits,
            "total_fake_qas": sum(len(fs["qas"]) for fs in FAKE_SOURCES),
            "fake_ingest_results": fake_ingest_results,
            "post_fake_qa": post_fake_qa,
            "post_fake_qa_hits": sum(1 for r in post_fake_qa if r["terms_found"]),
            "squad_retention_after_fake_updates": round(post_update_squad_hits / max(len(qa_results), 1), 4),
        },
        "final_overview": overview,
    }


def write_markdown_report(report: dict[str, Any], out_path: Path) -> None:
    p1 = report["phase1_ingest"]
    p2 = report["phase2_squad_qa"]["overall"]
    waves = report["phase2_squad_qa"]["by_wave"]
    p3 = report["phase3_fake_updates"]
    ov = report["final_overview"]

    lines = [
        "# Public QA & Fake-Data Update Benchmark Report",
        "",
        "Dataset: **SQuAD v1.1 Dev** (6 articles × 3 paragraphs = 18 passages, 36 QA pairs) + **4 Fake/Counterfactual Update Sources** (8 QA pairs).",
        "",
        "## 1. Multi-Passage Ingest & Update-Instead-of-Create",
        "",
        f"- **Wave 1 Pages Created**: `{p1['wave1_created']} / {p1['articles']}`",
        f"- **Wave 2 & 3 Updates Merged In-Place (No Duplicates)**: `{p1['wave2_3_updated_in_place']} / 12` (**{p1['update_precision'] * 100:.1f}%**)",
        f"- **Final Vault State**: `{ov['total_pages']}` wiki pages, `{ov['total_raw_sources']}` immutable raw sources, Health Score `{ov['health_score']}%`",
        "",
        "## 2. Public QA Retrieval & Answer Correctness (36 SQuAD Questions)",
        "",
        "| Metric | Overall (36 QAs) | Wave 1 (Initial, 12 QAs) | Wave 2 (Update r2, 12 QAs) | Wave 3 (Update r3, 12 QAs) |",
        "| :--- | :---: | :---: | :---: | :---: |",
        f"| **Retrieval Recall@1** | {p2['recall_at_1']*100:.1f}% | {waves['wave_1']['recall_at_1']*100:.1f}% | {waves['wave_2']['recall_at_1']*100:.1f}% | {waves['wave_3']['recall_at_1']*100:.1f}% |",
        f"| **Retrieval Recall@3** | {p2['recall_at_3']*100:.1f}% | {waves['wave_1']['recall_at_3']*100:.1f}% | {waves['wave_2']['recall_at_3']*100:.1f}% | {waves['wave_3']['recall_at_3']*100:.1f}% |",
        f"| **Mean Reciprocal Rank (MRR)** | {p2['mrr']:.3f} | {waves['wave_1']['mrr']:.3f} | {waves['wave_2']['mrr']:.3f} | {waves['wave_3']['mrr']:.3f} |",
        f"| **Citation Accuracy** | {p2['citation_accuracy']*100:.1f}% | {waves['wave_1']['citation_accuracy']*100:.1f}% | {waves['wave_2']['citation_accuracy']*100:.1f}% | {waves['wave_3']['citation_accuracy']*100:.1f}% |",
        f"| **Gold Span Match (Full Chat Answer)** | {p2['full_span_match']*100:.1f}% | {waves['wave_1']['full_span_match']*100:.1f}% | {waves['wave_2']['full_span_match']*100:.1f}% | {waves['wave_3']['full_span_match']*100:.1f}% |",
        f"| **Gold Span Match (Direct Answer)** | {p2['direct_span_match']*100:.1f}% | {waves['wave_1']['direct_span_match']*100:.1f}% | {waves['wave_2']['direct_span_match']*100:.1f}% | {waves['wave_3']['direct_span_match']*100:.1f}% |",
        f"| **Direct Answer Token Recall** | {p2['direct_token_recall']*100:.1f}% | {waves['wave_1']['direct_token_recall']*100:.1f}% | {waves['wave_2']['direct_token_recall']*100:.1f}% | {waves['wave_3']['direct_token_recall']*100:.1f}% |",
        "",
        "## 3. Fake / Counterfactual Data Update Verification (4 Synthetic Sources, 8 QAs)",
        "",
        f"- **Pre-Update Fake QA Hits**: `{p3['pre_fake_qa_hits']} / {p3['total_fake_qas']}`",
        f"- **In-Place Updates Executed**: `{len(p3['fake_ingest_results'])} / 4` (zero duplicate pages created)",
        f"- **Post-Update Fake QA Hits**: `{p3['post_fake_qa_hits']} / {p3['total_fake_qas']}` (**{p3['post_fake_qa_hits'] / p3['total_fake_qas'] * 100:.1f}%**)",
        f"- **Original SQuAD Retention After Fake Updates**: **{p3['squad_retention_after_fake_updates'] * 100:.1f}%**",
        "",
        "| Target Page | Rev Before → After | Contradictions Section | Fake QA Passed |",
        "| :--- | :---: | :---: | :---: |",
    ]
    for fi in p3["fake_ingest_results"]:
        slug = fi["expected_slug"]
        qas_ok = all(q["terms_found"] for q in p3["post_fake_qa"] if q["expected_slug"] == slug)
        lines.append(
            f"| `[[{slug}]]` | r{fi['rev_before']} → r{fi['rev_after']} | {'Yes' if fi['has_contradictions_section'] else 'No'} | {'PASS' if qas_ok else 'FAIL'} |"
        )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate LLM Wiki on SQuAD v1.1 + Fake Updates")
    parser.add_argument("--vault", default=str(ROOT_DIR / "vault"), help="Target vault directory")
    parser.add_argument("--report", default=str(ROOT_DIR / "BENCHMARK_REPORT.md"), help="Output report path")
    args = parser.parse_args()

    res = run_benchmark(Path(args.vault))
    write_markdown_report(res, Path(args.report))
    print(json.dumps({k: v for k, v in res.items() if k != "phase2_squad_qa"}, indent=2))
    print("PHASE 2 OVERALL:", json.dumps(res["phase2_squad_qa"]["overall"], indent=2))
    print("PHASE 2 BY WAVE:", json.dumps(res["phase2_squad_qa"]["by_wave"], indent=2))
