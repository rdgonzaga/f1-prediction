"""Shared matplotlib theme for notebooks."""
import matplotlib as mpl

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
ACCENT = "#2a78d6"
DEEMPHASIS = "#c3c2b7"
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def apply_theme() -> None:
    mpl.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "figure.dpi": 110,
        "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"], "font.size": 10,
        "text.color": INK, "axes.titlecolor": INK, "axes.labelcolor": INK_SECONDARY,
        "axes.titlesize": 12, "axes.titleweight": "semibold", "axes.titlelocation": "left", "axes.titlepad": 12,
        "axes.edgecolor": AXIS, "axes.linewidth": 1, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 1, "grid.linestyle": "-",
        "xtick.color": AXIS, "ytick.color": AXIS, "xtick.labelcolor": INK_SECONDARY, "ytick.labelcolor": INK_SECONDARY,
        "lines.linewidth": 2, "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round", "lines.markersize": 8,
        "legend.frameon": False, "legend.labelcolor": INK_SECONDARY,
    })
