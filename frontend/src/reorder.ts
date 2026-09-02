// Pure logic for drag-reorder: translate a "drop AT slot N" gesture
// into the (optimistic-order, after_id-for-server) pair the rest of
// the app needs.
//
// Why a separate module: the bug (tw-?? drop-off-by-one) lived in
// onDragEnd's inline math, which made it hard to unit-test. Pulling
// the pure parts out lets us cover every direction + same/cross-
// column case in vitest without needing a DOM.
//
// arrayMove semantics (matching @dnd-kit/sortable): moving items[a]
// to index b in a list produces [...items[0..b-1*], items[a],
// ...items[b..*]] where indices shift naturally. The card you drop
// ON slides out of the way; the dragged card sits AT that slot.

import { arrayMove } from "@dnd-kit/sortable";

export interface ReorderItem {
  id: string;
}

export interface ReorderPlan<T extends ReorderItem> {
  /** The new ordered list for the destination column, with active
   *  inserted at the resolved index. */
  nextOrder: T[];
  /** Server payload: the id of the card immediately preceding active
   *  in the new ordering, or null if active is at the top. */
  afterId: string | null;
}

/** Same-column reorder. Both indices are relative to the column's
 *  current ordering (which includes active). */
export function planSameColumnReorder<T extends ReorderItem>(
  items: readonly T[],
  activeId: string,
  overId: string,
): ReorderPlan<T> | null {
  const activeIdx = items.findIndex((t) => t.id === activeId);
  const overIdx = items.findIndex((t) => t.id === overId);
  if (activeIdx < 0 || overIdx < 0 || activeIdx === overIdx) return null;
  const nextOrder = arrayMove([...items], activeIdx, overIdx);
  const newActiveIdx = nextOrder.findIndex((t) => t.id === activeId);
  const afterId = newActiveIdx === 0 ? null : nextOrder[newActiveIdx - 1].id;
  return { nextOrder, afterId };
}

/** Cross-column drop ONTO a target. The destination items list is
 *  the destination column's current ordering (not yet including
 *  active). active gets inserted at overIdx; the over-card and
 *  everything after slides down by 1. */
export function planCrossColumnDropOnCard<T extends ReorderItem>(
  destItems: readonly T[],
  activeItem: T,
  overId: string,
): ReorderPlan<T> | null {
  const overIdx = destItems.findIndex((t) => t.id === overId);
  if (overIdx < 0) return null;
  const nextOrder = [
    ...destItems.slice(0, overIdx),
    activeItem,
    ...destItems.slice(overIdx),
  ];
  const afterId = overIdx === 0 ? null : destItems[overIdx - 1].id;
  return { nextOrder, afterId };
}
