export type ViewMode = "relation" | "chain" | "hierarchy" | "path";

export type EntityKind =
  | "Goal"
  | "Project"
  | "Metric"
  | "Department"
  | "Person"
  | "Document"
  | "Entity"
  | "Other";

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
