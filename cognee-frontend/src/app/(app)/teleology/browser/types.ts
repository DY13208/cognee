export type ViewMode = "relation" | "chain" | "hierarchy" | "path";

export type EntityKind =
  | "Goal"
  | "Purpose"
  | "Constraint"
  | "Project"
  | "Metric"
  | "Department"
  | "Person"
  | "Document"
  | "Entity"
  | "Other";

export type ReviewStatus = "proposed" | "confirmed";

export interface OntologyEntity {
  id: string;
  name: string;
  type: string;
  kind: EntityKind;
  description?: string;
  status?: string | null;
  parentName?: string | null;
  /** Extra relations not shown at current hop (for +N). */
  hiddenDegree?: number;
  /** Direct CPD children count (has_subgoal / advances). */
  childCount?: number;
  owner?: string | null;
  createdAt?: number | string | null;
  progress?: number | null;
  source?: string | null;
  /** Confirmed graph fact, or an AI suggestion that is not committed yet. */
  reviewStatus?: ReviewStatus;
}

export interface OntologyEdge {
  id: string;
  sourceId: string;
  targetId: string;
  relationship: string;
  sourceName: string;
  targetName: string;
  sourceType: string;
  targetType: string;
  status?: ReviewStatus;
}

export interface LaidOutNode extends OntologyEntity {
  x: number;
  y: number;
  column: "upstream" | "focus" | "downstream";
}

export interface LaidOutEdge extends OntologyEdge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}
