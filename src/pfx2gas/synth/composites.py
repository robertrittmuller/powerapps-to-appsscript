"""Semantic content for native Header and ModernCard controls.

Exact Fluent themes, template artwork and native profile menus are not emulated.
Only source expressions supply content; omitted image/text slots stay empty.
"""
import html
import json

from ..fidelity import mark_emission

PROPERTIES = {
    'ModernCard': ('Title','Subtitle','Description','Image','HeaderImage','ImageAltText','HeaderImageAltText',
                   'LayoutDirection','ImagePlacement','ImagePosition','BorderRadius','Fill','TitleColor','SubtitleColor',
                   'DescriptionColor','TitleSize','SubtitleSize','DescriptionSize','DisplayMode','AccessibleLabel','Tooltip','TabIndex'),
    'Header': ('Title','Logo','IsTitleVisible','IsLogoVisible','IsProfilePictureVisible','LogoTooltip','LogoMaxHeight',
               'UserImage','UserImageAltText','UserName','UserEmail','TitleFontSize','TitleRole','FontColor','Fill','Style','DisplayMode'),
}

NOTE = ('Semantic Header/Card content and source actions; portable layout/theme and no-photo initials fallback. '
        'Native profile menus, built-in sample artwork, exact Fluent typography and clipping are not reproduced.')


def has_action(ctrl, event):
    expr = ctrl.properties.get(event)
    return bool(expr and expr.raw.strip().casefold() not in {'', 'false', 'blank()'})


def markup(ctrl, style_attr, attrs):
    name = html.escape(ctrl.name, quote=True)
    if ctrl.type == 'ModernCard':
        tag = 'button' if has_action(ctrl, 'OnSelect') else 'article'
        button_type = ' type="button"' if tag == 'button' else ''
        return (f'<{tag}{button_type} data-control="{name}"{style_attr}{attrs} class="fx-modern-card" data-fx-composite="ModernCard">'
                '<img data-fx-part="preview" alt="" hidden>'
                '<span data-fx-part="card-content"><span data-fx-part="card-header">'
                '<img data-fx-part="header-image" alt="" hidden><span data-fx-part="headings">'
                '<span data-fx-part="title"></span><span data-fx-part="subtitle"></span></span></span>'
                '<span data-fx-part="description"></span></span>' + f'</{tag}>')
    action = 'true' if has_action(ctrl, 'OnSelectLogo') else 'false'
    logo_tag = 'button' if action == 'true' else 'span'
    logo_attrs = ' type="button" disabled' if action == 'true' else ''
    return (f'<header data-control="{name}"{style_attr}{attrs} class="fx-modern-header" data-fx-composite="Header">'
            f'<{logo_tag}{logo_attrs} data-fx-part="logo-action" data-fx-action="{action}" hidden>'
            f'<img data-fx-part="logo" alt=""></{logo_tag}>'
            '<span data-fx-part="title" role="heading" aria-level="1"></span>'
            '<span data-fx-part="profile" role="img" hidden><img data-fx-part="user-image" alt="" hidden>'
            '<span data-fx-part="initials" aria-hidden="true"></span></span></header>')


def emit(lines, ctrl, parent, row=False):
    if ctrl.type not in PROPERTIES:
        return
    if not row:
        lines.append('  FXRuntime.addEvaluator(function () {')
    root = 'row' if row else 'document'
    lines.append(f'    FXRuntime.compositeControl({root}, {ctrl.name!r}, {parent!r}, {{')
    for prop in PROPERTIES[ctrl.type]:
        expr = ctrl.properties.get(prop)
        if not expr or not expr.raw.strip():
            continue
        js = expr.js
        if js and 'await ' in js:
            from ..validate import js_syntax_ok
            if not js_syntax_ok('(function () { return (' + js + '); })')[0]:
                js = None
        if not js:
            js = 'FX.unsupported(' + json.dumps(ctrl.name + '.' + prop + ' requires a synchronous value') + ')'
            mark_emission(expr, 'unsupported', NOTE)
        else:
            mark_emission(expr, 'approximated', NOTE)
        lines.append(f'      {prop!r}: function (val, selfRef, parentRef) {{ return {js}; }},')
    lines.append('    });')
    if not row:
        lines.append('  });')


CSS = """
    .fx-modern-card { display:flex; flex-direction:column; align-items:stretch; gap:12px;
      border:0; border-radius:12px; background:#fff; color:#242424; padding:12px;
      font:inherit; text-align:left; overflow:auto; min-width:0; }
    .fx-modern-card [data-fx-part] { box-sizing:border-box; min-width:0; }
    .fx-modern-card [data-fx-part="preview"] { display:block; width:100%; min-height:0;
      flex:1 1 0; object-fit:cover; border-radius:inherit; }
    .fx-modern-card [data-fx-part="card-content"] { display:flex; flex:0 0 auto; flex-direction:column; gap:8px; }
    .fx-modern-card [data-fx-part="card-header"] { display:flex; align-items:center; gap:12px; }
    .fx-modern-card [data-fx-part="header-image"] { width:40px; height:40px; object-fit:contain; flex:0 0 auto; }
    .fx-modern-card [data-fx-part="headings"] { flex:1; }
    .fx-modern-card [data-fx-part="title"], .fx-modern-card [data-fx-part="subtitle"],
    .fx-modern-card [data-fx-part="description"] { display:block; overflow-wrap:anywhere; white-space:pre-wrap; line-height:1.35; }
    .fx-modern-card [data-fx-part="title"] { font-size:12pt; font-weight:600; }
    .fx-modern-card [data-fx-part="subtitle"], .fx-modern-card [data-fx-part="description"] { font-size:10.5pt; }
    .fx-modern-card[data-fx-direction="horizontal"] { flex-direction:row; }
    .fx-modern-card[data-fx-direction="horizontal"] [data-fx-part="preview"] { width:40%; height:100%; flex:0 0 40%; }
    .fx-modern-card[data-fx-direction="horizontal"] [data-fx-part="card-content"] { flex:1 1 0; }
    .fx-modern-card [data-fx-part][hidden], .fx-modern-header [data-fx-part][hidden] { display:none; }
    .fx-modern-card:disabled { cursor:default; }
    .fx-modern-card:focus-visible, .fx-modern-header button:focus-visible { outline:3px solid #0067b8; outline-offset:-3px; }
    .fx-modern-header { display:flex; align-items:center; gap:16px; padding:8px 16px; min-width:0;
      background:#0f6cbd; color:white; overflow:hidden; }
    .fx-modern-header [data-fx-part="logo-action"] { display:flex; align-items:center; justify-content:center;
      flex:0 1 auto; max-width:30%; height:100%; padding:0; border:0; background:transparent; color:inherit; }
    .fx-modern-header [data-fx-part="logo"] { display:block; max-width:100%; max-height:100%; object-fit:contain; }
    .fx-modern-header [data-fx-part="title"] { flex:1; min-width:0; font-size:20px; font-weight:600;
      overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .fx-modern-header [data-fx-part="profile"] { display:flex; align-items:center; justify-content:center;
      flex:0 0 40px; width:40px; height:40px; border-radius:50%; background:#e5e7eb; color:#242424; }
    .fx-modern-header [data-fx-part="user-image"] { width:100%; height:100%; border-radius:inherit; object-fit:cover; }
    .fx-modern-header [data-fx-part="initials"] { font-size:14px; font-weight:600; }
"""
