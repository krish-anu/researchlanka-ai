"""Regenerate the paper figures from the canonical ResearchLanka AI CSV."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "researchlanka-ai-dataset/data/researchlanka_ai_publications_v1.0.csv"
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(exist_ok=True)

BLUE = "#1769aa"
TEAL = "#00897b"
ORANGE = "#ef6c00"
INK = "#233142"
LIGHT = "#edf4fa"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.labelcolor": INK,
        "axes.edgecolor": "#7c8b99",
        "xtick.color": INK,
        "ytick.color": INK,
    }
)


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT / name, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def pipeline_figure() -> None:
    labels = [
        "OpenAlex, Crossref,\nSLJOL, repositories",
        "Common schema &\nmetadata normalization",
        "Ownership gate &\ndeduplication",
        "AI triage &\nhuman review",
        "Versioned dataset,\nAPI & dashboard",
    ]
    colors = [BLUE, BLUE, TEAL, ORANGE, TEAL]
    fig, ax = plt.subplots(figsize=(7.05, 1.55))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2)
    ax.axis("off")
    xs = [0.05, 2.08, 4.11, 6.14, 8.17]
    for i, (x, label, color) in enumerate(zip(xs, labels, colors)):
        box = FancyBboxPatch(
            (x, 0.52), 1.68, 0.96,
            boxstyle="round,pad=0.04,rounding_size=0.08",
            linewidth=1.25, edgecolor=color, facecolor=LIGHT,
        )
        ax.add_patch(box)
        ax.text(x + 0.84, 1.0, label, ha="center", va="center", color=INK,
                fontsize=7.2, weight="semibold")
        if i < len(xs) - 1:
            ax.annotate("", xy=(x + 2.0, 1.0), xytext=(x + 1.73, 1.0),
                        arrowprops={"arrowstyle": "-|>", "lw": 1.25, "color": "#607d8b"})
    ax.text(5, 0.14, "Row-level provenance and audit evidence retained across stages",
            ha="center", va="center", color="#455a64", fontsize=7.4)
    save(fig, "pipeline.png")


def corpus_figures(df: pd.DataFrame) -> None:
    years = pd.to_datetime(df["publication_date"], format="mixed").dt.year
    counts = years.value_counts().sort_index()

    fig, ax = plt.subplots(figsize=(3.45, 2.1))
    complete = counts.loc[2016:2025]
    ax.plot(complete.index, complete.values, marker="o", ms=3.5, lw=1.8, color=BLUE)
    ax.bar([2026], [counts.loc[2026]], width=0.58, color=ORANGE, alpha=0.8)
    ax.text(2026, counts.loc[2026] + 24, "partial", ha="center", color=ORANGE, fontsize=7)
    ax.set_ylabel("Publications")
    ax.set_xlabel("Publication year")
    ax.set_xticks(range(2016, 2027, 2))
    ax.grid(axis="y", alpha=0.22, lw=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, 730)
    save(fig, "annual_output.png")

    fields = df["primary_field"].fillna("Unspecified").value_counts()
    top = fields.iloc[:5]
    other = fields.iloc[5:].sum()
    plot = pd.concat([top, pd.Series({"Other / unspecified": other})]).sort_values()
    fig, ax = plt.subplots(figsize=(3.45, 2.1))
    bars = ax.barh(plot.index, plot.values, color=[TEAL] * (len(plot) - 1) + [BLUE])
    for bar in bars:
        ax.text(bar.get_width() + 18, bar.get_y() + bar.get_height() / 2,
                f"{int(bar.get_width()):,}", va="center", fontsize=7, color=INK)
    ax.set_xlabel("Publications")
    ax.grid(axis="x", alpha=0.2, lw=0.6)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, max(plot.values) * 1.18)
    save(fig, "field_distribution.png")


if __name__ == "__main__":
    data = pd.read_csv(DATA)
    pipeline_figure()
    corpus_figures(data)
    print(f"Wrote figures to {OUT}")
