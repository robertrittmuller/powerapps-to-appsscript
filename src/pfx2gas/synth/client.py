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

import re

from ..ir import AppIR, ControlNode

ELEMENT_MAP = {
    "Button": "button",
    "Label": "span",
    "TextInput": "input",
    "TextArea": "textarea",
    "Dropdown": "select",
    "ComboBox": "select",
    "CheckBox": "input",
    "DatePicker": "input",
    "Gallery": "div",
    "GalleryTemplate": "div",
    "Image": "img",
    "Icon": "span",
    "HtmlText": "div",
    "Form": "div",
    "Screen": "section",
    "GroupContainer": "div",
    "Header": "header",
    "Timer": "div",
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
    "ColumnChart": "bar", "Legend": "pie",  # legend renders with pie layout
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


def _static_map(expr, mapping: dict[str, str]) -> str | None:
    if not expr or expr.js is None:
        return None
    m = _QUOTED_RE.match(expr.js.strip())
    return mapping.get(m.group(1)) if m else None


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
    m = _QUOTED_RE.match(expr.js.strip())
    return m.group(1) if m else None


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
WEIGHT_MAP = {"Bold": "bold", "Semibold": "600", "Light": "300", "Regular": "400"}

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
    "DisabledFill": ("background-color", ":disabled"),
    "DisabledColor": ("color", ":disabled"),
    "DisabledBorderColor": ("border-color", ":disabled"),
    "FocusedBorderColor": ("border-color", ":focus-visible"),
    "FocusedFill": ("background-color", ":focus-visible"),
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
    expr = ctrl.properties.get("LayoutDirection")
    return bool(expr and expr.js)


def _static_style(ctrl: ControlNode, in_flex: bool, rules: list[str]) -> str:
    """Full static inline style: position/size, layout, cosmetics, colors."""
    props = ctrl.properties
    css: list[str] = []

    def px(name: str) -> str | None:
        return _static_px(props.get(name))

    def color(name: str) -> str | None:
        return _static_color(props.get(name))

    # --- position / size ----------------------------------------------------
    if in_flex:
        fp = props.get("FillPortions")
        if fp and fp.js and _NUM_RE.match(fp.js.strip()) and fp.js.strip() != "0":
            css.append(f"flex:{fp.js.strip()} 1 0%")
        align = _static_map(props.get("Align"), ALIGN_MAP)
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
    auto_h = _static_bool(props.get("AutoHeight"))
    if h and auto_h is not True:
        css.append(f"height:{h}")
    elif auto_h is True:
        css.append("height:auto")

    # --- container layout ----------------------------------------------------
    if _is_flex_container(ctrl):
        css.append("display:flex")
        direction = _static_map(props.get("LayoutDirection"), DIRECTION_MAP)
        if direction:
            css.append(f"flex-direction:{direction}")
        align = _static_map(props.get("LayoutAlignItems"), ALIGN_MAP)
        if align:
            css.append(f"align-items:{align}")
        justify = _static_map(props.get("LayoutJustifyContent"), JUSTIFY_MAP)
        if justify:
            css.append(f"justify-content:{justify}")
        wrap = _static_map(props.get("LayoutWrap"), WRAP_MAP)
        if wrap:
            css.append(f"flex-wrap:{wrap}")
    for prop, css_prop in COSMETIC_PX.items():
        v = px(prop)
        if v:
            css.append(f"{css_prop}:{v}")
    # border style: explicit enum, else solid when thickness+color present
    border_style = _static_map(props.get("BorderStyle"), BORDER_STYLE_MAP)
    if border_style and px("BorderThickness"):
        css.append(f"border-style:{border_style}")
    elif px("BorderThickness") and color("BorderColor"):
        css.append("border-style:solid")

    shadow = _static_map(props.get("DropShadow"), SHADOW_MAP)
    if shadow:
        css.append(f"box-shadow:{shadow}")

    # --- colors / typography --------------------------------------------------
    fill = color("Fill")
    if fill:
        css.append(f"background-color:{fill}")
    text_color = color("Color") or color("FontColor")
    if text_color:
        css.append(f"color:{text_color}")
    font = _static_raw(props.get("Font"))
    if font:
        css.append(f"font-family:'{font}'")
    weight = _static_map(props.get("FontWeight"), WEIGHT_MAP) or _static_px(props.get("FontWeight"))
    if weight:
        css.append(f"font-weight:{weight}")
    size = px("Size") or px("FontSize")
    if size:
        css.append(f"font-size:{size}")
    for prop, (css_prop, css_val) in BOOL_TEXT_PROPS.items():
        if _static_bool(props.get(prop)) is True:
            css.append(f"{css_prop}:{css_val}")
    lh = px("LineHeight")
    if lh:
        css.append(f"line-height:{lh}")
    valign = _static_map(props.get("VerticalAlign"), {"Top": "top", "Middle": "middle", "Bottom": "bottom"})
    if valign:
        css.append(f"display:flex;align-items:{valign}")
    vwrap = _static_raw(props.get("LayoutOverflowX"))
    if vwrap == "Overflow":
        css.append("overflow-x:auto")
    vwrap_y = _static_raw(props.get("LayoutOverflowY"))
    if vwrap_y == "Overflow":
        css.append("overflow-y:auto")
    ov = _static_raw(props.get("Overflow"))
    if ov == "Overflow":
        css.append("overflow:visible")
    elif ov in {"Hide", "Scrollbar"}:
        css.append("overflow:hidden")
    wrap = _static_bool(props.get("Wrap"))
    if wrap is False:
        css.append("white-space:nowrap")
    elif wrap is True:
        css.append("white-space:normal")
    if ctrl.type == "Image":
        pos = _static_map(props.get("ImagePosition"),
                          {"Fit": "contain", "Fill": "cover", "Stretch": "fill", "Tile": "cover"})
        if pos:
            css.append(f"object-fit:{pos}")
        rot = _static_px(props.get("ImageRotation"))
        if rot:
            css.append(f"transform:rotate({rot})")
    text_align = _static_map(props.get("Align"), {"Center": "center", "Start": "left", "End": "right"})
    if text_align and not in_flex:
        css.append(f"text-align:{text_align}")

    # --- hover/pressed/disabled CSS rules --------------------------------------
    for prop, (css_prop, pseudo) in HOVER_PROPS.items():
        v = color(prop)
        if v:
            sel = f'[data-control="{ctrl.name}"]:{pseudo}'
            rules.append(f"{sel} {{ {css_prop}:{v}; }}")

    return ";".join(css)


def _static_text(ctrl: ControlNode) -> str:
    expr = ctrl.properties.get("Text")
    if expr and ctrl.type in {"Button", "Label"} and expr.js and expr.js.startswith("'"):
        return expr.js[1:-1]
    return ""


def _static_extra_attrs(ctrl: ControlNode) -> str:
    """Static src/href-style attributes: Image.Image, Icon glyph, HtmlText content."""
    props = ctrl.properties
    out = ""
    if ctrl.type == "Image":
        src = _static_raw(props.get("Image"))
        if src:
            out += f' src="{src}"'
    if ctrl.type == "Icon":
        glyph = _static_raw(props.get("Icon"))
        if glyph:
            out += f' title="{glyph}"'
    if ctrl.type in {"HtmlText"}:
        content = _static_raw(props.get("HtmlText") or props.get("Content"))
        if content:
            out += f' data-static-html="{content}"'
    return out


def _chart_config(ctrl: ControlNode) -> str:
    """JSON config for a chart control (type, columns) from its properties."""
    props = ctrl.properties
    ctype = CHART_TYPES.get(ctrl.type) or "bar"
    labels = _static_raw(props.get("ItemsLabels"))
    values = _static_raw(props.get("ItemsValues"))
    cfg: dict[str, object] = {"type": ctype}
    if labels:
        cfg["cat"] = labels
    if values:
        cfg["val"] = values
    width = _static_px(props.get("Width"))
    height = _static_px(props.get("Height"))
    if width:
        cfg["width"] = int(float(width.replace("px", "")))
    if height:
        cfg["height"] = int(float(height.replace("px", "")))
    import json as _json
    return _json.dumps(cfg)


def _static_attrs(ctrl: ControlNode) -> str:
    """Accessibility attributes: Role -> ARIA role, AccessibleLabel/Tooltip -> aria-label."""
    props = ctrl.properties
    out = ""
    role = _static_raw(props.get("Role"))
    if role and role in ACCESSIBILITY_ROLES:
        out += f' role="{ACCESSIBILITY_ROLES[role]}"'
    label = _static_raw(props.get("AccessibleLabel")) or _static_raw(props.get("Tooltip"))
    if label:
        out += f' aria-label="{label}"'
    live = _static_raw(props.get("Live"))
    if live:
        out += f' aria-live="{live.lower()}"'
    # DisplayMode: static Disabled -> disabled/readonly attribute
    if _static_raw(props.get("DisplayMode")) == "Disabled":
        if ctrl.type in {"Button", "Icon"}:
            out += " disabled"
        elif ctrl.type in {"TextInput", "TextArea", "Dropdown", "ComboBox",
                           "CheckBox", "DatePicker", "Slider"}:
            out += " readonly"
    if ctrl.type in {"TextInput", "TextArea"}:
        max_len = _static_raw(props.get("MaxLength"))
        if max_len:
            out += f' maxlength="{max_len}"'
        if _static_bool(props.get("DelayOutput")) is True:
            out += ' data-delay-output="true"'
    tab_idx = _static_raw(props.get("TabIndex"))
    if tab_idx in {"0", "1", "-1", "2"}:
        out += f' tabindex="{tab_idx}"'
    if ctrl.type == "TextInput":
        vk = _static_raw(props.get("VirtualKeyboardMode"))
        if vk:
            out += f' inputmode="{"numeric" if "num" in vk.lower() else "text"}"'
    return out


def _render_control(ctrl: ControlNode, depth: int, in_flex: bool, rules: list[str]) -> str:
    tag = ELEMENT_MAP.get(ctrl.type, "div")
    indent = "  " * (depth + 1)
    style = _static_style(ctrl, in_flex, rules)
    style_attr = f' style="{style}"' if style else ""
    flex = _is_flex_container(ctrl)
    extra = ""
    if ctrl.type in {"TextInput", "TextArea"}:
        extra = ' type="text"'
    elif ctrl.type == "CheckBox":
        extra = ' type="checkbox"'
    elif ctrl.type == "DatePicker":
        extra = ' type="date"'
    elif ctrl.type == "Slider":
        extra = ' type="range"'

    if ctrl.type == "Gallery" or ctrl.type == "GalleryTemplate":
        inner_row = "\n".join(_render_control(c, depth + 2, flex, rules) for c in ctrl.children)
        return (
            f'{indent}<div data-control="{ctrl.name}"{style_attr} class="fx-gallery">\n'
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

    inner = ""
    close = f"</{tag}>" if tag not in {"input", "img", "br", "hr"} else ""
    if ctrl.children and ctrl.type not in VOID_CONTENT_TYPES:
        child_html = "\n".join(_render_control(c, depth + 1, flex, rules) for c in ctrl.children)
        inner = "\n" + child_html + "\n" + indent
    attrs = _static_extra_attrs(ctrl) + _static_attrs(ctrl)
    return f'{indent}<{tag} data-control="{ctrl.name}"{style_attr}{attrs}{extra}>{_static_text(ctrl)}{inner}{close}'


def render_screens_html(ir: AppIR) -> str:
    rules: list[str] = []
    parts = []
    for screen in ir.screens:
        parts.append(f'  <section data-screen="{screen.name}" style="display:none">')
        for ctrl in screen.controls:
            parts.append(_render_control(ctrl, 1, False, rules))
        parts.append("  </section>")
    style_block = ""
    if rules:
        style_block = "  <style>\n    " + "\n    ".join(rules) + "\n  </style>\n"
    return style_block + "\n".join(parts)


def render_app_js(ir: AppIR) -> str:
    lines = [
        "// App.js — generated by pfx2gas; transpiled Power Fx lives here.",
        "APP_MAIN = async function () {",
    ]
    # Collections are client-side state; declare them as empty arrays instead
    # of refreshing them from the server.
    for ds in ir.data_sources:
        if ds.origin == "collection":
            lines.append(f"  state.{ds.name} = [];")
    for ds in ir.data_sources:
        if ds.fields and ds.origin != "collection":
            lines.append(f"  refreshData({ds.name!r});")
    if ir.on_start and ir.on_start.js:
        lines.append("  // OnStart (transpiled from Power Fx)")
        for stmt in ir.on_start.js.splitlines():
            lines.append(f"  {stmt}")
    lines.append("  var __INITIAL_STATE_ONLY = null;")
    lines.append("")

    for screen in ir.screens:
        if screen.on_visible and screen.on_visible.js:
            lines.append(f"  FXRuntime.registerScreenHandler({screen.name!r}, async function () {{")
            for stmt in screen.on_visible.js.splitlines():
                lines.append(f"    {stmt}")
            lines.append("  });")

    for screen in ir.screens:
        for ctrl in screen.walk_controls():
            for event in ("OnSelect", "OnChange"):
                expr = ctrl.properties.get(event)
                if expr and expr.js:
                    lines.append(f"  // {ctrl.name}.{event}")
                    lines.append(f"  bind({ctrl.name!r}, {event!r}, async function () {{")
                    for stmt in expr.js.splitlines():
                        lines.append(f"    {stmt}")
                    lines.append("  });")

            if ctrl.type == "Gallery":
                items = ctrl.properties.get("Items")
                if items and items.js:
                    row_fns = []
                    handlers = {}
                    for child in ctrl.children:
                        texpr = child.properties.get("Text")
                        if texpr and texpr.js and not texpr.js.startswith("'"):
                            row_fns.append(
                                f"        var el_{child.name} = row.querySelector('[data-control=\"{child.name}\"]');"
                                f" if (el_{child.name}) el_{child.name}.textContent = {texpr.js};"
                            )
                        onsel = child.properties.get("OnSelect")
                        if onsel and onsel.js:
                            handlers[child.name] = onsel.js
                    lines.append(f"  // {ctrl.name}.Items (gallery)")
                    lines.append("  FXRuntime.gallery(")
                    lines.append(f"    {ctrl.name!r},")
                    lines.append(f"    function () {{ return {items.js}; }},")
                    lines.append("    function (item, row) {")
                    for rf in row_fns:
                        lines.append(rf)
                    lines.append("    },")
                    if handlers:
                        lines.append("    {")
                        for cname, js in handlers.items():
                            lines.append(f"      {cname}: async function (item) {{")
                            for stmt in js.splitlines():
                                lines.append(f"        {stmt}")
                            lines.append("      },")
                        lines.append("    }")
                    else:
                        lines.append("    null")
                    lines.append("  );")

            # --- chart rendering ------------------------------------------
            if ctrl.type in CHART_TYPES:
                items = ctrl.properties.get("Items")
                if items and items.js:
                    lines.append(f"  // {ctrl.name} (chart)")
                    lines.append("  FXRuntime.addEvaluator(async function () {")
                    lines.append(f'    var el = document.querySelector(\'[data-control="{ctrl.name}"]\');')
                    lines.append("    if (!el) return;")
                    lines.append("    var cfg = JSON.parse(el.getAttribute('data-chart') || '{}');")
                    lines.append(f"    var rows = {items.js};")
                    lines.append("    if (rows && rows.then) rows = await rows;")
                    lines.append("    el.innerHTML = FXCharts.svg(rows || [], cfg);")
                    lines.append("  });")

            # --- dropdown/combobox Items -> <option> population -------------
            if ctrl.type in {"Dropdown", "ComboBox", "ListBox"}:
                items_expr = ctrl.properties.get("Items")
                if items_expr and items_expr.js:
                    needs_async = "await " in items_expr.js
                    fn_head = "async function () {" if needs_async else "function () {"
                    lines.append(f"  // {ctrl.name}.Items (options)")
                    lines.append("  FXRuntime.addEvaluator(" + fn_head)
                    lines.append(f'    var el = document.querySelector(\'[data-control="{ctrl.name}"]\');')
                    lines.append("    if (!el || el.tagName !== 'SELECT') return;")
                    lines.append("    var current = el.value;")
                    lines.append(f"    var rows = {items_expr.js};" if needs_async
                                 else f"    var rows = {items_expr.js};")
                    lines.append("    var opts = (rows || []).map(function (r) {")
                    lines.append("        var v = (r && r.Value !== undefined && r.Value !== null) ? r.Value : r;")
                    lines.append("        var n = (r && r.Name !== undefined && r.Name !== null) ? r.Name : r;")
                    lines.append("        return '<option value=\"' + esc(v) + '\">' + esc(n) + '</option>';")
                    lines.append("    }).join('');")
                    lines.append("    if (el.__fxOpts !== opts) { el.__fxOpts = opts; el.innerHTML = opts; if (current) el.value = current; }")
                    lines.append("  });")

            text_expr = ctrl.properties.get("Text")
            if (text_expr and text_expr.js and not text_expr.js.startswith("'")
                    and ctrl.type not in {"Gallery"}):
                lines.append(f"  // {ctrl.name}.Text (reactive)")
                lines.append("  FXRuntime.addEvaluator(function () {")
                lines.append('    var el = document.querySelector(\'[data-control="' + ctrl.name + '"]\');')
                lines.append("    if (el) el.textContent = " + text_expr.js + ";")
                lines.append("  });")

            # Reactive fallbacks: layout/visual properties whose values are
            # formulas (static ones already became inline CSS above).
            reactive = [
                ("X", "left", "px"), ("Y", "top", "px"),
                ("Width", "width", "px"), ("Height", "height", "px"),
                ("Fill", "backgroundColor", "lower"), ("Color", "color", "lower"),
                ("FontColor", "color", "lower"),
                ("Size", "fontSize", "px"), ("FontSize", "fontSize", "px"),
                ("Visible", "display", None),
            ]
            for prop, css_prop, unit in reactive:
                expr = ctrl.properties.get(prop)
                if not expr or not expr.js or expr.js.strip().isdigit():
                    continue
                if expr.js.startswith("'"):
                    continue  # static literal already emitted as CSS
                lines.append(f"  // {ctrl.name}.{prop} (reactive style)")
                if prop == "Visible":
                    lines.append(f"  FXRuntime.styleControl({ctrl.name!r}, 'display', function () {{")
                    lines.append(f"    return ({expr.js}) ? '' : 'none';")
                    lines.append("  }, null);")
                else:
                    lines.append(f"  FXRuntime.styleControl({ctrl.name!r}, {css_prop!r}, function () {{")
                    lines.append(f"    return {expr.js};")
                    lines.append(f"  }}, {unit!r});")
    lines.append("};")
    return "\n".join(lines)


INDEX_CSS = """
    body { font-family: system-ui, sans-serif; margin: 0; padding: 16px; }
    [data-screen] { max-width: 100%; margin: 0 auto; position: relative; min-height: 90vh; }
    [data-screen] > [data-control] { position: absolute; }
    button { cursor: pointer; }
    input, select, textarea { box-sizing: border-box; }
    .fx-gallery { overflow: auto; }
    .fx-rows { display: block; }
    .fx-row { display: block; position: relative; border-bottom: 1px solid #eee; padding: 4px 0; }
    .fx-toast { position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%);
      background: #333; color: #fff; padding: 8px 16px; border-radius: 4px; display: none; z-index: 9999; }
    .fx-toast.error { background: #b3261e; }
"""


def render_index_html(ir: AppIR, screens_html: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{ir.name}</title>
  <style>{INDEX_CSS}</style>
  <base target="_top">
</head>
<body>
<?!= include('Screens'); ?>
<script>
<?!= include('gas-runtime'); ?>
<?!= include('fx-stdlib'); ?>
<?!= include('fx-charts'); ?>
<?!= include('App'); ?>
</script>
</body>
</html>
"""
