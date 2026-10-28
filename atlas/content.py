from __future__ import annotations

import re
from html import escape
from urllib.parse import quote, unquote, urljoin, urlsplit

import bleach
from bs4 import BeautifulSoup

ALLOWED_TAGS = {
    "div", "section", "p", "span", "a", "h2", "h3", "h4", "h5", "h6",
    "b", "strong", "i", "em", "small", "sup", "sub", "br", "hr", "blockquote",
    "ul", "ol", "li", "dl", "dt", "dd", "table", "caption", "thead", "tbody",
    "tfoot", "tr", "th", "td", "abbr", "code", "pre", "details", "summary",
    "figure", "figcaption", "time",
}
ALLOWED_ATTRS = {
    "*": ["id", "lang", "dir", "class"],
    "a": ["href", "target", "rel", "title"],
    "ol": ["start"], "li": ["value"],
    "th": ["colspan", "rowspan", "scope"], "td": ["colspan", "rowspan"],
    "time": ["datetime"], "abbr": ["title"],
}
FOCUS_TERMS = re.compile(
    r"用途|应用|利用|食用|烹|营养|风味|氣味|气味|味道|种类|栽培|分布|产地|歷史|历史|名称|種類|"
    r"culinar|uses|use in|cultivat|history|etymol|flavo|aroma|distribution|variet|description", re.I
)


def plain(value: str) -> str:
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def safe_url(value: str, base: str = "") -> str | None:
    value = value.strip()
    absolute = urljoin(base, value)
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return None
    return absolute


def repair_fragments(markup: str, source_url: str, prefix: str) -> str:
    soup = BeautifulSoup(markup, "html.parser")
    ids = {x["id"] for x in soup.find_all(id=True)}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#") and unquote(href[1:]) not in ids:
            anchor = unquote(href[1:])
            if anchor.startswith(prefix):
                anchor = anchor[len(prefix):]
            a["href"] = source_url + "#" + quote(anchor)
            a["target"] = "_blank"
            a["rel"] = ["noopener", "noreferrer"]
    return str(soup)


def article_content(raw: str, source_url: str, namespace: str) -> dict:
    """Clean source HTML, preserve hyperlinks and separate an extractive focus view."""
    soup = BeautifulSoup(raw, "html.parser")
    container = soup.select_one(".mw-parser-output") or soup
    for bad in container.select("script,style,iframe,object,embed,form,input,button,textarea,svg,math,.mw-editsection,.navbox,.vertical-navbox,.ambox,.metadata,.sistersitebox,.noprint,.mw-empty-elt,.shortdescription,.toc"):
        bad.decompose()
    # Article illustrations live in the dedicated, credited image collection.
    for image in container.find_all("img"):
        image.decompose()
    prefix = namespace + "-"
    for tag in container.find_all(True):
        if tag.has_attr("id"):
            tag["id"] = prefix + unquote(tag["id"])
        if tag.name == "a" and tag.has_attr("href"):
            href = tag["href"]
            if href.startswith("#"):
                tag["href"] = "#" + prefix + unquote(href[1:])
            else:
                absolute = safe_url(href, source_url)
                if absolute:
                    tag["href"] = absolute
                    tag["target"] = "_blank"
                    tag["rel"] = ["noopener", "noreferrer"]
                else:
                    del tag["href"]
        # Keep only a small set of semantic classes. Remote CSS never controls the reader.
        classes = [x for x in tag.get("class", []) if x in {"reference", "references", "mw-headline", "reflist", "thumbcaption", "infobox", "wikitable"}]
        if classes:
            tag["class"] = classes
        elif tag.has_attr("class"):
            del tag["class"]
    clean = bleach.clean(str(container), tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols=["http", "https"], strip=True, strip_comments=True)
    full_soup = BeautifulSoup(clean, "html.parser")
    body = full_soup.find("div", recursive=False) or full_soup
    # Parsoid may nest content in sections; flatten only these structural sections.
    for sec in list(body.find_all("section")):
        sec.unwrap()
    for wrapper in list(body.find_all("div")):
        if wrapper.find(["h2", "h3"], recursive=False):
            wrapper.unwrap()
    full = str(body)
    paragraphs = [p for p in body.find_all("p") if not p.find_parent(["table", "li"]) and len(p.get_text(strip=True)) > 25]
    summary = "\n".join(p.get_text(" ", strip=True) for p in paragraphs[:2])
    intro = []
    sections: list[tuple[str, list[str]]] = []
    current = None
    for node in body.children:
        if getattr(node, "name", None) in {"h2", "h3"}:
            current = (node.get_text(" ", strip=True), [str(node)])
            sections.append(current)
        elif current:
            current[1].append(str(node))
        elif getattr(node, "name", None) != "table":
            intro.append(str(node))
    selected = [str(x) for x in intro]
    matched = 0
    for heading, nodes in sections:
        if FOCUS_TERMS.search(heading):
            selected.extend(nodes)
            matched += 1
    if not matched:
        selected = [str(p) for p in paragraphs[:6]]
    focus = repair_fragments("".join(selected), source_url, prefix)
    full = repair_fragments(full, source_url, prefix)
    def headings(markup: str):
        parsed = BeautifulSoup(markup, "html.parser")
        result = []
        for h in parsed.find_all(["h2", "h3"]):
            target = h.get("id") or (h.find(id=True) or {}).get("id")
            if target:
                result.append({"title": h.get_text(" ", strip=True), "id": target, "level": int(h.name[1])})
        return result[:70]
    return {"html": full, "focus_html": focus, "summary": summary, "toc": headings(full), "focus_toc": headings(focus), "focus_section_count": matched}


def translation_blocks(markup: str, limit: int = 8) -> list[dict]:
    soup = BeautifulSoup(markup, "html.parser")
    blocks = []
    for p in soup.find_all("p"):
        if p.find_parent(["table", "li"]) or len(p.get_text(strip=True)) < 30:
            continue
        clone = BeautifulSoup(str(p), "html.parser").p
        links = {}
        for i, a in enumerate(list(clone.find_all("a"))):
            token = f"⟪LINK_{i}⟫"
            links[token] = str(a)
            a.replace_with(token)
        text = clone.get_text(" ", strip=True)
        if len(text) > 2200:
            continue
        blocks.append({"id": f"paragraph-{len(blocks)}", "text": text, "html": str(p), "links": links})
        if len(blocks) >= limit:
            break
    return blocks


def translated_html(text: str, links: dict[str, str]) -> str:
    # Only source anchors survive. Model text is escaped, including any HTML it creates.
    for token in links:
        if text.count(token) != 1:
            raise ValueError("译文未完整保留链接占位标记，请重试或查看原文。")
    if set(re.findall(r"⟪LINK_\d+⟫", text)) != set(links):
        raise ValueError("译文包含无法匹配的链接标记。")
    value = escape(text).replace("\n", "<br>")
    for token, anchor in links.items():
        anchor_soup = BeautifulSoup(anchor, "html.parser")
        for element in anchor_soup.find_all(id=True):
            del element["id"]
        value = value.replace(escape(token), str(anchor_soup))
    return "<p>" + value + "</p>"
