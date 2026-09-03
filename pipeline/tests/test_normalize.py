from autojob.normalize import canonical_url, clean_html, fingerprint, normalize_text


def test_canonical_strips_tracking_and_www():
    a = canonical_url("https://www.example.com/jobs/123?utm_source=x&ref=abc&id=9")
    assert a == "https://example.com/jobs/123?id=9"


def test_canonical_linkedin_keeps_only_numeric_id():
    a = canonical_url("https://ca.linkedin.com/jobs/view/operations-coordinator-at-acme-4287654321?trk=public")
    b = canonical_url("https://www.linkedin.com/jobs/view/4287654321/?refId=zzz")
    assert a == b == "https://linkedin.com/jobs/view/4287654321"


def test_canonical_indeed_keeps_jk():
    a = canonical_url("https://ca.indeed.com/viewjob?jk=abc123&from=serp&vjs=3")
    assert a == "https://ca.indeed.com/viewjob?jk=abc123"


def test_fingerprint_ignores_suffixes_and_case():
    assert fingerprint("Operations Coordinator", "Acme Inc.") == fingerprint("operations coordinator", "ACME")
    assert fingerprint("Ops", "Unknown") is None
    assert fingerprint("", "Acme") is None


def test_normalize_text():
    assert normalize_text("Trexity, Ltd.") == "trexity"


def test_clean_html():
    assert clean_html("<p>Hello&nbsp;<b>world</b></p><ul><li>one</li></ul>").startswith("Hello")
    assert clean_html("plain &amp; simple") == "plain & simple"


def test_fingerprint_tolerates_company_spelling_variants():
    assert fingerprint("Coordinator, Research Program & Operations", "The University of British Columbia") == \
        fingerprint("Coordinator, Research Program & Operations", "University of British Columbia")
    assert fingerprint("Business Operations Analyst", "Agentis Capital Advisors") == \
        fingerprint("Business Operations Analyst", "Agentis Capital")
    assert fingerprint("Ops", "Acme") != fingerprint("Ops", "Beta")
