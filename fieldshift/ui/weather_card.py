"""Card over the top-right corner of the map with the weather of the zone at
the centre of the view: now and over the day, hour by hour
(fieldshift.api.forecast). The coming days are in the Status panel.

It reloads a moment after the map stops moving, in a background thread, and
only when the centre moved to another forecast cell (about 10 km). Uses the
map only through MapView (center, view_changed).
"""

import os
import threading
from datetime import date

from fieldshift.api import forecast as forecast_api
from fieldshift.api import geocode
from fieldshift.i18n import tr
from fieldshift.qt import QtCore, QtWidgets

# distance (pixels) from the top-right corner of the map
MARGIN_PX = 12
# wait this long (ms) after the last map movement before loading
SETTLE_MS = 700
# hours shown in the strip, and the step between them
HOUR_COUNT = 8
HOUR_STEP = 3
# when set to "1" the card never contacts the service (tests)
OFFLINE_ENV = "FIELDSHIFT_OFFLINE"

# icon of each sky kind of the forecast
SKY_ICONS = {
    forecast_api.SKY_CLEAR: "☀️", forecast_api.SKY_PARTLY: "⛅", forecast_api.SKY_CLOUDY: "☁️",
    forecast_api.SKY_FOG: "🌫️", forecast_api.SKY_RAIN: "🌧️", forecast_api.SKY_SNOW: "❄️",
    forecast_api.SKY_STORM: "⛈️",
}

_STYLE = ("QFrame#weatherCard { background: rgba(255, 255, 255, 235); border: 1px solid #9aa39a;"
          " border-radius: 8px; } QLabel { background: transparent; border: none; color: #1b1b1b; }")


# (str iso_date)
# short weekday name of "YYYY-MM-DD" in the current language ("Mon")
def weekday_name(iso_date):
    return tr(f"weekday.{date.fromisoformat(iso_date).weekday()}")


# the floating weather card. fetch(lon, lat) -> Forecast replaces the real
# service (tests); without it and with FIELDSHIFT_OFFLINE=1 the card stays hidden
class WeatherCard(QtWidgets.QFrame):

    # internal: (int request number, Forecast or None), from the loader thread
    _loaded = QtCore.pyqtSignal(int, object, object)

    # (MapView view, callable fetch = None, callable zone_name = None)
    # puts the card over view.widget() and follows the view. zone_name(lon,
    # lat) -> str names the zone for the title (default: OpenStreetMap; with
    # a test fetch and no zone_name the title stays generic)
    def __init__(self, view, fetch=None, zone_name=None):
        super().__init__(view.widget())
        self.view = view
        self._zone_name = zone_name or (geocode.zone_name if fetch is None else None)
        self._fetch = fetch or forecast_api.get_forecast
        self._enabled = fetch is not None or os.environ.get(OFFLINE_ENV) != "1"
        self._request = 0            # number of the newest request
        self._cell = None            # forecast cell shown (or being loaded)
        self.forecast = None         # the Forecast shown, or None
        self.setObjectName("weatherCard")
        self.setStyleSheet(_STYLE)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.title_label = QtWidgets.QLabel(f"<b>{tr('weather.title')}</b>")
        self.now_label = QtWidgets.QLabel()
        self.hours_label = QtWidgets.QLabel()
        self.hours_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.summary_label = QtWidgets.QLabel()
        self.summary_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.credit_label = QtWidgets.QLabel(forecast_api.ATTRIBUTION)
        self.credit_label.setStyleSheet("color: #777; font-size: 10px;")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        for label in (self.title_label, self.now_label, self.hours_label, self.summary_label,
                      self.credit_label):
            layout.addWidget(label)
        self.hide()

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(SETTLE_MS)
        self._timer.timeout.connect(self.reload)
        self._loaded.connect(self._on_loaded)
        view.widget().installEventFilter(self)
        if self._enabled:
            view.view_changed.connect(self._timer.start)
            self._timer.start()

    # ()
    # loads the forecast of the centre of the map now, unless it is the zone
    # already shown. returns True when a load started
    def reload(self):
        center = self.view.center() if self._enabled else None
        if center is None:
            return False
        cell = forecast_api.cell_of(*center)
        if cell == self._cell:
            return False
        self._cell = cell
        self._request += 1
        if self.forecast is None:
            self._show_message(tr("weather.loading"))
        threading.Thread(target=self._run, args=(self._request, *center), daemon=True,
                         name="weather-card").start()
        return True

    # loader thread: fetch and report (None when the service fails)
    def _run(self, request, lon, lat):
        try:
            result = self._fetch(lon, lat)
        except Exception:
            result = None
        name = None
        if result is not None and self._zone_name is not None:
            try:
                name = self._zone_name(lon, lat)
            except Exception:
                name = None                     # no name: generic title
        self._loaded.emit(request, result, name)

    def _on_loaded(self, request, result, name):
        if request != self._request:
            return                              # the map moved on: stale answer
        self.forecast = result
        title = tr("weather.title_in", place=name) if name else tr("weather.title")
        self.title_label.setText(f"<b>{title}</b>")
        if result is None:
            self._cell = None                   # try again on the next movement
            self._show_message(tr("weather.unavailable"))
            return
        self.now_label.setText(tr("weather.now", icon=SKY_ICONS.get(result.sky, ""),
                                  temp=f"{result.temperature:.0f}",
                                  wind=f"{result.wind_kmh:.0f}"))
        hours = self._hours(result)

        def chance(h):
            return "" if h.rain_chance is None else f"{h.rain_chance:.0f}%"
        cells = "".join(
            f"<td align='center' style='padding: 0 4px;'>{h.time[11:13]}h<br>"
            f"<span style='font-size:15px'>{SKY_ICONS.get(h.sky, '')}</span><br>"
            f"<b>{h.temp:.0f}°</b><br>"
            f"<span style='color:#1e88e5'>{chance(h)}</span></td>" for h in hours)
        self.hours_label.setText(f"<table cellspacing='0'><tr>{cells}</tr></table>")
        self.hours_label.setVisible(bool(hours))
        today = result.days[0]
        lines = [tr("weather.today", tmax=f"{today.tmax:.0f}", tmin=f"{today.tmin:.0f}",
                    mm=f"{today.rain_mm:.1f}")
                 + " · " + tr("weather.elevation", m=f"{result.elevation:.0f}")]
        if today.tmin <= forecast_api.FROST_C:
            lines.append(f"<b style='color:#c62828'>❄ {tr('weather.frost_tonight')}</b>")
        self.summary_label.setText("<br>".join(lines))
        for label in (self.now_label, self.summary_label, self.credit_label):
            label.show()
        self._place()

    # the hours of the strip: from the current hour on, every HOUR_STEP
    def _hours(self, result):
        hours = list(result.hours)
        now = result.now[:13]
        start = next((i for i, h in enumerate(hours) if h.time[:13] >= now), 0) if now else 0
        return hours[start:start + HOUR_COUNT * HOUR_STEP:HOUR_STEP]

    def _show_message(self, text):
        self.now_label.setText(text)
        self.now_label.show()
        for label in (self.hours_label, self.summary_label, self.credit_label):
            label.hide()
        self._place()

    def _place(self):
        self.adjustSize()
        parent = self.parentWidget()
        self.move(max(0, parent.width() - self.width() - MARGIN_PX), MARGIN_PX)
        self.show()
        self.raise_()

    def eventFilter(self, watched, event):
        if (watched is self.parentWidget() and event.type() == QtCore.QEvent.Type.Resize
                and not self.isHidden()):
            self._place()
        return False
