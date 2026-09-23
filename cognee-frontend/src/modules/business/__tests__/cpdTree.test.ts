import { treeFromCompanyTreeApi } from "../cpdTree";

describe("treeFromCompanyTreeApi", () => {
  it("renders the backend tree including an unstamped company-ops root", () => {
    const tree = treeFromCompanyTreeApi({
      rootId: "ops",
      revision: "1314",
      complete: false,
      missing: ["unstamped:ops"],
      nodes: [
        {
          id: "ops",
          name: "公司运营",
          kind: "goal",
          sourceKey: "mindmap:room-yk3tz4aj:313047eb-0c98-4abb-a1ce-933b1081e234",
          sourceUid: "313047eb-0c98-4abb-a1ce-933b1081e234",
        },
        { id: "biz", name: "公司业务", kind: "goal" },
        { id: "ahc", name: "陈丽 C:AHC项目目标图", kind: "goal" },
      ],
      edges: [
        { source: "ops", target: "biz", label: "has_subgoal" },
        { source: "biz", target: "ahc", label: "has_subgoal" },
      ],
    });
    expect(tree.root.name).toBe("公司运营");
    expect(tree.goalCount).toBe(3);
    expect(tree.complete).toBe(false);
    expect(tree.goalEdgeCount).toBe(2);
  });

  it("does not treat an empty payload as a tree", () => {
    expect(() => treeFromCompanyTreeApi({ nodes: [], edges: [], missing: ["empty"] })).toThrow(
      /推不出公司模型主房间|尚未完成导入/,
    );
  });
});
