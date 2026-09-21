import { buildCPDTree } from "../cpdTree";

const ROOM = "room-yk3tz4aj";

function node(
  id: string,
  name: string,
  extras: Record<string, unknown> = {},
): CPDGraphNode {
  return {
    id,
    label: name,
    properties: {
      source_room: ROOM,
      source_scope: "company_model_only",
      cpd_kind: "goal",
      source_uid: extras.source_uid ?? id,
      source_key: extras.source_key ?? id,
      source_revision: extras.source_revision ?? "1",
      source_child_count: extras.source_child_count ?? 0,
      source_children_complete: extras.source_children_complete ?? true,
      source_position: extras.source_position ?? "",
      ...extras,
    },
  };
}

type CPDGraphNode = {
  id: string;
  label: string;
  properties: Record<string, unknown>;
};

describe("buildCPDTree", () => {
  it("still uses the known company-ops source uid when it is the unique parentless node", () => {
    const rootId = "313047eb-0c98-4abb-a1ce-933b1081e234";
    const tree = buildCPDTree({
      nodes: [
        node("n-root", "公司运营", { source_uid: rootId, source_child_count: 1 }),
        node("n-child", "AHC", { source_child_count: 0, source_position: "1" }),
      ],
      edges: [{ source: "n-root", target: "n-child", label: "has_subgoal" }],
    });
    expect(tree.root.id).toBe("n-root");
    expect(tree.complete).toBe(true);
  });

  it("infers the structural root when the stored source uid is not the hardcoded one", () => {
    const tree = buildCPDTree({
      nodes: [
        node("n-root", "公司运营", {
          source_uid: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
          source_child_count: 1,
        }),
        node("n-child", "AHC", { source_child_count: 0, source_position: "1" }),
      ],
      edges: [{ source: "n-root", target: "n-child", label: "has_subgoal" }],
    });
    expect(tree.root.name).toBe("公司运营");
    expect(tree.goalCount).toBe(2);
  });

  it("still renders when child counts are incomplete", () => {
    const tree = buildCPDTree({
      nodes: [
        node("n-root", "公司运营", {
          source_child_count: 3,
          source_children_complete: false,
        }),
        node("n-child", "AHC", { source_child_count: 0, source_position: "1" }),
      ],
      edges: [{ source: "n-root", target: "n-child", label: "has_subgoal" }],
    });
    expect(tree.root.name).toBe("公司运营");
    expect(tree.complete).toBe(false);
  });
});
