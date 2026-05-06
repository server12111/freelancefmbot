import io
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

_STYLE = {
    "figure.facecolor": "#1e1e2e",
    "axes.facecolor":   "#1e1e2e",
    "axes.edgecolor":   "#45475a",
    "axes.labelcolor":  "#cdd6f4",
    "xtick.color":      "#cdd6f4",
    "ytick.color":      "#cdd6f4",
    "text.color":       "#cdd6f4",
    "grid.color":       "#313244",
    "grid.alpha":       0.6,
}


def _apply_style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#45475a")
    ax.spines["bottom"].set_color("#45475a")
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)


def _to_png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return buf


def generate_bar_chart(
    labels: list[str],
    values: list[int | float],
    title: str,
    ylabel: str,
    color: str = "#89b4fa",
) -> io.BytesIO:
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.bar(labels, values, color=color, width=0.6, zorder=3)

        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + max(values) * 0.02,
                    str(int(val)) if isinstance(val, float) and val == int(val) else f"{val:.1f}",
                    ha="center", va="bottom", fontsize=9, color="#cdd6f4",
                )

        ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        plt.xticks(rotation=35, ha="right", fontsize=8)
        _apply_style(ax)
        plt.tight_layout()
        return _to_png(fig)


def generate_users_chart(data: dict[str, int]) -> io.BytesIO:
    labels = list(data.keys())
    values = list(data.values())
    return generate_bar_chart(labels, values, "📈 New User Registrations", "Users", "#89b4fa")


def generate_revenue_chart(data: dict[str, float]) -> io.BytesIO:
    labels = list(data.keys())
    values = list(data.values())
    return generate_bar_chart(labels, values, "💰 Revenue Over Time ($)", "USD", "#a6e3a1")


def generate_referral_chart(names: list[str], users: list[int], orders: list[int]) -> io.BytesIO:
    x = np.arange(len(names))
    width = 0.35

    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(10, 5))
        b1 = ax.bar(x - width / 2, users,  width, label="Users",  color="#89b4fa", zorder=3)
        b2 = ax.bar(x + width / 2, orders, width, label="Orders", color="#f38ba8", zorder=3)

        ax.set_title("🔗 Referral Link Performance", fontsize=13, fontweight="bold", pad=12)
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=25, ha="right", fontsize=9)
        ax.legend(facecolor="#313244", edgecolor="#45475a", labelcolor="#cdd6f4")
        _apply_style(ax)
        plt.tight_layout()
        return _to_png(fig)
