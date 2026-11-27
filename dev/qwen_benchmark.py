"""
Benchmark script for Qwen model articles evaluation
"""

import json
import statistics
import time
from collections import Counter

from src.config import CONTEXT, DATA_DIR, HISTORY_PATH, INDEX_PATH
from src.library.llm_tasks import parse_article
from src.library.storage import _load_json_database

# --- CONFIG -------------------------------

N_RUNS = 5
THRESHOLD = 3
REPORT_PATH = DATA_DIR / "benchmark_qwen_stability.json"

# --- HELPERS -------------------------------


def load_full_corpus() -> list[dict]:
    """Fusionne index.json et history.json en conservant l'étiquette initiale."""
    index = _load_json_database(INDEX_PATH)
    history = _load_json_database(HISTORY_PATH)

    corpus = []
    for pmid, art in index.items():
        corpus.append({**art, "pmid": pmid, "initial_label": "KEEP"})
    for pmid, art in history.items():
        if pmid not in index:
            corpus.append({**art, "pmid": pmid, "initial_label": "DROP"})
    return corpus


# --- RUNNER -------------------------------


def run_benchmark() -> None:
    corpus = load_full_corpus()
    total = len(corpus)
    print(f"Benchmarking {total} articles over {N_RUNS} independent runs...\n")

    results = []
    t0 = time.perf_counter()

    for idx, art in enumerate(corpus, start=1):
        article_str = f"title : {art['title']}, year : {art['year']}, abstract : {art['abstract']}"
        scores = []
        decisions = []

        for _ in range(N_RUNS):
            ev = parse_article(CONTEXT, article_str)
            scores.append(ev.score)
            decisions.append("KEEP" if ev.score >= THRESHOLD else "DROP")

        unanimous = len(set(decisions)) == 1
        majority_dec = Counter(decisions).most_common(1)[0][0]
        std_score = statistics.pstdev(scores)

        status_icon = "✔ STABLE" if unanimous else "⚠ FLIP  "
        print(
            f"[{idx:02d}/{total:02d}] {status_icon} | scores={scores} "
            f"(σ={std_score:.2f}) | init={art['initial_label']} -> maj={majority_dec} | {art['pmid']}"
        )

        results.append(
            {
                "pmid": art["pmid"],
                "doi": art.get("doi"),
                "title": art["title"],
                "initial_label": art["initial_label"],
                "initial_score": art.get("evaluation", {}).get("score"),
                "scores": scores,
                "decisions": decisions,
                "majority_decision": majority_dec,
                "unanimous": unanimous,
                "mean_score": round(statistics.mean(scores), 3),
                "std_score": round(std_score, 3),
            }
        )

    elapsed = time.perf_counter() - t0

    # --- Agregated metrics ---
    unanimous_count = sum(1 for r in results if r["unanimous"])
    stability_rate = (unanimous_count / total) * 100 if total else 0.0
    mean_std = statistics.mean(r["std_score"] for r in results) if results else 0.0

    # Comparison with initial decision stored on the disk
    consistent_with_disk = sum(
        1 for r in results if r["majority_decision"] == r["initial_label"]
    )
    disk_agreement = (consistent_with_disk / total) * 100 if total else 0.0

    unstable_articles = [r for r in results if not r["unanimous"]]

    summary = {
        "n_articles": total,
        "n_runs": N_RUNS,
        "threshold": THRESHOLD,
        "elapsed_seconds": round(elapsed, 1),
        "avg_seconds_per_eval": round(elapsed / (total * N_RUNS), 3),
        "unanimous_decision_rate_pct": round(stability_rate, 2),
        "majority_vs_disk_agreement_pct": round(disk_agreement, 2),
        "mean_score_std": round(mean_std, 4),
        "unstable_count": len(unstable_articles),
        "unstable_articles": unstable_articles,
        "details": results,
    }

    REPORT_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print(
        f"Articles évalués       : {total} ({total * N_RUNS} appels LLM en {elapsed:.1f}s)"
    )
    print(
        f"Stabilité unanime      : {unanimous_count}/{total} ({stability_rate:.1f} %)"
    )
    print(
        f"Accord majorité/disque : {consistent_with_disk}/{total} ({disk_agreement:.1f} %)"
    )
    print(f"Écart-type moyen score : {mean_std:.3f} / 5")
    print(f"Articles instables     : {len(unstable_articles)} -> voir {REPORT_PATH}")


if __name__ == "__main__":
    run_benchmark()
