# 复用 mind-map 企业微信单点登录

Cognee 登录页增加「企业微信登录」。用户已登录 mind-map 时直接进入 Cognee；否则跳到 mind-map 现有企业微信扫码登录（企业微信客户端使用网页授权），登录成功后返回 Cognee。企业微信 CorpID、AgentID、Secret 及原回调配置仍由 mind-map 管理，无需为 Cognee 新建企业微信应用。

## 部署配置

在 **mind-map 服务**的 `.env` 中增加：

```dotenv
MIND_MAP_COGNEE_SSO_SECRET=<新生成的至少 32 字符随机密钥>
COGNEE_SSO_REDIRECT_URI=https://xx.stillgroup.net:3030/sso/mind-map/callback
```

在 **Cognee 后端**的 `.env` 中增加：

```dotenv
MIND_MAP_SSO_ENABLED=true
MIND_MAP_SSO_ORIGIN=https://xx.stillgroup.net:8989
MIND_MAP_SSO_REDIRECT_URI=https://xx.stillgroup.net:3030/sso/mind-map/callback
MIND_MAP_COGNEE_SSO_SECRET=<与 mind-map 中相同的新密钥>
ENABLE_BACKEND_ACCESS_CONTROL=true
REQUIRE_AUTHENTICATION=true
```

可以在服务器运行 `openssl rand -hex 32` 生成共享密钥。不要复用企业微信 Secret，也不要把密钥放入 Git、前端变量或命令行日志。

Cognee 已启用 WorkBuddy 时，继续使用已有 `CODEBUDDY_SESSION_SECRET` 和会话时长，现有会话无需因接入 SSO 而更换签名密钥。如关闭 WorkBuddy，则还必须在 Cognee 后端配置：

```dotenv
MIND_MAP_SSO_SESSION_SECRET=<另外生成的至少 32 字符随机密钥>
MIND_MAP_SSO_SESSION_LIFETIME_SECONDS=604800
```

会话签名密钥必须与共享 SSO 密钥不同。两端只接受 HTTPS 和完全匹配的 Cognee 回调地址。前端容器保留 `COGNEE_INTERNAL_BACKEND_URL=http://cognee:8000`。

## 更新服务

先部署两个仓库的新代码并备份各自 `.env`。mind-map 按原有部署方式重建、更新 app 服务；使用带 Wiki 的部署时必须保留 `.secrets/wiki.env` 注入，不能用缺少该配置的 Compose 命令重建 app。认证初始化会自动创建独立的 `auth_cognee_codes` 表，不改写已有账号或会话。

本仓库的 Compose 将 `./cognee` 挂载到后端，因此代码同步后重启后端即可。前端需要重新构建，HTTPS 网关需要重启以加载不记录查询参数的日志格式：

```bash
docker compose --profile ui --profile https build frontend
docker compose --profile ui --profile https restart cognee
docker compose --profile ui --profile https up -d --no-deps frontend
docker compose --profile ui --profile https restart codebuddy-https
```

如果生产使用预构建镜像、没有代码挂载，应先重建后端镜像，再按原部署方式更新服务。无需重建 MCP 或改动知识库数据卷。

## 认证与账号权限

Cognee 生成浏览器绑定的 10 分钟 HttpOnly/Secure 状态 Cookie 和 S256 PKCE；mind-map 验证固定回调并检查已有登录会话，签发 90 秒授权码。只存授权码哈希，兑换时在 PostgreSQL 中原子删除。Cognee 后端凭独立共享密钥和 PKCE 校验码兑换企业微信成员身份，再签发自己的 HttpOnly/Secure 会话。浏览器收不到企业微信 Secret、共享密钥或企业微信访问令牌。

企业微信登录失败时，mind-map 将失败结果和原状态返回 Cognee，显示重试页面，避免再次自动发起扫码。兑换、数据库或会话签发失败时不创建登录会话，清除本次状态；用户从登录页重新开始。授权码消费后不自动重试兑换。

账号按 `企业 CorpID + 企业微信 UserID` 稳定映射为普通 Cognee 用户，首次登录创建独立非管理员账号。不同企业的同名 UserID 不会合并。已有邮箱、WorkBuddy 账号和知识库数据保留；不按姓名、邮箱或管理员权限自动合并账号，也不自动授予原账号的知识库权限。如需访问原知识库，由其所有者通过已有 ACL 分享，或另行完成经过确认的账号绑定。

退出 Cognee 会清理 Cognee 会话和未完成的 SSO 状态，mind-map 会话继续独立有效；再次点击企业微信登录可重新进入。mind-map 退出不会主动撤销已经签发的 Cognee 会话。

## 验收

```bash
curl -fsS https://xx.stillgroup.net:8989/api/auth/config
curl -fsS https://xx.stillgroup.net:3030/backend/api/v1/auth/mind-map/config
curl -I https://xx.stillgroup.net:3030/sso/mind-map/login
```

第二个请求应返回 `{"enabled":true}`，第三个应以 303 跳到 mind-map 的 `/api/auth/cognee/authorize`。随后分别用已有 mind-map 会话与无会话的浏览器完成登录，检查企业微信成员显示名、刷新后会话、退出、未登录 API 401、跨账号知识库隔离。授权码过期、重放、错误 PKCE 校验码和不匹配回调均必须拒绝。

自动检查：

```bash
# Cognee 仓库
uv run pytest cognee/tests/unit/modules/users/test_mind_map_sso.py cognee/tests/unit/modules/users/test_codebuddy_oauth.py -q
cd cognee-frontend
npm test -- --runInBand src/modules/users/__tests__/mindMapSsoProxy.test.ts src/modules/users/__tests__/codebuddyProxy.test.ts
npm run build

# mind-map 仓库，simple-mind-map 目录（PG 测试只创建并删除随机临时 schema）
node test/cogneeSso.test.js
node test/cogneeSso.pg.test.js
npm run test:auth
```

完整协议联调需要已安装依赖的 sibling `mind-map` 仓库和测试 PostgreSQL 的 `PGHOST`、`PGPORT`、`PGDATABASE`、`PGUSER`、`PGPASSWORD`。在 Cognee 仓库运行：

```bash
MIND_MAP_SSO_INTEGRATION=1 uv run pytest cognee/tests/integration/users/test_mind_map_sso_protocol.py -q
```

该测试使用验证证书的真实 HTTPS 请求、mind-map 原登录/回调/会话逻辑、随机 PostgreSQL schema、临时 SQLite 用户库及 Cognee 原生 JWT 认证；覆盖重启、重复登录、成员隔离、过期、重放、退出和企业微信成功/失败回跳。外部企业微信接口使用测试响应，线上真实扫码仍需要部署后验收。

禁用时设置 `MIND_MAP_SSO_ENABLED=false` 并重启 Cognee 后端，页面会隐藏企业微信入口。若同时关闭 WorkBuddy，会话密钥配置变化可能使当前会话失效，原账号与知识库仍保留。
