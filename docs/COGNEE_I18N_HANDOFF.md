# Cognee 前端国际化交接文档

更新时间：2026-09-10。当前仓库：`D:\projects\cognee`，分支：`codex/hux-dev`。

## 已完成

已在 `cognee-frontend` 接入源码级国际化，业务页与壳层已按交接目标迁完：

- 依赖：`next-intl@^4.14.2`。
- 支持 `zh-CN`、`en`，默认 `zh-CN`。
- Cookie：`cognee_locale`；缺失或不合法时回退简体中文。
- 不使用语言 URL 前缀，现有 URL、认证 Cookie 与后端 API 保持不变。
- 根布局从 Cookie 获取语言，设置 `<html lang>` 并使用 `NextIntlClientProvider`。
- 左侧导航栏底部已增加语言选择器；切换会写 Cookie、保留当前 URL，并调用 `router.refresh()` 重新获取服务端词典。
- 英文界面语言选择项为 `Chinese (Simplified) / English`；中文界面为 `简体中文 / English`。
- 登录页移除了错误的预填 `default_user@example.com/default_password`；改为用户自行输入配置账号。已将 `LOGIN_BAD_CREDENTIALS`、`LOGIN_USER_NOT_VERIFIED` 映射为本地化文案，未映射错误显示通用提示，不向普通用户泄露原始技术详情。
- 已迁移：登录/邮箱验证/欢迎页、引导（含 `ServeOnboarding`）、数据集主页与详情页、检索、会话、设置、技能、集成（含连接页、数据源、Slack 指南、link-slack）、API 密钥、图谱模型编辑、知识图谱/业务视图、仪表盘（含额度横幅、用例条、上传完成弹窗、智能体动态终端）、Cloud stub（activity / analytics / memory-gap-analysis）、等候名单、NPS 问卷、额度不足/低余额弹窗、功能公告、全站导航壳与 Help/Profile/Feedback/抽取设置。
- 日期/数字工具已改为接收 `Locale`，不再硬编码 `en-US`。
- 文档与部署：自定义前端镜像及 Compose 覆盖、术语表、翻译规范、部署说明均已新增。

本次没有修改后端 API、数据库字段、数据模型或数据库迁移；不需要迁移脚本。

## 关键文件

| 用途 | 文件 |
| --- | --- |
| 语言配置与 Cookie 名 | `cognee-frontend/src/i18n/config.ts` |
| 服务端 Cookie 解析 | `cognee-frontend/src/i18n/getRequestLocale.ts` |
| 词典加载 | `cognee-frontend/src/i18n/getMessages.ts` |
| 词典 | `cognee-frontend/src/i18n/messages/en.json`、`cognee-frontend/src/i18n/messages/zh-CN.json` |
| 全局 Provider | `cognee-frontend/src/app/layout.tsx` |
| 语言切换器 | `cognee-frontend/src/ui/layout/LanguageSwitcher.tsx` |
| 稳定错误码映射 | `cognee-frontend/src/i18n/errorMessages.ts` |
| 向导步骤标题映射 | `cognee-frontend/src/modules/integrations/stepTitleMap.ts` |
| 术语表 | `cognee-frontend/docs/i18n/TERMINOLOGY.md` |
| 国际化规范 | `cognee-frontend/docs/i18n/CONTRIBUTING.md` |
| 自定义前端覆盖 | `docker-compose.i18n.yml` |
| 部署说明 | `docs/frontend-i18n-deployment.md` |

## 已验证

在 `cognee-frontend` 目录执行：

```powershell
node -e "JSON.parse(require('fs').readFileSync('src/i18n/messages/en.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/messages/zh-CN.json','utf8')); console.log('JSON ok')"
npm test -- --runInBand
```

结果：`69` 个测试套件、`535` 条断言全部通过。两份词典键完全一致（1122 个叶子键）。Windows PowerShell 的 `ConvertFrom-Json` 会因 UTF-8 省略号损坏解析，不要用它校验词典。

生产构建此前已通过。Windows PowerShell 下原 `npm run build` 使用 POSIX 环境变量语法，需改为：

```powershell
$env:NEXT_TELEMETRY_DISABLED='1'; npx next build
```

`npm run lint` 当前仍报仓库既有错误（集中在 dashboard redesign、graph-models、integrations 等）；本次迁移不要批量 `--fix`。

自定义镜像 **尚未**按本轮源码重建。UI：`http://127.0.0.1:3000`，API：`http://127.0.0.1:8000`。

## 残留（有意保留或待人工回归）

1. **集成向导步骤正文**：步骤**标题**已通过 `stepTitleMap` 翻译；Claude Desktop / Cursor / VS Code / Gemini 等步骤里带 `<strong>` 的 JSX 说明仍为英文。代码块、斜杠命令、配置文件名保持原文。
2. **`FilterContext` 的 `Personal workspace`**：与工作区名称常量匹配，**不要翻译**。
3. **用户数据**：知识库名、智能体类型、模型名、会话 ID、模型回答、SKILL.md 正文、日志与原始 API 详情不翻译。
4. **会话页 Improve**：产品命令，中文界面可保留 `Improve`。
5. **浏览器回归尚未做**：默认中文、切英语、刷新后仍英语、清除 `cognee_locale` 后回退中文；登录态与当前路径不丢失；移动端侧栏无障碍标签。本环境没有浏览器工具。
6. **全量迁移结束后的 lint 债务**：确认没有本次新增错误后再处理既有 58 个 lint。

```powershell
docker compose -f docker-compose.yml -f docker-compose.i18n.yml --profile ui build frontend
docker compose -f docker-compose.yml -f docker-compose.i18n.yml --profile ui up -d --no-deps frontend
```

## 开发约定

- 客户端组件：`import { useLocale, useTranslations } from "next-intl"`。
- 服务端组件/布局：只通过 `getRequestLocale()` 和 `getMessages()` 获取语言，业务组件不要直接读取 Cookie。
- 新可见文案先添加到两份 JSON 词典，再调用 `t("key")`；两份词典键必须完全一致。
- 保留 Cognee、MCP、API、LLM、Embedding、pgvector、Kuzu、Neo4j、PostgreSQL、JSON、OAuth 原文。
- Brain 译为“知识库”、Dataset 为“数据集”、Search 为“检索”、Sessions 为“会话”、Mindmap/Knowledge Graph 为“知识图谱”、Agent 为“智能体”、Tenant 为“租户”、API Keys 为“API 密钥”。
- 不翻译用户输入、知识库内容、模型回答、代码、日志、API 原始技术详情。
- Toast/错误无稳定错误码时用 `genericError`，不暴露 `err.message`。

## 当前容器状态

- API：`http://127.0.0.1:8000`
- UI：`http://127.0.0.1:3000`
- MCP：端口 `8001`
- 自定义镜像：`cognee/cognee-ui-i18n:0.1.0-local`

前端覆盖只替换 `frontend` 服务；后端、MCP、PostgreSQL、端口、卷和网络均未变更。
