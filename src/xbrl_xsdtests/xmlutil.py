"""
stdlib ``xml.etree.ElementTree`` with a small lxml-compatible façade.

Serialization aims to match the prior lxml ``pretty_print`` output closely enough
that generated golden files stay stable.
"""

from __future__ import annotations

import io
import os
import weakref
from collections.abc import Iterator
from typing import Any
from xml.etree import ElementTree as ET

XMLSyntaxError = ET.ParseError
ParseError = ET.ParseError

Comment = ET.Comment
ProcessingInstruction = ET.ProcessingInstruction
QName = ET.QName
Element = ET.Element
ElementTree = ET.ElementTree

_parent_maps: weakref.WeakKeyDictionary[ET.Element, dict[ET.Element, ET.Element | None]] = (
    weakref.WeakKeyDictionary()
)
_element_nsmaps: weakref.WeakKeyDictionary[ET.Element, dict[str | None, str]] = weakref.WeakKeyDictionary()
_element_roots: weakref.WeakKeyDictionary[ET.Element, ET.Element] = weakref.WeakKeyDictionary()


def _build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element | None]:
    return {child: parent for parent in root.iter() for child in parent}


def _register_tree(root: ET.Element) -> None:
    _parent_maps[root] = _build_parent_map(root)
    for node in root.iter():
        _element_roots[node] = root


def _find_root(element: ET.Element) -> ET.Element:
    root = _element_roots.get(element)
    if root is not None:
        return root
    _register_tree(element)
    return element


def SubElement(
    parent: ET.Element,
    tag: str,
    attrib: dict[str, str] | None = None,
    **extra: str,
) -> ET.Element:
    if attrib is None:
        child: ET.Element = ET.SubElement(parent, tag, **extra)
    else:
        child = ET.SubElement(parent, tag, attrib, **extra)
    root = _element_roots.get(parent)
    if root is not None:
        _element_roots[child] = root
        parent_map = _parent_maps.get(root)
        if parent_map is not None:
            parent_map[child] = parent
    parent_ns = _element_nsmaps.get(parent)
    if parent_ns is not None:
        _element_nsmaps[child] = parent_ns
    return child


def _track_start_ns(stack: list[dict[str | None, str]], prefix: str, uri: str) -> None:
    stack[-1] = {**stack[-1], prefix or None: uri}


def _track_start(stack: list[dict[str | None, str]], element: ET.Element) -> None:
    _element_nsmaps[element] = stack[-1]
    stack.append(stack[-1])


def _track_end(stack: list[dict[str | None, str]]) -> None:
    stack.pop()


def _iterparse_ns(
    source: Any,
    events: tuple[str, ...],
) -> Iterator[tuple[str, Any]]:
    track_events = tuple(dict.fromkeys((*events, "start-ns", "start", "end")))
    stack: list[dict[str | None, str]] = [{}]
    for event, payload in ET.iterparse(source, events=track_events):
        if event == "start-ns":
            prefix, uri = payload
            _track_start_ns(stack, prefix, uri)
        elif event == "start":
            _track_start(stack, payload)
        elif event == "end":
            _track_end(stack)
        if event in events:
            yield event, payload


def _open_source(source: Any) -> tuple[Any, bool]:
    if isinstance(source, str):
        if os.path.isfile(source):
            return open(source, "rb"), True
        return io.BytesIO(source.encode("utf-8")), False
    if isinstance(source, bytes):
        return io.BytesIO(source), False
    return source, False


def parse(source: Any, *, track_ns: bool = False) -> ET.ElementTree:
    fh, close = _open_source(source)
    try:
        if track_ns:
            root: ET.Element | None = None
            for _event, payload in _iterparse_ns(fh, ("end",)):
                root = payload
            if root is None:
                raise ParseError("no element found")
            tree = ET.ElementTree(root)
        else:
            tree = ET.parse(fh)
        _register_tree(tree.getroot())
        return tree
    finally:
        if close:
            fh.close()


def fromstring(text: bytes | str, *, parser: Any = None, track_ns: bool = False) -> ET.Element:
    if parser is not None:
        raw = text.encode() if isinstance(text, str) else text
        root = ET.fromstring(raw, parser=parser)
        _register_tree(root)
        return root
    if isinstance(text, str):
        text = text.encode("utf-8")
    return parse(text, track_ns=track_ns).getroot()


def iterparse(
    source: Any,
    events: tuple[str, ...] = ("end",),
    tag: str | None = None,
    *,
    track_ns: bool = False,
) -> Iterator[tuple[str, ET.Element]]:
    if track_ns:
        iterator: Iterator[tuple[str, ET.Element]] = _iterparse_ns(source, events)
    else:
        iterator = ET.iterparse(source, events=events)
    for event, payload in iterator:
        if tag is not None and event == "end" and payload.tag != tag:
            continue
        yield event, payload


def localname(tag_or_element: str | ET.Element) -> str:
    tag = tag_or_element.tag if isinstance(tag_or_element, ET.Element) else tag_or_element
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag if isinstance(tag, str) else ""


def nsmap(element: ET.Element) -> dict[str | None, str]:
    """Namespace map in scope at ``element`` (closest ancestor wins)."""
    tracked = _element_nsmaps.get(element)
    if tracked is not None:
        return tracked
    root = _find_root(element)
    parent_map = _parent_maps[root]
    chain: list[ET.Element] = []
    current: ET.Element | None = element
    while current is not None:
        chain.append(current)
        current = parent_map.get(current)
    result: dict[str | None, str] = {}
    for el in reversed(chain):
        for key, value in el.attrib.items():
            if key == "xmlns":
                result[None] = value
            elif key.startswith("xmlns:"):
                result[key[6:]] = value
    return result


def element(tag: str, nsmap: dict[str | None, str] | None = None, **attrib: str) -> ET.Element:
    el = ET.Element(tag, attrib)
    effective_nsmap: dict[str | None, str] = {}
    if nsmap:
        for prefix, uri in nsmap.items():
            if prefix is None:
                el.set("xmlns", uri)
            else:
                el.set(f"xmlns:{prefix}", uri)
            effective_nsmap[prefix] = uri
    _element_nsmaps[el] = effective_nsmap
    _register_tree(el)
    return el


def _is_comment(node: ET.Element) -> bool:
    return not isinstance(node.tag, str)


def is_comment(node: ET.Element) -> bool:
    return _is_comment(node)


def _split_clark(tag: str) -> tuple[str, str]:
    uri, local = tag[1:].split("}", 1)
    return uri, local


def _prefix_for_uri(element: ET.Element, uri: str, *, element_nsmap: dict[str | None, str] | None = None) -> str | None:
    for prefix, mapped in (element_nsmap or nsmap(element)).items():
        if mapped == uri and prefix is not None:
            return prefix
    return None


def _format_tag(element: ET.Element, *, element_nsmap: dict[str | None, str] | None = None) -> str:
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        uri, local = _split_clark(tag)
        prefix = _prefix_for_uri(element, uri, element_nsmap=element_nsmap)
        if prefix:
            return f"{prefix}:{local}"
        return local
    return tag


def _format_attr_name(element: ET.Element, name: str, *, element_nsmap: dict[str | None, str] | None = None) -> str:
    if name.startswith("{"):
        uri, local = _split_clark(name)
        prefix = _prefix_for_uri(element, uri, element_nsmap=element_nsmap)
        if prefix:
            return f"{prefix}:{local}"
        return local
    return name


def _format_attr_key(element: ET.Element, name: str, *, element_nsmap: dict[str | None, str] | None = None) -> str:
    if name == "xmlns" or name.startswith("xmlns:"):
        return name
    return _format_attr_name(element, name, element_nsmap=element_nsmap)


def _format_attrs(element: ET.Element, *, element_nsmap: dict[str | None, str] | None = None) -> str:
    parts = [
        f'{_format_attr_key(element, name, element_nsmap=element_nsmap)}="{_escape_attr(value)}"'
        for name, value in element.attrib.items()
    ]
    return " ".join(parts)


def _escape_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def _escape_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _serialize_node(
    element: ET.Element,
    *,
    level: int,
    pretty_print: bool,
    element_nsmap: dict[str | None, str] | None = None,
) -> str:
    indent = "  " * level if pretty_print else ""

    if _is_comment(element):
        return f"{indent}<!--{element.text or ''}-->"

    scoped_nsmap = element_nsmap or nsmap(element)
    tag = _format_tag(element, element_nsmap=scoped_nsmap)
    attrs = _format_attrs(element, element_nsmap=scoped_nsmap)
    open_start = f"<{tag}"
    open_end = f"{open_start} {attrs}>" if attrs else f"{open_start}>"

    children = list(element)
    text = element.text

    if not children and text is not None:
        content = _escape_text(text)
        if attrs:
            return f"{indent}<{tag} {attrs}>{content}</{tag}>"
        return f"{indent}<{tag}>{content}</{tag}>"

    if not children and (text is None or text == ""):
        if attrs:
            return f"{indent}<{tag} {attrs}/>"
        return f"{indent}<{tag}/>"

    if not pretty_print:
        return ET.tostring(element, encoding="unicode")

    lines = [f"{indent}{open_end}"]
    for child in children:
        child_nsmap = scoped_nsmap if not _is_comment(child) else None
        lines.append(_serialize_node(child, level=level + 1, pretty_print=True, element_nsmap=child_nsmap))
    lines.append(f"{indent}</{tag}>")
    return "\n".join(lines)


def tostring(
    tree_or_element: ET.ElementTree | ET.Element,
    *,
    pretty_print: bool = False,
    xml_declaration: bool = False,
    encoding: str = "UTF-8",
    preceding_comment: str | None = None,
) -> bytes | str:
    root = tree_or_element.getroot() if isinstance(tree_or_element, ET.ElementTree) else tree_or_element
    if pretty_print:
        body = _serialize_node(root, level=0, pretty_print=True, element_nsmap=nsmap(root))
    else:
        body = ET.tostring(root, encoding="unicode")

    if encoding == "unicode":
        parts: list[str] = []
        if xml_declaration:
            parts.append("<?xml version='1.0' encoding='UTF-8'?>")
        if preceding_comment is not None:
            parts.append(f"<!--{preceding_comment}-->")
        parts.append(body)
        return "\n".join(parts)

    chunks: list[bytes] = []
    if xml_declaration:
        chunks.append(f"<?xml version='1.0' encoding='{encoding.upper()}'?>".encode())
    if preceding_comment is not None:
        chunks.append(f"<!--{preceding_comment}-->".encode())
    chunks.append(body.encode(encoding))
    result = b"\n".join(chunks)
    if pretty_print and not result.endswith(b"\n"):
        result += b"\n"
    return result


def previous_sibling(element: ET.Element) -> ET.Element | None:
    """Return the node immediately before ``element`` among its parent's children."""
    root = _find_root(element)
    parent = _parent_maps[root].get(element)
    if parent is None:
        return None
    children = list(parent)
    index = children.index(element)
    if index == 0:
        return None
    return children[index - 1]


def child_comments(element: ET.Element) -> list[ET.Element]:
    return [child for child in element if _is_comment(child)]
