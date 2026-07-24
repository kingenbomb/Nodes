# Nodes

ProxyScrape 注册与代理导出工具。浏览器仅用于获取 Turnstile token，邮箱创建、注册、收信、验证与代理列表获取均通过 HTTP 完成。

## 运行界面

![命令行运行界面](docs/images/runtime-menu.png)

启动后可设置注册数量、并发线程数以及是否隐藏浏览器窗口。

## 免责声明

本项目仅供技术研究、学习交流及合法授权的自动化测试使用，不得用于违反所在地法律法规、目标平台服务条款或损害第三方权益的活动。严禁用于批量养号、垃圾信息、欺诈、绕过访问控制或风控机制等滥用场景。

使用者应自行确认其操作已获得必要授权，并独立承担账号封禁、数据丢失、服务中断及其他直接或间接后果。项目作者与贡献者不对软件的可用性、准确性、合规性作任何明示或默示保证，也不对使用本项目产生的损失或法律责任负责。

## 项目文件

| 文件 | 说明 |
|------|------|
| `proxyscrape_register.py` | 交互式注册、邮箱验证与代理导出入口 |
| `proxyscrape_auth.py` | ProxyScrape 登录、注册与 Token 管理封装 |
| `启动注册.bat` | Windows 启动脚本 |
| `account/` | 本地账号与 Token 输出，不进入 Git |
| `node/` | 本地代理账号和节点输出，不进入 Git |

## 环境要求

- Python 3.10+
- Chromium/Chrome
- `turnstilePatch` 浏览器扩展

安装 Python 依赖：

```bash
python -m pip install requests DrissionPage PyJWT
```

## 本地隐私配置

项目不会在源码中保存 YYDS Key、自有域名或本机绝对路径。运行前通过环境变量配置：

| 环境变量 | 必需 | 说明 |
|----------|------|------|
| `YYDS_API_KEY` | 是 | YYDS Mail API Key |
| `YYDS_DOMAIN` | 否 | 已在 YYDS 验证的自有域名；留空则由 YYDS 选择域名 |
| `TURNSTILE_EXTENSION_PATH` | 是 | 本机 `turnstilePatch` 目录 |
| `PYTHON_EXE` | 否 | `启动注册.bat` 使用的 Python；默认使用 PATH 中的 `python` |

PowerShell 当前窗口配置示例：

```powershell
$env:YYDS_API_KEY = "YOUR_YYDS_API_KEY"
$env:YYDS_DOMAIN = ""
$env:TURNSTILE_EXTENSION_PATH = "D:\path\to\turnstilePatch"
python .\proxyscrape_register.py
```

这些值只存在于当前 PowerShell 进程，不会写入仓库。

## 切换 YYDS 域名

### 使用 YYDS 自动选择的域名

只设置 API Key，将 `YYDS_DOMAIN` 留空：

```powershell
$env:YYDS_API_KEY = "YOUR_YYDS_API_KEY"
Remove-Item Env:YYDS_DOMAIN -ErrorAction SilentlyContinue
```

创建邮箱时，域名由 YYDS 服务选择。

### 使用自己的域名

先在 YYDS 中添加并验证自有域名，然后仅在本地设置：

```powershell
$env:YYDS_API_KEY = "YOUR_YYDS_API_KEY"
$env:YYDS_DOMAIN = "mail.example.com"
```

`mail.example.com` 是公开占位符，请替换为已经验证的真实域名。真实域名不得写入源码、README 或提交记录。

两种模式仍使用同一套 YYDS API；切换后重新启动程序即可生效。

## 运行

PowerShell：

```powershell
python .\proxyscrape_register.py
```

或双击 `启动注册.bat`。如果 Python 不在 PATH 中，可先设置：

```powershell
$env:PYTHON_EXE = "D:\path\to\python.exe"
```

运行结果会写入：

- `account/accounts_*.jsonl`：邮箱、密码、访问 Token 和账户信息。
- `node/proxies_*.txt`：代理用户名、密码和节点地址。
- `proxyscrape_token.json`：`proxyscrape_auth.py` 的本地登录会话。

以上均包含敏感信息，已由 `.gitignore` 排除，禁止手动强制提交。

## 安全检查

上传或分享前建议执行：

```bash
git status --ignored
git grep -n -I -E "API_KEY|access_token|refresh_token|proxy_password"
```

公开的 ProxyScrape Turnstile sitekey 和 Google OAuth Client ID 来自网页前端，不是账户私钥；YYDS API Key、登录 Token、邮箱账户和代理凭据必须始终保留在本地。
