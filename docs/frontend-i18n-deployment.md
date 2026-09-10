# 本地化前端部署说明

本仓库的中英文 UI 由 `cognee-frontend` 源码构建，**不使用**官方预编译的
`cognee/cognee-ui` 镜像。部署覆盖文件
[`docker-compose.i18n.yml`](../docker-compose.i18n.yml) 只替换 `frontend`
服务的镜像构建来源；不会改动 API、MCP、PostgreSQL、数据卷、网络、端口或数据库。

## 启动

在仓库根目录执行：

```powershell
docker compose -f docker-compose.yml -f docker-compose.i18n.yml `
  --profile postgres --profile ui --profile mcp up -d --build
```

这会产生明确的本地镜像标签 `cognee/cognee-ui-i18n:0.1.0-local`。该标签仅供本机使用，
不会覆盖或拉取 `cognee/cognee-ui:latest`。

发布新的本地化 UI 时，先在 `docker-compose.i18n.yml` 中递增镜像标签，再重新构建；
不要使用 `latest`。若将镜像推送到私有仓库，保留相同的版本号并把镜像仓库前缀替换为
私有仓库地址。

仅重建本地化 UI（不重建后端服务）：

```powershell
docker compose -f docker-compose.yml -f docker-compose.i18n.yml `
  --profile ui build frontend
docker compose -f docker-compose.yml -f docker-compose.i18n.yml `
  --profile ui up -d --no-deps frontend
```

## 运行前配置

- 根目录 `.env` 仍是后端和 Compose 的唯一环境配置来源；不要把密钥写入镜像、
  Compose 覆盖文件或前端词典。
- `COGNEE_BACKEND_URL` 必须是**浏览器可访问**的 API 地址。例如本机 UI 使用
  `http://127.0.0.1:8000`；不能填 Docker 服务名 `http://cognee:8000`。
- 后端 `CORS_ALLOWED_ORIGINS` 必须包含 UI 的实际来源。默认本机场景至少应包含
  `http://localhost:3000` 与 `http://127.0.0.1:3000`。使用反向代理时，改为实际
  HTTPS 域名并移除不需要的开发来源。

## 验证与回退

```powershell
docker compose -f docker-compose.yml -f docker-compose.i18n.yml ps
Invoke-WebRequest http://127.0.0.1:3000/api/runtime-config
Invoke-WebRequest http://127.0.0.1:8000/health
```

浏览器验证顺序：首次/清除 `cognee_locale` Cookie 后显示简体中文；切换到 English，
刷新后仍显示英文；切换时当前 URL 和登录态不变。若页面无法访问 API，先检查上述
CORS 配置及 `COGNEE_BACKEND_URL`，不要修改前端词典来规避连接错误。

需要回到上游 UI 时，停止该覆盖组合后只使用基础文件：

```powershell
docker compose -f docker-compose.yml -f docker-compose.i18n.yml --profile ui down
docker compose --profile ui up -d
```

该操作不会删除 PostgreSQL 或 Cognee 数据卷。
