#!/usr/bin/env python3
"""Run isolated ADHD candidate branches on GPT-5.3-Codex-Spark.

The parent Codex model owns judgment and synthesis. This runner only generates
short candidate lists in empty, read-only, ephemeral Codex sessions.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MODEL = "gpt-5.3-codex-spark"
REASONING_EFFORT = "low"
MAX_FRAMES = 8
MAX_IDEAS_PER_FRAME = 10
MAX_CONTEXT_CHARS = 40_000
MAX_PROBLEM_CHARS = 20_000
MAX_PROMPT_CHARS = 12_000
DEFAULT_TIMEOUT_SECONDS = 90
MAX_TIMEOUT_SECONDS = 300
FRAME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class InputError(ValueError):
    """Raised when the orchestration request is invalid."""


@dataclass(frozen=True)
class Frame:
    id: str
    label: str
    prompt: str


@dataclass(frozen=True)
class Request:
    problem: str
    context: str
    frames: tuple[Frame, ...]
    ideas_per_frame: int
    concurrency: int
    timeout_seconds: int


def require_string(value: Any, field: str, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field} must be a non-empty string")
    value = value.strip()
    if len(value) > max_chars:
        raise InputError(f"{field} exceeds {max_chars} characters")
    return value


def require_int(
    value: Any,
    field: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise InputError(f"{field} must be between {minimum} and {maximum}")
    return value


def parse_request(raw: Any) -> Request:
    if not isinstance(raw, dict):
        raise InputError("input must be a JSON object")

    problem = require_string(raw.get("problem"), "problem", MAX_PROBLEM_CHARS)
    context_value = raw.get("context", "")
    if not isinstance(context_value, str):
        raise InputError("context must be a string")
    context = context_value.strip()
    if len(context) > MAX_CONTEXT_CHARS:
        raise InputError(f"context exceeds {MAX_CONTEXT_CHARS} characters")

    raw_frames = raw.get("frames")
    if not isinstance(raw_frames, list) or not raw_frames:
        raise InputError("frames must be a non-empty array")
    if len(raw_frames) > MAX_FRAMES:
        raise InputError(f"frames cannot contain more than {MAX_FRAMES} entries")

    frames: list[Frame] = []
    seen_ids: set[str] = set()
    for index, raw_frame in enumerate(raw_frames):
        if not isinstance(raw_frame, dict):
            raise InputError(f"frames[{index}] must be an object")
        frame_id = require_string(raw_frame.get("id"), f"frames[{index}].id", 64)
        if not FRAME_ID_RE.fullmatch(frame_id):
            raise InputError(
                f"frames[{index}].id must use lowercase letters, digits, and hyphens"
            )
        if frame_id in seen_ids:
            raise InputError(f"duplicate frame id: {frame_id}")
        seen_ids.add(frame_id)
        frames.append(
            Frame(
                id=frame_id,
                label=require_string(
                    raw_frame.get("label"), f"frames[{index}].label", 120
                ),
                prompt=require_string(
                    raw_frame.get("prompt"),
                    f"frames[{index}].prompt",
                    MAX_PROMPT_CHARS,
                ),
            )
        )

    ideas_per_frame = require_int(
        raw.get("ideas_per_frame", 6),
        "ideas_per_frame",
        1,
        MAX_IDEAS_PER_FRAME,
    )
    concurrency = require_int(
        raw.get("concurrency", min(5, len(frames))),
        "concurrency",
        1,
        min(5, len(frames)),
    )
    timeout_seconds = require_int(
        raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        "timeout_seconds",
        10,
        MAX_TIMEOUT_SECONDS,
    )
    return Request(
        problem=problem,
        context=context,
        frames=tuple(frames),
        ideas_per_frame=ideas_per_frame,
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
    )


def output_schema(ideas_per_frame: int) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["ideas"],
        "properties": {
            "ideas": {
                "type": "array",
                "minItems": ideas_per_frame,
                "maxItems": ideas_per_frame,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "rationale"],
                    "properties": {
                        "text": {"type": "string", "minLength": 1, "maxLength": 500},
                        "rationale": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 500,
                        },
                    },
                },
            }
        },
    }


def branch_prompt(request: Request, frame: Frame, attempt: int) -> str:
    retry_note = (
        "\nThe previous response failed execution or schema validation. "
        "Return exactly the requested JSON object."
        if attempt > 1
        else ""
    )
    context = request.context or "(no additional context)"
    return f"""You are in DIVERGENT mode. Generate candidates; do not review them.

Do not call tools, inspect files, browse, edit, rank, score, hedge, or recommend.
The first three obvious answers are banned. Push into structurally different
mechanisms while respecting immutable constraints.

PROBLEM:
{request.problem}

CONTEXT AND IMMUTABLE CONSTRAINTS:
{context}

FRAME ID: {frame.id}
FRAME: {frame.label}
VANTAGE:
{frame.prompt}

Generate exactly {request.ideas_per_frame} distinct ideas. Keep each idea to one
short phrase or sentence. Give one short clause explaining why this frame
surfaces it. Return only the JSON object required by the output schema.
{retry_note}"""


def validate_branch_payload(payload: Any, ideas_per_frame: int) -> list[dict[str, str]]:
    if not isinstance(payload, dict) or set(payload) != {"ideas"}:
        raise ValueError("response must contain only an ideas field")
    ideas = payload["ideas"]
    if not isinstance(ideas, list) or len(ideas) != ideas_per_frame:
        raise ValueError(f"response must contain exactly {ideas_per_frame} ideas")

    normalized: list[dict[str, str]] = []
    for item in ideas:
        if not isinstance(item, dict) or set(item) != {"text", "rationale"}:
            raise ValueError("each idea must contain text and rationale")
        text = item["text"]
        rationale = item["rationale"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("idea text must be non-empty")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("idea rationale must be non-empty")
        normalized.append({"text": text.strip(), "rationale": rationale.strip()})
    return normalized


def compact_error(message: str) -> str:
    clean = " ".join(message.strip().split())
    return clean[-500:] if clean else "unknown Codex execution failure"


def run_branch(
    codex_bin: str,
    request: Request,
    frame: Frame,
    run_dir: Path,
    schema_path: Path,
) -> dict[str, Any]:
    last_error = "unknown failure"
    for attempt in (1, 2):
        output_path = run_dir / f"{frame.id}.attempt-{attempt}.json"
        command = [
            codex_bin,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--model",
            MODEL,
            "--config",
            f'model_reasoning_effort="{REASONING_EFFORT}"',
            "--config",
            'approval_policy="never"',
            "--sandbox",
            "read-only",
            "--skip-git-repo-check",
            "--cd",
            str(run_dir),
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "--color",
            "never",
            "-",
        ]
        try:
            completed = subprocess.run(
                command,
                input=branch_prompt(request, frame, attempt),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=request.timeout_seconds,
                check=False,
                env={**os.environ, "NO_COLOR": "1"},
            )
            if completed.returncode != 0:
                last_error = compact_error(
                    completed.stderr or f"codex exited with {completed.returncode}"
                )
                continue
            if not output_path.is_file():
                last_error = "codex produced no final response file"
                continue
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            ideas = validate_branch_payload(payload, request.ideas_per_frame)
            for index, idea in enumerate(ideas, start=1):
                idea["id"] = f"{frame.id}-{index:02d}"
            return {
                "frame_id": frame.id,
                "frame_label": frame.label,
                "attempts": attempt,
                "ideas": ideas,
            }
        except subprocess.TimeoutExpired:
            last_error = f"timed out after {request.timeout_seconds} seconds"
        except (OSError, json.JSONDecodeError, UnicodeError, ValueError) as error:
            last_error = compact_error(str(error))

    return {
        "frame_id": frame.id,
        "frame_label": frame.label,
        "attempts": 2,
        "error": last_error,
    }


def execute(request: Request) -> tuple[dict[str, Any], bool]:
    codex_bin = shutil.which("codex")
    if not codex_bin:
        raise InputError("codex executable was not found on PATH")

    with tempfile.TemporaryDirectory(prefix="adhd-spark-") as temp_dir:
        run_dir = Path(temp_dir)
        schema_path = run_dir / "branch-output.schema.json"
        schema_path.write_text(
            json.dumps(output_schema(request.ideas_per_frame)),
            encoding="utf-8",
        )

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=request.concurrency
        ) as executor:
            futures = {
                frame.id: executor.submit(
                    run_branch,
                    codex_bin,
                    request,
                    frame,
                    run_dir,
                    schema_path,
                )
                for frame in request.frames
            }
            results = {frame_id: future.result() for frame_id, future in futures.items()}

    ordered = [results[frame.id] for frame in request.frames]
    branches = [result for result in ordered if "ideas" in result]
    failures = [result for result in ordered if "error" in result]
    minimum_successes = min(3, len(request.frames))
    succeeded = len(branches) >= minimum_successes
    output = {
        "generator": {
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "ephemeral": True,
            "sandbox": "read-only",
        },
        "requested_branches": len(request.frames),
        "successful_branches": len(branches),
        "minimum_successful_branches": minimum_successes,
        "branches": branches,
        "failures": failures,
    }
    return output, succeeded


def main() -> int:
    try:
        raw = json.load(sys.stdin)
        request = parse_request(raw)
        output, succeeded = execute(request)
        json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        if not succeeded:
            print(
                "insufficient successful Spark branches; no model fallback was used",
                file=sys.stderr,
            )
            return 2
        return 0
    except (InputError, json.JSONDecodeError) as error:
        print(f"invalid ADHD runner input: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
