"""FileXY's syntax highlighting: a Tk-free tokenizer emitting `(tag, start, end)` spans + the
tag-colour setup for a Tk Text widget. One regex-alternation pass per document.

TWO tiers of languages:
- the BESPOKE kinds (yaml / json / xml) - hand-tuned lookaheads (yaml block keys, json
  key-vs-string, xml tag-vs-attribute) that a generic rule table cannot express;
- the DATA-DRIVEN languages, Notepad++-UDL style: `langs.json` (shipped beside this module) defines
  each language as PLAIN DATA - extensions, line/block comment markers, string quotes, keyword
  groups, extra regex rules - compiled here into the same alternation engine. Adding a language is
  a JSON entry, no code; `load_languages(path)` merges a user file over the shipped one; the host
  UI can offer `available_kinds()` as a SELECTABLE language picker.

Pragmatic by design (a viewer, not a parser): YAML keys are recognized in BLOCK style (`key:` at line
start / after `- `), not inside flow `{...}`; a `#` starts a comment only at line start or after
whitespace. XML colours tag names + brackets (key), attribute names (bool tint), quoted values/CDATA
(str) and comments - a quoted word inside element TEXT also tints, which a viewer can live with."""
from __future__ import annotations

import json as _json
import os
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
    """`(tag, start, end)` spans for a bespoke kind (yaml/json/xml) or a langs.json language;
    [] for anything else."""
    out = []
    if kind in LANGS and kind not in _BESPOKE:
        return _lang_spans(LANGS[kind][0], text)
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


# --- the data-driven languages (Notepad++-UDL style; langs.json) ----------------------------------- #
_LANGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "langs.json")
_BESPOKE = ("yaml", "json", "xml")
OBJECT_KINDS = ("yaml", "json", "xml")        # the kinds with an Object-explorer view (objectview)


def _compile_language(name: str, spec: dict):
    """One langs.json entry -> (compiled alternation regex, extensions). Alternation order = comment
    markers, strings, keyword groups (keywords -> key colour, keywords2 -> bool tint), numbers,
    extra `[tag, pattern]` rules."""
    parts = []
    block = spec.get("comment_block") or []
    line = spec.get("comment_line") or ""
    comments = []
    if len(block) == 2:
        comments.append(re.escape(block[0]) + r".*?" + re.escape(block[1]))
    if line:
        comments.append(re.escape(line) + r"[^\n]*")
    if comments:
        parts.append("(?P<cmt>" + "|".join(comments) + ")")
    quotes = spec.get("strings") or []
    if quotes:
        parts.append("(?P<str>" + "|".join(
            re.escape(q) + r"(?:\\.|[^" + re.escape(q) + r"\\\n])*" + re.escape(q)
            for q in quotes) + ")")
    for i, (tag, pattern) in enumerate(spec.get("extra") or []):
        # extras take PRECEDENCE over keywords + numbers: a typed literal like WORD#16#F0 must
        # tokenize whole, not fall apart into the WORD keyword + a plain 16
        parts.append(f"(?P<x{i}_{tag}>{pattern})")
    for group, tag in (("keywords", "key"), ("keywords2", "bool")):
        words = spec.get(group) or []
        if words:
            alt = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
            parts.append(r"(?P<" + tag + r">\b(?:" + alt + r")\b)")
    if spec.get("numbers", True):
        parts.append(r"(?P<num>(?<![\w.])-?\d+(?:\.\d+)?(?![\w.]))")
    flags = re.DOTALL | (re.IGNORECASE if spec.get("case_insensitive") else 0)
    return re.compile("|".join(parts), flags), [e.lower() for e in spec.get("extensions") or []]


def load_languages(path: str | None = None) -> dict:
    """{name -> (regex, extensions)} from the SHIPPED langs.json, with `path` (a user file of the
    same shape) merged over it when given. A broken file loads as empty rather than crashing."""
    langs = {}
    for source in (p for p in (_LANGS_FILE, path) if p):
        try:
            with open(source, encoding="utf-8") as handle:
                data = _json.load(handle)
            for name, spec in data.items():
                langs[name] = _compile_language(name, spec)
        except Exception:  # noqa: BLE001 - a bad user langs file must not kill the viewer
            continue
    return langs


LANGS = load_languages()


def available_kinds() -> list:
    """Every selectable language for the picker: the bespoke kinds + the data-driven ones."""
    return list(_BESPOKE) + sorted(LANGS)


def object_kind_of(path: str) -> str | None:
    """The kinds that ALSO have an Object-explorer view (yaml/json/xml) - the doc-view router."""
    kind = kind_of(path)
    return kind if kind in OBJECT_KINDS else None


def _lang_spans(regex, text: str) -> list:
    out = []
    for m in regex.finditer(text):
        for group, value in m.groupdict().items():
            if value is None:
                continue
            tag = group.split("_", 1)[1] if group.startswith("x") and "_" in group else group
            out.append((f"hl_{tag}", m.start(group), m.end(group)))
            break
    return out


def kind_of(path: str) -> str | None:
    """The highlight kind for a filename: a bespoke kind (yaml/json/xml) or a data-driven language
    from langs.json (by extension); None = plain text."""
    low = str(path).lower()
    if low.endswith((".yaml", ".yml")):
        return "yaml"
    if low.endswith(".json"):
        return "json"
    if low.endswith(".xml"):
        return "xml"
    ext = os.path.splitext(low)[1]
    for name, (_regex, extensions) in LANGS.items():
        if ext in extensions:
            return name
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
