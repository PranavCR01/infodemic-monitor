import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { adaptBlindMaterial, fetchBlindMaterial } from "./blind-material";
import { MOCK_BLIND_MATERIAL } from "./mocks/blind-material";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
beforeEach(() => apiFetch.mockReset());

describe("adaptBlindMaterial (T40)", () => {
  const m = adaptBlindMaterial(MOCK_BLIND_MATERIAL);

  it("gives each claim the words the extractor quoted", () => {
    expect(m.claims.c1.quotes.map((q) => q.text).join(" ")).toMatch(/hot water/i);
  });

  it("keeps the server's retrieval order and never carries a relation", () => {
    const raw = MOCK_BLIND_MATERIAL.claims![0].references!;
    expect(m.claims.c1.sources.map((s) => s.id)).toEqual(raw.map((r) => r.evidence_id));
    for (const s of Object.values(m.claims).flatMap((c) => c.sources)) expect(s).not.toHaveProperty("relation");
  });

  it("sorts by rank when the server's list arrives out of order", () => {
    const shuffled = { ...MOCK_BLIND_MATERIAL, claims: [{ ...MOCK_BLIND_MATERIAL.claims![0], references: [...MOCK_BLIND_MATERIAL.claims![0].references!].reverse() }] };
    const ids = adaptBlindMaterial(shuffled).claims.c1.sources.map((s) => s.id);
    expect(ids).toEqual(MOCK_BLIND_MATERIAL.claims![0].references!.map((r) => r.evidence_id));
  });

  it("never links internal library documents", () => {
    const lib = adaptBlindMaterial({
      ...MOCK_BLIND_MATERIAL,
      claims: [{ claim_id: "c9", references: [{ evidence_id: "L1", source_kind: "library", rank: 1, title: "Internal memo", url: "https://x" }] }],
    });
    expect(lib.claims.c9.sources[0].url).toBeNull();
  });
});

describe("fetchBlindMaterial (T40)", () => {
  it("reads the material", async () => {
    apiFetch.mockResolvedValue(json(200, MOCK_BLIND_MATERIAL));
    const r = await fetchBlindMaterial("rev 1");
    expect(apiFetch.mock.calls[0][0]).toBe("/v1/reviews/rev%201/blind-material");
    expect(r.kind).toBe("ok");
  });

  it("knows when the reviewer isn't blind any more", async () => {
    apiFetch.mockResolvedValue(json(403, { detail: { code: "BLIND_STEP_NOT_ACTIVE", message: "…" } }));
    expect(await fetchBlindMaterial("rev-1")).toEqual({ kind: "not_blind" });
  });

  it("reports other failures as errors", async () => {
    apiFetch.mockResolvedValue(json(403, { detail: "Not a reviewer" }));
    expect(await fetchBlindMaterial("rev-1")).toEqual({ kind: "error" });
  });

  it("reports a lost connection as an error", async () => {
    apiFetch.mockRejectedValueOnce(new TypeError("offline"));
    expect(await fetchBlindMaterial("rev-1")).toEqual({ kind: "error" });
  });
});
