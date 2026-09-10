# UI 国际化开发规范

## 目标与边界

UI 支持 `zh-CN` 和 `en`，默认 `zh-CN`。语言偏好存于 Cookie `cognee_locale`；缺失、
损坏或不支持的值必须回退简体中文。语言选择只影响产品界面，不翻译知识库内容、用户
输入、模型回答、日志、代码或原始 API 载荷。

新增或修改用户可见文本时，必须使用国际化消息 API。禁止在 React 组件、Toast、表单
校验、Tooltip、`aria-label`、空状态、弹窗或前端错误映射中硬编码自然语言。只允许在
测试夹具、开发注释、日志和不可见的稳定技术标识符中保留英文字符串。

## 词典约定

- 国际化运行时、语言解析和 Provider 位于 `src/i18n/`；`src/i18n/request.ts` 是
  next-intl 的请求级配置（语言仍来自 Cookie，无 URL 前缀）。词典固定为
  `src/i18n/messages/zh-CN.json` 与 `src/i18n/messages/en.json`。功能组件不得自行读取 Cookie
  或创建语言上下文。
- 在每份词典内按领域拆分消息命名空间：`Auth`、`Setup`、`Welcome`、`LanguageSwitcher`、
  `navigation`、`dashboard`、`datasets`、`search`、`sessions`、`skills`、`knowledgeGraph`、
  `integrations`、`apiKeys`、`settings`、`graphModels`、`survey`、`waitlist`、`errors`、
  `common`。不要创建难以审查的单一巨型词典。
- 消息键采用稳定的语义路径，而不是英文原文或位置，例如
  `datasets.deleteDialog.confirmLabel`，不要使用 `deleteDatasetButtonText` 或
  `Delete dataset`。重命名英文文案不应导致键变更。
- 英文与中文消息目录必须拥有完全相同的键和 ICU 参数。复数、日期、数字和插值通过
  国际化库格式化；禁止在组件内拼接翻译片段。
- 参数以含义命名，如 `{datasetName}`、`{count}`，不能使用 `{value}`。中文、英文都
  必须能独立构成完整语句。
- 翻译前查阅 [术语表](./TERMINOLOGY.md)。专有名词不确定时保留英文并补表，不进行
  机器翻译或批量替换。

## 错误信息与可访问性

- 对后端返回的稳定错误码使用 `errors` 词典给出可行动的本地化提示。
- 未映射错误显示通用安全提示，不把服务端原始异常翻译或直接暴露给普通用户；原始详情
  仅在既有受控调试渠道记录/展示。
- 每个可交互控件的可访问名称也必须走词典。语言切换器须具有当前语言、目标语言和
  键盘可操作的语义。

## 合并前检查

1. 运行词典键一致性及术语检查；缺键、额外键、ICU 参数不一致均应失败。
2. 为语言解析/Cookie 回退、改动的文案、错误码映射和语言切换补单元测试。
3. 至少人工检查中文默认、英文切换、刷新持久化、清除 Cookie 回退中文，确认 URL、
   登录态和当前页面不变。
4. 运行 `npm run lint`、`npm test`、`npm run build`。

禁止为了通过构建而复制英文到中文词典；这属于缺失翻译，应先补充准确中文。
