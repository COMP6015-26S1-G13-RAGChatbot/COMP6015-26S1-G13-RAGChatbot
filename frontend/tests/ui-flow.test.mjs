import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const page = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");

test("chat flow exposes loading, citations, conflict, error, and abstention states", () => {
  for (const expected of ["Retrieving…", "<Citations", "conflict_status", "setError", "Insufficient evidence"]) assert.match(page, new RegExp(expected.replace("…", ".")));
});

test("audit flow uses the real API and distinguishes result states", () => {
  for (const expected of ["api.audit", "Run audit", "No conflict detected", "audit.conflict_status", "Insufficient evidence"]) assert.ok(page.includes(expected));
});

test("documents and evaluation are separate views", () => {
  for (const expected of ["api.documents", "api.evaluation", "Evaluation only", "Excluded because"]) assert.ok(page.includes(expected));
});
