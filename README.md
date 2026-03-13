## stove-protocol-skills

本仓库提供了一套脚本和 OpenClaw Skills，帮助你从 Stove Protocol 文档站点抓取 API 文档、转换为 Markdown，并基于这些文档构建可直接调用 Stove API 的技能。

### 依赖与环境

- Python 3.12（推荐使用 `uv` 管理虚拟环境）
- 已使用 `uv` 创建虚拟环境并安装依赖：

```bash
uv venv .venv
source .venv/bin/activate
uv pip install requests beautifulsoup4
```

后续使用脚本前，请确保激活虚拟环境：

```bash
source .venv/bin/activate
```

### 目录结构

- `scripts/crawler.py`：从 Stove Protocol 文档站点抓取并清洗 HTML。
- `scripts/convert_html_to_markdown.py`：将清洗后的 HTML 转为 Markdown。
- `scripts/sync_references.py`：把 `api-desc` 中的文档复制到各个 skill 的 `references/` 目录，并按文档内第一个 `#` 标题重命名；空文档会被跳过。
- `output/`：按 `public/maker/taker` 分类保存抓取到的精简版 HTML（已加入 `.gitignore`）。
- `api-desc/`：按 `public/maker/taker` 分类保存生成的 Markdown（已加入 `.gitignore`）。
- `skills/`：OpenClaw skills 定义与脚本：
  - `stove-public-api/`：Public API 相关 skill（只读公开数据）。
    - `SKILL.md`：skill 元数据与说明。
    - `scripts/public_api.py`：使用 Python 标准库封装的 Public API 调用入口（stats、ticker-stats、ticker-heatmap）。
    - `references/*.md`：与 Public API 相关的 Markdown 文档。
  - `stove-maker-api/`：Maker API 相关 skill（JWT 鉴权）。
    - `scripts/maker_api.py`：封装订单查询/创建/取消、手续费估算、仓位、nonce 等调用。
    - `references/*.md`：Maker API 文档。
  - `stove-taker-api/`：Taker API 相关 skill（API Key 鉴权）。
    - `scripts/taker_api.py`：封装校验/锁单/解锁/成交/拒绝，以及订单和成交记录查询。
    - `references/*.md`：Taker API 文档。

### 使用步骤

#### 1. 爬取文档 HTML

在仓库根目录执行：

```bash
source .venv/bin/activate
python scripts/crawler.py --output-dir output --workers 8 --log-level INFO
```

说明：

- `--output-dir`：HTML 输出根目录（默认 `output`）。
- `--workers`：每个站点的爬取线程数。
- `--log-level`：日志级别（`DEBUG/INFO/WARNING/ERROR`）。

爬虫会访问以下入口，并在其路径下递归抓取页面：

- `https://docs.proto.stove.finance/public`
- `https://docs.proto.stove.finance/taker`
- `https://docs.proto.stove.finance/maker`

抓取时会自动：

- 只保留页面正文（`div.vp-doc` 中的内容），去掉导航、脚本等冗余结构。
- 将每个页面保存为 `md5(url).html`，按模块分目录：`output/public|maker|taker`。

#### 2. 将 HTML 转换为 Markdown

在仓库根目录执行：

```bash
source .venv/bin/activate
python scripts/convert_html_to_markdown.py
```

脚本会：

- 遍历 `output/public|maker|taker` 下的所有 `.html`。
- 按页面结构将标题、段落、表格、列表、代码块等转换为 Markdown。
- 将结果写入：
  - `api-desc/public/*.md`
  - `api-desc/maker/*.md`
  - `api-desc/taker/*.md`

部分入口壳页面（例如仅包含空的 `div.vp-doc`，内容由前端运行时动态加载）会生成空的 Markdown，这是因为静态 HTML 中本身就没有可转换的正文内容。

#### 3. 同步文档到各个 Skill 的 `references/`

在仓库根目录执行：

```bash
source .venv/bin/activate
python scripts/sync_references.py
```

脚本会：

- 遍历 `api-desc/public|maker|taker` 下的所有 `.md`。
- 读取每个文件中第一个 `#` 标题，用作新的文件名（例如 `# Maker API` → `Maker API.md`）。
- 将文件内容复制到：
  - `skills/stove-public-api/references/*.md`
  - `skills/stove-maker-api/references/*.md`
  - `skills/stove-taker-api/references/*.md`
- 如果源 `md` 内容为空，则跳过，不复制。
- 如果目标文件已存在，则直接覆盖为最新版本。

#### 4. 在 OpenClaw 中使用 Skills 调用 Stove API

三个 skills 都通过 Python 脚本（`entryPoint.type: shell`）封装了 HTTP 调用逻辑，脚本只依赖 Python 标准库：

- Public：
  - `python skills/stove-public-api/scripts/public_api.py --env prod stats`
  - `python skills/stove-public-api/scripts/public_api.py --env prod ticker-stats --symbol AAPL --exchange 0`
  - `python skills/stove-public-api/scripts/public_api.py --env prod ticker-heatmap --exchange 0`
- Maker：
  - `python skills/stove-maker-api/scripts/maker_api.py --env prod --jwt-token YOUR_JWT orders --ticker AAPL --status pending,locked`
  - `python skills/stove-maker-api/scripts/maker_api.py --env prod --jwt-token YOUR_JWT positions`
- Taker：
  - `python skills/stove-taker-api/scripts/taker_api.py --env prod --api-key YOUR_API_KEY orders --status locked,filled`
  - `python skills/stove-taker-api/scripts/taker_api.py --env prod --api-key YOUR_API_KEY fill --body '{"order_hash":"0x...","...": "..."}'`

脚本会将 API 返回的 JSON 原样打印到标准输出，skill 本身负责解析 `code` 和 `data` 字段，并以更易读的形式总结返回给用户。

### 注意事项

- `output/` 与 `api-desc/` 都是生成产物，已经在 `.gitignore` 中忽略，默认不提交到 git。
- 如果文档站结构发生变化（例如正文容器不再是 `div.vp-doc`），可能需要调整爬虫与 Markdown 转换逻辑。
- 如果 Stove API 的路由或请求体结构发生变化，可根据 `skills/*/references/*.md` 中的最新文档，更新对应的 `scripts/*.py`。

