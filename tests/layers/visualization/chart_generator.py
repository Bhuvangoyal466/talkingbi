import io
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np
from core.logger import logger

CHART_STYLE = {
    "figure.figsize": (10, 6),
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.family": "sans-serif",
    "axes.titlesize": 14,
    "axes.labelsize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
}


def _safe_float(val, default=0.0):
    """Convert a value to float, returning default on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


class ChartGenerator:
    """
    Generates publication-quality Matplotlib charts from structured data.
    Returns base64-encoded PNG and execution-ready Python code.
    """

    def generate(self, extracted_data: dict, chart_type: dict) -> dict:
        """Generate chart and return image + code."""
        chart_type_str = chart_type.get("recommended_chart_type", "bar")

        try:
            fig, code = self._render(extracted_data, chart_type_str)
            img_b64 = self._fig_to_b64(fig)
            plt.close(fig)
            return {
                "image_base64": img_b64,
                "code": code,
                "chart_type": chart_type_str,
                "success": True,
            }
        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
            return {"success": False, "error": str(e)}

    def _render(self, data: dict, chart_type: str):
        """Render chart using Matplotlib."""
        plt.rcParams.update(CHART_STYLE)
        fig, ax = plt.subplots()

        values = data.get("values", [])
        if not values:
            ax.text(0.5, 0.5, "No data to display", ha="center", va="center",
                    transform=ax.transAxes, fontsize=14)
            return fig, "# No data"

        title = data.get("title", "Chart")
        xlabel = data.get("x_axis_label", "X")
        ylabel = data.get("y_axis_label", "Y")

        has_cat = any("category" in v for v in values)

        code_lines = [
            "import matplotlib.pyplot as plt",
            "import numpy as np",
            f"# {title}",
        ]

        if chart_type in ["bar", "horizontal_bar"] and not has_cat:
            x = [str(v["x"]) for v in values]
            y = [_safe_float(v["y"]) for v in values]
            colors = cm.Set2(np.linspace(0, 1, len(x)))

            if chart_type == "bar":
                ax.bar(x, y, color=colors, edgecolor="white", linewidth=0.5)
                if len(x) > 6:
                    ax.set_xticklabels(x, rotation=45, ha="right")
                else:
                    ax.set_xticklabels(x)
            else:
                ax.barh(x, y, color=colors, edgecolor="white", linewidth=0.5)
                ax.set_ylabel(xlabel)
                ax.set_xlabel(ylabel)
            code_lines += [f"x = {x}", f"y = {y}"]

        elif chart_type == "grouped_bar" and has_cat:
            cats = sorted(set(v.get("category", "") for v in values if "category" in v))
            x_labels = sorted(set(str(v["x"]) for v in values))
            x_pos = np.arange(len(x_labels))
            width = 0.8 / max(len(cats), 1)
            colors = cm.Set2(np.linspace(0, 1, len(cats)))

            for i, cat in enumerate(cats):
                cat_vals = {str(v["x"]): _safe_float(v["y"]) for v in values if v.get("category") == cat}
                y = [cat_vals.get(xl, 0) for xl in x_labels]
                offset = (i - len(cats) / 2 + 0.5) * width
                ax.bar(x_pos + offset, y, width, label=cat, color=colors[i], edgecolor="white")

            ax.set_xticks(x_pos)
            ax.set_xticklabels(x_labels, rotation=45, ha="right")
            ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=9)

        elif chart_type == "stacked_bar" and has_cat:
            cats = sorted(set(v.get("category", "") for v in values if "category" in v))
            x_labels = sorted(set(str(v["x"]) for v in values))
            x_pos = np.arange(len(x_labels))
            colors = cm.Set2(np.linspace(0, 1, len(cats)))
            bottoms = np.zeros(len(x_labels))

            for i, cat in enumerate(cats):
                cat_vals = {str(v["x"]): _safe_float(v["y"]) for v in values if v.get("category") == cat}
                y = np.array([cat_vals.get(xl, 0) for xl in x_labels])
                ax.bar(x_pos, y, bottom=bottoms, label=cat, color=colors[i], edgecolor="white")
                bottoms += y

            ax.set_xticks(x_pos)
            ax.set_xticklabels(x_labels, rotation=45, ha="right")
            ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=9)

        elif chart_type == "line":
            x_raw = [str(v["x"]) for v in values]
            y = [_safe_float(v["y"]) for v in values]
            x_idx = list(range(len(x_raw)))
            ax.plot(x_idx, y, marker="o", linewidth=2, markersize=5, color="#2196F3")
            ax.fill_between(x_idx, y, alpha=0.1, color="#2196F3")
            step = max(1, len(x_raw) // 8)
            ax.set_xticks(x_idx[::step])
            ax.set_xticklabels(x_raw[::step], rotation=45, ha="right")
            code_lines += [f"x = {x_raw}", f"y = {y}"]

        elif chart_type == "area":
            x_raw = [str(v["x"]) for v in values]
            y = [_safe_float(v["y"]) for v in values]
            x_idx = list(range(len(x_raw)))
            ax.fill_between(x_idx, y, alpha=0.4, color="#9C27B0")
            ax.plot(x_idx, y, color="#9C27B0", linewidth=2)
            step = max(1, len(x_raw) // 8)
            ax.set_xticks(x_idx[::step])
            ax.set_xticklabels(x_raw[::step], rotation=45, ha="right")

        elif chart_type == "pie":
            # Aggregate by label so duplicate states are summed
            from collections import defaultdict
            agg_map: dict = defaultdict(float)
            for v in values:
                agg_map[str(v["x"])] += abs(_safe_float(v["y"]))
            sorted_items = sorted(agg_map.items(), key=lambda t: t[1], reverse=True)
            MAX_SLICES = 15
            if len(sorted_items) > MAX_SLICES:
                top = sorted_items[:MAX_SLICES]
                other_total = sum(v for _, v in sorted_items[MAX_SLICES:])
                top.append(("Other", other_total))
            else:
                top = sorted_items
            x_pie = [k for k, _ in top]
            y_pie = [v for _, v in top]
            colors_pie = cm.Set3(np.linspace(0, 1, len(x_pie)))
            wedges, texts, autotexts = ax.pie(
                y_pie, labels=x_pie, autopct="%1.1f%%", colors=colors_pie,
                startangle=90, pctdistance=0.85,
            )
            for t in autotexts:
                t.set_fontsize(9)
            ax.set_aspect("equal")

        elif chart_type == "scatter":
            try:
                x_num = [float(v["x"]) for v in values]
            except (ValueError, TypeError):
                x_num = list(range(len(values)))
            y_num = [_safe_float(v["y"]) for v in values]
            ax.scatter(x_num, y_num, alpha=0.7, s=60, c="#E91E63",
                       edgecolors="white", linewidth=0.5)
            if len(x_num) >= 2:
                z = np.polyfit(x_num, y_num, 1)
                p = np.poly1d(z)
                x_sorted = sorted(x_num)
                ax.plot(x_sorted, p(x_sorted), "r--", alpha=0.5, linewidth=1.5,
                        label="Trend")
                ax.legend()

        elif chart_type == "histogram":
            y_vals = [_safe_float(v["y"]) for v in values]
            ax.hist(y_vals, bins=min(20, len(y_vals)), color="#4CAF50",
                    edgecolor="white", linewidth=0.5)

        else:
            # Fallback: simple bar
            x = [str(v["x"]) for v in values]
            y = [_safe_float(v["y"]) for v in values]
            ax.bar(x, y, color="#42A5F5")
            if len(x) > 6:
                ax.set_xticklabels(x, rotation=45, ha="right")

        ax.set_title(title, pad=15, fontweight="bold")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.3, linestyle="--")
        fig.tight_layout()

        code_lines.append(f"ax.set_title('{title}')")
        code_lines.append("plt.tight_layout()")
        code_lines.append("plt.savefig('chart.png', dpi=150, bbox_inches='tight')")

        return fig, "\n".join(code_lines)

    def _fig_to_b64(self, fig) -> str:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")
