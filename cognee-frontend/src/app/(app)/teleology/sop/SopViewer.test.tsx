import { render, screen } from "@testing-library/react";
import SopViewer from "./SopViewer";

const REAL_UID = "e1bd00ff-1f82-4a95-946e-7da665876c91";
const REAL_ID = "e7f37cf4-fda6-5856-93e2-c688fc0a1352";
const RUN_ID = "f7d609ae-4e88-4e4f-b8b3-523e92246bd4";

const proposal = {
  title: "制定项目利润目标 SOP 草案",
  goal: { id: "goal-profit", name: "提升项目利润" },
  run_id: RUN_ID,
  dataset_id: "dd3aa689-ec26-5887-9730-310eec869d1c",
  scope: "room-rujw4n4j",
  overall_confidence: 0.64,
  plan: [{
    id: "P1",
    text: "制定项目利润目标",
    evidence_status: "SOURCE",
    source_uid: REAL_UID,
    evidence_node_id: REAL_ID,
    reason: "节点名称明确以执行计划标记开头。",
  }],
  checks: [],
  inputs: [{ text: "利润测算模型", evidence_status: "SOURCE", source_uid: REAL_UID }],
  missing_details: [{ field: "负责人", reason: "当前资料未找到明确责任人", evidence_status: "MISSING" }],
  validation: { status: "NEEDS_REVIEW", unsupported_claims: [], quality_gaps: [], missing_fields: ["负责人"] },
};

describe("SopViewer", () => {
  it("shows the procedure, flow, gaps, and rationale without technical identifiers", () => {
    render(<SopViewer proposal={proposal} />);

    const reader = screen.getByTestId("sop-reader");
    expect(reader).toHaveTextContent("制定项目利润目标");
    expect(reader).toHaveTextContent("利润测算模型");
    expect(reader).toHaveTextContent("负责人");
    expect(reader).toHaveTextContent("节点名称明确以执行计划标记开头");
    expect(reader).toHaveTextContent("需要补充");
    expect(reader.textContent).not.toContain(REAL_UID);
    expect(reader.textContent).not.toContain(REAL_ID);
    expect(reader.textContent).not.toContain(RUN_ID);
    expect(reader.textContent).not.toContain("source_uid");
    expect(reader.textContent).not.toContain("evidence_node_id");
    expect(reader.textContent).not.toContain("run_id");

    const developer = screen.getByTestId("sop-developer");
    expect(developer).not.toHaveAttribute("open");
    expect(developer.textContent).toContain(REAL_UID);
    expect(developer.textContent).toContain(REAL_ID);
    expect(developer.textContent).toContain(RUN_ID);
    expect(developer.textContent).toContain("flowchart TD");
  });
});
