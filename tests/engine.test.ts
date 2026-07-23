import assert from "node:assert/strict";
import test from "node:test";

import { rankClusters } from "../src/engine.ts";
import type { Cluster, Idea } from "../src/types.ts";

function idea(id: string, total: number, trap?: string): Idea {
  return {
    id,
    frameId: "f",
    text: id,
    depth: 0,
    score: { novelty: total, viability: total, fit: total, total, trap },
  };
}

test("rankClusters orders by mean score of non-trap members", () => {
  const strong = idea("a", 9);
  const weak = idea("b", 2);
  const clusters: Cluster[] = [
    { label: "weak-angle", ideaIds: ["b"] },
    { label: "strong-angle", ideaIds: ["a"] },
  ];

  const ranked = rankClusters(clusters, [strong, weak]);

  assert.deepEqual(ranked.map((c) => c.label), ["strong-angle", "weak-angle"]);
});

test("rankClusters excludes trapped ideas from a cluster's score", () => {
  const trap = idea("a", 9, "looks good, isn't");
  const viable = idea("b", 5);
  const clusters: Cluster[] = [
    { label: "trap-only", ideaIds: ["a"] },
    { label: "mixed", ideaIds: ["a", "b"] },
  ];

  const ranked = rankClusters(clusters, [trap, viable]);

  // "trap-only" has no viable members, so it sorts last.
  assert.deepEqual(ranked.map((c) => c.label), ["mixed", "trap-only"]);
});

test("rankClusters handles clusters referencing unknown idea ids", () => {
  const clusters: Cluster[] = [{ label: "orphan", ideaIds: ["missing"] }];
  const ranked = rankClusters(clusters, []);
  assert.equal(ranked.length, 1);
  assert.equal(ranked[0].label, "orphan");
});
