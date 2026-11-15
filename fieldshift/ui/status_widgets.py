"""Pieces of the Status panel: the summary tiles and their text helpers.
Pure Qt, no QGIS.
"""

from fieldshift.i18n import tr
from fieldshift.qt import QtWidgets
from fieldshift.status import LEVEL_ALERT, LEVEL_OK, LEVEL_WATCH

# colour of each level
LEVEL_COLORS = {LEVEL_OK: "#2e7d32", LEVEL_WATCH: "#ef8f00", LEVEL_ALERT: "#d65858"}


# (StatusRow row, float value)
# the value with the row's decimals and unit ("23.4 °C")
def format_value(row, value):
    text = f"{value:.{row.decimals}f}"
    return f"{text} {row.unit}" if row.unit else text


# (StatusRow row)
# "↑ 2.1" / "↓ 0.4" / "=": newest value against the period mean
def trend_text(row):
    change = row.change()
    if row.fixed or abs(change) < 10 ** -row.decimals:
        return "="
    return f"{'↑' if change > 0 else '↓'} {abs(change):.{row.decimals}f}"


# (str source)
# a source name, translated when it is an i18n key ("status.source.farmer")
def source_text(source):
    return tr(source) if source.startswith("status.") else source


# a tile of the "today" summary: icon, name, newest value and trend
class SummaryTile(QtWidgets.QFrame):

    # (SummaryTile tile, int days)
    # days: length of the period the trend compares with
    def __init__(self, tile, days, parent=None):
        super().__init__(parent)
        self.tile = tile
        row = tile.row
        color = LEVEL_COLORS.get(row.level, LEVEL_COLORS[LEVEL_OK])
        self.setObjectName("summaryTile")
        self.setStyleSheet(
            f"QFrame#summaryTile {{ background: white; border: 1px solid #d5dbd5;"
            f" border-left: 4px solid {color}; border-radius: 6px; }}"
            f" QFrame#summaryTile:hover {{ background: #f1f8f1; }}"
            f" QLabel {{ border: none; background: transparent; }}")
        name = QtWidgets.QLabel(f"{tile.icon} {tr(row.label_key)}")
        name.setStyleSheet("color: #555; font-size: 11px;")
        value = QtWidgets.QLabel(f"<b>{format_value(row, row.latest())}</b>")
        value.setStyleSheet("font-size: 16px; color: #1b1b1b;")
        trend = QtWidgets.QLabel(tr("status.tile_trend", trend=trend_text(row), days=days))
        trend.setStyleSheet(f"color: {color}; font-size: 11px;")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(1)
        for label in (name, value, trend):
            layout.addWidget(label)
