"""Local-only interactive scientific charts for the optional PySide6 frontend."""
from __future__ import annotations

import base64
from collections.abc import Mapping
import hashlib
import json
import math
import unicodedata

try:
    from .scientific_ui_theme import CHART_SERIES_COLORS, COLORS
except ImportError:  # Support direct execution from scripts/.
    from scientific_ui_theme import CHART_SERIES_COLORS, COLORS

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    QtCore = QtGui = QtWidgets = None

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEnginePage = QWebEngineSettings = QWebEngineView = None


MAX_CHART_SERIES = 32
MAX_CHART_POINTS = 100_000
MAX_CHART_TOTAL_POINTS = 200_000
MAX_CHART_HTML_BYTES = 4 * 1024 * 1024
MAX_WEBENGINE_DATA_URL_BYTES = 2_000_000
_COLORS = CHART_SERIES_COLORS
WEBENGINE_AVAILABLE = all(
    item is not None for item in (QtCore, QtGui, QtWidgets, QWebEnginePage, QWebEngineSettings, QWebEngineView)
)


def _display_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"chart {label} must be a non-empty string of at most {maximum} characters")
    return "".join(
        char if char in "\t\n\r" or unicodedata.category(char) not in {"Cc", "Cf", "Cs"}
        else "\uFFFD"
        for char in value
    )


def _finite_number(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"chart {label} must be finite")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"chart {label} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"chart {label} must be finite")
    return result


def _normalize_chart_data(payload: object) -> dict[str, object]:
    required = {"title", "x_label", "y_label", "series"}
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise ValueError("chart payload must contain exactly title, x_label, y_label, and series")
    title = _display_text(payload["title"], "title", 200)
    x_label = _display_text(payload["x_label"], "x_label", 256)
    y_label = _display_text(payload["y_label"], "y_label", 256)
    raw_series = payload["series"]
    if (not isinstance(raw_series, (list, tuple)) or not raw_series
            or len(raw_series) > MAX_CHART_SERIES):
        raise ValueError(f"chart series limit is 1..{MAX_CHART_SERIES}")
    series: list[dict[str, object]] = []
    total_points = 0
    common_x: tuple[float, ...] | None = None
    names: set[str] = set()
    for index, raw in enumerate(raw_series):
        if not isinstance(raw, Mapping) or set(raw) != {"name", "x", "y"}:
            raise ValueError(f"chart series[{index}] must contain exactly name, x, and y")
        name = _display_text(raw["name"], f"series[{index}].name", 200)
        if name in names:
            raise ValueError("chart series names must be unique")
        names.add(name)
        raw_x, raw_y = raw["x"], raw["y"]
        if (not isinstance(raw_x, (list, tuple)) or not raw_x
                or len(raw_x) > MAX_CHART_POINTS):
            raise ValueError(f"chart series point limit is 1..{MAX_CHART_POINTS}")
        if not isinstance(raw_y, (list, tuple)) or len(raw_y) != len(raw_x):
            raise ValueError(f"chart series[{index}] x/y lengths must match")
        x_values = tuple(_finite_number(value, f"series[{index}] x value") for value in raw_x)
        y_values = tuple(_finite_number(value, f"series[{index}] y value") for value in raw_y)
        if any(right <= left for left, right in zip(x_values, x_values[1:])):
            raise ValueError(f"chart series[{index}] x values must be strictly increasing")
        if common_x is None:
            common_x = x_values
        elif x_values != common_x:
            raise ValueError("chart series must share the same x coordinates")
        total_points += len(x_values)
        if total_points > MAX_CHART_TOTAL_POINTS:
            raise ValueError(f"chart total point limit is {MAX_CHART_TOTAL_POINTS}")
        series.append({"name": name, "x": x_values, "y": y_values})
    return {"title": title, "x_label": x_label, "y_label": y_label, "series": tuple(series)}


_SCRIPT = r"""(()=>{
const host=document.getElementById('chart');
const raw=document.getElementById('payload').dataset.payload;
const bytes=Uint8Array.from(atob(raw),c=>c.charCodeAt(0));
const data=JSON.parse(new TextDecoder().decode(bytes));
const h=document.createElement('h2');h.textContent=data.title;host.appendChild(h);
const legend=document.createElement('div');legend.className='legend';host.appendChild(legend);
const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
svg.setAttribute('viewBox','0 0 960 480');svg.setAttribute('role','img');
svg.setAttribute('aria-label',data.title);host.appendChild(svg);
const tip=document.createElement('div');tip.className='tooltip';tip.setAttribute('role','status');host.appendChild(tip);
const ns='http://www.w3.org/2000/svg',L=82,R=20,T=24,B=72,W=960,H=480;
const allX=data.series[0].x;
let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;
for(const x of allX){if(x<xmin)xmin=x;if(x>xmax)xmax=x;}
for(const s of data.series)for(const y of s.y){if(y<ymin)ymin=y;if(y>ymax)ymax=y;}
if(xmin===xmax){xmin-=0.5;xmax+=0.5;}if(ymin===ymax){const p=Math.max(Math.abs(ymin)*0.05,1);ymin-=p;ymax+=p;}
else{const p=(ymax-ymin)*0.06;ymin-=p;ymax+=p;}
const px=x=>L+(x-xmin)/(xmax-xmin)*(W-L-R),py=y=>H-B-(y-ymin)/(ymax-ymin)*(H-T-B);
const el=(tag,attrs,text)=>{const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs||{}))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;svg.appendChild(n);return n;};
for(const y of [ymin,ymax])el('path',{d:`M${L},${py(y)}H${W-R}`,fill:'none',stroke:'#474550','stroke-width':1,class:'grid'});
el('path',{d:`M${L},${T}V${H-B}H${W-R}`,fill:'none',stroke:'#696574','stroke-width':2});
for(const [x,label] of [[L,String(allX[0])],[W-R,String(allX[allX.length-1])]])el('text',{x,y:H-B+24,'text-anchor':x===L?'start':'end',class:'tick'},label);
for(const [y,label] of [[T,String(ymax)],[H-B,String(ymin)]])el('text',{x:L-10,y:y+4,'text-anchor':'end',class:'tick'},label);
el('text',{x:(L+W-R)/2,y:H-16,'text-anchor':'middle',class:'axis'},data.x_label);
const ylabel=el('text',{x:18,y:(T+H-B)/2,'text-anchor':'middle',class:'axis',transform:`rotate(-90 18 ${(T+H-B)/2})`},data.y_label);
const colors=__SSEC_CHART_COLORS__;
const stride=Math.max(1,Math.ceil(allX.length/2000)),renderedIndices=[];
for(let j=0;j<allX.length;j+=stride)renderedIndices.push(j);
if(renderedIndices[renderedIndices.length-1]!==allX.length-1)renderedIndices.push(allX.length-1);
const paths=[];data.series.forEach((s,i)=>{const color=colors[i%colors.length];const d=renderedIndices.map((j,k)=>`${k?'L':'M'}${px(s.x[j]).toFixed(2)},${py(s.y[j]).toFixed(2)}`).join(' ');const path=el('path',{d,fill:'none',stroke:color,'stroke-width':2.5,'data-index':i,class:'series-line'});paths.push(path);const button=document.createElement('button');button.type='button';button.textContent=s.name;button.setAttribute('aria-pressed','true');button.style.borderColor=color;button.addEventListener('click',()=>{const on=button.getAttribute('aria-pressed')!=='true';button.setAttribute('aria-pressed',String(on));path.style.display=on?'':'none';});legend.appendChild(button);});
svg.addEventListener('mousemove',event=>{const point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;const p=point.matrixTransform(svg.getScreenCTM().inverse());if(p.x<L||p.x>W-R){tip.textContent='';return;}const ratio=(p.x-L)/(W-L-R),index=Math.max(0,Math.min(allX.length-1,Math.round(ratio*(allX.length-1))));const visible=data.series.map((s,i)=>paths[i].style.display==='none'?null:`${s.name}: ${s.y[index]}`).filter(Boolean);tip.textContent=`${data.x_label}: ${allX[index]} · ${visible.join(' · ')}`;});
svg.addEventListener('mouseleave',()=>{tip.textContent='';});
})();"""


def build_scientific_chart_html(plot_data: Mapping[str, object]) -> str:
    """Build a self-contained page; all project labels travel only as base64 JSON."""
    normalized = _normalize_chart_data(plot_data)
    encoded_payload = base64.b64encode(
        json.dumps(normalized, ensure_ascii=False, allow_nan=False,
                   separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    script = _SCRIPT.replace("__SSEC_CHART_COLORS__", json.dumps(CHART_SERIES_COLORS))
    script_hash = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    csp = (
        "default-src 'none'; base-uri 'none'; object-src 'none'; frame-src 'none'; "
        "connect-src 'none'; form-action 'none'; img-src 'none'; font-src 'none'; "
        f"script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'"
    )
    c = COLORS
    theme_css = (
        f":root{{color-scheme:dark;--surface:{c['surface']};--raised:{c['surface_raised']};"
        f"--text:{c['text']};--muted:{c['muted']};--border:{c['border']};--accent:{c['accent']};}}"
        "*{box-sizing:border-box}body{font:14px 'Segoe UI',system-ui,sans-serif;color:var(--text);"
        "background:var(--surface);margin:0;padding:14px}h2{font-size:16px;margin:4px 0 10px}"
        "svg{width:100%;height:auto;background:var(--surface);border-radius:8px}"
        ".axis{font:14px system-ui,sans-serif;fill:var(--text)}.tick{font:12px system-ui,sans-serif;fill:var(--muted)}"
        ".legend{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}"
        ".legend button{background:var(--raised);border:1px solid;border-radius:7px;padding:6px 10px;"
        "color:var(--text);cursor:pointer;transition:background-color 140ms ease,opacity 140ms ease}"
        ".legend button:hover{background:#403d49}.legend button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}"
        ".tooltip{min-height:1.5em;color:var(--muted);font-variant-numeric:tabular-nums;padding-top:5px}"
        "@media(prefers-reduced-motion:no-preference){.series-line{animation:line-in 260ms ease-out both}}"
        "@keyframes line-in{from{opacity:.15}to{opacity:1}}"
        "@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}"
    )
    html = (
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        f"<meta http-equiv=\"Content-Security-Policy\" content=\"{csp}\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<style>{theme_css}</style></head>"
        f"<body><div id=\"payload\" data-payload=\"{encoded_payload}\"></div>"
        "<main id=\"chart\"></main><script>" + script + "</script></body></html>"
    )
    if len(html.encode("utf-8")) > MAX_CHART_HTML_BYTES:
        raise ValueError(f"chart HTML exceeds the {MAX_CHART_HTML_BYTES}-byte limit")
    return html


if QtWidgets is not None:
    class _ChartPainter(QtWidgets.QFrame):
        def __init__(self, data: Mapping[str, object], parent=None):
            super().__init__(parent)
            self._data = _normalize_chart_data(data)
            self.setMinimumHeight(260)
            self.setAccessibleName(str(self._data["title"]))
            self.setAccessibleDescription("Gráfica estática de datos científicos validados.")

        def paintEvent(self, event) -> None:
            del event
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            painter.fillRect(self.rect(), QtGui.QColor(COLORS["surface"]))
            rect = self.rect().adjusted(88, 24, -18, -58)
            series = self._data["series"]
            x_values = series[0]["x"]
            y_values = tuple(value for item in series for value in item["y"])
            x_min, x_max = x_values[0], x_values[-1]
            y_min, y_max = min(y_values), max(y_values)
            if x_min == x_max:
                x_min -= 0.5
                x_max += 0.5
            if y_min == y_max:
                padding = max(abs(y_min) * 0.05, 1.0)
                y_min -= padding
                y_max += padding
            else:
                padding = (y_max - y_min) * 0.06
                y_min -= padding
                y_max += padding
            painter.setPen(QtGui.QPen(QtGui.QColor(COLORS["border"]), 1))
            for fraction in (0.0, 0.5, 1.0):
                y = rect.bottom() - round(fraction * rect.height())
                painter.drawLine(rect.left(), y, rect.right(), y)
            painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            painter.drawLine(rect.bottomLeft(), rect.topLeft())
            painter.setPen(QtGui.QColor(COLORS["muted"]))
            painter.drawText(34, rect.top() + 8, 48, 18,
                             QtCore.Qt.AlignmentFlag.AlignRight, f"{y_max:.4g}")
            painter.drawText(34, rect.bottom() - 9, 48, 18,
                             QtCore.Qt.AlignmentFlag.AlignRight, f"{y_min:.4g}")
            painter.drawText(rect.left(), rect.bottom() + 22, f"{x_min:.5g}")
            painter.drawText(rect.right() - 50, rect.bottom() + 22, f"{x_max:.5g}")
            painter.drawText(
                QtCore.QRectF(rect.left(), self.height() - 25, rect.width(), 20),
                QtCore.Qt.AlignmentFlag.AlignCenter,
                str(self._data["x_label"]),
            )
            painter.save()
            painter.translate(13, rect.center().y())
            painter.rotate(-90)
            painter.drawText(
                QtCore.QRectF(-rect.height() / 2, -10, rect.height(), 20),
                QtCore.Qt.AlignmentFlag.AlignCenter, str(self._data["y_label"]),
            )
            painter.restore()
            for index, item in enumerate(series):
                color = QtGui.QColor(_COLORS[index % len(_COLORS)])
                painter.setPen(QtGui.QPen(color, 2))
                path = QtGui.QPainterPath()
                stride = max(1, math.ceil(len(x_values) / 2000))
                sampled = list(range(0, len(x_values), stride))
                if sampled[-1] != len(x_values) - 1:
                    sampled.append(len(x_values) - 1)
                for point_index, data_index in enumerate(sampled):
                    x = rect.left() + (x_values[data_index] - x_min) / (x_max - x_min) * rect.width()
                    y = rect.bottom() - (item["y"][data_index] - y_min) / (y_max - y_min) * rect.height()
                    point = QtCore.QPointF(x, y)
                    if point_index == 0:
                        path.moveTo(point)
                    else:
                        path.lineTo(point)
                painter.drawPath(path)
                painter.drawLine(rect.left() + index * 155, rect.top() - 6,
                                 rect.left() + 16 + index * 155, rect.top() - 6)
                painter.drawText(rect.left() + 22 + index * 155, rect.top() - 1,
                                 str(item["name"]))


    def _data_table(data: Mapping[str, object]) -> QtWidgets.QTableWidget:
        normalized = _normalize_chart_data(data)
        series = normalized["series"]
        point_count = len(series[0]["x"])
        row_count = min(point_count, 200)
        indices = list(range(point_count))
        if point_count > row_count:
            stride = max(1, math.ceil(point_count / row_count))
            indices = list(range(0, point_count, stride))[:row_count]
            indices[-1] = point_count - 1
        table = QtWidgets.QTableWidget(len(indices), len(series) + 1)
        table.setObjectName("scientificChartDataTable")
        table.setHorizontalHeaderLabels((str(normalized["x_label"]), *(str(item["name"]) for item in series)))
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        for row_index, source_index in enumerate(indices):
            values = [series[0]["x"][source_index]]
            values.extend(item["y"][source_index] for item in series)
            for column, value in enumerate(values):
                table.setItem(row_index, column, QtWidgets.QTableWidgetItem(str(value)))
        if point_count > len(indices):
            table.setToolTip(f"Vista tabular limitada a {len(indices)} filas de {point_count} puntos.")
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        return table


    class _ScientificChartPage(QWebEnginePage):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._initial_local_document_pending = True

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            del navigation_type
            # Qt turns setHtml() into one UTF-8 data document. Permit only this
            # initial top-level load; links and subsequent navigation stay blocked.
            is_local_bootstrap = (
                self._initial_local_document_pending
                and is_main_frame
                and url.scheme() == "data"
                and url.toString().startswith("data:text/html;charset=UTF-8,")
            )
            if is_local_bootstrap:
                self._initial_local_document_pending = False
            return is_local_bootstrap

        def createWindow(self, window_type):
            del window_type
            return None


    class ScientificChartWidget(QtWidgets.QWidget):
        """Render one bounded series group locally, with a native chart fallback."""

        def __init__(self, plot_data: Mapping[str, object], parent=None):
            super().__init__(parent)
            self._data = _normalize_chart_data(plot_data)
            self.setObjectName("scientificChartWidget")
            self.setAccessibleName(str(self._data["title"]))
            self.setAccessibleDescription(
                f"Eje x: {self._data['x_label']}. Eje y: {self._data['y_label']}. "
                f"Series: {', '.join(str(item['name']) for item in self._data['series'])}."
            )
            layout = QtWidgets.QVBoxLayout(self)
            page_html = None
            if WEBENGINE_AVAILABLE and QWebEngineView is not None:
                try:
                    page_html = build_scientific_chart_html(self._data)
                except ValueError as exc:
                    if not str(exc).startswith("chart HTML exceeds the "):
                        raise
                if (page_html is not None
                        and len(page_html.encode("utf-8")) > MAX_WEBENGINE_DATA_URL_BYTES):
                    page_html = None
            if page_html is not None:
                view = QWebEngineView(self)
                view.setObjectName("scientificChartWebEngine")
                page = _ScientificChartPage(view)
                view.setPage(page)
                settings = view.settings()
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
                settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, False)
                view.setMinimumHeight(360)
                view.setHtml(page_html, QtCore.QUrl("about:blank"))
                layout.addWidget(view)
                layout.addWidget(_data_table(self._data))
            else:
                fallback = QtWidgets.QFrame(self)
                fallback.setObjectName("scientificChartFallback")
                fallback_layout = QtWidgets.QVBoxLayout(fallback)
                fallback_layout.addWidget(_ChartPainter(self._data, fallback))
                fallback_layout.addWidget(_data_table(self._data))
                layout.addWidget(fallback)
else:
    class ScientificChartWidget:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("ScientificChartWidget requires PySide6")
