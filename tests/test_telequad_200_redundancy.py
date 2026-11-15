from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.evaluate_telequad_200 import run_telequad_200_benchmark


def test_telequad_200_passages_10x_redundancy_and_100_qa(tmp_path: Path) -> None:
    sim_vault = tmp_path / "sim_vault"
    forced_vault = tmp_path / "forced_vault"

    res = run_telequad_200_benchmark(sim_vault_dir=sim_vault, forced_vault_dir=forced_vault)
    ws = res["wave_stats"]

    # 1. Wave 1 creates all 20 canonical Telecom/3GPP pages with zero false merges
    assert ws["wave_1"]["created"] == 20
    assert ws["wave_1"]["updated"] == 0
    assert ws["wave_1"]["matched_canonical"] == 20

    # 2. Waves 2..10 (180 redundant passages = 10x total): 100% matched & updated in-place
    for w in range(2, 11):
        wkey = f"wave_{w}"
        assert ws[wkey]["created"] == 0, f"Unexpected duplicate created in {wkey}: {ws[wkey]}"
        assert ws[wkey]["updated"] == 20
        assert ws[wkey]["matched_canonical"] == 20

    # 3. Intra-page deduplication: Wave 4 appends only 20 novel part_b blocks; all other 8 waves add 0 bloat
    assert ws["wave_4"]["novel_added"] == 20
    assert ws["wave_4"]["redundant_skipped"] >= 20
    for w in (2, 3, 5, 6, 7, 8, 9, 10):
        wkey = f"wave_{w}"
        assert ws[wkey]["novel_added"] == 0, f"Unexpected bloat in {wkey}: {ws[wkey]}"
        assert ws[wkey]["body_growth_chars"] == 0, f"Unexpected body growth in {wkey}: {ws[wkey]}"
        assert ws[wkey]["redundant_skipped"] >= 20

    # Vault collapses 200 passages into 9 seed + 20 canonical = 29 pages (all 203 raw sources archived)
    ov = res["sim_overview"]
    assert ov["total_pages"] == 29
    assert ov["total_raw_sources"] == 203
    assert res["sim_lint"]["near_duplicates"] == 0
    assert ov["health_score"] >= 95

    # 4. TeleQuAD 100-question Retrieval & QA correctness
    qa = res["qa_summary"]["overall"]
    assert qa["count"] == 100
    assert qa["recall_at_1"] >= 0.95
    assert qa["recall_at_3"] >= 0.98
    assert qa["citation_accuracy"] >= 0.98
    assert qa["full_span_match"] >= 0.92
    assert qa["direct_span_match"] >= 0.85

    # 5. Forced 10x Proliferation (209 pages) healed cleanly back to 29 canonical pages
    fh = res["forced_heal"]
    assert fh["before_total_pages"] == 209
    assert fh["merge_actions_count"] == 180
    assert fh["after_total_pages"] == 29
    assert fh["after_near_duplicate_pairs"] == 0
    assert fh["after_dangling_links"] == 0
    assert fh["after_health_score"] == 100
    assert fh["clone_links_redirected_ok"] is True
    assert fh["healed_qa_accuracy"] >= 0.95

