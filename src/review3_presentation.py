"""Preserve a user-supplied PPTX package while replacing slide text only."""
import html
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET
from src import config

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
SHAPE = re.compile(r"<p:sp(?:\s[^>]*)?>.*?</p:sp>", re.S)
PARAGRAPH = re.compile(r"<a:p(?:\s[^>]*)?>.*?</a:p>", re.S)
TEXT = re.compile(r"(<a:t(?:\s[^>]*)?>)(.*?)(</a:t>)", re.S)
BLANK = re.compile(r"\[(?:__|describe[^\]]*)\]")


def paragraph_text(xml):
    return "".join(html.unescape(match.group(2)) for match in TEXT.finditer(xml))


def replace_paragraph(xml, replacement):
    """Retain runs/styles/namespace declarations; put all new text in the first run."""
    count = 0
    def replace(match):
        nonlocal count
        count += 1
        value = html.escape(replacement, quote=False) if count == 1 else ""
        return match.group(1) + value + match.group(3)
    result = TEXT.sub(replace, xml)
    if count == 0:
        raise ValueError("A replacement paragraph needs an existing text run.")
    return result


def inspect_slide(xml):
    root = ET.fromstring(xml)
    shapes = root.findall(".//p:sp", NS)
    matches = list(SHAPE.finditer(xml))
    if len(shapes) != len(matches):
        raise ValueError("Unexpected shape layout; manual review is required.")
    records = []
    for index, (shape, match) in enumerate(zip(shapes, matches)):
        paragraphs = [paragraph_text(item.group()) for item in PARAGRAPH.finditer(match.group())]
        nonempty = [value for value in paragraphs if value.strip()]
        records.append({"index": index, "paragraphs": nonempty})
    body = max(records, key=lambda item: (len(item["paragraphs"]), sum(map(len, item["paragraphs"]))))
    titles = [item for item in records if len(item["paragraphs"]) == 1
              and item["paragraphs"][0] != "FMCG Product Intelligence System"]
    title = next((item for item in titles if 'sz="3600"' in matches[item["index"]].group()), None)
    return records, body, title


def rewrite_slide(xml, title, paragraphs):
    records, body, title_record = inspect_slide(xml)
    if len(paragraphs) != len(body["paragraphs"]) or title_record is None:
        raise ValueError("Slide paragraph/title structure differs from the supplied deck.")
    changes = []
    def shape_replace(match):
        index = shape_replace.index
        shape_replace.index += 1
        targets = paragraphs if index == body["index"] else [title] if index == title_record["index"] else None
        if targets is None:
            return match.group()
        position = 0
        def paragraph_replace(item):
            nonlocal position
            original = paragraph_text(item.group())
            if not original.strip():
                return item.group()
            replacement = targets[position]
            position += 1
            changes.append({"original": original, "replacement": replacement,
                            "original_blank_count": len(BLANK.findall(original))})
            return replace_paragraph(item.group(), replacement)
        rewritten = PARAGRAPH.sub(paragraph_replace, match.group())
        if position != len(targets):
            raise ValueError("Not all replacement paragraphs were written.")
        if index == body["index"]:
            rewritten = re.sub(r'\bsz="2000"', f'sz="{config.REVIEW3_BODY_FONT_SIZE}"', rewritten)
            # Normal autofit keeps the text inside its existing shape.
            rewritten = re.sub(r"<a:bodyPr([^>]*)/>", r"<a:bodyPr\1><a:normAutofit/></a:bodyPr>", rewritten)
            def autofit(item):
                children = re.sub(r"<a:(?:spAutoFit|noAutofit|normAutofit)\b[^>]*/>", "", item.group(2))
                return "<a:bodyPr" + item.group(1) + ">" + children + "<a:normAutofit/></a:bodyPr>"
            rewritten = re.sub(r"<a:bodyPr([^>]*)>(.*?)</a:bodyPr>", autofit, rewritten, flags=re.S)
        return rewritten
    shape_replace.index = 0
    updated = SHAPE.sub(shape_replace, xml)
    ET.fromstring(updated)
    return updated, changes


def build_deck(source, destination, plan):
    if Path(source).resolve() == Path(destination).resolve():
        raise ValueError("The original presentation cannot be overwritten.")
    audit = []
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as filled:
        for item in original.infolist():
            payload = original.read(item.filename)
            match = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", item.filename)
            if match and int(match.group(1)) in plan:
                number = int(match.group(1))
                content = plan[number]
                updated, changes = rewrite_slide(payload.decode("utf-8"), content["title"], content["paragraphs"])
                payload = updated.encode("utf-8")
                audit.append({"slide": number, "title": content["title"], "changes": changes})
            filled.writestr(item, payload)
    return sorted(audit, key=lambda item: item["slide"])
