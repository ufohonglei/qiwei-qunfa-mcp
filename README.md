# 企微群发 MCP 服务

这个 MCP 服务通过 stdio 运行，不占用固定端口。它不会直接访问数据库，只调用后端
`/api/v1/wecom-broadcast/*` 接口，并通过 `Authorization: Bearer <token>` 让后端按用户角色权限判断是否允许操作。

## 生成用户 Token

用户也可以登录后台后，点击右上角用户名，打开 `MCP Token` 弹窗自助创建和删除自己的 token。

管理员也可以在已部署的后端服务上为系统用户生成 MCP token：

```bash
cd /path/to/zhongtai-api
python3 scripts/create_user_api_token.py <username> --name "Codex MCP"
```

脚本只会显示一次明文 token，数据库中保存的是 token hash。

## 安装

### 从本地目录安装

开发或内部分发时，可以直接从这个目录安装：

```bash
pipx install /path/to/mcp-server
```

或使用 `uvx` 直接运行：

```bash
uvx --from /path/to/mcp-server qiwei-qunfa-mcp
```

如果包已经发布到 PyPI 或私有 Python 包仓库，其他电脑可以直接使用：

```bash
uvx qiwei-qunfa-mcp
```

### 从 Git 地址安装

如果把 `mcp-server/` 作为单独仓库发布，也可以这样安装：

```bash
pipx install "git+https://github.com/ufohonglei/qiwei-qunfa-mcp.git"
```

或在 MCP 配置里直接让 `uvx` 从 Git 地址运行。

## MCP 配置

推荐使用可安装包入口：

```json
{
  "mcpServers": {
    "qiwei-qunfa": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/ufohonglei/qiwei-qunfa-mcp.git",
        "qiwei-qunfa-mcp"
      ],
      "env": {
        "QIWEI_API_BASE": "https://api.your-domain.com",
        "QIWEI_API_TOKEN": "qwmcp_xxx"
      }
    }
  }
}
```

如果已经用 `pipx install` 装到本机，也可以配置为：

```json
{
  "mcpServers": {
    "qiwei-qunfa": {
      "command": "qiwei-qunfa-mcp",
      "args": [],
      "env": {
        "QIWEI_API_BASE": "https://api.your-domain.com",
        "QIWEI_API_TOKEN": "qwmcp_xxx"
      }
    }
  }
}
```

旧的源码路径配置仍然可用：

```json
{
  "mcpServers": {
    "qiwei-qunfa": {
      "command": "python3",
      "args": [
        "/path/to/qiwei-qunfa-mcp/server.py"
      ],
      "env": {
        "QIWEI_API_BASE": "http://127.0.0.1:8000",
        "QIWEI_API_TOKEN": "qwmcp_xxx"
      }
    }
  }
}
```

## 权限

MCP 不单独维护权限。每个工具调用都会携带 `QIWEI_API_TOKEN` 请求后端，后端通过 token 找到系统用户，再按该用户角色里的权限点判断。

主要权限对应关系：

```text
search_wecom_users          recipient_group.view
refresh_wecom_users         recipient_group.edit
search_wecom_chats          recipient_group.view
refresh_wecom_chats         recipient_group.edit
list_recipient_groups       recipient_group.view
create_recipient_group      recipient_group.create
update_recipient_group      recipient_group.edit
delete_recipient_group      recipient_group.delete
list_broadcast_tasks        wecom_broadcast.view
get_broadcast_task          wecom_broadcast.view
create_broadcast_task       wecom_broadcast.create
update_broadcast_task       wecom_broadcast.edit
cancel_broadcast_task       wecom_broadcast.execute
delete_broadcast_task       wecom_broadcast.delete
upload_broadcast_image      wecom_broadcast.create
```

如果用户没有对应权限，后端会返回 403，MCP 会把错误返回给客户端。
