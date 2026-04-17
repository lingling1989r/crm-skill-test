---
name: order-demo-api
description: 连接 Order Demo Workspace API，支持客户、订单、产品、知识库、概览的查询与写操作，并提供中文命令封装。显式触发 `/order-demo-api`，或当用户明确要求操作该 CRM API 时使用。
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# Order Demo Workspace API Skill

这个 skill 用于打通 `http://111.229.202.81:3021/swagger` 对应的业务接口。

## When This Skill Activates

显式触发：
- `/order-demo-api`
- “用 order demo api”
- “帮我查一下这个 CRM 的订单/客户/产品/知识库/概览”

意图触发：
- 查询 dashboard 概览
- 按 ID、手机号、订单号、SKU、关键词查询业务数据
- 新增、更新、删除客户 / 订单 / 产品 / 知识文章
- 验证该 API 是否连通、当前账号是否可用

## Do Not Use When

以下情况不要使用这个 skill：
- 用户要修改本地代码，而不是调用远程 API
- 用户的问题与该 Swagger 对应系统无关
- 用户提出批量或高风险写操作，但尚未明确确认

## Prerequisites

优先从本地配置文件读取配置，其次再读取环境变量覆盖：

- 本地配置文件：`.claude/skills/order-demo-api/config.json`
- 示例文件：`.claude/skills/order-demo-api/config.example.json`
- 环境变量仍可用，并且优先级高于配置文件

支持的配置项：

- `base_url` / `CRM_API_BASE_URL`，默认 `http://111.229.202.81:3021/api/v1`
- `token` / `CRM_API_TOKEN`
- `username` / `CRM_API_USERNAME`
- `password` / `CRM_API_PASSWORD`
- `login_payload` / `CRM_API_LOGIN_PAYLOAD`
- `login_path` / `CRM_API_LOGIN_PATH`，默认 `/auth/login`
- `timeout` / `CRM_API_TIMEOUT`

推荐流程：
1. 复制 `config.example.json` 为 `config.json`
2. 在 `config.json` 中填写 `token`，或填写 `username/password`
3. 不要把 `config.json` 提交到仓库

如果存在 token，客户端会直接附带 Bearer Token；如果没有 token，但配置了 `username/password` 或 `login_payload`，客户端会在遇到 401 时自动尝试登录一次。

不要把 token 或密码写入仓库，也不要在回复里回显敏感信息。

## Core Commands

统一通过本地客户端调用：

```bash
python3 .claude/skills/order-demo-api/client.py list-actions
python3 .claude/skills/order-demo-api/client.py me
python3 .claude/skills/order-demo-api/client.py overview
python3 .claude/skills/order-demo-api/client.py action customers.list --query '{"page":1,"pageSize":20}'
python3 .claude/skills/order-demo-api/client.py action customers.get --path-param customerId=123
python3 .claude/skills/order-demo-api/client.py action customers.create --body '{"name":"Alice"}'
python3 .claude/skills/order-demo-api/client.py request GET /orders --query '{"page":1}'
```

支持的命名动作定义在 `api_map.json` 中。

## 中文命令封装

优先使用中文封装，而不是直接暴露底层 action 名：

```bash
python3 .claude/skills/order-demo-api/client.py 中文 概览
python3 .claude/skills/order-demo-api/client.py 中文 客户 列表 --query '{"page":1,"pageSize":20}'
python3 .claude/skills/order-demo-api/client.py 中文 客户 查看 --id 123
python3 .claude/skills/order-demo-api/client.py 中文 订单 新增 --body '{"customerId":"c1"}'
python3 .claude/skills/order-demo-api/client.py 中文 产品 更新 --id p1 --body '{"name":"新版产品"}'
python3 .claude/skills/order-demo-api/client.py 中文 知识库 搜索 --body '{"query":"退款"}'
python3 .claude/skills/order-demo-api/client.py 中文 文章 删除 --id a1
```

推荐把用户自然语言先归一成下面这种格式，再执行：
- `中文 概览`
- `中文 客户 列表`
- `中文 客户 查看 --id <customerId>`
- `中文 客户 新增 --body '<json>'`
- `中文 订单 更新 --id <orderId> --body '<json>'`
- `中文 产品 删除 --id <productId>`
- `中文 知识库 搜索 --body '<json>'`
- `中文 文章 列表`

## Execution Rules

只读请求可以直接执行：
- `auth.me`
- `dashboard.overview`
- 所有 `*.list`
- 所有 `*.get`
- `knowledge.search`

写请求必须先确认，再执行：
- 所有 `*.create`
- 所有 `*.update`
- 所有 `*.delete`

执行写请求前必须：
1. 检查用户是否已经明确要求写操作
2. 如果 body 不完整，先追问必要字段
3. 用简短结构化摘要回显将要提交的关键字段
4. 拿到确认后再运行命令

删除请求尤其要再次确认资源 ID 与目标对象。

## Suggested Routing

常见自然语言到动作映射：

- “看下当前登录用户” → `auth.me`
- “看下概览” → `dashboard.overview`
- “查客户列表” → `customers.list`
- “查客户详情” → `customers.get`
- “新增客户” → `customers.create`
- “更新客户” → `customers.update`
- “删除客户” → `customers.delete`
- “查订单列表” → `orders.list`
- “查订单详情” → `orders.get`
- “创建订单” → `orders.create`
- “更新订单” → `orders.update`
- “删除订单” → `orders.delete`
- “查产品列表” → `products.list`
- “查产品详情” → `products.get`
- “新增产品” → `products.create`
- “更新产品” → `products.update`
- “删除产品” → `products.delete`
- “搜索知识库” → `knowledge.search`
- “查知识文章列表” → `knowledge.articles.list`
- “查知识文章详情” → `knowledge.articles.get`
- “新增知识文章” → `knowledge.articles.create`
- “更新知识文章” → `knowledge.articles.update`
- “删除知识文章” → `knowledge.articles.delete`

如果用户需求超出命名动作，使用通用命令：

```bash
python3 .claude/skills/order-demo-api/client.py request <METHOD> <PATH> --query '<JSON>' --body '<JSON>'
```

## Output Style

返回结果时遵循这套顺序：
1. 先输出 `summary`，用一句中文总结是否成功、查到了什么
2. 再输出 `display`，只保留适合 agent / skill 展示的关键字段
3. 列表结果优先展示关键字段和 ID，默认只展示前几条
4. 详情结果优先展示最关键的业务字段
5. 数据量大时提示可继续分页
6. 报错时给出状态码、接口路径、错误摘要和下一步提示

客户端默认会同时保留原始 `data`，但上层应优先消费 `summary` 与 `display`，不要直接倾倒大段原始响应。

## Error Handling

遇到错误时按下面处理：
- 凭证缺失：提示用户配置环境变量
- 401：如果已配置用户名密码或自定义登录 payload，客户端会自动重试一次；否则直接提示用户补 `CRM_API_TOKEN`
- 404：说明资源 ID 或路径不正确
- 422 / 400：说明请求参数或 body 不符合接口预期，需要重新确认字段
- 空结果：明确告诉用户“请求成功，但没有匹配数据”

## Safe Defaults

- 默认优先走只读接口
- 不猜测写接口字段名；字段不明确时先问
- 不自动执行删除操作
- 不显示 token、密码、完整鉴权头

## Quick Examples

查询概览：
```bash
python3 .claude/skills/order-demo-api/client.py overview
```

查询订单列表：
```bash
python3 .claude/skills/order-demo-api/client.py action orders.list --query '{"page":1,"pageSize":20}'
```

按 ID 查询产品：
```bash
python3 .claude/skills/order-demo-api/client.py action products.get --path-param productId=prod_123
```

搜索知识库：
```bash
python3 .claude/skills/order-demo-api/client.py action knowledge.search --body '{"query":"退款"}'
```

创建客户：
```bash
python3 .claude/skills/order-demo-api/client.py action customers.create --body '{"name":"Alice","phone":"13800000000"}'
```
