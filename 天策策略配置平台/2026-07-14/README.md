# 天策策略配置平台 — TDForge 集成

基于 TDForge 框架的天策策略配置平台独立实例。

## 实例信息

- **位置**: `/Users/td/Desktop/AI提效/TDForge-tiance-config`
- **Gateway**: 端口 8003
- **Frontend**: 端口 3002
- **依赖安装**: backend 用 `uv sync`，frontend 用 `pnpm install`

## 文件说明

- `tiance_config.py` — 后端执行引擎，提供 6 步流水线 API、文件上传、后台任务执行、日志追踪
- `tiance-config-page.tsx` — 前端 React 组件，含流水线可视化、执行按钮、实时日志面板
- `page-route.tsx` — Next.js 路由页面

## 6 步流水线

1. **元数据管理** — 通过 Gateway Proxy 拉取天策平台全量元数据
2. **字段配置** — 上传字段映射 JSON，调用 field-forge 脚本生成 .xls
3. **函数配置** — 上传函数定义 JSON，编码为 .fun 文件
4. **规则集配置** — 上传规则文件，调用 rule-forge 脚本生成 .rss
5. **策略配置** — 上传策略 Excel，调用 policy-forge 脚本生成 .pls
6. **组件生命周期** — 收集所有产物，生成导入报告

## 启动方式

```bash
# 后端
cd backend
GATEWAY_PORT=8003 PYTHONPATH=. .venv/bin/python3 -m uvicorn app.gateway.app:app --port 8003

# 前端
cd frontend
DEER_FLOW_INTERNAL_GATEWAY_BASE_URL=http://127.0.0.1:8003 npx next dev -p 3002
```
