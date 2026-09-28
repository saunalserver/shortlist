"""LLM scoring of one job against the candidate profile.

v1 (prompts/scorer.md): the model reads rules and picks the 1–10 score itself.
v2 (prompts/scorer_v2.md): the model only extracts facts — role family, duties match, seniority,
years, contract, location, signals — and ``compute_v2`` turns them into the score with the weights
in ``scoring.v2``. Same facts → same score on any model, and the weights can be tuned against the
user's apply/dismiss history (scripts/eval_scorer.py).
"""
from __future__ import annotations

import logging
from typing import Any

from autojob.llm import LLM, LLMBudgetExceeded
from autojob.settings import Settings

logger = logging.getLogger("autojob")

MIN_FULL_DESCRIPTION = 200


TARGET_FAMILIES = {"operations", "bizops_strategy", "revops_salesops_gtm", "growth_ops", "implementation_onboarding",
                   "business_systems_analysis", "automation_ai_ops", "project_program_coord", "product_ops"}
ADJACENT_FAMILIES = {"customer_success", "supply_chain_procurement", "data_analytics", "finance_ops",
                     "customer_support_ops", "marketing_execution"}
# Off-target families that are never worth a look, whatever the other facts say.
HARD_OFF_FAMILIES = {"software_engineering", "data_science_ml", "hr_recruiting", "trades_field_physical",
                     "healthcare_clinical", "retail_hospitality", "call_center"}
SIGNALS = {"automation_ai", "bilingual_french", "early_career", "tool_overlap", "candidate_domain", "ownership"}
NOT_PERMANENT = {"contract", "temporary", "part_time", "internship"}


class Scorer:
    def __init__(self, settings: Settings, llm: LLM, version: int | None = None):
        self.llm = llm
        self.version = int(version or settings.get("scoring.version", 1) or 1)
        self.weights = settings.get("scoring.v2", {}) or {}
        prompt = "scorer_v2" if self.version == 2 else "scorer"
        self.system_prompt = settings.prompt(prompt).replace("{candidate_profile}", settings.candidate_profile())

    def score(self, job: dict[str, Any]) -> dict[str, Any] | None:
        """Return the parsed verdict dict (plus ``low_confidence`` and ``model``) or None on failure."""
        description = (job.get("description") or "").strip()
        full = len(description) >= MIN_FULL_DESCRIPTION
        text = description or (job.get("snippet") or "")
        label = "Full job description" if full else (
            "Snippet only — the full description could NOT be fetched. Score with LOW CONFIDENCE "
            "and lean on the title, company and location.")
        meta = []
        if job.get("company"):
            meta.append(f"Company: {job['company']}")
        if job.get("location"):
            meta.append(f"Location: {job['location']}")
        if job.get("employment_type"):
            meta.append(f"Employment type: {job['employment_type']}")
        if job.get("salary_min") or job.get("salary_max"):
            meta.append(f"Salary: {job.get('salary_min') or '?'}–{job.get('salary_max') or '?'} {job.get('salary_currency') or ''}")
        if job.get("source"):
            meta.append(f"Source: {job['source']}")
        user = f"Title: {job.get('title', '')}\nURL: {job.get('url', '')}\n" + "\n".join(meta) + f"\n\n{label}:\n{text}"
        try:
            result = self.llm.chat_json(self.system_prompt, user, temperature=0.2)
        except LLMBudgetExceeded:
            raise  # the pipeline stops scoring; remaining jobs stay 'new' for the next run
        except Exception as e:  # noqa: BLE001
            logger.error("scoring failed for '%s': %s", job.get("title"), str(e)[:200])
            return None
        if self.version == 2:
            result.update(compute_v2(result, self.weights))
        try:
            result["fit_score"] = max(1, min(10, int(result.get("fit_score", 0))))
        except (TypeError, ValueError):
            result["fit_score"] = 1
        result["skip"] = bool(result.get("skip", False))
        result["strengths"] = [str(s) for s in (result.get("strengths") or [])][:3]
        result["gaps"] = [str(g) for g in (result.get("gaps") or [])][:3]
        result["low_confidence"] = not full
        result["model"] = self.llm.last_model
        return result


def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def compute_v2(facts: dict[str, Any], w: dict[str, Any]) -> dict[str, Any]:
    """Score + skip from extracted facts. Returns fit_score, skip, skip_reason, score_breakdown, facts."""
    f = {k: v for k, v in facts.items() if k not in ("fit_score", "skip", "skip_reason")}
    family = str(f.get("role_family") or "").strip().lower()
    seniority = str(f.get("seniority") or "").strip().lower()
    emp_type = str(f.get("employment_type") or "unknown").strip().lower()
    employer = str(f.get("employer_type") or "unknown").strip().lower()
    signals = sorted({str(x).strip().lower() for x in (f.get("signals") or [])} & SIGNALS)
    missing = [str(m) for m in (f.get("missing_must_haves") or []) if str(m).strip()]
    match = _int(f.get("duties_match"))
    match = 1 if match is None else max(0, min(3, match))
    years = _int(f.get("years_required"))

    fam_w = w.get("family_base", {}) or {}
    tier = "target" if family in TARGET_FAMILIES else "adjacent" if family in ADJACENT_FAMILIES else "off"
    parts: list[tuple[str, int]] = [(f"{tier}:{family or '?'}", int(fam_w.get(tier, {"target": 6, "adjacent": 4}.get(tier, 2))))]
    parts.append((f"duties {match}", int((w.get("duties_match") or {}).get(match, 0))))
    if seniority:
        parts.append((seniority, int((w.get("seniority") or {}).get(seniority, 0))))
    if f.get("people_manager") is True:
        parts.append(("manages people", int(w.get("people_manager", -2))))
    if years is not None:
        yw = w.get("years_required") or {}
        key = "le2" if years <= 2 else "eq3" if years == 3 else "eq4" if years == 4 else "ge5"
        parts.append((f"{years}y required", int(yw.get(key, 0))))
    if missing:
        parts.append((f"{len(missing)} missing must-have", max(-2, int(w.get("missing_must_have", -1)) * len(missing))))
    if signals:
        parts.append(("+".join(signals), min(len(signals), int(w.get("signals_cap", 2)))))
    parts.append((f"employer {employer}", int((w.get("employer") or {}).get(employer, 0))))
    score = max(1, min(10, sum(v for _, v in parts)))

    reasons = []
    if f.get("location_ok") is False:
        reasons.append(f"location: {f.get('location_note') or 'not doable from Vancouver'}")
    if emp_type in NOT_PERMANENT:
        reasons.append(f"employment type: {emp_type}")
    if seniority in ("senior", "lead", "executive"):
        reasons.append(f"seniority: {seniority}")
    if years is not None and years >= 5:
        reasons.append(f"{years}+ years required")
    if family in HARD_OFF_FAMILIES:
        reasons.append(f"role family: {family}")
    if employer == "agency_or_hidden":
        reasons.append("agency / hidden employer")
    if f.get("careers_index") is True:
        reasons.append("careers index page, not a posting")
    if f.get("citizenship_required") is True:
        reasons.append("citizenship / PR required")
    if reasons:
        score = min(score, 3)
    return {
        "fit_score": score,
        "skip": bool(reasons),
        "skip_reason": "; ".join(reasons) or None,
        "score_breakdown": ", ".join(f"{k} {v:+d}" for k, v in parts) + f" = {score}",
        "facts": f,
    }
