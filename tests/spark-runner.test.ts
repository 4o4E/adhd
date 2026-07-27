import assert from "node:assert/strict";
import { chmod, mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const runner = resolve("skills/adhd/scripts/run_spark_branches.py");

const request = {
  problem: "Design a queue that degrades gracefully under burst load.",
  context: "Keep ordering per tenant.",
  ideas_per_frame: 2,
  concurrency: 3,
  frames: [
    { id: "hardware", label: "hardware", prompt: "Think in caches and buses." },
    { id: "biology", label: "biology", prompt: "Use immune system mechanisms." },
    { id: "markets", label: "markets", prompt: "Use auctions and clearing." },
  ],
};

async function fakeCodexEnvironment() {
  const directory = await mkdtemp(join(tmpdir(), "adhd-runner-test-"));
  const binDirectory = join(directory, "bin");
  const logPath = join(directory, "codex.log");
  await mkdir(binDirectory);
  const codexPath = join(binDirectory, "codex");
  await writeFile(
    codexPath,
    `#!/usr/bin/env node
const fs = require("node:fs");
const args = process.argv.slice(2);
const prompt = fs.readFileSync(0, "utf8");
const frame = /FRAME ID: ([a-z0-9-]+)/.exec(prompt)?.[1] ?? "unknown";
fs.appendFileSync(process.env.FAKE_CODEX_LOG, JSON.stringify({ args, frame }) + "\\n");
if (process.env.FAKE_FAIL_FRAME === frame) process.exit(7);
const output = args[args.indexOf("--output-last-message") + 1];
const count = Number(/Generate exactly (\\d+)/.exec(prompt)?.[1] ?? 1);
const ideas = Array.from({ length: count }, (_, index) => ({
  text: frame + " idea " + (index + 1),
  rationale: "frame-specific mechanism"
}));
fs.writeFileSync(output, JSON.stringify({ ideas }));
`,
    "utf8",
  );
  await chmod(codexPath, 0o755);
  return {
    directory,
    logPath,
    env: {
      ...process.env,
      PATH: `${binDirectory}:${process.env.PATH ?? ""}`,
      FAKE_CODEX_LOG: logPath,
    },
  };
}

test("pins Spark in isolated read-only sessions and emits stable IDs", async () => {
  const fixture = await fakeCodexEnvironment();
  try {
    const result = spawnSync("python3", [runner], {
      input: JSON.stringify(request),
      encoding: "utf8",
      env: fixture.env,
    });
    assert.equal(result.status, 0, result.stderr);

    const payload = JSON.parse(result.stdout);
    assert.equal(payload.generator.model, "gpt-5.3-codex-spark");
    assert.equal(payload.generator.reasoning_effort, "low");
    assert.equal(payload.successful_branches, 3);
    assert.deepEqual(
      payload.branches.flatMap((branch: { ideas: Array<{ id: string }> }) =>
        branch.ideas.map((idea) => idea.id),
      ),
      [
        "hardware-01",
        "hardware-02",
        "biology-01",
        "biology-02",
        "markets-01",
        "markets-02",
      ],
    );

    const calls = (await readFile(fixture.logPath, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    assert.equal(calls.length, 3);
    for (const call of calls) {
      assert.deepEqual(call.args.slice(0, 2), ["exec", "--ephemeral"]);
      assert.ok(call.args.includes("gpt-5.3-codex-spark"));
      assert.ok(call.args.includes('model_reasoning_effort="low"'));
      assert.ok(call.args.includes('approval_policy="never"'));
      assert.ok(call.args.includes("read-only"));
      assert.ok(call.args.includes("--ignore-user-config"));
      assert.ok(call.args.includes("--ignore-rules"));
    }
  } finally {
    await rm(fixture.directory, { recursive: true, force: true });
  }
});

test("retries failures and refuses to continue below the success threshold", async () => {
  const fixture = await fakeCodexEnvironment();
  try {
    const result = spawnSync("python3", [runner], {
      input: JSON.stringify(request),
      encoding: "utf8",
      env: { ...fixture.env, FAKE_FAIL_FRAME: "markets" },
    });
    assert.equal(result.status, 2);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.successful_branches, 2);
    assert.equal(payload.failures.length, 1);
    assert.equal(payload.failures[0].frame_id, "markets");
    assert.equal(payload.failures[0].attempts, 2);

    const calls = (await readFile(fixture.logPath, "utf8")).trim().split("\n");
    assert.equal(calls.length, 4);
    assert.match(result.stderr, /no model fallback was used/);
  } finally {
    await rm(fixture.directory, { recursive: true, force: true });
  }
});
