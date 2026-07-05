"""Text-mode syntax highlighting for the Files tab (UI_REFRESH_PLAN D): a Tk-free tokenizer emitting
`(tag, start, end)` spans for YAML, JSON and XML, and the tag-colour setup for a Tk Text widget. Same
regex-alternation + debounce-free single-pass approach as the Database Explorer's SQL highlighter
(the panes are read-only, so one pass at load time is all that's needed).

Pragmatic by design (a viewer, not a parser): YAML keys are recognized in BLOCK style (`key:` at line
start / after `- `), not inside flow `{...}`; a `#` starts a comment only at line start or after
whitespace (so a `#` inside a quoted scalar stays part of the string, which the alternation order
already guarantees for quoted strings). XML colours tag names + brackets (key), attribute names
(bool tint), quoted values/CDATA (str) and comments - a quoted word inside element TEXT also tints,
which a viewer can live with."""
from __future__ import annotations

import re

# tag -> (dark colour, light colour, italic?)
COLORS = {
    "hl_key":  ("#74b9ff", "#0055cc", False),
    "hl_str":  ("#55efc4", "#1a7e1a", False),
    "hl_num":  ("#fdcb6e", "#c05c00", False),
    "hl_bool": ("#a29bfe", "#7040a0", False),
    "hl_cmt":  ("#b2bec3", "#6e7a8a", True),
}

_YAML = re.compile(
    r"(?P<cmt>(?:^|(?<=\s))#[^\n]*)"
    r"|(?P<str>\"(?:\\.|[^\"\\\n])*\"|'(?:''|[^'\n])*')"
    r"|(?P<key>^[ \t]*(?:-[ \t]+)?[^\s#\-][^:\n]*?)(?=:(?:[ \t]|$))"
    r"|(?P<bool>\b(?:true|false|null|yes|no|on|off)\b|(?<=\s)~(?=\s|$))"
    r"|(?P<num>(?<![\w.\-])-?\d+(?:\.\d+)?(?![\w.]))",
    re.MULTILINE | re.IGNORECASE,
)

_JSON = re.compile(
    r"(?P<str>\"(?:\\.|[^\"\\])*\")"
    r"|(?P<bool>\b(?:true|false|null)\b)"
    r"|(?P<num>-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)",
)

_WS_COLON = re.compile(r"[ \t\r\n]*:")

_XML = re.compile(
    r"(?P<cmt><!--.*?-->)"                                   # comments first (swallow their innards)
    r"|(?P<str><!\[CDATA\[.*?\]\]>|\"[^\"\n]*\"|'[^'\n]*')"  # CDATA + quoted attribute values
    r"|(?P<key></?[A-Za-z_][\w.:-]*|<[?!][\w.:-]*|[?/]?>)"   # tag names + brackets + declarations
    r"|(?P<bool>[A-Za-z_][\w.:-]*(?=\s*=))",                 # attribute names (before '=')
    re.DOTALL,
)


def spans(kind: str, text: str) -> list:
    """`(tag, start, end)` spans for `kind` in {'yaml', 'json', 'xml'}; [] for anything else."""
    out = []
    if kind == "xml":
        for m in _XML.finditer(text):
            for tag in ("cmt", "str", "key", "bool"):
                if m.group(tag) is not None:
                    out.append((f"hl_{tag}", m.start(tag), m.end(tag)))
                    break
    elif kind == "yaml":
        for m in _YAML.finditer(text):
            for tag in ("cmt", "str", "key", "bool", "num"):
                if m.group(tag) is not None:
                    out.append((f"hl_{tag}", m.start(tag), m.end(tag)))
                    break
    elif kind == "json":
        for m in _JSON.finditer(text):
            if m.group("str") is not None:
                # a string directly followed by ':' is a KEY
                tag = "hl_key" if _WS_COLON.match(text, m.end()) else "hl_str"
                out.append((tag, m.start(), m.end()))
            elif m.group("bool") is not None:
                out.append(("hl_bool", m.start(), m.end()))
            else:
                out.append(("hl_num", m.start(), m.end()))
    return out


def kind_of(path: str) -> str | None:
    """The highlight kind for a filename: 'yaml' | 'json' | 'xml' | None."""
    low = str(path).lower()
    if low.endswith((".yaml", ".yml")):
        return "yaml"
    if low.endswith(".json"):
        return "json"
    if low.endswith(".xml"):
        return "xml"
    return None


def configure_tags(text_widget, mode: str) -> None:
    """Configure the highlight tags on a Tk Text for dark/light `mode` (call again on a theme switch)."""
    dark = mode == "dark"
    for tag, (dark_color, light_color, italic) in COLORS.items():
        kwargs = {"foreground": dark_color if dark else light_color}
        if italic:
            try:
                from pipeline4.gui import theme
                kwargs["font"] = (theme.MONO_FONT[0], theme.MONO_FONT[1], "italic")
            except Exception:  # noqa: BLE001
                pass
        text_widget.tag_configure(tag, **kwargs)


def apply(text_widget, kind: str, content: str) -> None:
    """Tag `content` (already inserted at 1.0) on `text_widget` in one pass."""
    for tag, start, end in spans(kind, content):
        text_widget.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")
