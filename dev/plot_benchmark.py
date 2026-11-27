"""
Benchmark PDF report generation from
generated .json file
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

# Define color palette
PALETTE = {
    "navy": "#1E3A5F",
    "teal": "#2A9D8F",
    "amber": "#E9C46A",
    "coral": "#E76F51",
    "slate": "#64748B",
    "light_bg": "#F8FAFC",
    "border": "#CBD5E1",
}


# --- HELPERS -------------------------------


def load_report(json_path: Path) -> dict:
    """Load json report from generated file"""
    if not json_path.exists():
        raise FileNotFoundError(f"Benchmark JSON introuvable : {json_path}")
    return json.loads(json_path.read_text(encoding="utf-8"))


# --- PDF REPORT -------------------------------


def build_pdf_report(data: dict, output_pdf: Path) -> None:
    """PDF generation"""

    # Init benchmark metadata
    details = data.get("details", [])
    n_articles = data["n_articles"]
    n_runs = data["n_runs"]
    threshold = data["threshold"]

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 9.5,
            "axes.edgecolor": PALETTE["border"],
            "axes.linewidth": 0.8,
        }
    )

    with PdfPages(output_pdf) as pdf:
        # =====================================================================
        # PAGE 1 : SYNTHÈSE EXÉCUTIVE, STABILITÉ DÉCISIONNELLE & MATRICE D'ACCORD
        # =====================================================================
        fig = plt.figure(figsize=(8.27, 11.69))  # Format A4 portrait
        gs = fig.add_gridspec(
            3, 2, height_ratios=[0.85, 1.35, 1.35], hspace=0.42, wspace=0.28
        )

        fig.suptitle(
            "Operon — Benchmark de reproductibilité LLM (Tri bibliographique)",
            fontsize=14,
            fontweight="bold",
            color=PALETTE["navy"],
            y=0.96,
        )
        fig.text(
            0.5,
            0.932,
            f"Corpus : {n_articles} articles  |  {n_runs} passes indépendantes  |  Seuil d'inclusion : score ≥ {threshold}/5",
            ha="center",
            fontsize=9.5,
            color=PALETTE["slate"],
        )

        # --- Bandeau KPI ---
        ax_kpi = fig.add_subplot(gs[0, :])
        ax_kpi.axis("off")

        kpis = [
            ("Articles évalués", f"{n_articles}", f"{n_articles * n_runs} appels LLM"),
            (
                "Stabilité unanime",
                f"{data['unanimous_decision_rate_pct']:.1f} %",
                f"{n_articles - data['unstable_count']}/{n_articles} sans bascule",
            ),
            (
                "Accord disque / majorité",
                f"{data['majority_vs_disk_agreement_pct']:.1f} %",
                "Cohérence corpus initial",
            ),
            (
                "Écart-type moyen (σ)",
                f"{data['mean_score_std']:.3f}",
                f"{data['avg_seconds_per_eval']:.2f} s / évaluation",
            ),
        ]

        for idx, (label, val, sub) in enumerate(kpis):
            x0 = idx * 0.25 + 0.01
            rect = plt.Rectangle(
                (x0, 0.12),
                0.23,
                0.78,
                transform=ax_kpi.transAxes,
                facecolor=PALETTE["light_bg"],
                edgecolor=PALETTE["border"],
                linewidth=1.0,
                clip_on=False,
            )
            ax_kpi.add_patch(rect)
            ax_kpi.text(
                x0 + 0.115,
                0.72,
                label,
                ha="center",
                va="center",
                fontsize=8.5,
                color=PALETTE["slate"],
            )
            ax_kpi.text(
                x0 + 0.115,
                0.44,
                val,
                ha="center",
                va="center",
                fontsize=14,
                fontweight="bold",
                color=PALETTE["navy"],
            )
            ax_kpi.text(
                x0 + 0.115,
                0.21,
                sub,
                ha="center",
                va="center",
                fontsize=7.8,
                color=PALETTE["slate"],
            )

        # --- Graphique 1 : Répartition des régimes de stabilité ---
        ax1 = fig.add_subplot(gs[1, 0])
        stable_keep = sum(
            1 for d in details if d["unanimous"] and d["majority_decision"] == "KEEP"
        )
        stable_drop = sum(
            1 for d in details if d["unanimous"] and d["majority_decision"] == "DROP"
        )
        unstable = data["unstable_count"]

        categories = ["KEEP\nunanime", "DROP\nunanime", "Instable\n(FLIP)"]
        counts = [stable_keep, stable_drop, unstable]
        colors = [PALETTE["teal"], PALETTE["navy"], PALETTE["coral"]]

        bars = ax1.bar(categories, counts, color=colors, width=0.55)
        ax1.set_title(
            "Stabilité de la décision binaire",
            fontweight="bold",
            color=PALETTE["navy"],
            pad=10,
        )
        ax1.set_ylabel("Nombre d'articles")
        ax1.set_ylim(0, max(counts) * 1.18 if counts else 1)
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)

        for bar, c in zip(bars, counts):
            pct = (c / n_articles * 100) if n_articles else 0
            ax1.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(counts) * 0.02,
                f"{c}\n({pct:.1f}%)",
                ha="center",
                va="bottom",
                fontsize=8.5,
                fontweight="bold",
            )

        # --- Graphique 2 : Distribution des scores moyens ---
        ax2 = fig.add_subplot(gs[1, 1])
        mean_scores = [d["mean_score"] for d in details]
        bins = np.linspace(0, 5, 11)
        ax2.hist(
            mean_scores, bins=bins, color=PALETTE["navy"], edgecolor="white", alpha=0.9
        )
        ax2.axvline(
            threshold,
            color=PALETTE["coral"],
            linestyle="--",
            linewidth=1.5,
            label=f"Seuil d'inclusion ({threshold})",
        )
        ax2.set_title(
            "Distribution des scores moyens",
            fontweight="bold",
            color=PALETTE["navy"],
            pad=10,
        )
        ax2.set_xlabel("Score moyen sur 5 passes")
        ax2.set_ylabel("Nombre d'articles")
        ax2.set_xticks(range(6))
        ax2.legend(frameon=False, fontsize=8.5)
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_visible(False)

        # --- Graphique 3 : Matrice de confusion Disque vs Vote Majoritaire ---
        ax3 = fig.add_subplot(gs[2, 0])
        labels = ["KEEP", "DROP"]
        matrix = np.zeros((2, 2), dtype=int)
        for d in details:
            i = 0 if d["initial_label"] == "KEEP" else 1
            j = 0 if d["majority_decision"] == "KEEP" else 1
            matrix[i, j] += 1

        ax3.imshow(matrix, cmap="Blues", aspect="auto")
        ax3.set_xticks([0, 1], labels=["Maj: KEEP", "Maj: DROP"])
        ax3.set_yticks([0, 1], labels=["Init: KEEP", "Init: DROP"])
        ax3.set_title(
            "Accord Initial vs Vote Majoritaire",
            fontweight="bold",
            color=PALETTE["navy"],
            pad=10,
        )

        for i in range(2):
            for j in range(2):
                text_color = (
                    "white" if matrix[i, j] > matrix.max() * 0.5 else PALETTE["navy"]
                )
                ax3.text(
                    j,
                    i,
                    f"{matrix[i, j]}",
                    ha="center",
                    va="center",
                    fontsize=13,
                    fontweight="bold",
                    color=text_color,
                )

        # --- Graphique 4 : Histogramme des écarts-types intra-article ---
        ax4 = fig.add_subplot(gs[2, 1])
        stds = [d["std_score"] for d in details]
        zero_std = sum(1 for s in stds if s == 0.0)
        non_zero_stds = [s for s in stds if s > 0.0]

        ax4.bar(
            ["σ = 0.00\n(Identique)", "σ > 0.00\n(Variable)"],
            [zero_std, len(non_zero_stds)],
            color=[PALETTE["teal"], PALETTE["amber"]],
            width=0.5,
        )
        ax4.set_title(
            "Variance des notes attribuées",
            fontweight="bold",
            color=PALETTE["navy"],
            pad=10,
        )
        ax4.set_ylabel("Nombre d'articles")
        ax4.set_ylim(0, max(zero_std, len(non_zero_stds)) * 1.18)
        ax4.spines["top"].set_visible(False)
        ax4.spines["right"].set_visible(False)
        for idx_b, val_b in enumerate([zero_std, len(non_zero_stds)]):
            ax4.text(
                idx_b,
                val_b + max(zero_std, len(non_zero_stds)) * 0.02,
                f"{val_b} ({val_b / n_articles * 100:.1f}%)",
                ha="center",
                va="bottom",
                fontsize=8.5,
                fontweight="bold",
            )

        fig.text(
            0.5,
            0.03,
            f"Généré automatiquement par Operon  •  Durée totale du benchmark : {data['elapsed_seconds']} s",
            ha="center",
            fontsize=8,
            color=PALETTE["slate"],
        )
        pdf.savefig(fig)
        plt.close(fig)

        # =====================================================================
        # PAGE 2 : PROFIL DISPERSION/SCORE & TABLEAU DES ARTICLES FRONTIÈRES
        # =====================================================================
        fig2 = plt.figure(figsize=(8.27, 11.69))
        gs2 = fig2.add_gridspec(2, 1, height_ratios=[1.0, 1.45], hspace=0.32)

        fig2.suptitle(
            "Analyse des cas frontières et de la dispersion intra-modèle",
            fontsize=13,
            fontweight="bold",
            color=PALETTE["navy"],
            y=0.96,
        )

        # --- Scatter : Écart-type vs Score moyen ---
        ax_sc = fig2.add_subplot(gs2[0])
        rng = np.random.default_rng(42)

        for is_unanimous, label, color, marker in [
            (True, "Décision unanime", PALETTE["teal"], "o"),
            (False, "Bascule KEEP/DROP (FLIP)", PALETTE["coral"], "D"),
        ]:
            subset = [d for d in details if d["unanimous"] == is_unanimous]
            if not subset:
                continue
            xs = np.array([d["mean_score"] for d in subset]) + rng.normal(
                0, 0.03, len(subset)
            )
            ys = np.array([d["std_score"] for d in subset]) + rng.normal(
                0, 0.015, len(subset)
            )
            ax_sc.scatter(
                xs,
                np.clip(ys, 0, None),
                label=f"{label} (n={len(subset)})",
                color=color,
                marker=marker,
                s=48,
                alpha=0.85,
                edgecolors="white",
                linewidth=0.6,
            )

        ax_sc.axvline(threshold, color=PALETTE["coral"], linestyle="--", linewidth=1.2)
        ax_sc.axvspan(
            threshold - 0.5,
            threshold + 0.5,
            color=PALETTE["amber"],
            alpha=0.15,
            label="Zone frontière (±0.5)",
        )
        ax_sc.set_title(
            "Dispersion (σ) en fonction du score moyen (avec léger jitter visuel)",
            fontweight="bold",
            color=PALETTE["navy"],
            pad=10,
        )
        ax_sc.set_xlabel("Score moyen (0 = hors-sujet, 5 = génomique humaine malgache)")
        ax_sc.set_ylabel("Écart-type des scores (σ)")
        ax_sc.set_xlim(-0.2, 5.2)
        ax_sc.legend(frameon=False, loc="upper right", fontsize=8.5)
        ax_sc.spines["top"].set_visible(False)
        ax_sc.spines["right"].set_visible(False)

        # --- Tableau des articles instables ou divergents par rapport au disque ---
        ax_tbl = fig2.add_subplot(gs2[1])
        ax_tbl.axis("off")

        flagged = [
            d
            for d in details
            if (not d["unanimous"]) or (d["majority_decision"] != d["initial_label"])
        ]
        flagged.sort(key=lambda x: (-x["std_score"], x["pmid"]))

        ax_tbl.set_title(
            f"Articles instables ou divergents du corpus initial ({len(flagged)} cas détectés)",
            fontweight="bold",
            color=PALETTE["navy"],
            loc="left",
            pad=8,
        )

        if not flagged:
            ax_tbl.text(
                0.5,
                0.5,
                "Aucun article instable ni divergent : 100 % de reproductibilité sur l'ensemble du corpus.",
                ha="center",
                va="center",
                fontsize=10,
                color=PALETTE["teal"],
                fontweight="bold",
            )
        else:
            rows = []
            for d in flagged[
                :22
            ]:  # Cap à 22 lignes pour tenir proprement sur la page A4
                short_title = (
                    (d["title"][:46] + "…") if len(d["title"]) > 47 else d["title"]
                )
                scores_str = ",".join(str(s) for s in d["scores"])
                rows.append(
                    [
                        d["pmid"],
                        short_title,
                        f"[{scores_str}]",
                        f"{d['std_score']:.2f}",
                        f"{d['initial_label']} → {d['majority_decision']}",
                    ]
                )

            table = ax_tbl.table(
                cellText=rows,
                colLabels=["PMID", "Titre", "Scores", "σ", "Init → Maj"],
                colWidths=[0.13, 0.45, 0.17, 0.08, 0.17],
                loc="upper center",
                cellLoc="left",
            )
            table.auto_set_font_size(False)
            table.set_fontsize(7.8)
            table.scale(1, 1.35)

            for (row_idx, col_idx), cell in table.get_celld().items():
                cell.set_edgecolor(PALETTE["border"])
                cell.set_linewidth(0.5)
                if row_idx == 0:
                    cell.set_facecolor(PALETTE["navy"])
                    cell.get_text().set_color("white")
                    cell.get_text().set_weight("bold")
                elif row_idx % 2 == 0:
                    cell.set_facecolor(PALETTE["light_bg"])

        pdf.savefig(fig2)
        plt.close(fig2)

    print(f"Rapport PDF généré avec succès : {output_pdf}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Génère un rapport PDF matplotlib depuis le benchmark Qwen."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/benchmark_qwen_stability.json"),
        help="Chemin vers le fichier JSON produit par qwen_benchmark.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/benchmark_qwen_report.pdf"),
        help="Chemin de sortie du fichier PDF",
    )
    args = parser.parse_args()

    data = load_report(args.input)
    build_pdf_report(data, args.output)


if __name__ == "__main__":
    main()
