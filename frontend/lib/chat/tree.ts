// Client-side message tree for editing & branching. The server returns every message
// of a conversation (each with parent_id + active_child_id) plus the active root; we
// rebuild the tree and derive the visible path by following active_child pointers.

import type { ConversationDetail } from "../api/types";

export interface TreeNode {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  reasoning: string | null;
  reasoning_ms: number | null;
  model: string | null;
  parent_id: string | null;
  active_child_id: string | null;
  created_at: string;
}

export interface Tree {
  nodes: Record<string, TreeNode>;
  rootId: string | null; // conversation.active_child_id
}

export const emptyTree = (): Tree => ({ nodes: {}, rootId: null });

export function buildTree(detail: ConversationDetail): Tree {
  const nodes: Record<string, TreeNode> = {};
  for (const m of detail.messages) {
    nodes[m.id] = {
      id: m.id,
      role: m.role,
      content: m.content,
      reasoning: m.reasoning,
      reasoning_ms: m.reasoning_ms,
      model: m.model,
      parent_id: m.parent_id,
      active_child_id: m.active_child_id,
      created_at: m.created_at,
    };
  }
  return { nodes, rootId: detail.active_child_id };
}

// The visible conversation: follow active_child from the root down to a leaf.
export function activePath(tree: Tree): TreeNode[] {
  const path: TreeNode[] = [];
  const seen = new Set<string>();
  let id = tree.rootId;
  while (id && !seen.has(id)) {
    seen.add(id);
    const n = tree.nodes[id];
    if (!n) break;
    path.push(n);
    id = n.active_child_id;
  }
  return path;
}

export function childrenOf(tree: Tree, parentId: string | null): TreeNode[] {
  return Object.values(tree.nodes)
    .filter((n) => n.parent_id === parentId)
    .sort((a, b) => (a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0));
}

export interface Versions {
  index: number;
  count: number;
  prevId: string | null;
  nextId: string | null;
}

// Sibling versions of a node (other children of its parent) for the `< n/m >` switcher.
export function versionsOf(tree: Tree, node: TreeNode): Versions {
  const sibs = childrenOf(tree, node.parent_id);
  const index = sibs.findIndex((s) => s.id === node.id);
  return {
    index,
    count: sibs.length,
    prevId: index > 0 ? sibs[index - 1].id : null,
    nextId: index >= 0 && index < sibs.length - 1 ? sibs[index + 1].id : null,
  };
}

// Immutably select a child on the active path. Deeper selections are preserved
// (per-branch memory): the path below simply follows existing active_child pointers.
export function setActiveChild(tree: Tree, parentId: string | null, childId: string): Tree {
  if (parentId === null) return { ...tree, rootId: childId };
  const parent = tree.nodes[parentId];
  if (!parent) return tree;
  return {
    ...tree,
    nodes: { ...tree.nodes, [parentId]: { ...parent, active_child_id: childId } },
  };
}
