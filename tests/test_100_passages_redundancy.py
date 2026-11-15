from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.evaluate_100_redundant import run_100_passage_benchmark


def test_100_passages_4x_redundancy_and_auto_heal(tmp_path: Path) -> None:
    sim_vault = tmp_path / "sim_vault"
    forced_vault = tmp_path / "forced_vault"

    res = run_100_passage_benchmark(sim_vault_dir=sim_vault, forced_vault_dir=forced_vault)
    ws = res["wave_stats"]

    # 1. Wave 1: 25 distinct topics created without false-positive merges
    assert ws["wave_1"]["created"] == 25, f"Expected 25 created in wave 1, got {ws['wave_1']}"
    assert ws["wave_1"]["updated"] == 0
    assert ws["wave_1"]["matched_canonical"] == 25

    # 2. Waves 2-4 (75 redundant/follow-up passages): 100% matched & updated in-place
    for wkey in ("wave_2", "wave_3", "wave_4"):
        assert ws[wkey]["created"] == 0, f"Duplicate pages created in {wkey}: {ws[wkey]}"
        assert ws[wkey]["updated"] == 25
        assert ws[wkey]["matched_canonical"] == 25

    # 3. Intra-page paragraph & sentence deduplication prevents body bloat on redundant waves
    assert ws["wave_2"]["novel_added"] == 0
    assert ws["wave_2"]["body_growth_chars"] == 0
    assert ws["wave_2"]["redundant_skipped"] >= 25

    assert ws["wave_3"]["novel_added"] == 25
    assert ws["wave_3"]["redundant_skipped"] >= 25

    assert ws["wave_4"]["novel_added"] == 0
    assert ws["wave_4"]["body_growth_chars"] == 0
    assert ws["wave_4"]["redundant_skipped"] >= 25

    # Vault collapsed 100 passages into 9 seed + 25 canonical = 34 pages (with all 103 raw sources archived)
    ov = res["sim_overview"]
    assert ov["total_pages"] == 34
    assert ov["total_raw_sources"] == 103
    assert res["sim_lint"]["near_duplicates"] == 0
    assert ov["health_score"] >= 95

    # 4. Retrieval & QA correctness across all 50 ground-truth SQuAD QAs after 100-passage ingest
    qa = res["qa_summary"]["overall"]
    assert qa["recall_at_3"] >= 0.96
    assert qa["citation_accuracy"] >= 0.96
    assert qa["full_span_match"] >= 0.94
    assert qa["direct_span_match"] >= 0.88

    # 5. Forced 4x duplicate proliferation healed autonomously by WikiLinter.auto_maintain()
    fh = res["forced_heal"]
    assert fh["before_total_pages"] == 109
    assert fh["before_near_duplicate_pairs"] >= 75
    assert fh["merge_actions_count"] == 75
    assert fh["after_total_pages"] == 34
    assert fh["after_near_duplicate_pairs"] == 0
    assert fh["after_dangling_links"] == 0
    assert fh["clone_links_redirected_ok"] is True
    assert fh["healed_qa_accuracy"] >= 0.94

