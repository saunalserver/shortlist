from autojob.sources.yc import candidate_slugs, slug_from_domain, slug_from_name


def test_domain_slugs():
    assert slug_from_domain("https://www.mystartup.io") == "mystartup"
    assert slug_from_domain("https://careers.mystartup.io") == "mystartup"
    assert slug_from_domain("https://www.mystartup.co.uk") == "mystartup"
    assert slug_from_domain("") == ""


def test_name_slug():
    assert slug_from_name("Llama's AI Corp.") == "llamas-ai-corp"


def test_candidates_dedupe():
    assert candidate_slugs("mystartup", "Mystartup", "https://mystartup.com") == ["mystartup"]
    assert len(candidate_slugs("a", "B C", "https://d.io")) == 3
