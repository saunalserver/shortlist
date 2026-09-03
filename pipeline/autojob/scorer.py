"""LLM scoring of one job against the candidate profile."""
from __future__ import annotations

import logging
from typing import Any

from autojob.llm import LLM, LLMBudgetExceeded
from autojob.settings import Settings

logger = logging.getLogger("autojob")

MIN_FULL_DESCRIPTION = 200


class Scorer:
    def __init__(self, settings: Settings, llm: LLM):
        self.llm = llm
        self.system_prompt = settings.prompt("scorer").replace("{candidate_profile}", settings.candidate_profile())

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
