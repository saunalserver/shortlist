"""2026-09-28 location policy: remote jobs doable from Vancouver; undecidable remote kept."""
import pytest

from autojob import db as D
from autojob.models import RawJob
from autojob.prefilter import _all_words, is_local, location_reason
from autojob.settings import get_settings


@pytest.fixture(scope="module")
def loc_cfg():
    return get_settings().get("prefilter.location")


@pytest.mark.parametrize("loc,remote,dropped", [
    ("Remote (office: Paris, France)", None, False),   # office city, residency unknown → keep
    ("Télétravail, FR", None, False),
    ("Germany", True, False),                          # source flag says remote
    ("Remote — United Kingdom, Germany", None, False),
    ("Paris, France", None, True),                     # on-site abroad
    ("Lyon", None, True),
    ("Remote — EMEA", None, True),                     # region = residency rule
    ("Remote - Europe", None, True),
    ("Remote (France) / EMEA", None, True),
    ("Télétravail partiel - Paris", None, True),       # partial remote = on-site abroad
    ("Hybrid/Remote - London", None, True),
    ("Paris, France (occasional remote)", None, True),
    ("Remote (office: Belgrade, Serbia)", True, True),  # not in remote_ok_countries
    ("Remote - India", None, True),
    ("Richmond Hill, ON", None, True),                 # not Richmond, BC
    ("Richmond, BC", None, False),
    ("Remote, Canada", None, False),
])
def test_eu_remote_policy(loc_cfg, loc, remote, dropped):
    assert (location_reason(loc, loc_cfg, remote) is not None) is dropped


def test_all_words_strips_plurals():
    assert _all_words("remote uks and parises", ("uk", "paris")) == ["uk", "paris"]


def test_is_local():
    assert is_local("burnaby, bc") and not is_local("richmond hill, on")


def test_no_fingerprint_keeps_same_title_other_ministry(tmp_path):
    p = tmp_path / "t.db"
    D.init_db(p)
    conn = D.connect(p)
    a = RawJob(url="https://x/1", title="Policy Analyst", company="BC Public Service — Ministry of Health",
               source="bcps", extra={"no_fingerprint": True})
    b = RawJob(url="https://x/2", title="Policy Analyst", company="BC Public Service — Ministry of Finance",
               source="bcps", extra={"no_fingerprint": True})
    new, _, dup_fp = D.insert_jobs(conn, [a, b], None)
    assert len(new) == 2 and dup_fp == 0
