# 复用 mind-map 企业微信单点登录

Cognee 登录页默认内嵌企业微信二维码，提供刷新和「账号密码登录」切换按钮。两种模式均保留「Login WorkBuddy」按钮和原 `/oauth/login` 授权流程；关闭企业微信 SSO 后也保留 WorkBuddy 及密码登录。已登录 mind-map 的用户可点击「使用已有登录状态」直接进入 Cognee（企业微信客户端使用网页授权）。企业微信 CorpID、AgentID、Secret 及原回调配置仍由 mind-map 管理，无需新建应用或登记 Cognee 回调域名。

所有经过 mind-map 验证的企业微信成员都使用已有 Cognee 账号 `izw99s@hotmail.com`，共享该账号的全部内容和权限。

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
MIND_MAP_SSO_ACCOUNT_EMAIL=izw99s@hotmail.com
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

内嵌二维码通过 mind-map 现有 `/api/auth/qr` 生成，原企业微信回调仍是 `https://xx.stillgroup.net:8989/api/auth/wecom/callback`。两端需要使用同一 HTTPS 主机名，端口可以不同，以便浏览器状态 Cookie 在原回调中保持有效。二维码初始化失败时可以刷新、使用已有登录状态或切换账号密码；状态到期会自动刷新。

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

完成企业微信身份和授权码验证后，Cognee 按 `MIND_MAP_SSO_ACCOUNT_EMAIL` 查找现有账号（默认 `izw99s@hotmail.com`），直接以其原用户 ID 签发会话。因此数据所有权、租户、角色、管理员权限和 ACL 与该账号的密码登录完全一致，不复制数据、不创建新用户，也不改动密码或权限。目标账号不存在或被停用时拒绝登录。

企业 CorpID + UserID 仍分别保存在 OAuthIdentity 中用于身份映射。旧版本创建的独立 SSO 账号保留；下次成功登录时将相应 SSO 身份关联到指定账号，不迁移或删除旧账号的数据。每个通过现有企业微信应用身份验证的成员都会取得这个共享账号的完整权限。

退出 Cognee 会清理 Cognee 会话和未完成的 SSO 状态，mind-map 会话继续独立有效；再次点击企业微信登录可重新进入。mind-map 退出不会主动撤销已经签发的 Cognee 会话。

## 验收

```bash
curl -fsS https://xx.stillgroup.net:8989/api/auth/config
curl -fsS https://xx.stillgroup.net:3030/backend/api/v1/auth/mind-map/config
curl -fsS https://xx.stillgroup.net:3030/sso/mind-map/qr -o /dev/null
```

第二个请求应返回 `{"enabled":true}`，第三个应返回 200 的二维码 JSON。页面默认显示二维码，切换账号密码及返回二维码均正常，「Login WorkBuddy」在两种模式下均可打开原授权入口。分别用已有 mind-map 会话与无会话的浏览器完成登录，确认用户 ID 为目标账号原 ID，知识库列表和角色权限与该账号密码登录一致。验证刷新后会话、退出、未登录 API 401、授权码过期/重放、错误 PKCE 和不匹配回调均被拒绝。

自动检查：

```bash
# Cognee 仓库
uv run pytest cognee/tests/unit/modules/users/test_mind_map_sso.py cognee/tests/unit/modules/users/test_codebuddy_oauth.py -q
cd cognee-frontend
npm test -- --runInBand --runTestsByPath src/modules/users/__tests__/mindMapSsoProxy.test.ts src/modules/users/__tests__/wecomQrMessage.test.ts src/modules/users/__tests__/codebuddyProxy.test.ts 'src/app/(auth)/local-login/partials/LocalSignInForm.test.tsx'
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

该测试使用验证证书的真实 HTTPS 请求、mind-map 原登录/回调/会话逻辑、随机 PostgreSQL schema、临时 SQLite 用户库及 Cognee 原生 JWT 和知识库权限 API；覆盖重启、多个成员共用原账号、直接/租户/角色知识库权限、二维码刷新和原回调、过期、重放、退出及登录失败。外部企业微信接口使用测试响应，线上真实扫码仍需要部署后验收。

禁用时设置 `MIND_MAP_SSO_ENABLED=false` 并重启 Cognee 后端，页面会隐藏企业微信入口。若同时关闭 WorkBuddy，会话密钥配置变化可能使当前会话失效，原账号与知识库仍保留。
