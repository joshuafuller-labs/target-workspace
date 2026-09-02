// Drag-reorder unit tests. Filed against the "+1 / -1 drop" bug
// where dropping on slot N landed at slot N+1.
//
// All test cases name the *intended* result first: drop AT slot N
// means the dragged card ends up at array index N.

import { describe, expect, it } from "vitest";

import {
  planCrossColumnDropOnCard,
  planSameColumnReorder,
} from "./reorder";

const items = (...ids: string[]) => ids.map((id) => ({ id }));

describe("planSameColumnReorder", () => {
  it("drag down: from idx 1 to idx 4 lands AT idx 4", () => {
    // Before: [A B C D E F]  ->  drag B onto E
    // After:  [A C D E B F]  -> B at index 4
    const plan = planSameColumnReorder(
      items("A", "B", "C", "D", "E", "F"),
      "B",
      "E",
    );
    expect(plan).not.toBeNull();
    expect(plan!.nextOrder.map((t) => t.id)).toEqual([
      "A", "C", "D", "E", "B", "F",
    ]);
    // B is at index 4 → after_id = E (idx 3)
    expect(plan!.afterId).toBe("E");
  });

  it("drag up: from idx 4 to idx 1 lands AT idx 1 — the +1 bug", () => {
    // Before: [A B C D E F]  ->  drag E onto B
    // After:  [A E B C D F]  -> E at index 1
    // Old buggy logic placed E AFTER B (at idx 2). This test would
    // have caught it: assert E at idx 1.
    const plan = planSameColumnReorder(
      items("A", "B", "C", "D", "E", "F"),
      "E",
      "B",
    );
    expect(plan).not.toBeNull();
    expect(plan!.nextOrder.map((t) => t.id)).toEqual([
      "A", "E", "B", "C", "D", "F",
    ]);
    // E is at index 1 → after_id = A (idx 0)
    expect(plan!.afterId).toBe("A");
  });

  it("drag to top: from idx 4 to idx 0 yields afterId=null", () => {
    const plan = planSameColumnReorder(
      items("A", "B", "C", "D", "E"),
      "E",
      "A",
    );
    expect(plan!.nextOrder.map((t) => t.id)).toEqual([
      "E", "A", "B", "C", "D",
    ]);
    expect(plan!.afterId).toBeNull();
  });

  it("drag to bottom: from idx 0 to idx N-1 yields afterId of the last existing card", () => {
    const plan = planSameColumnReorder(
      items("A", "B", "C", "D"),
      "A",
      "D",
    );
    expect(plan!.nextOrder.map((t) => t.id)).toEqual(["B", "C", "D", "A"]);
    expect(plan!.afterId).toBe("D");
  });

  it("drop on self is a no-op", () => {
    expect(
      planSameColumnReorder(items("A", "B", "C"), "B", "B"),
    ).toBeNull();
  });

  it("unknown active or over returns null", () => {
    expect(
      planSameColumnReorder(items("A", "B"), "Z", "A"),
    ).toBeNull();
    expect(
      planSameColumnReorder(items("A", "B"), "A", "Z"),
    ).toBeNull();
  });
});

describe("planCrossColumnDropOnCard", () => {
  it("drop on idx 0: afterId is null, active inserts at front", () => {
    const plan = planCrossColumnDropOnCard(
      items("X", "Y", "Z"),
      { id: "NEW" },
      "X",
    );
    expect(plan!.nextOrder.map((t) => t.id)).toEqual(["NEW", "X", "Y", "Z"]);
    expect(plan!.afterId).toBeNull();
  });

  it("drop on idx 2: active inserts at idx 2, afterId is items[1]", () => {
    const plan = planCrossColumnDropOnCard(
      items("X", "Y", "Z"),
      { id: "NEW" },
      "Z",
    );
    expect(plan!.nextOrder.map((t) => t.id)).toEqual(["X", "Y", "NEW", "Z"]);
    expect(plan!.afterId).toBe("Y");
  });

  it("drop with no matching overId returns null", () => {
    expect(
      planCrossColumnDropOnCard(
        items("X", "Y"),
        { id: "NEW" },
        "no-such-id",
      ),
    ).toBeNull();
  });
});
