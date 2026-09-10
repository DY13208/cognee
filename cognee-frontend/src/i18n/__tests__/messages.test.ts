import en from "@/i18n/messages/en.json";
import zhCN from "@/i18n/messages/zh-CN.json";

function keys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) return [prefix];
  return Object.entries(value).flatMap(([key, child]) => keys(child, prefix ? `${prefix}.${key}` : key));
}

describe("message catalogues", () => {
  it("keep identical translation keys in English and Simplified Chinese", () => {
    expect(keys(zhCN).sort()).toEqual(keys(en).sort());
  });

  it("retains required terminology in the glossary-backed catalogue", () => {
    expect(zhCN.datasets.title).toBe("知识库");
    expect(en.datasets.title).toBe("Knowledge bases");
    expect(zhCN.datasets.memoryBar.graphModel).toBe("图谱模型");
    expect(zhCN.datasets.memoryBar.ontology).toBe("本体");
    expect(zhCN.datasets.memoryBar.prompt).toBe("提示词");
    expect(zhCN.Setup.serve.connectedTitle).toBe("已连接到 Cognee Cloud");
    expect(zhCN.Setup.serve.viewDatasets).toBe("查看数据集");
    expect(zhCN.navigation.items.brain).toBe("知识库");
    expect(en.navigation.items.brain).toBe("Knowledge bases");
    expect(zhCN.navigation.items.search).toBe("检索");
    expect(zhCN.navigation.items.sessions).toBe("会话");
    expect(zhCN.navigation.items.mindmap).toBe("知识图谱");
    expect(zhCN.navigation.items.apiKeys).toBe("API 密钥");
    expect(zhCN.navigation.openNav).toBe("打开导航");
    expect(zhCN.apiKeys.title).toBe("API 密钥");
    expect(en.apiKeys.title).toBe("API Keys");
    expect(zhCN.apiKeys.revoke).toBe("撤销");
    expect(zhCN.integrations.agents).toBe("智能体");
    expect(zhCN.integrations.connected).toBe("已连接");
    expect(zhCN.survey.title).toBe("快速提问");
    expect(zhCN.waitlist.title).toBe("目前已满员");
    expect(zhCN.knowledgeGraph.title).toBe("知识图谱");
    expect(zhCN.dashboard.credits.goToBilling).toBe("前往账单");
  });
});
