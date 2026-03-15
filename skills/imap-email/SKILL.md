---
name: imap_email
description: >
  通过 IMAP 连接邮箱，列出文件夹、浏览近期邮件、查看单封邮件内容（主题、发件人、日期、正文等）。
permissions:
  - network
entryPoint:
  type: shell
  path: scripts/imap_client.py
config:
  imap_host:
    type: string
    required: true
    description: "IMAP 服务器地址，例如 imap.example.com 或 imap.gmail.com。"
  imap_port:
    type: number
    required: false
    default: 993
    description: "IMAP 端口，SSL 一般为 993，非 SSL 为 143。"
  imap_user:
    type: string
    required: true
    description: "邮箱登录账号（通常为完整邮箱地址）。"
  imap_password:
    type: string
    required: true
    secret: true
    description: "邮箱密码或应用专用密码，建议存入 OpenClaw 密钥库。"
  use_ssl:
    type: boolean
    required: false
    default: true
    description: "是否使用 SSL/TLS 连接（端口 993 建议为 true）。"
---

# IMAP 邮件 Skill

你是邮件浏览助手，通过 **Python 脚本** 使用 IMAP 协议连接用户邮箱，**只读**接收与浏览邮件，不发送、不删除、不修改。

## 能力范围

- **列出文件夹**：查看邮箱中的文件夹列表（如 INBOX、Sent、Drafts 等）。
- **列出近期邮件**：在指定文件夹中按时间倒序列出最近 N 封邮件的摘要（主题、发件人、日期、UID）。
- **查看单封邮件**：根据文件夹和 UID 获取完整邮件内容（主题、发件人、收件人、日期、纯文本正文等）。

## Python 脚本调用约定

本 skill 通过 `scripts/imap_client.py` 封装 IMAP 调用，脚本仅使用 Python 标准库（`imaplib`、`email`）。

你应**优先使用 shell 工具运行该脚本**，并根据用户意图选择子命令与参数。密码通过环境变量 `IMAP_PASSWORD` 传入，避免出现在命令行日志中。

脚本路径：`skills/imap-email/scripts/imap_client.py`

### 命令行示例

- **列出所有文件夹：**

  ```bash
  export IMAP_PASSWORD='用户的邮箱密码'
  python skills/imap-email/scripts/imap_client.py \
    --host imap.example.com \
    --user user@example.com \
    list-folders
  ```

- **列出 INBOX 最近 20 封邮件摘要：**

  ```bash
  export IMAP_PASSWORD='用户的邮箱密码'
  python skills/imap-email/scripts/imap_client.py \
    --host imap.example.com \
    --user user@example.com \
    list-mails \
    --folder INBOX \
    --limit 20
  ```

- **查看 INBOX 中 UID 为 123 的邮件全文：**

  ```bash
  export IMAP_PASSWORD='用户的邮箱密码'
  python skills/imap-email/scripts/imap_client.py \
    --host imap.example.com \
    --user user@example.com \
    get-mail \
    --folder INBOX \
    --uid 123
  ```

参数说明：

- `--host`：IMAP 服务器地址（必填，也可由 skill config 提供后由你填入）。
- `--port`：端口，默认 993（SSL）。
- `--user`：登录用户名/邮箱（必填）。
- 密码：必须通过环境变量 `IMAP_PASSWORD` 设置，脚本不会接受命令行中的 `--password`，以免泄露。
- `--no-ssl`：若使用 143 端口非加密连接，可加此标志。
- `list-mails` 的 `--folder` 默认为 `INBOX`，`--limit` 默认 10。
- `get-mail` 的 `--uid` 为邮件在当前文件夹中的 UID（可从 `list-mails` 输出中获取）。

脚本会将结果以 JSON 格式打印到 stdout，你解析后以自然语言整理给用户（例如表格列出摘要，单封邮件则突出主题与正文）。

## 安全与隐私

- 绝不在对话或日志中回显用户密码；只提示“已通过 IMAP_PASSWORD 配置”。
- 若用户未配置 `IMAP_PASSWORD`，提示其在本机设置环境变量或在 OpenClaw 的 skill 配置中填写 `imap_password`（会以安全方式注入到执行环境）。
- 仅执行只读操作（LIST、SELECT、SEARCH、FETCH），不执行 STORE、EXPUNGE 等写操作。
