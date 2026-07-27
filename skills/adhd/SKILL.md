---
name: adhd
description: Run explicit ADHD-mode divergent ideation in Codex. Generate isolated candidate branches with GPT-5.3-Codex-Spark under varied cognitive frames, then use the current parent model to deduplicate, score, cluster, flag traps, and deepen the strongest options. Use only when the user explicitly invokes /adhd, $adhd, ADHD mode, or asks to run this skill. Best for open-ended architecture, design, naming, API/SDK surface, strategy, and fuzzy debugging; skip canonical lookups and bugs with a known root cause.
---

# ADHD

Push past the first obvious answers without paying strong-model cost for every
candidate. Keep generation and judgment mechanically separate:

- Use `gpt-5.3-codex-spark` only for isolated candidate generation.
- Use the current parent model for reframing, review, scoring, clustering,
  trap detection, selection, and deepening.
- Never silently replace Spark with another model.

## Operating contract

- Run only after explicit invocation. For an ordinary brainstorming request,
  answer normally or suggest `$adhd`; do not spend parallel model quota
  implicitly.
- Treat the result as ideation, not authorization to implement, edit files,
  change databases, deploy, or contact external systems.
- Preserve user constraints and applicable repository instructions. Explicit
  invocation bypasses only the cost gate, never safety or approval rules.
- Do not use generic subagent calls for Phase 1 unless the available spawn
  interface can explicitly pin `gpt-5.3-codex-spark`. A prompt that merely says
  "use Spark" is not model routing.

## Pre-flight

Before running the loop:

1. Confirm that the problem is open-ended and admits multiple viable answers.
   If it has one canonical answer or a known root cause, explain that ADHD is a
   poor fit and answer directly.
2. Capture four fields:
   - `original_problem`: the user's actual question.
   - `divergence_problem`: the same job-to-be-done with incidental
     implementation anchors removed.
   - `constraints`: immutable requirements such as compliance, budget,
     deadlines, protocols, compatibility, and explicit user boundaries.
   - `context`: only the concise evidence branches need; do not duplicate a
     repository or long transcript into every branch.
3. Keep the original problem and constraints for Phase 2. Candidate generation
   may remove incidental anchors; review must judge candidates against reality.

## Phase 1: Diverge with Spark

Pick five frames from the table. For code-shaped problems, choose four tagged
`code` or `design` and at least one tagged `wild`. Vary frame selection across
runs.

Resolve this skill's directory, then invoke its runner with JSON on standard
input:

```bash
python3 <skill-dir>/scripts/run_spark_branches.py <<'JSON'
{
  "problem": "the divergence_problem",
  "context": "concise context and immutable constraints",
  "ideas_per_frame": 6,
  "concurrency": 5,
  "frames": [
    {
      "id": "hardware-engineer",
      "label": "hardware engineer",
      "prompt": "the exact vantage prompt from the frame table"
    }
  ]
}
JSON
```

Include every selected frame in `frames`; the one-frame array above only shows
the input shape.

The runner enforces the load-bearing invariants:

- one ephemeral Codex process per branch;
- model `gpt-5.3-codex-spark` with low reasoning effort;
- empty temporary working directory and read-only sandbox;
- no branch-to-branch context;
- no tools or file changes requested from the generator;
- strict JSON output with stable idea IDs;
- one retry for a failed or malformed branch;
- success only when at least three branches return.

If fewer than three branches succeed, stop and report the failure evidence.
Do not fall back to the parent model or another paid model without the user's
approval.

## Phase 2: Focus with the parent model

Keep this phase in the current parent context/model. Do not send it through the
Spark runner.

1. **Normalize.** Merge all successful branches. Remove exact duplicates and
   combine near-duplicates that rely on the same mechanism. Preserve source
   idea IDs for traceability.
2. **Score.** Give every remaining idea:
   - `novelty` from 0 to 10: distance from the obvious default;
   - `viability` from 0 to 10: ability to work or ship under the constraints;
   - `fit` from 0 to 10: how directly it solves the original problem;
   - `strength`: the most concrete advantage over competing ideas;
   - optional `trap`: a specific hidden cost or failure mechanism.
3. **Cluster.** Form three to six clusters by underlying mechanism, not surface
   vocabulary.
4. **Rank.** Compute `novelty × 0.35 + viability × 0.40 + fit × 0.25`. Exclude
   traps from the primary shortlist but report them separately. Keep two to
   four shortlist ideas.
5. **Pick the non-obvious option.** Among viable shortlist ideas, prefer the
   highest `novelty + viability × 0.5`; mark it with `★`.
6. **Deepen the top three.** For each, provide:
   - a four-to-eight-sentence implementation or operating sketch;
   - the load-bearing risk;
   - the first concrete validation step;
   - three to five child ideas, hybrids, or unlocked directions.
7. **Commit to a judgment.** Recommend the most promising option and explain
   why. Do not end with an undifferentiated list.

## Frames

| Frame | Vantage prompt | Tags |
|---|---|---|
| **hardware engineer** | Think in latency, memory layout, and physical constraints. Re-ask this as a hardware or firmware problem. What do bus topology, caches, and timing budgets reveal? | code, wild |
| **regulator** | Audit the system for compliance and failure modes. Ask what must be provable, traceable, or refusable. | design, general |
| **10-year-old** | Approach the problem without software conventions. Generate naive but unencumbered mechanisms. | general, wild |
| **competitor trying to break it** | Try to exploit, fail, or sabotage the obvious solution, then invert each failure into a design idea. | code, design |
| **biology** | Transplant a mechanism from immune systems, neural plasticity, cell signaling, evolution, or ecosystems. | code, wild |
| **logistics** | Apply queues, batching, just-in-time delivery, hub-and-spoke, returns, or last-mile logistics literally. | code, design |
| **game design** | Identify loops, rewards, friction, save states, and speedrun tricks. Treat the user or system as a player. | design, general |
| **markets** | Treat the problem as a market with buyers, sellers, market makers, auctions, futures, or clearing houses. | design, wild |
| **inversion** | Ask how to guarantee the opposite outcome, then negate each answer back into a candidate. | code, design, general |
| **extreme: $0 budget, 1 hour** | Find the crudest version that preserves the load-bearing behavior with no money, no team, and one hour. | code, general |
| **extreme: infinite budget, 10 years** | Explore what becomes possible with effectively unlimited compute, people, and time. | design, wild |
| **remove the load-bearing assumption** | Name the framework, database, request model, file system, network, or other assumption everyone treats as fixed; remove it. | code, design, wild |
| **speedrunner** | Find glitches, skips, out-of-bounds moves, and abusive-but-legal shortcuts. | code, wild |
| **ant colony** | Remove the central planner. Use many simple actors, local rules, and emergent coordination. | code, wild |
| **3am on-call** | Design from the perspective of the engineer paged when it fails. Prefer observable, reversible, runbook-shaped mechanisms. | code, design |

## Output

Render the result in this order:

1. **Brief:** original problem, divergence reframe, immutable constraints, and
   branch success/failure count.
2. **Wide set:** candidates grouped by mechanism with source IDs and score chips
   such as `[N7 V8 F9]`.
3. **Converge:** two to four candidates, selection reasons, `★` non-obvious
   viable pick, and a separate trap list.
4. **Focus:** three deepened candidates with sketch, load-bearing risk, first
   validation step, and child ideas.
5. **Recommendation:** the option to pursue first and the evidence that would
   change that choice.
6. **Provocation:** one wildcard question that opens a genuinely different
   direction.
7. **Provenance:** state that Phase 1 used
   `gpt-5.3-codex-spark` and Phase 2 used the current parent model. Do not call
   Spark "cheaper" unless current pricing evidence establishes that; describe
   it as the fast candidate generator with separate usage limits.

## Calibration

- Default to five frames and six ideas per frame.
- Use three frames and four ideas only when the user explicitly asks for a
  smaller run.
- Stop padding when new candidates repeat existing mechanisms.
- Keep wild ideas visible but clearly separated from viable recommendations.
- Retry only malformed or failed branches. Do not retry merely because a branch
  produced unexciting ideas.

## Anti-patterns

- Simulating all branches sequentially in one context.
- Letting a branch see another branch's candidates.
- Letting Spark score or approve its own output.
- Giving candidate generators repository write access or tools.
- Treating unusual vocabulary as structural novelty.
- Hiding failed branches or silently substituting another model.
- Presenting the output as permission to implement.

## Requirements and attribution

Require Python 3, a local `codex` CLI, and access to
`gpt-5.3-codex-spark`. The runner uses the user's existing Codex
authentication and does not accept API keys.

This Codex adaptation is maintained at
https://github.com/4o4E/adhd and derives from
https://github.com/UditAkhourii/adhd under the MIT License. The companion npm
CLI in the repository remains the upstream Claude Agent SDK implementation; it
does not use this skill's Spark runner.
