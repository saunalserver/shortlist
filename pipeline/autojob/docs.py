"""Tailored resume + cover letter generation (LaTeX → PDF).

Neither document is written by the model in LaTeX. Resume: the template is parsed into a
summary paragraph and bullets per section; the model returns a bullet ORDER (and at most one
drop per section) plus a new summary that may only cite facts already in the template
(``summary_is_grounded``). Overflow is fixed by dropping trailing bullets, no model call.
Cover letter: the model returns JSON fields that are escaped and rendered into a fixed template.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autojob.llm import LLM
from autojob.settings import OUTPUT_DIR, Settings

logger = logging.getLogger("autojob")

_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}
_LATEX_RE = re.compile("|".join(re.escape(k) for k in _LATEX_SPECIALS))


def latex_escape(text: str) -> str:
    text = (text or "").replace("\u2014", "--").replace("\u2013", "--").replace("\u2019", "'").replace("\u201c", "``").replace("\u201d", "''")
    return _LATEX_RE.sub(lambda m: _LATEX_SPECIALS[m.group(0)], text)


def output_folder(job: dict[str, Any], base: Path | None = None) -> Path:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    company = re.sub(r"[^\w]+", "_", (job.get("company") or "Unknown")).strip("_")[:40] or "Unknown"
    return (base or OUTPUT_DIR) / day / f"{company}_{job['id']}"


def compile_tex(tex: str, folder: Path, name: str) -> tuple[Path | None, int]:
    """Write ``name``.tex, run pdflatex, return (pdf_path or None, page_count)."""
    folder.mkdir(parents=True, exist_ok=True)
    tex_path = folder / f"{name}.tex"
    tex_path.write_text(tex, encoding="utf-8")
    if not shutil.which("pdflatex"):
        raise RuntimeError("pdflatex not found — install TeX Live (texlive-latex-extra) or TinyTeX")
    for _ in range(2):
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={folder}", str(tex_path)],
            capture_output=True, text=True, timeout=90,
        )
        if proc.returncode != 0:
            tail = proc.stdout[-800:]
            logger.warning("pdflatex failed for %s:\n%s", tex_path.name, tail)
            break
    pdf = folder / f"{name}.pdf"
    for ext in (".aux", ".log", ".out"):
        (folder / f"{name}{ext}").unlink(missing_ok=True)
    if not pdf.exists():
        return None, 0
    return pdf, page_count(pdf)


def page_count(pdf: Path) -> int:
    if shutil.which("pdfinfo"):
        try:
            out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=10).stdout
            m = re.search(r"^Pages:\s+(\d+)", out, re.M)
            if m:
                return int(m.group(1))
        except (subprocess.SubprocessError, OSError):
            pass
    # Fallback: count /Type /Page objects
    data = pdf.read_bytes()
    return max(1, len(re.findall(rb"/Type\s*/Page[^s]", data)))


def _looks_like_full_document(tex: str) -> bool:
    return "\\documentclass" in tex and "\\begin{document}" in tex and "\\end{document}" in tex


_BEGIN_DOC = "\\begin{document}"


def keep_template_preamble(template: str, generated: str) -> str:
    """Return ``generated`` with its preamble replaced by the template's.

    The model is told not to touch packages or geometry, but it still does now and then
    (e.g. ``\\usepackage{setspace}`` → ``setspacing``, which fails to compile). Everything
    before ``\\begin{document}`` carries no job-specific content, so the template's copy is
    always the right one.
    """
    ti, gi = template.find(_BEGIN_DOC), generated.find(_BEGIN_DOC)
    if ti == -1 or gi == -1:
        return generated
    return template[:ti] + generated[gi:]


class DocGenerator:
    def __init__(self, settings: Settings, llm: LLM):
        self.settings = settings
        self.llm = llm
        self.resume_prompt = settings.prompt("resume")
        self.cl_prompt = settings.prompt("cover_letter").replace("{candidate_profile}", settings.candidate_profile())
        self.resume_template = settings.resume_template_path.read_text(encoding="utf-8")
        self.cl_template = settings.cover_letter_template_path.read_text(encoding="utf-8")

    # -- resume -----------------------------------------------------------------
    def _resume_plan(self, job: dict[str, Any], parts: ResumeParts) -> dict[str, Any] | None:
        """Ask the model for a summary + bullet order. Returns None when it cannot be trusted."""
        listing = []
        for sec in parts.sections:
            listing.append(f"## {sec.heading}")
            listing += [f"  [{i}] {latex_to_text(b.text)}" for i, b in enumerate(sec.bullets)]
        user = (f"Current summary:\n{latex_to_text(parts.summary_text)}\n\nBullets by section:\n" + "\n".join(listing)
                + f"\n\nJob to tailor for:\nTitle: {job.get('title')}\nCompany: {job.get('company')}\n"
                f"Job description:\n{job.get('description') or job.get('snippet') or ''}\n"
                f"Why this job was shortlisted: {job.get('fit_reasoning') or ''}")
        try:
            return self.llm.chat_json(self.resume_prompt, user, temperature=0.3)
        except Exception as e:  # noqa: BLE001
            logger.warning("resume plan failed: %s", str(e)[:160])
            return None

    def resume(self, job: dict[str, Any], folder: Path) -> Path | None:
        """Tailored resume = your template with bullets reordered (and at most a few dropped to fit one page)
        plus a rewritten summary that may only use facts already in the template. Wording is never changed."""
        parts = parse_resume(self.resume_template)
        plan = self._resume_plan(job, parts) if parts.sections else None
        orders: dict[str, list[int]] = {}
        summary = None
        if plan:
            summary = str(plan.get("summary") or "").strip()
            if summary and not summary_is_grounded(summary, self.resume_template):
                logger.warning("resume summary mentioned things not in the template — keeping the original summary")
                summary = None
            for sec in plan.get("sections") or []:
                heading = str(sec.get("heading", ""))
                target = next((p for p in parts.sections if p.heading == heading), None)
                if not target:
                    continue
                order = [i for i in (sec.get("order") or []) if isinstance(i, int) and 0 <= i < len(target.bullets)]
                order += [i for i in range(len(target.bullets)) if i not in order]   # anything forgotten goes last
                drop = sec.get("drop")
                if isinstance(drop, int) and drop in order and len(order) > 1:
                    order.remove(drop)
                orders[heading] = list(dict.fromkeys(order))
        else:
            logger.warning("no usable resume plan — compiling the template with its original order")

        tex = render_resume(self.resume_template, parts, summary, orders)
        pdf, pages = compile_tex(tex, folder, "resume")
        # Overflow: drop the last bullet of the longest section, retry (deterministic, no model call).
        for _ in range(4):
            if not (pdf and pages > 1):
                break
            victim = max((s for s in parts.sections if len(orders.get(s.heading, list(range(len(s.bullets))))) > 1),
                         key=lambda s: len(orders.get(s.heading, list(range(len(s.bullets))))), default=None)
            if victim is None:
                break
            cur = orders.get(victim.heading, list(range(len(victim.bullets))))
            orders[victim.heading] = cur[:-1]
            logger.info("resume is %d pages — dropping the last bullet of '%s'", pages, victim.heading)
            tex = render_resume(self.resume_template, parts, summary, orders)
            pdf, pages = compile_tex(tex, folder, "resume")
        if pdf is None:
            logger.warning("resume compile failed — compiling the untouched base template instead")
            pdf, pages = compile_tex(self.resume_template, folder, "resume")
        if pdf and pages > 1:
            logger.warning("resume still %d pages for %s", pages, job.get("company"))
        return pdf

    # -- cover letter -----------------------------------------------------------
    def cover_letter(self, job: dict[str, Any], folder: Path) -> Path | None:
        user = (f"Job title: {job.get('title')}\nCompany: {job.get('company')}\nLocation: {job.get('location') or ''}\n"
                f"Job description:\n{job.get('description') or job.get('snippet') or ''}\n\n"
                f"Why this job was shortlisted: {job.get('fit_reasoning') or ''}\n"
                f"Candidate strengths for this role: {job.get('strengths') or ''}\nKnown gaps: {job.get('gaps') or ''}")
        data = self.llm.chat_json(self.cl_prompt, user, temperature=0.4)
        tex = render_cover_letter(self.cl_template, data, job)
        pdf, pages = compile_tex(tex, folder, "cover_letter")
        if pdf and pages > 1:
            logger.info("cover letter is %d pages — asking the model to shorten", pages)
            shorter = self.llm.chat_json(
                self.cl_prompt,
                user + "\n\nIMPORTANT: your previous draft overflowed to a second page. Cut the total to at most "
                       "150 words: one body paragraph of ≤ 50 words, three bullets of ≤ 12 words each, one-sentence "
                       "opening and closing, no gap sentence unless essential.",
                temperature=0.3,
            )
            tex = render_cover_letter(self.cl_template, shorter, job)
            pdf2, pages2 = compile_tex(tex, folder, "cover_letter")
            if pdf2:
                pdf, pages = pdf2, pages2
        if pdf and pages > 1:
            logger.warning("cover letter still %d pages for %s", pages, job.get("company"))
        return pdf

    # -- both -------------------------------------------------------------------
    def generate(self, job: dict[str, Any], folder: Path | None = None) -> tuple[Path, bool, bool]:
        folder = folder or output_folder(job)
        resume_ok = self.resume(job, folder) is not None
        try:
            cl_ok = self.cover_letter(job, folder) is not None
        except Exception as e:  # noqa: BLE001
            logger.error("cover letter failed for %s: %s", job.get("company"), str(e)[:200])
            cl_ok = False
        return folder, resume_ok, cl_ok


# ---------------------------------------------------------------------------
# Resume structure: the template is data, the model only chooses order + summary
# ---------------------------------------------------------------------------

@dataclass
class Bullet:
    start: int      # offset of "\\resumeItem{" in the template
    end: int        # offset just past the closing brace
    text: str       # bullet content (LaTeX)


@dataclass
class Section:
    heading: str    # first argument of the preceding \\resumeSubheading (e.g. "Operations Specialist (Contract)")
    bullets: list[Bullet]


@dataclass
class ResumeParts:
    summary_span: tuple[int, int] | None
    summary_text: str
    sections: list[Section]


def _balanced_arg(tex: str, open_idx: int) -> int:
    """Given the index of an opening brace, return the index just past its matching closing brace."""
    depth = 0
    i = open_idx
    while i < len(tex):
        c = tex[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(tex)


def _commented(tex: str, idx: int) -> bool:
    """True when position ``idx`` sits on a line that is commented out with an unescaped %."""
    line_start = tex.rfind("\n", 0, idx) + 1
    return re.search(r"(?<!\\)%", tex[line_start:idx]) is not None


def parse_resume(tex: str) -> ResumeParts:
    """Find the summary paragraph and every \\resumeItem{...} grouped under its \\resumeSubheading.
    Commented-out blocks (a Projects section kept for later, say) are ignored."""
    summary_span, summary_text = None, ""
    m = re.search(r"\\section\*?\{Summary\}[^\n]*\n", tex)
    if m:
        start = m.end()
        end_m = re.search(r"\n\s*(\\section|\\begin|%|\\resumeSubHeadingListStart)", tex[start:])
        end = start + end_m.start() if end_m else len(tex)
        summary_span, summary_text = (start, end), tex[start:end].strip()

    sections: list[Section] = []
    for hm in re.finditer(r"\\resumeSubheading\s*\{", tex):
        if _commented(tex, hm.start()):
            continue
        h_end = _balanced_arg(tex, hm.end() - 1)
        heading = tex[hm.end():h_end - 1].strip()
        # bullets belong to this heading until the next \resumeSubheading
        nxt = re.search(r"\\resumeSubheading\s*\{", tex[h_end:])
        block_end = h_end + nxt.start() if nxt else len(tex)
        bullets: list[Bullet] = []
        for bm in re.finditer(r"\\resumeItem\s*\{", tex[h_end:block_end]):
            b_start = h_end + bm.start()
            if _commented(tex, b_start):
                continue
            b_end = _balanced_arg(tex, h_end + bm.end() - 1)
            bullets.append(Bullet(b_start, b_end, tex[h_end + bm.end():b_end - 1]))
        if bullets:
            sections.append(Section(heading, bullets))
    return ResumeParts(summary_span, summary_text, sections)


def render_resume(tex: str, parts: ResumeParts, summary: str | None, orders: dict[str, list[int]]) -> str:
    """Apply bullet orders (indices into each section; missing indices are dropped) and an optional new summary."""
    edits: list[tuple[int, int, str]] = []
    for sec in parts.sections:
        order = orders.get(sec.heading)
        if order is None or order == list(range(len(sec.bullets))):
            continue
        first, last = sec.bullets[0], sec.bullets[-1]
        # keep the original separators between items (usually "\n  ")
        sep = tex[sec.bullets[0].end:sec.bullets[1].start] if len(sec.bullets) > 1 else "\n  "
        body = sep.join(f"\\resumeItem{{{sec.bullets[i].text}}}" for i in order if 0 <= i < len(sec.bullets))
        edits.append((first.start, last.end, body))
    if summary and parts.summary_span:
        edits.append((parts.summary_span[0], parts.summary_span[1], latex_escape(summary) + "\n"))
    out = tex
    for start, end, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        out = out[:start] + repl + out[end:]
    return out


_TEX_CMD = re.compile(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?")


def latex_to_text(tex: str) -> str:
    """Rough LaTeX → plain text for what we show the model."""
    t = tex.replace("\\&", "&").replace("\\$", "$").replace("\\%", "%").replace("\\#", "#").replace("\\_", "_")
    t = t.replace("\\textasciitilde", "~").replace("--", "-")
    t = _TEX_CMD.sub("", t)
    return re.sub(r"\s+", " ", t.replace("{", "").replace("}", "")).strip()


_NUM = re.compile(r"\d[\d,.]*\+?[kK%]?")
_COMMON_CAPS = {"i", "my", "we", "the", "a", "an", "and", "at", "in", "to", "for", "of", "with", "on", "as", "from",
                "english", "french", "bilingual", "operations", "ops", "sql", "python"}


def summary_is_grounded(summary: str, template: str) -> bool:
    """The summary may only cite numbers and proper nouns/tools that already appear in the resume."""
    base = latex_to_text(template).lower()
    base_words = set(re.findall(r"[a-z0-9][a-z0-9+#'-]*", base))
    for num in _NUM.findall(summary):
        if num.rstrip("+kK%").rstrip(".,") not in base:
            logger.info("summary rejected: number %r not in resume", num)
            return False
    words = summary.split()
    for i, w in enumerate(words):
        clean = re.sub(r"'s$", "", w.strip(".,;:()\"'"))
        if not clean or not clean[0].isupper():
            continue
        if i == 0 or words[i - 1].endswith((".", "!", "?", ":")):
            continue   # sentence-initial capital
        parts = [x.lower() for x in re.split(r"[/&-]", clean) if x]
        if any(x not in base_words and x not in _COMMON_CAPS for x in parts):
            logger.info("summary rejected: %r is not in the resume", clean)
            return False
    return True


def render_cover_letter(template: str, data: dict[str, Any], job: dict[str, Any]) -> str:
    body_paras = [p for p in (data.get("body") or []) if isinstance(p, str) and p.strip()]
    if isinstance(data.get("body"), str):
        body_paras = [data["body"]]
    bullets = [b for b in (data.get("bullets") or []) if isinstance(b, dict) and b.get("text")]
    bullet_tex = "\n".join(
        f"    \\item \\textbf{{{latex_escape(str(b.get('label', '')).rstrip(':'))}:}} {latex_escape(str(b['text']))}" for b in bullets
    )
    bullets_block = ("\\begin{itemize}[leftmargin=1.5em, itemsep=0pt]\n" + bullet_tex + "\n\\end{itemize}") if bullet_tex else ""
    gap = latex_escape(str(data.get("gap") or "").strip())
    fields = {
        "OPENING": latex_escape(str(data.get("opening", "")).strip()),
        "BODY": "\n\n".join(latex_escape(p.strip()) for p in body_paras),
        "BULLETS": bullets_block,
        "GAP": gap,
        "CLOSING": latex_escape(str(data.get("closing", "")).strip()),
        "COMPANY": latex_escape(job.get("company") or ""),
        "ROLE": latex_escape(job.get("title") or ""),
        "DATE": datetime.now().strftime("%B %d, %Y"),
    }
    out = template
    for k, v in fields.items():
        out = out.replace("{{" + k + "}}", v)
    # Drop an empty GAP paragraph cleanly
    out = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", out)
    return out
