"""Stage 4b: synthesize the client side (Index.html, App.js) from the IR.

UI-parity notes:
- Classic layout: static numeric X/Y/Width/Height/ZIndex become absolute
  inline styles; reactive ones become styleControl evaluators.
- Modern auto-layout: containers with a LayoutDirection property render as
  CSS flexbox (flex-direction, gap, align-items, justify-content, wrap,
  min-width/height); children use FillPortions -> flex and Align -> align-self.
- Cosmetics (Padding*, Radius*, Border*, DropShadow, Hover*/Pressed* states,
  Font, FontColor) are statically evaluated to CSS where possible.
- Static color expressions (RGBA/ColorFade over literals) are evaluated at
  generation time; anything non-static stays reactive.
- Galleries render their row template per item via FXRuntime.gallery, with
  per-row child handlers bound to the item (ThisItem semantics).
"""
from __future__ import annotations

import ast
import html
import json
import re

from ..fidelity import mark_emission
from ..controls import EXPLICITLY_UNSUPPORTED_INPUTS
from ..fx.naming import snake as _snake
from ..icons import icon_glyph, is_icon_name
from ..ir import AppIR, ControlNode


def _behavior_js(expr, subject: str) -> str:
    """A failed behavior translation must remain an observable failure."""
    return expr.js or f"FX.unsupported({json.dumps(subject + ': formula could not be translated')});"

ELEMENT_MAP = {
    "Button": "button",
    "Label": "span",
    "TextInput": "input",
    "TextArea": "textarea",
    "Dropdown": "select",
    "ComboBox": "select",
    "ListBox": "select",
    "CheckBox": "input",
    "DatePicker": "input",
    "FluentDatePicker": "input",
    "Gallery": "div",
    "GalleryTemplate": "div",
    "Image": "img",
    "Icon": "span",
    "HtmlText": "div",
    "Form": "div",
    "Screen": "section",
    "GroupContainer": "div",
    "Header": "header",
    "Timer": "button",
    "Slider": "input",
    "Rectangle": "div",
    "Chart": "div",
    "InfoButton": "span",
    "DataCard": "div",
    "DataTable": "div",
    "CanvasComponent": "div",
    "Legend": "div",
    "Chart": "div",
}

# Chart family per control type / variant (Power Apps chart controls).
CHART_TYPES = {
    "Chart": "bar", "PieChart": "pie", "BarChart": "bar", "LineChart": "line",
    "ColumnChart": "bar", "Legend": "legend",
}

# Properties consumed by the chart renderer (excluded from generic styling).
CHART_PROPS = {"Items", "ItemsLabels", "ItemsValues", "ChartType", "LayoutMinWidth",
               "LayoutMinHeight"}

# Render as semantic HTML but suppress children (self-contained visuals).
VOID_CONTENT_TYPES = {"Rectangle", "Chart", "InfoButton"}

CONTAINER_TYPES = {"GroupContainer"}

# ---- static CSS value evaluation --------------------------------------------

_NUM_RE = re.compile(r"^(\d+(?:\.\d+)?)$")
_QUOTED_RE = re.compile(r"^'([^']*)'$")
_RGBA_RE = re.compile(r"^FX\.rgba\(([^)]*)\)$")
_FADE_RE = re.compile(r"^FX\.colorFade\((.*), (-?[\d.]+)\)$")
_UNSAFE_HTML_BLOCK_RE = re.compile(
    r"<\s*(script|style|iframe|object|embed|svg|math)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_UNSAFE_HTML_TAG_RE = re.compile(
    r"<\s*/?\s*(script|style|iframe|object|embed|svg|math|link|meta|form|input|button)\b[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_EVENT_HANDLER_RE = re.compile(
    r"\s+on[a-z0-9_-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE,
)
_UNSAFE_URL_ATTR_RE = re.compile(
    r"\s+(?:href|src|xlink:href)\s*=\s*(?:(['\"])\s*(?:javascript|vbscript)\s*:"
    r"[\s\S]*?\1|(?:javascript|vbscript)\s*:[^\s>]*)",
    re.IGNORECASE,
)
_UNSAFE_HTML_ATTR_RE = re.compile(
    r"\s+(?:srcdoc|action|formaction)\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE,
)


def _fade_channel(c: float, t: float) -> int:
    if t >= 0:
        return round(c + (255 - c) * t)
    return round(c * (1 + t))


def _rgba_css(args: list[float]) -> str:
    r, g, b = (max(0, min(255, round(v))) for v in args[:3])
    a = args[3] if len(args) > 3 else 1.0
    if a >= 0.999:
        return f"#{r:02x}{g:02x}{b:02x}"
    return f"rgba({r},{g},{b},{round(a, 3)})"


def _static_color(expr) -> str | None:
    """RGBA/ColorFade over literals -> CSS color; quoted enum -> lowercase name."""
    if not expr or expr.js is None:
        return None
    js = expr.js.strip()
    m = _QUOTED_RE.match(js)
    if m:
        return m.group(1).lower().replace(" ", "-")
    m = _RGBA_RE.match(js)
    if m:
        try:
            return _rgba_css([float(x) for x in m.group(1).split(",")])
        except ValueError:
            return None
    m = _FADE_RE.match(js)
    if m:
        base = _static_color(type(expr)(raw=expr.raw, kind=expr.kind, js=m.group(1)))
        if base and base.startswith("#"):
            t = float(m.group(2))
            r, g, b = (int(base[i:i + 2], 16) for i in (1, 3, 5))
            return _rgba_css([_fade_channel(r, t), _fade_channel(g, t), _fade_channel(b, t), 1.0])
        return base
    return None


def _static_px(expr) -> str | None:
    if not expr or expr.js is None:
        return None
    m = _NUM_RE.match(expr.js.strip())
    return f"{m.group(1)}px" if m else None


def _static_pt(expr) -> str | None:
    """Power Apps font Size values are points, while geometry uses pixels."""
    value = _static_px(expr)
    return f"{value[:-2]}pt" if value else None


def _static_map(expr, mapping: dict[str, str]) -> str | None:
    if not expr or expr.js is None:
        return None
    js = expr.js.strip()
    m = _QUOTED_RE.match(js)
    if m:
        return mapping.get(m.group(1))
    # Older canvas exports frequently serialize enum members as bare values
    # (for example ``Align = Center`` and ``FontWeight = Bold``).  The Power
    # Fx emitter conservatively treats a bare identifier as app state, but in
    # a property-specific enum map the original spelling is unambiguous.
    raw = (expr.raw or "").strip()
    if js == f"state.{raw}" and raw in mapping:
        return mapping[raw]
    return None


def _static_bool(expr) -> bool | None:
    if not expr or expr.js is None:
        return None
    js = expr.js.strip()
    if js == "true":
        return True
    if js == "false":
        return False
    return None


def _static_raw(expr) -> str | None:
    if not expr or expr.js is None:
        return None
    js = expr.js.strip()
    if len(js) < 2 or js[0] not in {"'", '"'} or js[-1] != js[0]:
        return None
    try:
        value = ast.literal_eval(js)
    except (SyntaxError, ValueError):
        m = _QUOTED_RE.match(js)
        return m.group(1) if m else None
    return value if isinstance(value, str) else None


def _sanitize_static_html(content: str) -> str:
    """Preserve HtmlText presentation without carrying executable markup."""
    previous = None
    while previous != content:
        previous = content
        content = _UNSAFE_HTML_BLOCK_RE.sub("", content)
    content = _UNSAFE_HTML_TAG_RE.sub("", content)
    content = _EVENT_HANDLER_RE.sub("", content)
    content = _UNSAFE_URL_ATTR_RE.sub("", content)
    return _UNSAFE_HTML_ATTR_RE.sub("", content)


# ---- property mapping tables -------------------------------------------------

DIRECTION_MAP = {"Horizontal": "row", "Vertical": "column"}
ALIGN_MAP = {"Start": "flex-start", "Center": "center", "End": "flex-end",
             "Stretch": "stretch"}
JUSTIFY_MAP = {"Start": "flex-start", "Center": "center", "End": "flex-end",
               "SpaceBetween": "space-between"}
WRAP_MAP = {"Wrap": "wrap", "Single": "nowrap"}
SHADOW_MAP = {
    "None": "none", "SemiLight": "0 1px 3px rgba(0,0,0,.30)",
    "Light": "0 2px 4px rgba(0,0,0,.25)", "Regular": "0 3px 8px rgba(0,0,0,.30)",
    "Heavy": "0 6px 14px rgba(0,0,0,.34)", "Bold": "0 10px 24px rgba(0,0,0,.40)",
}
WEIGHT_MAP = {"Bold": "bold", "Semibold": "600", "Normal": "normal", "Lighter": "lighter",
              "Light": "300", "Regular": "400", "bold": "bold", "600": "600",
              "normal": "normal", "lighter": "lighter"}


def _font_stack(font: str) -> str:
    """Keep the requested Power Apps face with a platform-safe fallback."""
    if ',' in font:
        # Canvas enum values can already contain an ordered CSS fallback list.
        # Sanitizing the whole string as one face silently creates a bogus font.
        faces = [re.sub(r'[^\w .-]', '', face).strip() for face in font.split(',')]
        generic = {'serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui'}
        return ', '.join(face if face.lower() in generic else f"'{face}'" for face in faces if face) or 'system-ui'
    safe = re.sub(r"[^A-Za-z0-9 ._-]", "", font) or "system-ui"
    lower = safe.lower()
    if lower in {"georgia", "times new roman", "times"}:
        return f"'{safe}', Georgia, 'Times New Roman', serif"
    if lower in {"courier", "courier new", "consolas"}:
        return f"'{safe}', 'Courier New', monospace"
    return f"'{safe}', Arial, system-ui, sans-serif"

COSMETIC_PX = {
    "PaddingLeft": "padding-left", "PaddingRight": "padding-right",
    "PaddingTop": "padding-top", "PaddingBottom": "padding-bottom",
    "RadiusTopLeft": "border-top-left-radius", "RadiusTopRight": "border-top-right-radius",
    "RadiusBottomLeft": "border-bottom-left-radius", "RadiusBottomRight": "border-bottom-right-radius",
    "BorderThickness": "border-width", "LayoutGap": "gap",
    "LayoutMinWidth": "min-width", "LayoutMinHeight": "min-height",
}

HOVER_PROPS = {
    "HoverFill": ("background-color", "hover"),
    "HoverColor": ("color", "hover"),
    "HoverBorderColor": ("border-color", "hover"),
    "PressedFill": ("background-color", "active"),
    "DisabledFill": ("background-color", "disabled"),
    "DisabledColor": ("color", "disabled"),
    "DisabledBorderColor": ("border-color", "disabled"),
    "FocusedBorderColor": ("border-color", "focus-visible"),
    "FocusedFill": ("background-color", "focus-visible"),
}

BOOL_TEXT_PROPS = {
    "Italic": ("font-style", "italic"),
    "Underline": ("text-decoration-line", "underline"),
    "Strikethrough": ("text-decoration-line", "line-through"),
}

BORDER_STYLE_MAP = {
    "None": "none", "Solid": "solid", "Dashed": "dashed",
    "Dotted": "dotted", "Double": "double",
}

ACCESSIBILITY_ROLES = {
    "ButtonControl": "button", "LinkControl": "link", "HeadingControl": "heading",
    "ImageControl": "img", "TextBoxControl": "textbox", "GridControl": "grid",
    "ListControl": "list", "PresentationControl": "presentation",
    "ParagraphControl": "paragraph", "SeparatorControl": "separator",
}


def _is_flex_container(ctrl: ControlNode) -> bool:
    # Studio exports include LayoutDirection even when LayoutMode is Manual.
    mode = ctrl.properties.get("LayoutMode")
    if mode and mode.raw.strip() in {"LayoutMode.Manual", "LayoutMode.Auto"}:
        mark_emission(mode)
        return mode.raw.strip() == "LayoutMode.Auto"
    if ctrl.variant == "ManualLayout":
        return False
    expr = ctrl.properties.get("LayoutDirection")
    return bool(expr and expr.js)


def _static_style(ctrl: ControlNode, in_flex: bool, rules: list[str]) -> str:
    """Full static inline style: position/size, layout, cosmetics, colors."""
    props = ctrl.properties
    css: list[str] = []

    def px(name: str) -> str | None:
        value = _static_px(props.get(name))
        if value:
            mark_emission(props.get(name))
        return value

    def color(name: str) -> str | None:
        value = _static_color(props.get(name))
        if value:
            mark_emission(props.get(name))
        return value

    def pt(name: str) -> str | None:
        value = _static_pt(props.get(name))
        if value:
            mark_emission(props.get(name))
        return value

    def mapped(name: str, mapping: dict[str, str]) -> str | None:
        value = _static_map(props.get(name), mapping)
        if value:
            mark_emission(props.get(name))
        return value

    def boolean(name: str) -> bool | None:
        value = _static_bool(props.get(name))
        if value is not None:
            mark_emission(props.get(name))
        return value

    def raw(name: str) -> str | None:
        value = _static_raw(props.get(name))
        if value is not None:
            mark_emission(props.get(name))
        return value

    # --- position / size ----------------------------------------------------
    if in_flex:
        fp = props.get("FillPortions")
        if fp and fp.js and _NUM_RE.match(fp.js.strip()) and fp.js.strip() != "0":
            css.append(f"flex:{fp.js.strip()} 1 0%")
            mark_emission(fp)
        align = mapped("Align", ALIGN_MAP)
        if align:
            css.append(f"align-self:{align}")
    else:
        x, y = px("X"), px("Y")
        if x:
            css.append(f"left:{x}")
        if y:
            css.append(f"top:{y}")
        z = px("ZIndex")
        if z:
            css.append(f"z-index:{z[:-2]}")
    w, h = px("Width"), px("Height")
    if w:
        css.append(f"width:{w}")
    auto_h = boolean("AutoHeight")
    if h and auto_h is not True:
        css.append(f"height:{h}")
    elif auto_h is True:
        css.append("height:auto")

    # --- container layout ----------------------------------------------------
    if _is_flex_container(ctrl):
        css.append("display:flex")
        direction = mapped("LayoutDirection", DIRECTION_MAP)
        if direction:
            css.append(f"flex-direction:{direction}")
        align = mapped("LayoutAlignItems", ALIGN_MAP)
        if align:
            css.append(f"align-items:{align}")
        justify = mapped("LayoutJustifyContent", JUSTIFY_MAP)
        if justify:
            css.append(f"justify-content:{justify}")
        wrap = mapped("LayoutWrap", WRAP_MAP)
        if wrap:
            css.append(f"flex-wrap:{wrap}")
    for prop, css_prop in COSMETIC_PX.items():
        v = px(prop)
        if v:
            css.append(f"{css_prop}:{v}")
    # BorderColor is independent of the text color. Omitting it lets CSS use
    # currentColor and turns transparent Power Apps borders into dark boxes.
    border_width = px("BorderThickness")
    border_color = color("BorderColor")
    if border_color:
        css.append(f"border-color:{border_color}")

    # border style: explicit enum, else solid when thickness+color present
    border_style = mapped("BorderStyle", BORDER_STYLE_MAP)
    if border_style and border_width:
        css.append(f"border-style:{border_style}")
    elif border_width and border_color:
        css.append("border-style:solid")

    shadow = mapped("DropShadow", SHADOW_MAP)
    if shadow:
        css.append(f"box-shadow:{shadow}")

    # --- colors / typography --------------------------------------------------
    fill = color("Fill")
    if fill:
        css.append(f"background-color:{fill}")
    text_color = color("Color") or color("FontColor")
    if text_color:
        css.append(f"color:{text_color}")
    font = raw("Font")
    if font:
        css.append(f"font-family:{_font_stack(font)}")
    weight = mapped("FontWeight", WEIGHT_MAP) or px("FontWeight")
    if weight:
        css.append(f"font-weight:{weight}")
    size = pt("Size") or pt("FontSize")
    if size:
        css.append(f"font-size:{size}")
    for prop, (css_prop, css_val) in BOOL_TEXT_PROPS.items():
        if _static_bool(props.get(prop)) is True:
            mark_emission(props.get(prop))
            css.append(f"{css_prop}:{css_val}")
    line_height = props.get("LineHeight")
    if line_height and line_height.js and _NUM_RE.match(line_height.js.strip()):
        # Power Apps LineHeight is a multiplier (1.2), not a CSS pixel value.
        css.append(f"line-height:{line_height.js.strip()}")
        mark_emission(line_height)
    valign = mapped("VerticalAlign", {"Top": "flex-start", "Middle": "center", "Bottom": "flex-end"})
    if valign:
        css.append(f"display:flex;align-items:{valign}")
    vwrap = raw("LayoutOverflowX")
    if vwrap == "Overflow":
        css.append("overflow-x:auto")
    vwrap_y = raw("LayoutOverflowY")
    if vwrap_y == "Overflow":
        css.append("overflow-y:auto")
    overflow = mapped("Overflow", {"Overflow":"visible", "Hide":"hidden", "Hidden":"hidden",
                                   "Scroll":"auto", "Scrollbar":"auto"})
    if overflow:
        css.append(f"overflow:{overflow}")
    wrap = boolean("Wrap")
    if wrap is False:
        css.append("white-space:nowrap")
    elif wrap is True:
        css.append("white-space:normal")
    if ctrl.type == "Image":
        pos = mapped("ImagePosition",
                     {"Fit": "contain", "Fill": "cover", "Stretch": "fill", "Tile": "cover"})
        if pos:
            css.append(f"object-fit:{pos}")
        rot = _static_px(props.get("ImageRotation"))
        if rot:
            css.append(f"transform:rotate({rot})")
    text_align = mapped("Align", {
        "Center": "center", "Left": "left", "Start": "left",
        "Right": "right", "End": "right", "Justify": "justify",
    })
    if text_align and not in_flex:
        css.append(f"text-align:{text_align}")
        if valign:
            # VerticalAlign makes classic text controls flex containers; in
            # that layout text-align alone does not move the flex item.
            css.append(f"justify-content:{text_align}")

    # --- hover/pressed/disabled CSS rules --------------------------------------
    for prop, (css_prop, pseudo) in HOVER_PROPS.items():
        v = color(prop)
        if v:
            sel = f'[data-control="{ctrl.name}"]:{pseudo}'
            rules.append(f"{sel} {{ {css_prop}:{v}; }}")

    return ";".join(css)


def _static_text(ctrl: ControlNode) -> str:
    expr = ctrl.properties.get("Text")
    text = _static_raw(expr)
    if text is not None and ctrl.type in {"Button", "Label"}:
        mark_emission(expr)
        return html.escape(text)
    return ""


def _static_html(ctrl: ControlNode) -> str:
    if ctrl.type != "HtmlText":
        return ""
    expr = ctrl.properties.get("HtmlText") or ctrl.properties.get("Content")
    content = _static_raw(expr)
    if content is None:
        return ""
    mark_emission(
        expr,
        "approximated",
        "static HtmlText markup is rendered after executable tags and attributes are removed",
    )
    return _sanitize_static_html(content)


def _static_scalar(expr) -> str | None:
    """Return a safe-to-embed scalar value from translated literal JS."""
    if not expr or expr.js is None:
        return None
    raw = _static_raw(expr)
    if raw is not None:
        return raw
    js = expr.js.strip()
    if _NUM_RE.match(js) or js in {"true", "false"}:
        return js
    return None


def _input_attrs(ctrl: ControlNode) -> str:
    """Static input defaults used both at first paint and by Reset()."""
    if ctrl.type not in {"TextInput", "TextArea", "Dropdown", "ComboBox",
                          "CheckBox", "DatePicker", "FluentDatePicker", "Slider"}:
        return ""
    props = ctrl.properties
    out = ""
    default = _static_scalar(props.get("Default"))
    if default is not None:
        escaped = html.escape(default, quote=True)
        out += f' data-fx-default="{escaped}"'
        if ctrl.type == "CheckBox":
            if default == "true":
                out += " checked"
        elif ctrl.type not in {"Dropdown", "ComboBox"}:
            out += f' value="{escaped}"'
        mark_emission(
            props.get("Default"),
            "approximated" if ctrl.type == "TextArea" else "emitted",
            "textarea defaults are restored by Reset; non-empty first-paint text remains limited"
            if ctrl.type == "TextArea" else "",
        )
    placeholder = _static_scalar(props.get("HintText") or props.get("Placeholder"))
    if placeholder is not None and ctrl.type in {"TextInput", "TextArea"}:
        out += f' placeholder="{html.escape(placeholder, quote=True)}"'
        mark_emission(props.get("HintText") or props.get("Placeholder"))
    return out


def _static_extra_attrs(ctrl: ControlNode, media_resources: dict[str, str]) -> str:
    """Static src/title-style attributes for images and icons."""
    props = ctrl.properties
    out = ""
    if ctrl.type == "Image":
        src = _static_raw(props.get("Image"))
        if src:
            src = media_resources.get(src, src)
            out += f' src="{html.escape(src, quote=True)}"'
            mark_emission(props.get("Image"))
    if ctrl.type == "Icon":
        glyph_name = _static_raw(props.get("Icon"))
        if glyph_name:
            out += f' title="{html.escape(glyph_name, quote=True)}"'
            mark_emission(props.get("Icon"))
    return out


def _chart_config(ctrl: ControlNode) -> str:
    """JSON config for a chart control (type, columns) from its properties."""
    props = ctrl.properties
    ctype = CHART_TYPES.get(ctrl.type) or "bar"
    labels = _static_raw(props.get("ItemsLabels"))
    values = _static_raw(props.get("ItemsValues"))
    cfg: dict[str, object] = {"type": ctype}
    if labels:
        cfg["cat"] = _snake(labels)
        mark_emission(props.get("ItemsLabels"))
    if values:
        cfg["val"] = _snake(values)
        mark_emission(props.get("ItemsValues"))
    width = _static_px(props.get("Width"))
    height = _static_px(props.get("Height"))
    if width:
        cfg["width"] = int(float(width.replace("px", "")))
    if height:
        cfg["height"] = int(float(height.replace("px", "")))
    show_labels = _static_bool(props.get("ShowLabels"))
    if show_labels is not None:
        cfg["showLabels"] = show_labels
    foreground = _static_color(props.get("Color") or props.get("FontColor"))
    if foreground:
        cfg["foreground"] = foreground
    import json as _json
    return _json.dumps(cfg)


def _static_attrs(ctrl: ControlNode) -> str:
    """Accessibility attributes: Role -> ARIA role, AccessibleLabel/Tooltip -> aria-label."""
    props = ctrl.properties
    out = ""
    role = _static_raw(props.get("Role"))
    if role and role in ACCESSIBILITY_ROLES:
        out += f' role="{ACCESSIBILITY_ROLES[role]}"'
        mark_emission(props.get("Role"))
    label = _static_raw(props.get("AccessibleLabel")) or _static_raw(props.get("Tooltip"))
    if label:
        out += f' aria-label="{html.escape(label, quote=True)}"'
        mark_emission(props.get("AccessibleLabel") or props.get("Tooltip"))
    live = _static_raw(props.get("Live"))
    if live:
        out += f' aria-live="{live.lower()}"'
        mark_emission(props.get("Live"))
    # DisplayMode: static Disabled -> disabled/readonly attribute
    if _static_raw(props.get("DisplayMode")) == "Disabled":
        if ctrl.type in {"Button", "Icon", "Dropdown", "ComboBox",
                         "CheckBox", "DatePicker", "FluentDatePicker", "Slider"}:
            out += " disabled"
        elif ctrl.type in {"TextInput", "TextArea"}:
            out += " readonly"
        mark_emission(props.get("DisplayMode"))
    if ctrl.type in {"TextInput", "TextArea"}:
        max_len = _static_scalar(props.get("MaxLength"))
        if max_len:
            out += f' maxlength="{max_len}"'
            mark_emission(props.get("MaxLength"))
        if _static_bool(props.get("DelayOutput")) is True:
            out += ' data-delay-output="true"'
            mark_emission(props.get("DelayOutput"), "approximated",
                          "DelayOutput is retained as runtime metadata")
    tab_idx = _static_scalar(props.get("TabIndex"))
    if tab_idx in {"0", "1", "-1", "2"}:
        out += f' tabindex="{tab_idx}"'
        mark_emission(props.get("TabIndex"))
    if ctrl.type == "TextInput":
        vk = _static_raw(props.get("VirtualKeyboardMode"))
        if vk:
            out += f' inputmode="{"numeric" if "num" in vk.lower() else "text"}"'
            mark_emission(props.get("VirtualKeyboardMode"))
    if ctrl.type in {"ComboBox", "ListBox"} and _static_bool(props.get("SelectMultiple")) is True:
        out += " multiple"
        mark_emission(props.get("SelectMultiple"))
    return out


def _gallery_row_controls(ctrl: ControlNode) -> list[ControlNode]:
    """Flatten structural GalleryTemplate nodes into one rendered row."""
    controls: list[ControlNode] = []
    for child in ctrl.children:
        if child.type == "GalleryTemplate":
            controls.extend(child.children)
        else:
            controls.append(child)
    return controls


def _render_control(
    ctrl: ControlNode,
    depth: int,
    in_flex: bool,
    rules: list[str],
    media_resources: dict[str, str],
) -> str:
    tag = ELEMENT_MAP.get(ctrl.type, "div")
    input_mode = _static_raw(ctrl.properties.get('Mode')) if ctrl.type in {'TextInput', 'TextArea'} else None
    if input_mode in {'SingleLine', 'MultiLine', 'Password'}:
        tag = 'textarea' if input_mode == 'MultiLine' else 'input'
    indent = "  " * (depth + 1)
    style = _static_style(ctrl, in_flex, rules)
    style_attr = f' style="{style}"' if style else ""
    if ctrl.primary_output:
        style_attr += f' data-fx-primary-output="{html.escape(_snake(ctrl.primary_output), quote=True)}"'
    flex = _is_flex_container(ctrl)
    extra = ""
    if ctrl.type in {"TextInput", "TextArea"}:
        extra = ' type="password"' if input_mode == 'Password' else ' type="text"' if tag == 'input' else ''
    elif ctrl.type == "CheckBox":
        extra = ' type="checkbox"'
    elif ctrl.type in {"DatePicker", "FluentDatePicker"}:
        extra = ' type="date"'
        if ctrl.type == 'FluentDatePicker':
            extra += ' data-fx-date-value="local"'
    elif ctrl.type == "Slider":
        extra = ' type="range"'
    if ctrl.type == "CanvasComponent":
        template = html.escape(ctrl.component_template or "unknown", quote=True)
        extra += f' class="fx-component" data-component-template="{template}"'
    elif ctrl.type == "GroupContainer" and not flex:
        extra += ' class="fx-manual-container"'
    elif ctrl.type == "Image":
        extra += ' class="fx-image"'
    elif ctrl.type == "Form":
        extra += ' class="fx-form fx-card-layout"'
    elif ctrl.type == "FluidGrid":
        extra += ' class="fx-card-layout"'
    elif ctrl.type == "DataCard":
        extra += ' class="fx-data-card"'

    # --- icon rendering -----------------------------------------------------
    # Power Apps stores icon *names* ('customer-service', 'Icon.Filter') in
    # Image/Icon properties. A bare name is not a URL: render the mapped
    # Unicode glyph (Segoe MDL2) instead of a broken <img> / empty <span>.
    if ctrl.type == "Image":
        src = _static_raw(ctrl.properties.get("Image"))
        if src and src not in media_resources and is_icon_name(src):
            mark_emission(ctrl.properties.get("Image"), "approximated",
                          "Power Apps icon name mapped to a Unicode glyph")
            return (f'{indent}<span data-control="{ctrl.name}"{style_attr}'
                    f' class="fx-icon" title="{src}" data-icon-name="{src}"'
                    f'{_static_attrs(ctrl)}>{icon_glyph(src)}</span>')
    if ctrl.type == "Icon":
        glyph_name = _static_raw(ctrl.properties.get("Icon"))
        glyph = icon_glyph(glyph_name) if glyph_name else None
        if glyph:
            mark_emission(ctrl.properties.get("Icon"), "approximated",
                          "Power Apps icon mapped to a Unicode glyph")
            return (f'{indent}<span data-control="{ctrl.name}"{style_attr}'
                    f' class="fx-icon" title="{glyph_name}" data-icon-name="{glyph_name}"'
                    f'{_static_attrs(ctrl)}>{glyph}</span>')

    if ctrl.type == "Gallery" or ctrl.type == "GalleryTemplate":
        row_controls = _gallery_row_controls(ctrl)
        inner_row = "\n".join(
            _render_control(c, depth + 2, flex, rules, media_resources)
            for c in row_controls
        )
        row_size = _static_scalar(ctrl.properties.get("TemplateSize"))
        row_padding = _static_scalar(ctrl.properties.get("TemplatePadding"))
        wrap_count = _static_scalar(ctrl.properties.get("WrapCount"))
        orientation = (_static_raw(ctrl.properties.get("Layout")) or '').lower()
        gallery_attrs = ""
        if orientation in {"horizontal", "vertical"}:
            gallery_attrs += f' data-gallery-layout="{orientation}"'
            mark_emission(ctrl.properties.get("Layout"), "approximated",
                          "gallery preserves its static orientation; dynamic orientation requires review")
        if row_size:
            gallery_attrs += f' data-template-size="{html.escape(row_size, quote=True)}"'
            mark_emission(ctrl.properties.get("TemplateSize"), "approximated",
                          "gallery template extent follows TemplateSize in its source orientation")
        if row_padding:
            gallery_attrs += f' data-template-padding="{html.escape(row_padding, quote=True)}"'
            mark_emission(ctrl.properties.get("TemplatePadding"), "approximated",
                          "gallery row padding follows TemplatePadding")
        if wrap_count:
            gallery_attrs += f' data-wrap-count="{html.escape(wrap_count, quote=True)}"'
            mark_emission(ctrl.properties.get("WrapCount"), "approximated",
                          "gallery wrap count is retained as runtime metadata")
        return (
            f'{indent}<div data-control="{ctrl.name}"{style_attr}{gallery_attrs} class="fx-gallery">\n'
            f'{indent}  <div class="fx-rows"></div>\n'
            f'{indent}  <template>\n'
            f'{indent}    <div class="fx-row">\n{inner_row}\n{indent}    </div>\n'
            f'{indent}  </template>\n'
            f'{indent}</div>'
        )

    if ctrl.type in CHART_TYPES:
        cfg = _chart_config(ctrl).replace("&", "&amp;").replace('"', "&quot;")
        return (f'{indent}<div data-control="{ctrl.name}"{style_attr} '
                f'data-chart="{cfg}" class="fx-chart"></div>')

    if ctrl.type in EXPLICITLY_UNSUPPORTED_INPUTS:
        control_type = html.escape(ctrl.type, quote=True)
        return (
            f'{indent}<div data-control="{ctrl.name}"{style_attr} '
            f'class="fx-unsupported-control" data-unsupported-control="{control_type}" '
            f'role="status">Unsupported input: {control_type}</div>'
        )

    inner = ""
    close = f"</{tag}>" if tag not in {"input", "img", "br", "hr"} else ""
    if ctrl.children and ctrl.type not in VOID_CONTENT_TYPES:
        child_html = "\n".join(
            _render_control(c, depth + 1, flex, rules, media_resources)
            for c in ctrl.children
        )
        inner = "\n" + child_html + "\n" + indent
    attrs = _static_extra_attrs(ctrl, media_resources) + _static_attrs(ctrl) + _input_attrs(ctrl)
    content = _static_html(ctrl) if ctrl.type == "HtmlText" else _static_text(ctrl)
    return f'{indent}<{tag} data-control="{ctrl.name}"{style_attr}{attrs}{extra}>{content}{inner}{close}'


def render_screens_html(ir: AppIR) -> str:
    rules: list[str] = []
    parts = []
    for screen in ir.screens:
        # Every screen starts hidden; the runtime reveals ir.start_screen at
        # bootstrap (Power Apps shows the first screen in screen order).
        parts.append(f'  <section data-screen="{screen.name}" style="display:none">')
        for ctrl in screen.controls:
            parts.append(_render_control(ctrl, 1, False, rules, ir.media_resources))
        parts.append("  </section>")
    style_block = ""
    if rules:
        style_block = "  <style>\n    " + "\n    ".join(rules) + "\n  </style>\n"
    return style_block + "\n".join(parts)


def _control_parents(ir: AppIR) -> dict[str, str]:
    parents: dict[str, str] = {}

    def visit(ctrl: ControlNode, parent_name: str) -> None:
        parents[ctrl.name] = parent_name
        for child in ctrl.children:
            visit(child, parent_name if ctrl.type == "GalleryTemplate" else ctrl.name)

    for screen in ir.screens:
        for ctrl in screen.controls:
            visit(ctrl, screen.name)
    return parents


def _referenced_control_properties(ir: AppIR, parents: dict[str, str]) -> dict[str, set[str]]:
    """Properties that must be readable through val() by another formula."""
    controls = {ctrl.name for screen in ir.screens for ctrl in screen.walk_controls()}
    referenced: dict[str, set[str]] = {}
    for screen in ir.screens:
        for owner in screen.walk_controls():
            for expr in owner.properties.values():
                for base, prop in re.findall(
                    r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
                    expr.raw,
                ):
                    if base == 'Self':
                        referenced.setdefault(owner.name, set()).add(prop)
                    elif base == "Parent" and owner.name in parents:
                        referenced.setdefault(parents[owner.name], set()).add(prop)
                    elif base in controls:
                        referenced.setdefault(base, set()).add(prop)
    return referenced


FORM_INPUT_TYPES = {
    "TextInput", "TextArea", "Dropdown", "ComboBox", "ListBox",
    "CheckBox", "DatePicker", "FluentDatePicker", "Slider",
}


def _descendants(ctrl: ControlNode):
    for child in ctrl.children:
        yield child
        yield from _descendants(child)


def _form_source_name(ctrl: ControlNode) -> str | None:
    expr = ctrl.properties.get("DataSource")
    if not expr:
        return None
    raw = expr.raw.strip()
    if raw.startswith("[@") and raw.endswith("]"):
        raw = raw[2:-1]
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        raw = raw[1:-1]
    return raw if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ ]*", raw) else None


def _card_input(card: ControlNode) -> ControlNode | None:
    """Find the input whose value the DataCard Update formula submits."""
    update = card.properties.get("Update")
    if update:
        names = {child.name: child for child in _descendants(card)}
        for name in re.findall(
            r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\."
            r"(?:Text|Value|Selected|SelectedItems|SelectedDate|Checked)\b",
            update.raw,
        ):
            if name in names and names[name].type in FORM_INPUT_TYPES:
                return names[name]
    return next((child for child in _descendants(card)
                 if child.type in FORM_INPUT_TYPES), None)


def _fallback_input_value(input_ctrl: ControlNode) -> str:
    prop = {
        "CheckBox": "checked",
        "DatePicker": "selected_date",
        "FluentDatePicker": "value",
        "Dropdown": "selected",
        "ComboBox": "selected",
        "ListBox": "selected",
    }.get(input_ctrl.type, "text")
    return f"val({input_ctrl.name!r}).{prop}"


def _emit_form_registration(lines: list[str], form: ControlNode) -> bool:
    """Wire a Power Apps Form/DataCard tree into the deterministic runtime."""
    source = _form_source_name(form)
    cards: list[tuple[ControlNode, ControlNode, str]] = []
    for card in _descendants(form):
        if card.type != "DataCard":
            continue
        field = _static_raw(card.properties.get("DataField"))
        input_ctrl = _card_input(card)
        if field and input_ctrl:
            cards.append((card, input_ctrl, _snake(field)))
    if not source or not cards:
        return False

    lines.append(f"  // {form.name} (Form/DataCard submit contract)")
    lines.append(f"  FXRuntime.registerForm({form.name!r}, {{")
    lines.append(f"    dataSource: {source!r},")
    source_expr = form.properties.get("DataSource")
    mark_emission(source_expr, "emitted", "mapped to the generated Google Sheets data source")
    mode = form.properties.get("DefaultMode")
    if mode and mode.js:
        lines.append(f"    defaultMode: function () {{ return {mode.js}; }},")
        mark_emission(mode)
    else:
        lines.append("    defaultMode: function () { return 'edit'; },")
    item = form.properties.get("Item")
    if item and item.js:
        lines.append(f"    item: function () {{ return {item.js}; }},")
        mark_emission(item)
    else:
        lines.append("    item: function () { return null; },")
    lines.append("    cards: [")
    for card, input_ctrl, field in cards:
        display = _static_raw(card.properties.get("DisplayName")) or field
        required = card.properties.get("Required")
        update = card.properties.get("Update")
        lines.append("      {")
        lines.append(f"        name: {card.name!r}, field: {field!r}, input: {input_ctrl.name!r},")
        lines.append(f"        inputType: {input_ctrl.type!r}, displayName: {display!r},")
        if required and required.js:
            lines.append(f"        required: function () {{ return {required.js}; }},")
            mark_emission(required)
        else:
            lines.append("        required: function () { return false; },")
        if update and update.js:
            lines.append(f"        update: function () {{ return {update.js}; }},")
            mark_emission(update)
        else:
            lines.append(
                f"        update: function () {{ return {_fallback_input_value(input_ctrl)}; }},"
            )
        lines.append("      },")
        mark_emission(card.properties.get("DataField"))
        if card.properties.get("DisplayName"):
            mark_emission(card.properties.get("DisplayName"))
        if card.properties.get("Default"):
            mark_emission(
                card.properties.get("Default"), "approximated",
                "DataCard default is derived from the current Form.Item field",
            )
    lines.append("    ],")
    for prop_name, config_name in (("OnSuccess", "onSuccess"), ("OnFailure", "onFailure")):
        expr = form.properties.get(prop_name)
        if expr and expr.raw:
            lines.append(f"    {config_name}: async function () {{")
            for stmt in _behavior_js(expr, f"{form.name}.{prop_name}").splitlines():
                lines.append(f"      {stmt}")
            lines.append("    },")
            mark_emission(expr)
    lines.append("  });")
    return True


def _row_descendants(ctrl: ControlNode):
    """Visit controls owned by this row, stopping at nested gallery templates."""
    def visit(child):
        yield child
        if child.type != 'Gallery':
            for descendant in child.children:
                yield from visit(descendant)
    for child in _gallery_row_controls(ctrl):
        yield from visit(child)


def _emit_gallery(lines: list[str], ctrl: ControlNode, parent_names: dict[str, str], referenced_props: dict[str, set[str]], nested: bool = False):
    items = ctrl.properties.get("Items")
    if items and items.js:
        mark_emission(items)
        row_fns = []
        handlers = {}
        gallery_select = ctrl.properties.get("OnSelect")
        # Legacy exports store row selection on the structural
        # GalleryTemplate. Its DOM wrapper is flattened, but its
        # action must survive Select(Parent) from a row child.
        selection_owner = ctrl
        if not gallery_select or not gallery_select.raw:
            templates = [child for child in ctrl.children if child.type == "GalleryTemplate"]
            if len(templates) == 1:
                selection_owner = templates[0]
                gallery_select = selection_owner.properties.get("OnSelect")
        if gallery_select and gallery_select.raw:
            handlers[ctrl.name] = (parent_names.get(selection_owner.name), {"OnSelect": _behavior_js(gallery_select, f"{selection_owner.name}.OnSelect")})
            mark_emission(gallery_select)
        row_controls = list(_row_descendants(ctrl))
        referenced_expressions = []
        # Register all row-owned property definitions before any visual formula
        # reads Self/another row control, including later siblings.
        for child in row_controls:
            registered = [(prop, expr) for prop, expr in child.properties.items()
                          if prop in referenced_props.get(child.name, set()) and expr.js
                          and 'await ' not in expr.js
                          and not (child.type == 'FluentDatePicker' and prop == 'Value')]
            if registered:
                row_fns.append(f'        FXRuntime.registerRowProps(row, {child.name!r}, {parent_names.get(child.name)!r}, {{')
                for prop, expr in registered:
                    row_fns.append(f'          {_snake(prop)!r}: function (val, selfRef, parentRef) {{ return {expr.js}; }},')
                    referenced_expressions.append(expr)
                row_fns.append('        });')
        for child in row_controls:
            if child.type == 'Gallery':
                nested_lines=[]
                _emit_gallery(nested_lines, child, parent_names, referenced_props, nested=True)
            else:
                nested_lines=[]
            texpr = child.properties.get("Text")
            row_properties: list[tuple[str, object]] = []
            if texpr and texpr.js and _static_raw(texpr) is None:
                row_properties.append(("text", texpr))
            row_inputs = [('TemplateSize','templateSize')] if child.type == 'Gallery' else []
            if child.type in {"Dropdown", "ComboBox", "ListBox"}:
                display_property = "Value" if child.type == "Dropdown" and "Value" in child.properties else "DisplayFields"
                row_inputs.extend([(display_property, "displayFields"), ("Items", "items"),
                                   ("DefaultSelectedItems", "default")])
            if child.type in {"TextInput", "TextArea", "Dropdown", "ComboBox", "ListBox",
                              "CheckBox", "DatePicker", "FluentDatePicker", "Slider"}:
                if "DefaultSelectedItems" not in child.properties:
                    default_prop = 'Value' if child.type == 'FluentDatePicker' else 'DefaultDate' if child.type == 'DatePicker' else 'Default'
                    row_inputs.append((default_prop, "default"))
                row_inputs.extend([("DisplayMode", "disabled"), ("Reset", "reset")])
            if child.type == 'FluentDatePicker':
                row_inputs.append(('AcceptsFocus', 'acceptsFocus'))
                row_inputs.extend([('AccessibleLabel', 'ariaLabel'), ('Tooltip', 'title')])
            if child.type == "Image":
                row_inputs.append(("Image", "src"))
            if child.type in {'TextInput', 'TextArea'}:
                row_inputs.insert(0, ('Mode', 'mode'))
            for prop_name, runtime_key in row_inputs:
                prop_expr = child.properties.get(prop_name)
                if prop_expr and prop_expr.js and "await " not in prop_expr.js:
                    # Static image assets/icons are resolved by the HTML renderer.
                    if runtime_key == "src" and _static_raw(prop_expr) is not None:
                        continue
                    row_properties.append((runtime_key, prop_expr))
            row_reactive = [
                ("X", "left"), ("Y", "top"),
                ("Width", "width"), ("Height", "height"),
                ("Fill", "backgroundColor"), ("Color", "color"),
                ("FontColor", "color"), ("Size", "fontSize"),
                ("FontSize", "fontSize"), ("Visible", "display"),
            ]
            for prop_name, runtime_key in row_reactive:
                prop_expr = child.properties.get(prop_name)
                if not prop_expr or not prop_expr.js:
                    continue
                if prop_name in {"Fill", "Color", "FontColor"} \
                        and _static_color(prop_expr) is not None:
                    continue
                if prop_name in {"X", "Y", "Width", "Height", "Size", "FontSize"} \
                        and _static_px(prop_expr) is not None:
                    continue
                if prop_expr.js.startswith("'"):
                    continue
                row_properties.append((runtime_key, prop_expr))
            if row_properties:
                row_fns.append(
                    f"        FXRuntime.rowControl(row, {child.name!r}, {parent_names.get(child.name)!r}, {{"
                )
                for runtime_key, prop_expr in row_properties:
                    row_fns.append(
                        f"          {runtime_key!r}: function (val, selfRef, parentRef) {{ return {prop_expr.js}; }},"
                    )
                    mark_emission(
                        prop_expr,
                        "approximated" if runtime_key in {"display", "src"} else "emitted",
                        "gallery-row formula is evaluated in ThisItem/Self/Parent context",
                    )
                row_fns.append("        });")
            row_fns.extend('      '+line for line in nested_lines)
            if child.type == 'Gallery':
                continue  # Its events belong to its own selected child row.
            events = {}
            for event in (("OnSelect", "OnChange", "OnCheck", "OnUncheck") if child.type == 'CheckBox' else ("OnSelect", "OnChange")):
                expr = child.properties.get(event)
                if expr and expr.raw:
                    events[event] = _behavior_js(expr, f"{child.name}.{event}")
                    mark_emission(expr)
            if events:
                handlers[child.name] = (parent_names.get(child.name), events)
        lines.append(f"  // {ctrl.name}.Items (gallery)")
        lines.append("  FXRuntime.rowGallery(" if nested else "  FXRuntime.gallery(")
        if nested:
            lines.append("    row,")
        lines.append(f"    {ctrl.name!r},")
        read = "var val = function (name) { return FXRuntime.rowValue(row, name); }; " if nested else ""
        lines.append(f"    function () {{ {read}var selfRef = val({ctrl.name!r}), parentRef = val({parent_names.get(ctrl.name)!r}); return {items.js}; }},")
        lines.append("    function (item, row) {")
        for rf in row_fns:
            lines.append(rf)
        lines.append("    },")
        if handlers:
            lines.append("    {")
            for cname, (parent, events) in handlers.items():
                lines.append(f"      {cname!r}: {{ parent: {parent!r},")
                for event, js in events.items():
                    lines.append(f"        {event!r}: async function (item, row, selectControl, checkedValue) {{")
                    lines.append("          var val = function (name) { return FXRuntime.rowValue(row, name); };")
                    lines.append(f"          var selfRef = val({cname!r}), parentRef = val({parent!r});")
                    if event in {'OnCheck', 'OnUncheck'}:
                        lines.append("          selfRef.value = selfRef.checked = checkedValue;")
                    lines.append(f"          var resetControl = function (name) {{ return FXRuntime.resetRowControl(row, name === 'Self' ? {cname!r} : name === 'Parent' ? {parent!r} : name); }};")
                    for stmt in js.splitlines():
                        lines.append(f"          {stmt}")
                    lines.append("        },")
                lines.append("      },")
            lines.append("    },")
        else:
            lines.append("    null,")
        lines.append("    " + json.dumps({child.name: _snake(child.name) for child in row_controls}) + ",")
        lines.append("    {")
        default=ctrl.properties.get('Default')
        if default and default.js and 'await ' not in default.js:
            lines.append(f"      Default: function () {{ {read}var selfRef=val({ctrl.name!r}), parentRef=val({parent_names.get(ctrl.name)!r}); return {default.js}; }},")
            mark_emission(default, 'approximated', 'gallery default selects its matching loaded row; otherwise the first loaded row is selected')
        lines.append("    }")
        lines.append("  );")
        for expr in referenced_expressions:
            # A readable property does not make an approximated UI/layout
            # adapter exact. Let actual rendering classify it first.
            if expr.emission_status in {'pending', 'ignored'}:
                mark_emission(expr, 'emitted', 'exposed to dependent formulas in its owning gallery row')


def render_app_js(ir: AppIR) -> str:
    from ..data_contract import external_tables
    from ..services import service_contracts
    import json
    lines = [
        "// App.js — generated by pfx2gas; transpiled Power Fx lives here.",
        "APP_MAIN = async function () {",
    ]
    parent_names = _control_parents(ir)
    referenced_props = _referenced_control_properties(ir, parent_names)
    contexts = {screen.name: screen.context_vars for screen in ir.screens}
    lines.append(f"  FXRuntime.configureContexts({json.dumps(contexts)});")
    lines.append('  FXRuntime.configureServices(' + json.dumps(service_contracts(ir)).replace('<', '\\u003c') + ');')
    lines.append(f"  FXRuntime.configureCanvas({json.dumps(ir.layout)}, {{")
    def canvas_properties(properties, supported):
        for name in supported:
            expr = properties.get(name)
            if not expr or not expr.raw:
                continue
            js = expr.js if expr.js and "await " not in expr.js else (
                f"FX.unsupported({json.dumps('canvas property ' + name)})")
            lines.append(f"    {_snake(name)!r}: function (val, selfRef, parentRef) {{ return {js}; }},")
            mark_emission(expr, "emitted" if expr.js and "await " not in expr.js else "unsupported")
    canvas_properties(ir.properties, ("MinScreenWidth", "MinScreenHeight", "SizeBreakpoints"))
    lines.append("  }, {")
    for screen in ir.screens:
        lines.append(f"  {screen.name!r}: {{")
        canvas_properties(screen.properties, ("Width", "Height", "Size", "Orientation", "Fill"))
        lines.append("  },")
    lines.append("  });")
    row_scoped = {"Gallery", "DataTable"}
    gallery_children = {c.name for s in ir.screens for ctrl in s.walk_controls()
                        if ctrl.type in row_scoped
                        for child in ctrl.children for c in child.walk()}
    # Register lazy template formulas before OnStart or any dependent layout.
    # In particular Height can read Self.TemplateHeight before Items exists.
    for screen in ir.screens:
        for ctrl in screen.walk_controls():
            if ctrl.type != "Gallery" or ctrl.name in gallery_children:
                continue
            expr = ctrl.properties.get("TemplateSize")
            if expr and expr.js and "await " not in expr.js and not re.search(r"\bitem\b", expr.js):
                lines.append(f"  FXRuntime.registerGalleryTemplate({ctrl.name!r}, {parent_names.get(ctrl.name)!r}, "
                             f"function (val, selfRef, parentRef) {{ return {expr.js}; }});")
                mark_emission(expr, "approximated", "gallery TemplateSize formula updates template extent with state and viewport changes")
    # Collections are client-side state; declare them as empty arrays instead
    # of refreshing them from the server.
    for ds in ir.data_sources:
        if ds.origin == "collection":
            lines.append(f"  state[{ds.name!r}] = [];")
        elif ds.origin == "option_set":
            values = {_snake(option["name"]): option["value"] for option in ds.option_values}
            for name in dict.fromkeys([ds.name, *ds.aliases]):
                lines.append(f"  state[{name!r}] = {json.dumps(values)};")
    collection_contracts = {ds.name: {'aliases':ds.metadata.get('columnAliases', {}),
                            'error':ds.metadata.get('collectionContractError')}
                           for ds in ir.data_sources if ds.origin == 'collection'
                           and ds.metadata.get('columnAliases')}
    if collection_contracts:
        lines.append('  FX.collections.configureContracts(state, ' + json.dumps(collection_contracts).replace('<', '\\u003c') + ');')
    external_sources = [ds.name for ds in external_tables(ir.data_sources)]
    if external_sources:
        from ..relationships import relationship_contracts
        lines.append('  FXRuntime.configureRelationships(' + json.dumps(relationship_contracts(ir)).replace('<', '\\u003c') + ');')
        calls = ", ".join(f"refreshData({name!r})" for name in external_sources)
        lines.append("  // Load external data before formulas/evaluators consume it.")
        lines.append(f"  await Promise.all([{calls}]);")
    if ir.on_start and ir.on_start.raw:
        lines.append("  // OnStart (transpiled from Power Fx)")
        for stmt in _behavior_js(ir.on_start, "App.OnStart").splitlines():
            lines.append(f"  {stmt}")
        mark_emission(ir.on_start)
    lines.append("  var __INITIAL_STATE_ONLY = null;")
    lines.append("")

    registered_forms: set[str] = set()
    for screen in ir.screens:
        for ctrl in screen.walk_controls():
            if ctrl.type == "Form" and _emit_form_registration(lines, ctrl):
                registered_forms.add(ctrl.name)

    for screen in ir.screens:
        for event, expr, helper in (
            ("OnVisible", screen.on_visible, "registerScreenHandler"),
            ("OnHidden", screen.properties.get("OnHidden"), "registerScreenHiddenHandler"),
        ):
            if not expr or not expr.raw:
                continue
            lines.append(f"  FXRuntime.{helper}({screen.name!r}, async function (val, selfRef, parentRef) {{")
            for stmt in _behavior_js(expr, f"{screen.name}.{event}").splitlines():
                lines.append(f"    {stmt}")
            lines.append("  });")
            mark_emission(expr)

    for screen in ir.screens:
        # Row-scoped container children (gallery rows, data-table rows) are
        # rendered per-row with `item` bound by their container's runtime;
        # registering them at top level produces "control not found" and
        # "item is not defined". Descendants only — the container itself must
        # still emit its own registration.
        form_children = {child.name for form in screen.walk_controls() if form.type == "Form"
                         for child in _descendants(form)}
        for ctrl in screen.walk_controls():
            if ctrl.name in gallery_children:
                continue
            if ctrl.type in {"TextInput", "TextArea", "CheckBox", "DatePicker", "FluentDatePicker", "Slider", "Button"}:
                inputs = [("DisplayMode", "disabled"), ("Reset", "reset")]
                # Form/DataCard record application already owns their defaults.
                # Standalone inputs need the same reactive default contract as
                # gallery rows, including defaults populated by LoadData.
                if ctrl.name not in form_children and ctrl.type != "Button":
                    default_prop = 'Value' if ctrl.type == 'FluentDatePicker' else 'DefaultDate' if ctrl.type == 'DatePicker' else 'Default'
                    inputs.insert(0, (default_prop, "default"))
                if ctrl.type == 'FluentDatePicker':
                    inputs.append(('AcceptsFocus', 'acceptsFocus'))
                    inputs.extend([('AccessibleLabel', 'ariaLabel'), ('Tooltip', 'title')])
                if ctrl.type in {'TextInput', 'TextArea'}:
                    inputs.insert(0, ('Mode', 'mode'))
                properties = [(key, ctrl.properties[prop]) for prop, key in inputs
                              if prop in ctrl.properties and ctrl.properties[prop].js
                              and "await " not in ctrl.properties[prop].js]
                if properties:
                    lines.append(f"  FXRuntime.inputControl({ctrl.name!r}, {parent_names.get(ctrl.name)!r}, {{")
                    for key, expr in properties:
                        lines.append(f"    {key!r}: function (val, selfRef, parentRef) {{ return {expr.js}; }},")
                        mark_emission(expr)
                    lines.append("  });")
            wanted_props = set(referenced_props.get(ctrl.name, set()))
            wanted_props.update(ctrl.component_inputs)
            if wanted_props:
                registered = []
                for prop_name in ctrl.properties:
                    if ctrl.type == 'FluentDatePicker' and prop_name == 'Value':
                        continue  # Value reads the user's current date, not its initial formula.
                    if prop_name not in wanted_props:
                        continue
                    expr = ctrl.properties.get(prop_name)
                    if (expr and expr.js and "await " not in expr.js
                            and not re.search(r"\bitem\b", expr.js)):
                        registered.append((prop_name, expr))
                if registered:
                    lines.append(f"  // {ctrl.name} properties consumed by dependent controls")
                    lines.append(
                        f"  FXRuntime.registerControlProps({ctrl.name!r}, "
                        f"{parent_names.get(ctrl.name)!r}, {{"
                    )
                    for prop_name, expr in registered:
                        lines.append(f"    {_snake(prop_name)!r}: function () {{ return {expr.js}; }},")
                        if prop_name in ctrl.component_inputs:
                            mark_emission(
                                expr,
                                "approximated",
                                f"input is wired into emulated {ctrl.component_template} component children",
                            )
                        else:
                            mark_emission(expr, "emitted", "exposed to dependent control formulas")
                    lines.append("  });")
            for event in (("OnSelect", "OnChange", "OnCheck", "OnUncheck") if ctrl.type == 'CheckBox' else ("OnSelect", "OnChange")):
                if ctrl.type == "Gallery":
                    continue  # Invoked with the selected row, never by DOM bubbling.
                expr = ctrl.properties.get(event)
                if expr and expr.raw:
                    lines.append(f"  // {ctrl.name}.{event}")
                    lines.append(f"  bind({ctrl.name!r}, {event!r}, async function (val, selfRef, parentRef) {{")
                    for stmt in _behavior_js(expr, f"{ctrl.name}.{event}").splitlines():
                        lines.append(f"    {stmt}")
                    lines.append(f"  }}, {parent_names.get(ctrl.name)!r});")
                    form_refs = re.findall(
                        r"\b(?:SubmitForm|ResetForm)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)",
                        expr.raw,
                    )
                    missing_forms = sorted(set(form_refs) - registered_forms)
                    if missing_forms:
                        expr.emission_status = "unsupported"
                        expr.fidelity_note = (
                            "form action has no generated DataSource/DataCard contract: "
                            + ", ".join(missing_forms)
                        )
                    else:
                        mark_emission(expr)

            if ctrl.type == "Timer":
                lines.append(f"  FXRuntime.registerTimer({ctrl.name!r}, {screen.name!r}, {{")
                for prop_name in ("Duration", "Start", "AutoStart", "AutoPause", "Repeat", "Reset"):
                    expr = ctrl.properties.get(prop_name)
                    if expr and expr.js and "await " not in expr.js:
                        lines.append(f"    {prop_name!r}: function () {{")
                        lines.append(f"      var selfRef = val({ctrl.name!r}), parentRef = val({parent_names.get(ctrl.name)!r});")
                        lines.append(f"      return {expr.js};")
                        lines.append("    },")
                        mark_emission(expr)
                for event in ("OnTimerStart", "OnTimerEnd"):
                    expr = ctrl.properties.get(event)
                    if expr and expr.raw:
                        lines.append(f"    {event!r}: async function () {{")
                        lines.append(f"      var selfRef = val({ctrl.name!r}), parentRef = val({parent_names.get(ctrl.name)!r});")
                        lines.append(f"      var resetControl = function (target) {{ return FXRuntime.resetControl(target === 'Self' ? {ctrl.name!r} : target); }};")
                        for stmt in _behavior_js(expr, f"{ctrl.name}.{event}").splitlines():
                            lines.append(f"      {stmt}")
                        lines.append("    },")
                        mark_emission(expr)
                lines.append("  });")

            if ctrl.type == "Gallery":
                _emit_gallery(lines, ctrl, parent_names, referenced_props)

            # --- chart rendering ------------------------------------------
            if ctrl.type in CHART_TYPES:
                items = ctrl.properties.get("Items")
                if items and items.js:
                    mark_emission(items, "approximated",
                                  "chart data is rendered by the generated SVG chart runtime")
                    lines.append(f"  // {ctrl.name} (chart)")
                    lines.append("  FXRuntime.addEvaluator(async function () {")
                    lines.append(f'    var el = FXRuntime.controlElement({ctrl.name!r});')
                    lines.append("    if (!el) return;")
                    lines.append("    var cfg = JSON.parse(el.getAttribute('data-chart') || '{}');")
                    lines.append(f"    var selfRef = val({ctrl.name!r}), parentRef = val({parent_names.get(ctrl.name)!r});")
                    for prop, key in [("ShowLabels", "showLabels"), ("ItemColorSet", "colors"),
                                      ("Width", "width"), ("Height", "height"),
                                      ("Color", "foreground"), ("FontColor", "foreground")]:
                        expr = ctrl.properties.get(prop)
                        if expr and expr.js:
                            lines.append(f"    cfg.{key} = {expr.js};")
                            mark_emission(expr)
                    lines.append(f"    var rows = {items.js};")
                    lines.append("    if (rows && rows.then) rows = await rows;")
                    lines.append(f"    FXRuntime.renderChart({ctrl.name!r}, rows || [], cfg);")
                    lines.append("  });")

            # --- dropdown/combobox Items -> <option> population -------------
            if ctrl.type in {"Dropdown", "ComboBox", "ListBox"}:
                items_expr = ctrl.properties.get("Items")
                if items_expr and items_expr.js:
                    mark_emission(items_expr)
                    display_expr = ((ctrl.properties.get("Value") if ctrl.type == "Dropdown" else None)
                                    or ctrl.properties.get("DisplayFields")
                                    or ctrl.properties.get("SearchFields"))
                    default_selected = ctrl.properties.get("DefaultSelectedItems")
                    reset_expr = ctrl.properties.get("Reset")
                    needs_async = any(expr and expr.js and "await " in expr.js
                                      for expr in (items_expr, display_expr, default_selected, reset_expr))
                    fn_head = "async function () {" if needs_async else "function () {"
                    lines.append(f"  // {ctrl.name}.Items (options)")
                    lines.append("  FXRuntime.addEvaluator(" + fn_head)
                    lines.append(f'    var el = FXRuntime.controlElement({ctrl.name!r});')
                    lines.append("    if (!el || el.tagName !== 'SELECT') return;")
                    lines.append(f"    var selfRef = val({ctrl.name!r}), parentRef = val({parent_names.get(ctrl.name)!r});")
                    lines.append(f"    var rows = {items_expr.js};")
                    if display_expr and display_expr.js:
                        lines.append(f"    var displayFields = {display_expr.js};")
                        if display_expr is ctrl.properties.get("SearchFields"):
                            mark_emission(
                                display_expr, "approximated",
                                "used as a label fallback; native select search is not implemented",
                            )
                        else:
                            mark_emission(display_expr, "emitted",
                                          "used to choose the displayed option field")
                    else:
                        lines.append("    var displayFields = [];")
                    if default_selected and default_selected.js:
                        lines.append(f"    var defaults = {default_selected.js};")
                        mark_emission(default_selected)
                    if reset_expr and reset_expr.js:
                        lines.append(f"    var reset = {reset_expr.js};")
                        mark_emission(reset_expr)
                    # Use the row-control contract for both scopes: retain typed
                    # records for Reset, reevaluate changed defaults, and preserve
                    # every selected record when option labels are refreshed.
                    lines.append(f"    FXRuntime.rowControl(document, {ctrl.name!r}, {parent_names.get(ctrl.name)!r}, {{")
                    lines.append("      displayFields: function () { return displayFields; },")
                    lines.append("      items: function () { return rows; },")
                    if default_selected and default_selected.js:
                        lines.append("      default: function () { return defaults; },")
                    if reset_expr and reset_expr.js:
                        lines.append("      reset: function () { return reset; },")
                    lines.append("    });")
                    if not (default_selected and default_selected.js):
                        lines.append("    if (!el.__fxDefaultApplied) { el.__fxDefaultApplied = true; var d = el.getAttribute('data-fx-default'); if (d !== null) el.value = d; }")
                    lines.append("  });")

            text_expr = ctrl.properties.get("Text")
            if (text_expr and text_expr.js and not text_expr.js.startswith("'")
                    and ctrl.type not in {"Gallery"}):
                lines.append(f"  // {ctrl.name}.Text (reactive)")
                lines.append("  FXRuntime.addEvaluator(function () {")
                lines.append(f"    var el = FXRuntime.controlElement({ctrl.name!r});")
                lines.append("    if (el) {")
                lines.append("      var previousSelf = selfRef, previousParent = parentRef;")
                lines.append("      selfRef = val(" + repr(ctrl.name) + "); parentRef = val(" +
                             repr(parent_names.get(ctrl.name)) + ");")
                lines.append("      try { el.textContent = " + text_expr.js +
                             "; } finally { selfRef = previousSelf; parentRef = previousParent; }")
                lines.append("    }")
                lines.append("  });")
                mark_emission(text_expr)

            image_expr = ctrl.properties.get("Image")
            if (ctrl.type == "Image" and image_expr and image_expr.js
                    and _static_raw(image_expr) is None):
                lines.append(f"  // {ctrl.name}.Image (reactive source)")
                lines.append(f"  FXRuntime.attrControl({ctrl.name!r}, 'src', function () {{")
                lines.append(f"    return {image_expr.js};")
                lines.append(f"  }}, {parent_names.get(ctrl.name)!r});")
                mark_emission(
                    image_expr,
                    "approximated",
                    "dynamic image source is bound; an empty or failed source uses the generated placeholder",
                )

            html_expr = ctrl.properties.get("HtmlText") or ctrl.properties.get("Content")
            if (ctrl.type == "HtmlText" and html_expr and html_expr.js
                    and _static_raw(html_expr) is None):
                lines.append(f"  // {ctrl.name}.HtmlText (reactive sanitized markup)")
                lines.append(f"  FXRuntime.htmlControl({ctrl.name!r}, function () {{")
                lines.append(f"    return {html_expr.js};")
                lines.append(f"  }}, {parent_names.get(ctrl.name)!r});")
                mark_emission(
                    html_expr,
                    "approximated",
                    "dynamic HtmlText is rendered after executable markup is removed",
                )

            # Reactive fallbacks: layout/visual properties whose values are
            # formulas (static ones already became inline CSS above).
            reactive = [
                ("X", "left", "px"), ("Y", "top", "px"),
                ("Width", "width", "px"), ("Height", "height", "px"),
                ("Fill", "backgroundColor", "lower"), ("Color", "color", "lower"),
                ("FontColor", "color", "lower"),
                ("Size", "fontSize", "pt"), ("FontSize", "fontSize", "pt"),
                ("Visible", "display", None),
            ]
            for prop, css_prop, unit in reactive:
                expr = ctrl.properties.get(prop)
                if not expr or not expr.js or expr.js.strip().isdigit():
                    continue
                if prop in {"Fill", "Color", "FontColor"} and _static_color(expr) is not None:
                    continue
                if prop in {"X", "Y", "Width", "Height", "Size", "FontSize"} \
                        and _static_px(expr) is not None:
                    continue
                if expr.js.startswith("'"):
                    continue  # static literal already emitted as CSS
                lines.append(f"  // {ctrl.name}.{prop} (reactive style)")
                if prop == "Visible":
                    lines.append(f"  FXRuntime.styleControl({ctrl.name!r}, 'display', function () {{")
                    lines.append(f"    return ({expr.js}) ? '' : 'none';")
                    lines.append(f"  }}, null, {parent_names.get(ctrl.name)!r});")
                else:
                    lines.append(f"  FXRuntime.styleControl({ctrl.name!r}, {css_prop!r}, function () {{")
                    lines.append(f"    return {expr.js};")
                    lines.append(f"  }}, {unit!r}, {parent_names.get(ctrl.name)!r});")
                mark_emission(expr)
    # Cards use row/order coordinates instead of ordinary pixel coordinates.
    # Register after ordinary bindings so layout can consume dynamic child
    # heights; the runtime settles geometry without replacing edited nodes.
    for screen in ir.screens:
        for host in screen.walk_controls():
            if host.type not in {"Form", "FluidGrid"} or host.name in gallery_children:
                continue
            cards = [child for child in host.children if child.type == "DataCard"]
            if not cards:
                continue
            lines.append(f"  FXRuntime.registerCardLayout({host.name!r}, [")
            for card in cards:
                lines.append(f"    {{name: {card.name!r}, properties: {{")
                for prop in ("X", "Y", "Width", "Height", "Visible", "WidthFit"):
                    expr = card.properties.get(prop)
                    if expr and expr.js and "await " not in expr.js:
                        lines.append(f"      {prop!r}: function (val, selfRef, parentRef) {{ return {expr.js}; }},")
                        mark_emission(expr, "emitted", "card layout uses source row/order coordinates and minimum dimensions")
                lines.append("    }},")
            columns = host.properties.get("NumberOfColumns")
            column_js = columns.js if columns and columns.js and "await " not in columns.js else '1'
            lines.append(f"  ], function (val, selfRef, parentRef) {{ return {column_js}; }}, {parent_names.get(host.name)!r});")
            if columns and column_js == columns.js:
                mark_emission(columns, "emitted", "sets default card width when no Width formula is exported")
    # Bootstrap: reveal the start screen after APP_MAIN runs. APP_MAIN is
    # invoked on DOMContentLoaded (gas-runtime), and APP_MAIN closes with this
    # navigation so the first paint matches Power Apps' start screen.
    if ir.start_screen:
        lines.append("  // Start screen (first in the original app's screen order)")
        lines.append(f"  go({ir.start_screen!r});")
    lines.append("};")
    return "\n".join(lines)


INDEX_CSS = """
    html, body { margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; overflow: auto; }
    #fx-canvas { margin: 0 auto; position: relative; }
    [data-screen] { position: relative; box-sizing: border-box; }
    [data-control] { box-sizing: border-box; }
    [data-screen] > [data-control] { position: absolute; }
    button { cursor: pointer; overflow: hidden; }
    input, select, textarea { box-sizing: border-box; }
    .fx-gallery { overflow: auto; }
    .fx-component { position: absolute; overflow: hidden; }
    .fx-component > [data-control] { position: absolute; box-sizing: border-box; }
    .fx-manual-container, .fx-data-card { position: relative; }
    .fx-manual-container > [data-control], .fx-data-card > [data-control] { position: absolute; }
    .fx-card-layout { position: relative; overflow: auto; }
    .fx-card-layout > .fx-data-card { position: absolute; }
    .fx-rows { display: block; }
    .fx-row { display: block; position: relative; border-bottom: 1px solid #eee; padding: 4px 0; }
    .fx-row > [data-control] { position: absolute; box-sizing: border-box; }
    .fx-icon { font-family: 'Apple Symbols', 'Noto Sans Symbols 2', 'Segoe UI Symbol', sans-serif;
      display: inline-flex; align-items: center; justify-content: center;
      user-select: none; line-height: 1; }
    .fx-image { background-color: #eef2f7;
      background-image: radial-gradient(circle at 50% 34%, #94a3b8 0 16%, transparent 17%),
        radial-gradient(ellipse at 50% 96%, #94a3b8 0 34%, transparent 35%);
      background-repeat: no-repeat; }
    .fx-image[src] { background-image: none; }
    .fx-unsupported-control { display:flex; align-items:center; justify-content:center;
      min-width:160px; min-height:48px; padding:8px; border:2px dashed #b3261e;
      background:#fff1f0; color:#7a1b16; font-size:13px; }
    .fx-data-card[data-fx-error] { outline: 1px solid #b3261e; }
    .fx-data-card[data-fx-error]::after { content: attr(data-fx-error); color: #b3261e;
      display: block; font-size: 12px; line-height: 1.25; }
    [aria-invalid="true"] { outline: 2px solid #b3261e; outline-offset: 1px; }
    .fx-toast { position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%);
      background: #333; color: #fff; padding: 8px 16px; border-radius: 4px; display: none; z-index: 9999; }
    .fx-toast.error { background: #b3261e; }
"""


def render_index_html(ir: AppIR, screens_html: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{ir.name}</title>
  <style>{INDEX_CSS}</style>
  <base target="_top">
</head>
<body>
<div id="fx-canvas">
<?!= include('Screens.html'); ?>
</div>
<script type="application/json" id="fx-launch-parameters"><?!= launchParametersJSON ?></script>
<script type="application/json" id="fx-storage-context"><?!= storageContextJSON ?></script>
<script>
<?!= include('gas-runtime.js.html'); ?>
<?!= include('fx-stdlib.js.html'); ?>
<?!= include('fx-charts.js.html'); ?>
<?!= include('App.js.html'); ?>
</script>
</body>
</html>
"""
