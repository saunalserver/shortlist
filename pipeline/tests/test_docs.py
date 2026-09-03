from autojob.docs import latex_escape, render_cover_letter


def test_latex_escape():
    assert latex_escape("R&D at 100% — $5 #1 under_score") == r"R\&D at 100\% -- \$5 \#1 under\_score"


def test_render_cover_letter_fills_placeholders():
    tmpl = "HEAD\n{{OPENING}}\n\n{{BODY}}\n\n{{BULLETS}}\n\n{{GAP}}\n\n{{CLOSING}}\nEND"
    data = {"opening": "Hi & hello", "body": ["p1", "p2"], "bullets": [{"label": "Data:", "text": "SQL_1"}],
            "gap": "", "closing": "Bye"}
    out = render_cover_letter(tmpl, data, {"company": "Acme", "title": "Ops"})
    assert "Hi \\& hello" in out
    assert "\\item \\textbf{Data:} SQL\\_1" in out
    assert "p1\n\np2" in out
    assert "{{" not in out


def test_keep_template_preamble_restores_packages():
    from autojob.docs import keep_template_preamble

    template = "\\documentclass{article}\n\\usepackage{setspace}\n\\begin{document}\nORIGINAL\n\\end{document}"
    generated = "\\documentclass{article}\n\\usepackage{setspacing}\n\\begin{document}\nTAILORED\n\\end{document}"
    out = keep_template_preamble(template, generated)
    assert "setspacing" not in out and "\\usepackage{setspace}" in out and "TAILORED" in out
    assert keep_template_preamble(template, "no document here") == "no document here"


TEMPLATE = r"""\documentclass{article}
\begin{document}
\section*{Summary}
Ops specialist. Ran \$100K USD/month in spend with Everflow. Bilingual English/French.

\section*{Work Experience}
\resumeSubHeadingListStart
\resumeSubheading
{Growth Operations Specialist (Contract)}{Jun 2026 -- Aug 2026}
{Peakflow}{Vancouver, BC}
\resumeItemListStart
  \resumeItem{Managed \textasciitilde\$100K USD/month across 12+ affiliates.}
  \resumeItem{Owned the attribution stack in Everflow.}
  \resumeItem{Ran 15+ A/B experiments.}
\resumeItemListEnd
\resumeSubheading
{Operations Specialist}{Oct 2025 -- Mar 2026}
{Trexity}{Vancouver}
\resumeItemListStart
  \resumeItem{Built workflows in Make and n8n.}
  \resumeItem{Dashboards in BigQuery.}
\resumeItemListEnd
\resumeSubHeadingListEnd
\end{document}
"""


def test_parse_resume_finds_summary_and_bullets():
    from autojob.docs import parse_resume

    parts = parse_resume(TEMPLATE)
    assert parts.summary_text.startswith("Ops specialist.")
    assert [s.heading for s in parts.sections] == ["Growth Operations Specialist (Contract)", "Operations Specialist"]
    assert [len(s.bullets) for s in parts.sections] == [3, 2]
    assert parts.sections[0].bullets[0].text.startswith("Managed")


def test_render_resume_reorders_drops_and_never_rewrites():
    from autojob.docs import parse_resume, render_resume

    parts = parse_resume(TEMPLATE)
    out = render_resume(TEMPLATE, parts, "New summary with 15+ experiments.", {"Growth Operations Specialist (Contract)": [2, 0]})
    body = out.split(r"\resumeItemListStart")[1]
    assert body.index("Ran 15+ A/B experiments.") < body.index("Managed")
    assert "Owned the attribution stack" not in out          # dropped
    assert "Built workflows in Make and n8n." in out          # untouched section
    assert "New summary with 15+ experiments." in out and "Ops specialist. Ran" not in out
    assert out.count(r"\resumeItem{") == 4


def test_summary_guard_rejects_new_numbers_and_tools():
    from autojob.docs import summary_is_grounded

    assert summary_is_grounded("Ops specialist who ran $100K USD/month with Everflow and 15+ experiments.", TEMPLATE)
    assert not summary_is_grounded("Ops specialist with Salesforce experience.", TEMPLATE)      # tool not in resume
    assert not summary_is_grounded("Managed $250K in spend.", TEMPLATE)                          # number not in resume
    assert summary_is_grounded("Bilingual English/French. Ran experiments with Make.", TEMPLATE)  # sentence-initial caps ok


def test_parse_resume_ignores_commented_blocks():
    from autojob.docs import parse_resume

    tex = TEMPLATE.replace("\\end{document}", """% \\resumeSubheading{SprayOps}{2026}{SaaS}{}
% \\resumeItemListStart
%   \\resumeItem{...}
% \\resumeItemListEnd
\\end{document}""")
    parts = parse_resume(tex)
    assert [s.heading for s in parts.sections] == ["Growth Operations Specialist (Contract)", "Operations Specialist"]
