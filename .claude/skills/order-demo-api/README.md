# order-demo-api

项目内 Claude Code skill，用于连接 `Order Demo Workspace API`。

## 文件说明

- `SKILL.md`：skill 入口说明与调用规则
- `client.py`：Python 客户端，负责登录、鉴权和请求发送
- `api_map.json`：命名动作与接口路径映射

## 环境变量

如果接口启用了鉴权，推荐至少配置以下一种方式。没有登录态也可以先直接请求；若接口要求鉴权，再补 token。

### 方式一：直接提供 token

```bash
export CRM_API_TOKEN='your-jwt-token'
```

### 方式二：提供用户名密码

```bash
export CRM_API_USERNAME='your-username'
export CRM_API_PASSWORD='your-password'
```

### 方式三：自定义登录 payload

如果登录接口不是默认的 `username/password` 格式，可以直接提供 JSON：

```bash
export CRM_API_LOGIN_PAYLOAD='{"email":"demo@example.com","password":"secret"}'
```

### 可选变量

```bash
export CRM_API_BASE_URL='http://111.229.202.81:3021/api/v1'
export CRM_API_LOGIN_PATH='/auth/login'
export CRM_API_TIMEOUT='20'
```

## 常用命令

列出可用动作：

```bash
python3 .claude/skills/order-demo-api/client.py list-actions
```

查看当前用户：

```bash
python3 .claude/skills/order-demo-api/client.py me
```

查看 dashboard 概览：

```bash
python3 .claude/skills/order-demo-api/client.py 中文 概览
```

查询客户列表：

```bash
python3 .claude/skills/order-demo-api/client.py 中文 客户 列表 --query '{"page":1,"pageSize":20}'
```

查询订单详情：

```bash
python3 .claude/skills/order-demo-api/client.py 中文 订单 查看 --id order_123
```

创建产品：

```bash
python3 .claude/skills/order-demo-api/client.py 中文 产品 新增 --body '{"name":"Demo Product"}'
```

搜索知识库：

```bash
python3 .claude/skills/order-demo-api/client.py 中文 知识库 搜索 --body '{"query":"退款"}'
```

通用请求：

```bash
python3 .claude/skills/order-demo-api/client.py request GET /products --query '{"page":1}'
python3 .claude/skills/order-demo-api/client.py request PATCH /customers/cus_123 --body '{"name":"New Name"}'
```

## 调试建议

先做最小验证：

```bash
python3 .claude/skills/order-demo-api/client.py list-actions
python3 .claude/skills/order-demo-api/client.py 中文 概览
python3 .claude/skills/order-demo-api/client.py 中文 客户 列表
```

如果返回 401：
- 先检查这个接口是否本来就要求鉴权
- 若要求鉴权，补 `CRM_API_TOKEN`
- 只有你明确配置了用户名密码 / 登录 payload 时，客户端才会尝试自动重试一次

如果返回 404：
- 检查 `CRM_API_BASE_URL`
- 检查资源 ID 或路径

如果返回 400 / 422：
- 检查 `--body` 或 `--query` 的 JSON 结构
- 重新确认接口实际需要的字段

## 输出结构

客户端默认返回三层信息：

- `summary`：一句中文摘要，适合直接给 skill / agent 使用
- `display`：提炼后的展示数据，适合 UI 或自然语言层消费
- `data`：原始接口响应，便于调试或二次处理

建议上层优先消费 `summary` 和 `display`，只在需要排查问题时再查看 `data`。

## 说明

Swagger 当前没有暴露详细 schema，因此首版客户端采用“路径 + 方法 + body/query 透传”的方式，确保先把调用链路打通，再逐步细化字段映射。
