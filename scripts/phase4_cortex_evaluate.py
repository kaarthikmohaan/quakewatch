"""Preview or run bounded Cortex briefs over saved public SQL aggregates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.phase4_cortex_aggregates import OUTPUT_PATH as AGGREGATES_PATH
from scripts.phase4_usage import checked_admin_profile


MODEL = "claude-haiku-4-5"
MAX_NEW_CALLS = 9
MAX_OUTPUT_TOKENS = 120
BRIEFS_PATH = AGGREGATES_PATH.parent / "phase4_briefs.json"
SITE_NAMES = {
    "seattle": "Seattle",
    "san-francisco": "San Francisco",
    "anchorage": "Anchorage",
}


def load_cases(path: Path = AGGREGATES_PATH) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    cases = document["cases"]
    if document["case_count"] != 10 or len(cases) != 10:
        raise RuntimeError("expected exactly ten saved SQL aggregates")
    if len({case["CASE_ID"] for case in cases}) != 10:
        raise RuntimeError("duplicate saved case ID")
    for case in cases:
        if case["SITE_KEY"] not in SITE_NAMES or case["RADIUS_KM"] != 250:
            raise RuntimeError("unexpected public site or radius")
        if case["INPUT_SHA256"] != hashlib.sha256(
            json.dumps({k: v for k, v in case.items() if k != "INPUT_SHA256"},
                       sort_keys=True, default=str).encode()
        ).hexdigest():
            raise RuntimeError(f"aggregate hash mismatch: {case['CASE_ID']}")
    return cases


def prompt_for(case: dict) -> str:
    site = SITE_NAMES[case["SITE_KEY"]]
    return (
        "Write exactly one sentence with these SQL facts. Use the form: "
        "'In the modeled [site] sample for [window], [count] events were "
        "within 250 km; the nearest event [ID] was [distance] km from "
        "[site], magnitude [magnitude], source status [status], and its "
        "source record was [age] hours old at the SQL check time.' "
        "Use only the supplied values. No risk, shaking, damage, advice, "
        "or complete-coverage claim. Do not add a heading.\n"
        f"site={site}; window={case['START_UTC']} to {case['END_UTC']}; "
        f"count={case['EVENT_COUNT']}; radius=250 km; "
        f"nearest ID={case['NEAREST_EVENT_ID']}; "
        f"distance from {site}={case['NEAREST_DISTANCE_KM']} km; "
        f"magnitude={case['NEAREST_MAGNITUDE']}; "
        f"source status={case['NEAREST_SOURCE_STATUS']}; "
        f"age at SQL check={case['NEAREST_RECORD_AGE_HOURS']} hours."
    )


def check_brief(message: str, case: dict) -> list[str]:
    """Strict local screen; accepted text still needs human comparison to SQL."""
    problems = []
    site = SITE_NAMES[case["SITE_KEY"]]
    lower = message.lower().replace(",", "")
    required = {
        "site": site,
        "event count": f"{case['EVENT_COUNT']} events",
        "radius": "250 km",
        "event ID": case["NEAREST_EVENT_ID"],
        "distance": f"{case['NEAREST_DISTANCE_KM']} km from {site}",
        "magnitude": f"magnitude {case['NEAREST_MAGNITUDE']}",
        "source status": str(case["NEAREST_SOURCE_STATUS"]),
        "record age": f"{case['NEAREST_RECORD_AGE_HOURS']} hours",
        "sample scope": "modeled",
    }
    for label, expected in required.items():
        if expected.lower() not in lower:
            problems.append(f"missing or misstated {label}")
    if re.search(r"\b(risk|shaking|damage|evacuat\w*|shelter|safe|danger|should|alert)\b", lower):
        problems.append("hazard or action language")
    if re.search(r"\b(complete|all|every|guaranteed)\s+(source\s+)?coverage\b", lower):
        problems.append("unsupported coverage claim")
    if re.search(r"\baway from\s+" + re.escape(str(case["NEAREST_EVENT_ID"]).lower()) + r"\b", lower):
        problems.append("distance anchored to event ID")
    if not message.rstrip().endswith("."):
        problems.append("incomplete ending")
    return problems


def read_cache(path: Path = BRIEFS_PATH) -> dict:
    if not path.exists():
        return {"model": MODEL, "results": {}}
    cache = json.loads(path.read_text(encoding="utf-8"))
    if cache.get("model") != MODEL or not isinstance(cache.get("results"), dict):
        raise RuntimeError("unexpected Cortex cache format or model")
    return cache


def write_cache(cache: dict, path: Path = BRIEFS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(cache, indent=2, sort_keys=True, default=str) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def pending_cases(cases: list[dict], cache: dict) -> list[dict]:
    # The Seattle day already used its one allowed retry with llama3.1-8b.
    return [case for case in cases if case["CASE_ID"] != "seattle-day"
            and case["INPUT_SHA256"] not in cache["results"]]


def retry_case(cases: list[dict], cache: dict, case_id: str) -> dict:
    matches = [case for case in cases if case["CASE_ID"] == case_id
               and case_id != "seattle-day"]
    if len(matches) != 1:
        raise RuntimeError("retry case is not one of the nine eligible cases")
    case = matches[0]
    previous = cache["results"].get(case["INPUT_SHA256"])
    if not previous or previous["status"] not in {"rejected", "error"}:
        raise RuntimeError("retry requires a completed rejected or error attempt")
    if "retry" in previous:
        raise RuntimeError("this aggregate has already used its one retry")
    return case


def execute(retry_case_id: str | None = None) -> dict:
    import snowflake.connector

    cases = load_cases()
    cache = read_cache()
    pending = ([retry_case(cases, cache, retry_case_id)] if retry_case_id
               else pending_cases(cases, cache))
    if len(pending) > (1 if retry_case_id else MAX_NEW_CALLS):
        raise RuntimeError("pending Cortex calls exceed the reviewed cap")
    if not pending:
        return {"status": "cached", "new_calls": 0, "results_path": str(BRIEFS_PATH)}
    for case in pending:
        if case["EVENT_COUNT"] <= 0 or case["NEAREST_MAGNITUDE"] is None:
            raise RuntimeError(f"case needs deterministic fallback: {case['CASE_ID']}")
        if len(prompt_for(case)) > 1200:
            raise RuntimeError(f"prompt exceeds 1200 characters: {case['CASE_ID']}")
    profile = checked_admin_profile(Path.home() / ".snowflake" / "config.toml")
    profile["role"] = "QUAKEWATCH_ROLE"
    new_calls = 0
    with snowflake.connector.connect(**profile, warehouse="QUAKEWATCH_WH") as connection:
        with connection.cursor() as cursor:
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            if cursor.fetchone() != ("QUAKEWATCH_ROLE", "QUAKEWATCH_WH"):
                raise RuntimeError("unexpected Cortex role or warehouse")
            for case in pending:
                prompt = prompt_for(case)
                # Persist an attempt marker first. If the process loses the
                # response, a rerun cannot silently duplicate a paid call.
                marker = {
                    "case_id": case["CASE_ID"], "model": MODEL,
                    "input_sha256": case["INPUT_SHA256"],
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "status": "attempt_started",
                    "fallback": "Use saved SQL aggregate until result is reviewed.",
                }
                if retry_case_id:
                    cache["results"][case["INPUT_SHA256"]]["retry"] = marker
                else:
                    cache["results"][case["INPUT_SHA256"]] = marker
                write_cache(cache)
                try:
                    cursor.execute(
                        "SELECT AI_COMPLETE(model => 'claude-haiku-4-5', prompt => %s, "
                        "model_parameters => {'temperature': 0, 'max_tokens': 120}, "
                        "show_details => TRUE)",
                        (prompt,),
                    )
                    query_id = cursor.sfqid
                    details = cursor.fetchone()[0]
                    if isinstance(details, str):
                        details = json.loads(details)
                    brief = details.get("choices", [{}])[0].get("messages", "")
                    problems = check_brief(brief, case)
                    result = {
                        "case_id": case["CASE_ID"],
                        "model": MODEL,
                        "input_sha256": case["INPUT_SHA256"],
                        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                        "query_id": query_id,
                        "usage": details.get("usage"),
                        "brief": brief,
                        "status": "rejected" if problems else "needs_human_fact_check",
                        "problems": problems,
                        "fallback": None if not problems else "Use saved SQL aggregate.",
                    }
                except snowflake.connector.errors.ProgrammingError as error:
                    result = {
                        "case_id": case["CASE_ID"], "model": MODEL,
                        "input_sha256": case["INPUT_SHA256"],
                        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                        "status": "error", "snowflake_error_code": error.errno,
                        "fallback": "Use saved SQL aggregate.",
                    }
                new_calls += 1
                if retry_case_id:
                    cache["results"][case["INPUT_SHA256"]]["retry"] = result
                else:
                    cache["results"][case["INPUT_SHA256"]] = result
                write_cache(cache)
                if result["status"] == "error":
                    break
    return {
        "status": "saved", "new_calls": new_calls,
        "results_path": str(BRIEFS_PATH),
        "counts": {status: sum(r.get("retry", r)["status"] == status
                               for r in cache["results"].values())
                   for status in ("needs_human_fact_check", "rejected", "error")},
        "note": "Local checks cannot certify factuality; compare every brief with the saved SQL row.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run approved paid Cortex calls")
    parser.add_argument("--retry-case", help="one separately approved retry for this rejected case")
    args = parser.parse_args()
    cases = load_cases()
    cache = read_cache()
    pending = ([retry_case(cases, cache, args.retry_case)] if args.retry_case
               else pending_cases(cases, cache))
    if args.execute:
        print(json.dumps(execute(args.retry_case), indent=2, sort_keys=True))
    else:
        print(f"Preview only: model={MODEL}; saved cases={len(cases)}; "
              f"pending calls={len(pending)}; max output tokens/call={MAX_OUTPUT_TOKENS}")
        print("Seattle day is excluded: its one retry was already used.")
        print(f"Results if approved: {BRIEFS_PATH} (ignored by Git)")


if __name__ == "__main__":
    main()
