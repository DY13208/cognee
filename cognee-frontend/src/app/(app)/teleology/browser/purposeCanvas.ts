import type { GraphNodeSummary, ProposalItem, TeleologyProposal } from "@/modules/teleology/teleologyApi";
import { displayName } from "./entityMeta";
import type { EntityKind, OntologyEdge, OntologyEntity, ReviewStatus } from "./types";

export interface PurposeNeighborhoodInput {
  focus: GraphNodeSummary;
  parent?: GraphNodeSummary | null;
  purposes: GraphNodeSummary[];
  constraints: GraphNodeSummary[];
  relations: OntologyEdge[];
  proposal: TeleologyProposal | null;
  children: GraphNodeSummary[];
}

function asEntity(
  node: GraphNodeSummary,
  kind: EntityKind,
  reviewStatus: ReviewStatus,
): OntologyEntity {
  return {
    id: node.id,
    name: displayName(node.name, node.id),
    type: node.type || kind,
    kind,
    description: node.description,
    status: node.status,
    parentName: node.parent_name,
    childCount: node.child_count || 0,
    owner: node.owner,
    createdAt: node.created_at,
    progress: node.progress,
    source: node.source,
    reviewStatus,
  };
}

function stub(id: string, name: string, kind: EntityKind, reviewStatus: ReviewStatus): OntologyEntity {
  return {
    id,
    name: displayName(name, id),
    type: kind,
    kind,
    reviewStatus,
  };
}

/** One-hop relationship canvas: confirmed facts stay solid, AI suggestions stay dashed. */
export function buildPurposeNeighborhood(input: PurposeNeighborhoodInput): {
  entities: OntologyEntity[];
  edges: OntologyEdge[];
} {
  const entities = new Map<string, OntologyEntity>();
  const edges: OntologyEdge[] = [];
  const edgeIds = new Set<string>();
  const put = (entity: OntologyEntity) => {
    if (!entities.has(entity.id)) entities.set(entity.id, entity);
  };
  const link = (edge: OntologyEdge) => {
    if (!edge.sourceId || !edge.targetId || edge.sourceId === edge.targetId || edgeIds.has(edge.id)) return;
    edgeIds.add(edge.id);
    edges.push(edge);
  };

  put(asEntity(input.focus, "Goal", "confirmed"));
  if (input.parent && input.parent.id !== input.focus.id) {
    put(asEntity(input.parent, "Goal", "confirmed"));
    link({
      id: `tree|${input.parent.id}|${input.focus.id}`,
      sourceId: input.parent.id,
      targetId: input.focus.id,
      sourceName: input.parent.name,
      targetName: input.focus.name,
      sourceType: "Goal",
      targetType: "Goal",
      relationship: "has_subgoal",
      status: "confirmed",
    });
  }
  for (const purpose of input.purposes) {
    put(asEntity(purpose, "Purpose", "confirmed"));
    link({
      id: `why|${purpose.id}|${input.focus.id}`,
      sourceId: purpose.id,
      targetId: input.focus.id,
      sourceName: purpose.name,
      targetName: input.focus.name,
      sourceType: "Purpose",
      targetType: "Goal",
      relationship: "purpose",
      status: "confirmed",
    });
  }
  for (const constraint of input.constraints) {
    put(asEntity(constraint, "Constraint", "confirmed"));
    link({
      id: `constraint|${constraint.id}|${input.focus.id}`,
      sourceId: constraint.id,
      targetId: input.focus.id,
      sourceName: constraint.name,
      targetName: input.focus.name,
      sourceType: "Constraint",
      targetType: "Goal",
      relationship: "constrains",
      status: "confirmed",
    });
  }
  for (const child of input.children) {
    put(asEntity(child, "Goal", "confirmed"));
    link({
      id: `child|${input.focus.id}|${child.id}`,
      sourceId: input.focus.id,
      targetId: child.id,
      sourceName: input.focus.name,
      targetName: child.name,
      sourceType: "Goal",
      targetType: "Goal",
      relationship: "has_subgoal",
      status: "confirmed",
    });
  }
  for (const relation of input.relations) {
    const evidence = relation.relationship === "evidence";
    const endpointKind = (type: string): EntityKind =>
      evidence || type === "Data" ? "Other" : type === "Purpose" ? "Purpose" : type === "Constraint" ? "Constraint" : "Goal";
    if (!entities.has(relation.sourceId)) {
      put({
        ...stub(relation.sourceId, relation.sourceName, endpointKind(relation.sourceType), "confirmed"),
        type: evidence ? "Data" : relation.sourceType,
        source: evidence ? "company_tree" : undefined,
        childCount: evidence ? 0 : undefined,
      });
    }
    if (!entities.has(relation.targetId)) {
      put({
        ...stub(relation.targetId, relation.targetName, endpointKind(relation.targetType), "confirmed"),
        type: evidence ? "Data" : relation.targetType,
        source: evidence ? "company_tree" : undefined,
        childCount: evidence ? 0 : undefined,
      });
    }
    link({ ...relation, status: relation.status || "confirmed" });
  }

  const openItems = (input.proposal?.items || []).filter((item) => item.status !== "ignored" && item.kind !== "gap");
  const byItem = new Map(openItems.map((item) => [item.id, item]));
  const proposalKind = (item: ProposalItem): EntityKind =>
    item.kind === "purpose" ? "Purpose" : item.kind === "constraint" ? "Constraint" : "Goal";
  for (const item of openItems) {
    if (item.kind === "relation") continue;
    put({
      ...stub(item.id, item.name || item.id, proposalKind(item), "proposed"),
      description: item.reason,
    });
    const towardFocus = item.kind === "purpose" || item.kind === "constraint";
    link({
      id: `proposal|${item.id}`,
      sourceId: towardFocus ? item.id : input.focus.id,
      targetId: towardFocus ? input.focus.id : item.id,
      sourceName: towardFocus ? item.name : input.focus.name,
      targetName: towardFocus ? input.focus.name : item.name,
      sourceType: towardFocus ? proposalKind(item) : "Goal",
      targetType: towardFocus ? "Goal" : proposalKind(item),
      relationship: item.kind === "purpose" ? "purpose" : item.kind === "constraint" ? "constrains" : "suggests",
      status: "proposed",
    });
  }
  for (const item of openItems) {
    if (item.kind !== "relation" || !item.source || !item.target) continue;
    for (const ref of [item.source, item.target]) {
      if (entities.has(ref)) continue;
      const named = byItem.get(ref);
      put(stub(ref, named?.name || (ref === input.focus.id ? input.focus.name : ref), named ? proposalKind(named) : "Goal", named ? "proposed" : "confirmed"));
    }
    link({
      id: `proposal-rel|${item.id}`,
      sourceId: item.source,
      targetId: item.target,
      sourceName: entities.get(item.source)?.name || item.source,
      targetName: entities.get(item.target)?.name || item.target,
      sourceType: entities.get(item.source)?.type || "Goal",
      targetType: entities.get(item.target)?.type || "Goal",
      relationship: item.relationship || "serves",
      status: "proposed",
    });
  }

  return { entities: [...entities.values()], edges };
}
