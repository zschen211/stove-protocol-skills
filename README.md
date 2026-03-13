## stove-protocol-skills

本仓库提供了一套脚本，帮助你从 Stove Protocol 文档站点抓取 API 文档，并将其转换为可阅读的 Markdown 文件。

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
- `output/`：按 `public/maker/taker` 分类保存抓取到的精简版 HTML（已加入 `.gitignore`）。
- `api-desc/`：按 `public/maker/taker` 分类保存生成的 Markdown（已加入 `.gitignore`）。

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

### 注意事项

- `output/` 与 `api-desc/` 都是生成产物，已经在 `.gitignore` 中忽略，默认不提交到 git。
- 如果文档站结构发生变化（例如正文容器不再是 `div.vp-doc`），可能需要调整脚本中的解析与清洗逻辑。
