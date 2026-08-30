"""Extract narration prose from a production script markdown file.

Rules:
  - Keep only content under the `## Narration` H2, up to the next H2.
  - Drop all markdown headings (###, ####, ...) - they are structural
    (e.g. "Cold open", "Title card"), not spoken words.
  - Strip the `[HUMAN]` production marker but keep the prose after it.
  - Drop bold-label metadata lines (**Status:** ...), list bullets and blockquotes.
  - Normalise inline markdown emphasis and smart quotes so the tokenizer
    does not see stray asterisks or unicode punctuation.

Also usable on a plain .txt file, in which case paragraphs are returned as-is.
"""

import re
import unicodedata

_SMART = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "–": "-", "—": " - ", "―": " - ",
    "…": "...", " ": " ", " ": " ", " ": " ",
}


def _clean_inline(text: str) -> str:
    for bad, good in _SMART.items():
        text = text.replace(bad, good)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)          # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)       # links -> label
    text = re.sub(r"`([^`]*)`", r"\1", text)                   # inline code
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)             # bold
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)    # italic
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = text.replace("\\", "")
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def extract_narration(md: str, section: str = "Narration") -> list[str]:
    """Return a list of narration paragraphs."""
    lines = md.splitlines()

    # Locate the `## <section>` block. If absent, treat the whole file as prose.
    start, end = None, len(lines)
    for i, ln in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(section)}\s*$", ln.strip(), re.I):
            start = i + 1
            break
    if start is None:
        start = 0
    else:
        for j in range(start, len(lines)):
            if re.match(r"^##\s+\S", lines[j]):
                end = j
                break

    body: list[str] = []
    in_fence = False
    for ln in lines[start:end]:
        s = ln.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if s.startswith("#"):            # any heading level -> structural, drop
            continue
        if s.startswith((">", "|", "---", "***")):
            continue
        if re.match(r"^[-*+]\s+", s) or re.match(r"^\d+\.\s+", s):
            continue                      # list items are not narration prose
        if re.match(r"^\*\*[^*]+:\*\*", s):   # **Status:** metadata line
            continue
        s = re.sub(r"^\[HUMAN\]\s*", "", s)   # production marker
        s = re.sub(r"^\[[A-Z][A-Z _-]{2,}\]\s*", "", s)  # other ALLCAPS markers
        body.append(s)

    # Re-join into paragraphs on blank lines.
    paras, cur = [], []
    for s in body:
        if not s:
            if cur:
                paras.append(" ".join(cur))
                cur = []
        else:
            cur.append(s)
    if cur:
        paras.append(" ".join(cur))

    out = []
    for p in paras:
        p = _clean_inline(p)
        if p and re.search(r"[A-Za-z]", p):
            out.append(p)
    return out


def read_script(path: str, section: str = "Narration") -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    if path.lower().endswith((".md", ".markdown")):
        return extract_narration(raw, section)
    paras = [_clean_inline(p) for p in re.split(r"\n\s*\n", raw)]
    return [p for p in paras if p and re.search(r"[A-Za-z]", p)]


if __name__ == "__main__":
    import sys
    ps = read_script(sys.argv[1])
    words = sum(len(p.split()) for p in ps)
    print(f"{len(ps)} paragraphs, {words} words, ~{words/145:.1f} min at 145 WPM\n")
    for i, p in enumerate(ps):
        print(f"[{i:02d}] ({len(p.split())}w) {p[:110]}{'...' if len(p) > 110 else ''}")
