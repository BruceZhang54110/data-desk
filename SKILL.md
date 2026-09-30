---
name: data-desk
description: 'Local data workbench: create and manage a local SQLite database, then use the DuckDB engine to query, analyze, profile, and convert local files (CSV, JSON, Parquet, Excel, SQLite, GeoJSON) without any server setup. Use when the user wants to create a local database, import data files into tables, run SQL or ask data questions in natural language, summarize or profile a dataset, convert between file formats, or export query results. Triggers on: 建个数据库, 存到数据库, 导入数据, 查一下这份数据, 分析这个CSV或Excel, 数据统计汇总, convert to parquet, 本地数据分析, SQL snippets, 对账, 发票核对, 余额表, 银行流水, 账龄, 税负, 财税分析, or any request to persist and query local data.'
agent_created: true
---

# Data Desk — 本地数据案头

把它想象成放在你电脑里的一套"私人仓库 + 算账先生"：

- **仓库**是一个普通的 SQLite 文件——就像一个 Excel 文件一样，可以随意拷贝、备份、发给别人，它就是你自己的数据仓库
- **算账先生**是 DuckDB，一个速度飞快的查询引擎，负责往仓库里存数据、算数据、取数据

你不需要懂 SQL，也不需要安装任何数据库软件、不需要联网。直接说人话就行，比如：

- "帮我把这个 CSV 存进数据库" → 自动建表导入
- "上个月北京卖了多少" → 自动翻译成 SQL 去查，给你答案
- "这份数据长什么样" → 自动做一张字段和统计的速览表
- "导出成 Excel / Parquet" → 一句话完成格式转换
- "把这份 Excel 里的客户名单和库里的订单表对一下" → **不同格式的文件直接联查**：CSV、Excel、Parquet、JSON、数据库里的表，不管存在哪、是什么格式，都能放在同一条查询里互相 JOIN、汇总对比——不用先统一起来，也不用导来导去
- 你说行话它也懂：说"对账""核发票""余额表对比"，会自动进入财税模式，按借贷、红冲、期间这些行规来算（详见下方"领域识别"）

**工作原理（一句话）**：DuckDB 可以把 SQLite 文件"挂载"成自己的数据库直接读写，同时它天生就能直接读 CSV、JSON、Parquet、Excel 等文件。所以不管数据是散落的文件还是库里的表，都交给同一个引擎处理——这也正是"跨格式联查"的底气：所有数据源在它眼里都是表，天然可以互相 JOIN。

## 前置检查

每次会话首次使用前：

```bash
command -v duckdb || test -x "$HOME/.local/bin/duckdb"
```

- `command -v duckdb` 找不到时，先探测 `$HOME/.local/bin/duckdb`（官方安装脚本 `install.duckdb.org` 的默认位置）和 `/usr/local/bin/duckdb`；找到后将其目录加入 PATH 或后续命令直接用完整路径
- 都找不到再按平台引导安装：macOS `brew install duckdb` 或官方脚本 `curl -fsSL https://install.duckdb.org | sh`；Linux 同官方脚本；Windows `winget install DuckDB.cli`。也可直接运行 `python scripts/data-desk.py init` 让脚本给出探测结果
- 安装后继续，不要中断任务

## 活动数据库（会话状态）

本技能维护"活动数据库"概念，配置存放在项目目录 `.data-desk/` 下：

- `.data-desk/active_db` — 纯文本，一行绝对路径，指向当前 SQLite 数据库文件
- 解析逻辑：环境变量 `DATA_DESK_DB` > `.data-desk/active_db` > 询问用户（默认建议 `./data/main.sqlite`）

```bash
mkdir -p .data-desk && echo "$PWD/data/main.sqlite" > .data-desk/active_db
```

所有子任务先解析活动库路径，再执行。用户说"换个库/新建一个库"时更新此文件。

## 核心任务

按用户意图路由到以下任务。每个任务都可用 `scripts/data-desk.py` 辅助脚本（见下文）或直接写 duckdb 命令完成。

### 1. 初始化 / 新建数据库

```bash
duckdb -c "INSTALL sqlite; LOAD sqlite; ATTACH 'DB_PATH' AS db (TYPE sqlite); SELECT 1;"
```

- SQLite 文件在首次写入时自动创建；父目录需存在（`mkdir -p`）
- 建议建库时同时建一个 `_meta` 表记录导入历史（文件名、表名、行数、时间），方便用户日后回顾
- 完成后报告：库路径、当前表清单

### 2. 导入数据（文件 → 表）

DuckDB 直接读文件建表，自动推断 schema：

```sql
-- CSV（自动识别表头和分隔符）
CREATE OR REPLACE TABLE t_name AS SELECT * FROM 'data.csv';

-- JSON / NDJSON
CREATE OR REPLACE TABLE t_name AS SELECT * FROM 'data.json';

-- Parquet（可 glob 批量）
CREATE OR REPLACE TABLE t_name AS SELECT * FROM 'data/*.parquet';

-- Excel（需先 INSTALL excel; LOAD excel;）
CREATE OR REPLACE TABLE t_name AS SELECT * FROM read_xlsx('file.xlsx', header = true);
```

规则：
- 表名从文件名派生（`sales_2026.csv` → `sales_2026`），非法字符转下划线
- 导入前先探一下文件（`DESCRIBE SELECT * FROM 'file'` 或 `SELECT count() FROM 'file'`），超大文件（>1M 行）先告知用户预计规模
- 导入后 `SELECT count()` 验证行数，并登记到 `_meta` 表
- 同名表默认 `CREATE OR REPLACE` 覆盖；若用户数据可能重复导入，先问还是追加（`INSERT INTO t SELECT * FROM ...`）

### 3. 查询与自然语言问答

会话流程：

1. `ATTACH 'DB_PATH' AS db (TYPE sqlite); USE db;`（不 `USE` 的话裸表名不可用，必须写 `db.表名`）
2. 了解表结构：`SHOW TABLES;` → 对相关表 `DESCRIBE db.t_name;`
3. 自然语言问题 → 生成 SQL（参考 `references/friendly-sql.md` 的 DuckDB 惯用法）→ 执行 → 用一句话解释结果

注意事项：
- **先估后查**：无 LIMIT 且目标表 >100 万行时，先建议加 `LIMIT` 或聚合，征得同意再执行
- 跨源联邦：SQLite 表可以和本地 CSV/Parquet 直接 JOIN（`FROM db.t JOIN 'other.csv' ON ...`），这是本技能的招牌能力，主动使用
- 只读分析场景可加 `(READ_ONLY)` 防误写
- 结果 >100 行时提示截断

### 4. 统计画像（profile）

快速了解一张表：

```sql
DESCRIBE db.t_name;    -- 列名与类型
SUMMARIZE db.t_name;   -- 每列统计：min/max/近似唯一数/空值率
```

用户问"这份数据长什么样/有哪些字段/质量如何"时，走这条路径并总结成简表。

### 5. 导出与格式转换

```sql
COPY (SELECT ...) TO 'out.parquet';                      -- Parquet
COPY (SELECT ...) TO 'out.csv' (FORMAT csv, HEADER);     -- CSV
COPY (SELECT ...) TO 'out.json' (FORMAT json, ARRAY true);
COPY (SELECT ...) TO 'out.xlsx' (FORMAT xlsx, HEADER true);  -- 需 excel 扩展；不带 HEADER 会丢表头
```

整表转储（导出库里的表）：`COPY db.t_name TO 'out.parquet';`。**输入与输出不得是同一个文件**——把 SQLite 库文件既当输入又当输出会破坏数据，脚本已做防护，手写命令时同样要遵守。GeoJSON 等空间格式需要先 `INSTALL spatial; LOAD spatial;`，再用 GDAL 驱动导出。

### 6. 表与库管理

- 列表：`SHOW TABLES;`
- 行数统计：对 SQLite 挂载表 `duckdb_tables()` 的 `estimated_size` 只是估计值（可能偏差较大），报给用户的行数要用 `SELECT count()` 实算
- 删表：`DROP TABLE db.t_name;`（执行前向用户确认表名）
- 改名：`ALTER TABLE db.t_name RENAME TO new_name;`
- 备份：直接 `cp` SQLite 文件即可（单文件即整库），建议在批量修改前备份
- 直查原始 SQL：用户给的 SQLite 语法 SQL 直接透传时，也可用 `sqlite3 DB_PATH` 执行（只读建议加 `.headers on` 与 `-readonly`）

## 领域识别

本技能按「基础引擎 → 领域包」分层（详见宪法原则 III，首个领域：`caishui` 财税）：

1. **命中**：用户话术或数据特征命中财税特征 → 加载 `references/caishui.md`，向用户声明"已进入财税模式"，会话内持续生效
2. **未命中**：按通用数据工具响应，不加载领域内容
3. **临界不确定**：一句话询问用户是否为财税场景，不猜测

- 触发关键词：科目、凭证、借贷、借方、贷方、余额表、流水、对账、进项、销项、发票、税、税率、申报、账龄、明细账、总账、红冲、价税合计
- 表结构特征：列名含"借方/贷方/科目编码/发票号码/价税合计"，或"交易日期+收支标志"组合
- 领域命中时配方优先；未命中走上方通用路由，既有行为不变

## 辅助脚本

`scripts/data-desk.py` 是跨平台 Python 辅助脚本（macOS / Linux / Windows 通用），优先用它减少重复写命令：

```bash
python scripts/data-desk.py init <db路径>            # 建库（含父目录）
python scripts/data-desk.py import <db> <文件...>    # 每个文件建一张同名表，打印行数
python scripts/data-desk.py tables <db>              # 列出表与实算行数
python scripts/data-desk.py query <db> "<SQL>"       # 执行 SQL，CSV 输出
python scripts/data-desk.py convert <输入文件> <输出文件>  # 按扩展名转换格式
```

- Windows 上同样可用（duckdb CLI 用 `winget install DuckDB.cli` 安装即可，脚本会自动探测 PATH 与常见安装位置）
- 脚本只做机械操作；涉及判断（表名冲突、大数据量确认、自然语言转 SQL）仍由本技能流程负责

## 错误处理

- `Extension "sqlite" not loaded` → `INSTALL sqlite; LOAD sqlite;` 后重试
- 表找不到 → 先 `SHOW TABLES` 列出现有表，给出最接近的候选
- 文件找不到 → `find "$PWD" -name "<名>" -not -path '*/.git/*'` 定位
- 文件编码/分隔符异常 → 显式指定 `read_csv('f', delim=';', encoding='utf-8')` 等参数
- SQLite 文件损坏或被锁 → 报告错误，建议从备份恢复；不要尝试修复损坏的库文件
- 其他持续报错 → 用报错关键词检索 DuckDB 官方文档（duckdb.org/docs）排查后重试

## 安全边界

- 只在用户明确同意的路径范围内读写文件；临时探查文件时优先 sandbox 模式：

```sql
SET allowed_paths=['FILE_PATH'];
SET enable_external_access=false;
SET lock_configuration=true;
```

注意：需要 `ATTACH` SQLite 或访问多种文件的任务不能开 `enable_external_access=false`，此时靠"只操作用户指定的文件"这一纪律兜底。

- 删表、覆盖同名表、批量修改前必须确认；修改前建议 `cp` 备份 SQLite 文件
- 不要把含敏感数据的查询结果原文写入日志或长期记忆
