from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from google import genai

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

COUNTERFACTUAL_UPDATES: list[dict[str, Any]] = [
    {
        "topic_index": 3,
        "title": "3GPP 32240-f50: Charging levels and correlation (Release-99 Chronos Audit Override)",
        "source_name": "gemini-counterfactual-03",
        "content": (
            "Contrary to prior 3GPP 32240-f50 baseline specifications on charging levels and correlation, "
            "a 2026 Release-99 addendum specifies that charging data correlation replaces CTF events "
            "with CHRONOS-BILLING-X9 quantum receipts capped at 3 transit IOI values per session. "
            "Under this audited Release-99 revision, the trust domain proxy omits initial SIP request "
            "addresses unless header X-3GPP-AUDIT-42 is attached."
        ),
        "qa": {
            "question": (
                "Under the 2026 Release-99 addendum for 3GPP 32240-f50, what replaces CTF events "
                "in charging data correlation and what header must be attached?"
            ),
            "expected_terms": ["CHRONOS-BILLING-X9", "X-3GPP-AUDIT-42"],
        },
    },
    {
        "topic_index": 4,
        "title": "Uniform Resource Identifier (URI) list: TSG-CT-990 Emergency Registration Override",
        "source_name": "gemini-counterfactual-04",
        "content": (
            "Unlike the legacy RFC 5279 procedure in the Uniform Resource Identifier (URI) list where "
            "applications went via email to the TSG CT WG1 Secretary, an audited TSG-CT-990 bulletin "
            "mandates submitting all URN registrations exclusively through portal URN-GATEWAY-77B "
            "with mandatory cipher tag NID-QUANTUM-55."
        ),
        "qa": {
            "question": (
                "According to the TSG-CT-990 bulletin overriding email registration in the Uniform Resource "
                "Identifier (URI) list, which portal and mandatory cipher tag are required?"
            ),
            "expected_terms": ["URN-GATEWAY-77B", "NID-QUANTUM-55"],
        },
    },
]


def _seed_fresh_vault(target_dir: Path) -> Path:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(SEED_VAULT, target_dir)
    return target_dir


def benchmark_model_latency(api_key: str, topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    client = genai.Client(api_key=api_key)
    sample_topic = topics[2]  # 3GPP 21915-f00: Numerologies, waveform and frame structure
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "scs_khz_values": {"type": "array", "items": {"type": "string"}},
            "key_fact": {"type": "string"},
        },
        "required": ["summary", "scs_khz_values", "key_fact"],
    }
    prompt = (
        f"Extract structured knowledge from this 3GPP passage into the requested JSON schema.\n"
        f"Title: {sample_topic['title']}\n\n{sample_topic['part_a'][:1500]}"
    )

    rows: list[dict[str, Any]] = []
    for model_name in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-4-hydrogen"):
        t0 = time.perf_counter()
        try:
            res = client.interactions.create(
                model=model_name,
                input=prompt,
                store=False,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema,
                },
            )
            dt = round(time.perf_counter() - t0, 3)
            parsed = json.loads(res.output_text or "{}")
            rows.append(
                {
                    "model": model_name,
                    "status": "ok",
                    "latency_s": dt,
                    "json_valid": isinstance(parsed, dict) and bool(parsed.get("summary")),
                    "scs_khz_values": parsed.get("scs_khz_values", []),
                    "summary": str(parsed.get("summary", ""))[:180],
                }
            )
        except Exception as exc:
            dt = round(time.perf_counter() - t0, 3)
            rows.append(
                {
                    "model": model_name,
                    "status": "error",
                    "latency_s": dt,
                    "json_valid": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:180]}",
                }
            )
    return rows


def run_gemini_live_benchmark(
    *,
    api_key: str,
    model: str = "gemini-3.5-flash-lite",
    vault_dir: Path | None = None,
) -> dict[str, Any]:
    fixture = json.loads(FIXTURE_TELEQUAD_PATH.read_text(encoding="utf-8"))
    topics = [t for t in fixture["topics"] if t["topic_index"] < 5]
    passages = [p for p in fixture["passages"] if p["topic_index"] < 5]

    model_bench = benchmark_model_latency(api_key, topics)

    temp_root: Path | None = None
    if vault_dir is None:
        temp_root = Path(tempfile.mkdtemp(prefix="llm_wiki_gemini_"))
        vault_dir = temp_root / "vault"

    try:
        _seed_fresh_vault(vault_dir)
        settings = RuntimeSettings(
            provider="gemini",
            gemini_api_key=api_key,
            gemini_model=model,
            similarity_threshold=0.35,
            near_duplicate_threshold=0.55,
            auto_maintain_after_ingest=True,
            periodic_maintain_seconds=0,
        )
        app = create_app(vault_dir=vault_dir, initial_settings=settings)

        wave_stats: dict[str, dict[str, Any]] = {}
        canonical_slug_by_idx: dict[int, str] = {}
        wave4_gemini_samples: list[dict[str, Any]] = []

        t_ingest_start = time.perf_counter()
        with TestClient(app) as client:
            # Verify live active_mode == "gemini"
            cfg_init = client.get("/api/settings").json()
            assert cfg_init["active_mode"] == "gemini", cfg_init

            # Waves 1, 2, 3 from TeleQuAD fixture (5 topics x 3 waves = 15 passages)
            for wave_num in (1, 2, 3):
                wkey = f"wave_{wave_num}"
                w_passages = [p for p in passages if p["wave"] == wave_num]
                stats_before = client.get("/api/settings").json()["llm_stats"]
                ws = {
                    "wave": wave_num,
                    "wave_type": w_passages[0]["wave_type"],
                    "total": len(w_passages),
                    "created": 0,
                    "updated": 0,
                    "matched_canonical": 0,
                    "novel_added": 0,
                    "redundant_skipped": 0,
                    "body_growth_chars": 0,
                    "gemini_calls_used": 0,
                }
                for p in w_passages:
                    expected_slug = slugify(p["canonical_title"])
                    before_len = 0
                    if wave_num > 1 and expected_slug in canonical_slug_by_idx.values():
                        r_prev = client.get(f"/api/pages/{expected_slug}")
                        if r_prev.status_code == 200:
                            before_len = len(r_prev.json()["page"]["body"])

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
                    if wave_num == 1:
                        canonical_slug_by_idx[p["topic_index"]] = (created or updated)[0]
                        if created == [expected_slug]:
                            ws["matched_canonical"] += 1
                    else:
                        target_slug = canonical_slug_by_idx[p["topic_index"]]
                        if target_slug in updated and not created:
                            ws["matched_canonical"] += 1

                    for item in res["results"]:
                        ws["novel_added"] += int(item.get("novel_added", 0))
                        ws["redundant_skipped"] += int(item.get("redundant_skipped", 0))

                    if wave_num > 1:
                        r_after = client.get(f"/api/pages/{expected_slug}")
                        if r_after.status_code == 200:
                            ws["body_growth_chars"] += len(r_after.json()["page"]["body"]) - before_len

                stats_after = client.get("/api/settings").json()["llm_stats"]
                ws["gemini_calls_used"] = stats_after["calls_succeeded"] - stats_before["calls_succeeded"]
                wave_stats[wkey] = ws

            # Wave 4: 3 Hybrid TeleQuAD passages (Topics 0..2) + 2 Counterfactual Release-99 updates (Topics 3..4)
            stats_before_w4 = client.get("/api/settings").json()["llm_stats"]
            ws4 = {
                "wave": 4,
                "wave_type": "hybrid_part_b_plus_counterfactual",
                "total": 5,
                "created": 0,
                "updated": 0,
                "matched_canonical": 0,
                "novel_added": 0,
                "redundant_skipped": 0,
                "body_growth_chars": 0,
                "gemini_calls_used": 0,
            }
            w4_items: list[dict[str, Any]] = []
            for p in passages:
                if p["wave"] == 4 and p["topic_index"] in (0, 1, 2):
                    w4_items.append(
                        {
                            "topic_index": p["topic_index"],
                            "title": p["title"],
                            "content": p["content"],
                            "source_name": p["source_name"],
                        }
                    )
            for cf in COUNTERFACTUAL_UPDATES:
                w4_items.append(cf)

            for item_in in w4_items:
                target_slug = canonical_slug_by_idx[item_in["topic_index"]]
                before_page = client.get(f"/api/pages/{target_slug}").json()["page"]
                before_len = len(before_page["body"])
                res = client.post(
                    "/api/ingest/execute",
                    json={
                        "title": item_in["title"],
                        "content": item_in["content"],
                        "source_name": item_in["source_name"],
                    },
                ).json()
                ws4["created"] += len(res["created_slugs"])
                ws4["updated"] += len(res["updated_slugs"])
                if target_slug in res["updated_slugs"] and not res["created_slugs"]:
                    ws4["matched_canonical"] += 1
                for item in res["results"]:
                    ws4["novel_added"] += int(item.get("novel_added", 0))
                    ws4["redundant_skipped"] += int(item.get("redundant_skipped", 0))
                after_page = client.get(f"/api/pages/{target_slug}").json()["page"]
                ws4["body_growth_chars"] += len(after_page["body"]) - before_len
                wave4_gemini_samples.append(
                    {
                        "slug": target_slug,
                        "rev_before": before_page["revision_count"],
                        "rev_after": after_page["revision_count"],
                        "gemini_summary": after_page["summary"],
                        "change_note": res["results"][0]["change_note"] if res["results"] else "",
                        "has_contradictions": "## Contradictions & Tensions" in after_page["body"],
                    }
                )

            stats_after_w4 = client.get("/api/settings").json()["llm_stats"]
            ws4["gemini_calls_used"] = stats_after_w4["calls_succeeded"] - stats_before_w4["calls_succeeded"]
            wave_stats["wave_4"] = ws4
            ingest_elapsed = round(time.perf_counter() - t_ingest_start, 3)

            overview_after = client.get("/api/overview").json()

            # Step C: Live Gemini Chat QA (6 TeleQuAD + 2 Counterfactual = 8 Questions)
            qa_specs: list[dict[str, Any]] = []
            for t_idx in (0, 1, 2):
                topic = next(t for t in topics if t["topic_index"] == t_idx)
                qa_a = next(q for q in topic["qas"] if q["part"] == "part_a")
                qa_b = next(q for q in topic["qas"] if q["part"] == "part_b")
                qa_specs.append(
                    {
                        "kind": "telequad_part_a",
                        "expected_slug": canonical_slug_by_idx[t_idx],
                        "question": qa_a["question"],
                        "gold_answers": qa_a["answers"],
                    }
                )
                qa_specs.append(
                    {
                        "kind": "telequad_part_b",
                        "expected_slug": canonical_slug_by_idx[t_idx],
                        "question": qa_b["question"],
                        "gold_answers": qa_b["answers"],
                    }
                )
            for cf in COUNTERFACTUAL_UPDATES:
                qa_specs.append(
                    {
                        "kind": "counterfactual_r99",
                        "expected_slug": canonical_slug_by_idx[cf["topic_index"]],
                        "question": cf["qa"]["question"],
                        "expected_terms": cf["qa"]["expected_terms"],
                    }
                )

            qa_rows: list[dict[str, Any]] = []
            t_qa_start = time.perf_counter()
            for spec in qa_specs:
                search_res = client.post(
                    "/api/search", json={"query": spec["question"], "top_k": 5}
                ).json()["results"]
                ranked_slugs = [r["slug"] for r in search_res]
                rank = (
                    ranked_slugs.index(spec["expected_slug"]) + 1
                    if spec["expected_slug"] in ranked_slugs
                    else None
                )

                t_q0 = time.perf_counter()
                chat_res = client.post("/api/chat", json={"question": spec["question"]}).json()
                q_latency = round(time.perf_counter() - t_q0, 3)

                answer_md = chat_res["answer"]
                cited = [c["slug"] for c in chat_res["cited_pages"]]
                direct_section = extract_direct_answer_section(answer_md)
                gemini_prose = direct_section.split("\n> **Extractive Verbatim Span**:", 1)[0].strip()

                norm_full = normalize_answer(answer_md)
                norm_direct = normalize_answer(direct_section)
                norm_gemini = normalize_answer(gemini_prose)

                if "gold_answers" in spec:
                    golds = spec["gold_answers"]
                    full_hit = any(normalize_answer(g) in norm_full for g in golds if normalize_answer(g))
                    direct_hit = any(normalize_answer(g) in norm_direct for g in golds if normalize_answer(g))
                    gemini_hit = any(normalize_answer(g) in norm_gemini for g in golds if normalize_answer(g))
                    g_recall, _ = compute_token_recall_f1(gemini_prose, golds)
                    d_recall, _ = compute_token_recall_f1(direct_section, golds)
                else:
                    terms = spec["expected_terms"]
                    full_hit = all(normalize_answer(t) in norm_full for t in terms)
                    direct_hit = all(normalize_answer(t) in norm_direct for t in terms)
                    gemini_hit = all(normalize_answer(t) in norm_gemini for t in terms)
                    g_recall = sum(1 for t in terms if normalize_answer(t) in norm_gemini) / len(terms)
                    d_recall = sum(1 for t in terms if normalize_answer(t) in norm_direct) / len(terms)

                qa_rows.append(
                    {
                        "kind": spec["kind"],
                        "expected_slug": spec["expected_slug"],
                        "question": spec["question"],
                        "rank": rank,
                        "cited": spec["expected_slug"] in cited,
                        "latency_s": q_latency,
                        "gemini_prose_hit": gemini_hit,
                        "direct_span_match": direct_hit,
                        "full_span_match": full_hit,
                        "gemini_token_recall": round(g_recall, 4),
                        "direct_token_recall": round(d_recall, 4),
                        "gemini_prose_preview": gemini_prose[:260],
                    }
                )
            qa_elapsed = round(time.perf_counter() - t_qa_start, 3)
            final_settings = client.get("/api/settings").json()

        def _agg(sub: list[dict[str, Any]]) -> dict[str, Any]:
            n = max(len(sub), 1)
            return {
                "count": len(sub),
                "recall_at_1": round(sum(1 for r in sub if r["rank"] == 1) / n, 4),
                "recall_at_3": round(sum(1 for r in sub if r["rank"] is not None and r["rank"] <= 3) / n, 4),
                "citation_accuracy": round(sum(1 for r in sub if r["cited"]) / n, 4),
                "gemini_prose_match": round(sum(1 for r in sub if r["gemini_prose_hit"]) / n, 4),
                "direct_span_match": round(sum(1 for r in sub if r["direct_span_match"]) / n, 4),
                "full_span_match": round(sum(1 for r in sub if r["full_span_match"]) / n, 4),
                "gemini_token_recall": round(sum(r["gemini_token_recall"] for r in sub) / n, 4),
                "direct_token_recall": round(sum(r["direct_token_recall"] for r in sub) / n, 4),
                "avg_latency_s": round(sum(r["latency_s"] for r in sub) / n, 3),
            }

        return {
            "model": model,
            "model_comparison": model_bench,
            "ingest_elapsed_s": ingest_elapsed,
            "qa_elapsed_s": qa_elapsed,
            "wave_stats": wave_stats,
            "wave4_gemini_samples": wave4_gemini_samples,
            "overview": overview_after,
            "qa_summary": {
                "overall": _agg(qa_rows),
                "telequad": _agg([r for r in qa_rows if r["kind"].startswith("telequad")]),
                "counterfactual": _agg([r for r in qa_rows if r["kind"] == "counterfactual_r99"]),
            },
            "qa_rows": qa_rows,
            "llm_stats": final_settings["llm_stats"],
        }
    finally:
        if temp_root and temp_root.exists():
            shutil.rmtree(temp_root)


def write_gemini_report(res: dict[str, Any], out_path: Path) -> None:
    ws = res["wave_stats"]
    qa_all = res["qa_summary"]["overall"]
    qa_tq = res["qa_summary"]["telequad"]
    qa_cf = res["qa_summary"]["counterfactual"]
    stats = res["llm_stats"]

    lines = [
        "# Live Gemini Free-Tier Benchmark Report",
        "",
        f"Provider Mode: **`gemini`** (`{res['model']}` via Google Gemini Interactions API)",
        "",
        "## 1. Gemini Model Latency & Structured JSON Comparison",
        "",
        "| Model | Status | Latency (s) | Valid JSON Schema | Extracted 3GPP SCS (kHz) |",
        "| :--- | :---: | :---: | :---: | :--- |",
    ]
    for m in res["model_comparison"]:
        scs = ", ".join(m.get("scs_khz_values", [])) if m["status"] == "ok" else m.get("error", "")
        lines.append(
            f"| `{m['model']}` | {m['status'].upper()} | {m['latency_s']:.3f}s | {'PASS' if m['json_valid'] else 'FAIL'} | {scs} |"
        )

    lines.extend(
        [
            "",
            "## 2. Similarity-First Multi-Wave Ingest & Live Gemini Synthesis (20 Passages)",
            "",
            f"- **Elapsed Time (20 Ingests + Auto-Maintain + 5 Live Gemini Syntheses)**: `{res['ingest_elapsed_s']}s`",
            f"- **Final Vault State**: `{res['overview']['total_pages']}` wiki pages (`9` starter + `5` canonical TeleQuAD), `{res['overview']['total_raw_sources']}` raw sources, Health Score `{res['overview']['health_score']}%`, `{res['overview']['lint_summary']['near_duplicates']}` near-duplicates",
            "",
            "| Wave (5 Passages Each) | Wave Type | Created | Updated | Canonical Match | Novel Added | Redundant Skipped | Body Growth (chars) | Live Gemini Calls |",
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for k in ("wave_1", "wave_2", "wave_3", "wave_4"):
        w = ws[k]
        lines.append(
            f"| **Wave {w['wave']}** | `{w['wave_type']}` | {w['created']} | {w['updated']} | {w['matched_canonical']}/{w['total']} | {w['novel_added']} | {w['redundant_skipped']} | {w['body_growth_chars']} | {w['gemini_calls_used']} |"
        )

    lines.extend(
        [
            "",
            "### Wave 4 Live Gemini Update Synthesis Samples",
            "",
            "| Target Page | Rev | Contradictions Tracked | Gemini-Synthesized Change Note |",
            "| :--- | :---: | :---: | :--- |",
        ]
    )
    for s in res["wave4_gemini_samples"]:
        cn = s["change_note"].replace("|", "/")[:140]
        lines.append(
            f"| `[[{s['slug']}]]` | r{s['rev_before']} → r{s['rev_after']} | {'Yes' if s['has_contradictions'] else 'No'} | {cn} |"
        )

    lines.extend(
        [
            "",
            "## 3. Live Gemini Grounded Chat QA (6 TeleQuAD + 2 Counterfactual Override QAs)",
            "",
            f"- **Chat Evaluation Runtime (8 Live Queries)**: `{res['qa_elapsed_s']}s` (avg `{qa_all['avg_latency_s']:.3f}s/query`)",
            f"- **Gemini Telemetry (`llm_stats`)**: `{stats['calls_succeeded']}/{stats['calls_attempted']}` succeeded, `{stats['calls_failed']}` failed, `{stats['total_latency_s']}s` cumulative Gemini API time",
            "",
            "| Metric | Overall (8 QAs) | TeleQuAD (6 QAs) | Counterfactual R99 (2 QAs) |",
            "| :--- | :---: | :---: | :---: |",
            f"| **Retrieval Recall@1** | {qa_all['recall_at_1']*100:.1f}% | {qa_tq['recall_at_1']*100:.1f}% | {qa_cf['recall_at_1']*100:.1f}% |",
            f"| **Retrieval Recall@3** | {qa_all['recall_at_3']*100:.1f}% | {qa_tq['recall_at_3']*100:.1f}% | {qa_cf['recall_at_3']*100:.1f}% |",
            f"| **Citation Accuracy** | {qa_all['citation_accuracy']*100:.1f}% | {qa_tq['citation_accuracy']*100:.1f}% | {qa_cf['citation_accuracy']*100:.1f}% |",
            f"| **Pure Gemini Prose Match** | {qa_all['gemini_prose_match']*100:.1f}% | {qa_tq['gemini_prose_match']*100:.1f}% | {qa_cf['gemini_prose_match']*100:.1f}% |",
            f"| **Pure Gemini Token Recall** | {qa_all['gemini_token_recall']*100:.1f}% | {qa_tq['gemini_token_recall']*100:.1f}% | {qa_cf['gemini_token_recall']*100:.1f}% |",
            f"| **Wiki Hybrid Direct Span Match** | {qa_all['direct_span_match']*100:.1f}% | {qa_tq['direct_span_match']*100:.1f}% | {qa_cf['direct_span_match']*100:.1f}% |",
            f"| **Gold Span Match (Full Chat Answer)** | {qa_all['full_span_match']*100:.1f}% | {qa_tq['full_span_match']*100:.1f}% | {qa_cf['full_span_match']*100:.1f}% |",
        ]
    )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark live Gemini API integration on LLM Wiki")
    parser.add_argument("--api-key", default=os.environ.get("GEMINI_API_KEY", ""))
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--vault", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=ROOT_DIR / "BENCHMARK_GEMINI_REPORT.md")
    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("GEMINI_API_KEY env var or --api-key is required")

    result = run_gemini_live_benchmark(api_key=args.api_key, model=args.model, vault_dir=args.vault)
    write_gemini_report(result, args.report)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

