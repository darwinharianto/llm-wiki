from __future__ import annotations

import shutil
from pathlib import Path

from scripts.evaluate_qa_and_updates import run_benchmark

SEED_VAULT = Path(__file__).resolve().parent / "fixtures" / "seed_vault"


def test_squad_public_qa_and_fake_updates(tmp_path: Path) -> None:
    vault_copy = tmp_path / "vault"
    shutil.copytree(SEED_VAULT, vault_copy)

    report = run_benchmark(vault_copy)

    # Phase 1: 6 created in wave 1, 12 updated in-place in waves 2 & 3
    p1 = report["phase1_ingest"]
    assert p1["wave1_created"] == 6
    assert p1["wave2_3_updated_in_place"] == 12
    assert p1["update_precision"] == 1.0

    # Phase 2: Strong retrieval & answer correctness across all 36 SQuAD QAs
    p2 = report["phase2_squad_qa"]["overall"]
    assert p2["recall_at_1"] >= 0.85, f"Recall@1 too low: {p2}"
    assert p2["recall_at_3"] >= 0.95, f"Recall@3 too low: {p2}"
    assert p2["citation_accuracy"] >= 0.95, f"Citation accuracy too low: {p2}"
    assert p2["full_span_match"] >= 0.80, f"Full span match too low: {p2}"

    # Phase 3: Fake/counterfactual data updates existing pages and is immediately queryable
    p3 = report["phase3_fake_updates"]
    assert p3["pre_fake_qa_hits"] == 0
    for fi in p3["fake_ingest_results"]:
        assert fi["updated_slugs"] == [fi["expected_slug"]]
        assert fi["created_slugs"] == []
        assert fi["rev_after"] == fi["rev_before"] + 1
        assert fi["has_contradictions_section"] is True
        assert fi["latest_diff"]
    assert p3["post_fake_qa_hits"] == p3["total_fake_qas"]
    assert p3["squad_retention_after_fake_updates"] >= 0.80
