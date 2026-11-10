"""A tiny Markdown-to-HTML converter for the guides: headings, paragraphs, lists, quotes, links,
bold, italic, code. Everything is escaped first, so guide files cannot inject markup."""
import re
from html import escape


def front_matter(text):
    """Split '---\\nkey: value\\n---\\nbody' into (dict, body)."""
    meta = {}
    if text.startswith("---"):
        head, _, body = text[3:].partition("\n---")
        for line in head.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        return meta, body.lstrip("\n")
    return meta, text


def inline(s):
    s = escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<em>\1</em>", s)

    def link(m):
        text, url = m.group(1), m.group(2)
        if not re.match(r"^(https?://|/|#|\.\./|\./|\{base\})", url):
            return m.group(0)
        ext = url.startswith("http")
        return f'<a href="{escape(url, quote=True)}"' + (' rel="noopener"' if ext else "") + f">{text}</a>"

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)


def render(text):
    out, para, lst, kind = [], [], [], None

    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    def flush_list():
        nonlocal kind
        if lst:
            out.append(f"<{kind}>" + "".join(f"<li>{inline(i)}</li>" for i in lst) + f"</{kind}>")
            lst.clear()
        kind = None

    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        ul = re.match(r"^\s*[-*]\s+(.*)$", line)
        ol = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if not line.strip():
            flush_para()
            flush_list()
        elif m:
            flush_para()
            flush_list()
            level = len(m.group(1))
            slug = re.sub(r"[^a-z0-9]+", "-", m.group(2).lower()).strip("-")
            out.append(f'<h{level} id="{slug}">{inline(m.group(2))}</h{level}>')
        elif ul or ol:
            flush_para()
            want = "ul" if ul else "ol"
            if kind and kind != want:
                flush_list()
            kind = want
            lst.append((ul or ol).group(1))
        elif line.startswith(">"):
            flush_para()
            flush_list()
            out.append("<blockquote><p>" + inline(line.lstrip("> ").strip()) + "</p></blockquote>")
        elif lst and raw.startswith(("  ", "\t")):
            lst[-1] += " " + line.strip()
        else:
            flush_list()
            para.append(line.strip())
    flush_para()
    flush_list()
    return "\n".join(out)
