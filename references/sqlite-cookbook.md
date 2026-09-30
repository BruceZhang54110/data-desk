# SQLite 仓库手册（data-desk 版）

data-desk 用 SQLite 文件作为持久仓库，用 DuckDB（sqlite 扩展）读写它。本手册记录二者的边界与技巧。

## ATTACH 语法

```sql
LOAD sqlite;
ATTACH '绝对或相对路径.sqlite' AS db (TYPE sqlite);          -- 可读写
ATTACH '路径.sqlite' AS db (TYPE sqlite, READ_ONLY);          -- 只读
USE db;                                                        -- 设为默认库
DETACH db;                                                     -- 断开
```

挂载后：`SHOW TABLES;`、`db.table_name` 限定表名、跨库 JOIN 均可用。

## 类型系统差异（重要）

- SQLite 是动态类型（类型亲和性），DuckDB 是强类型。通过 sqlite 扩展读出时，DuckDB 会把 SQLite 值映射为 `VARCHAR / BIGINT / DOUBLE / BLOB` 等
- CSV 导入建表时若想得到更精确的类型（DATE、DECIMAL），先 `CREATE TABLE ... (col DATE, ...)` 定义好列型，再 `INSERT INTO t SELECT ... FROM 'f.csv'`
- 存 JSON 列：SQLite 中声明为 TEXT，查询时用 DuckDB 的 JSON 函数处理 `col->>$.key` 或 `json_extract_string(col, '$.key')`
- 时间戳：SQLite 常用整数 unix 时间或 ISO 文本；转换用 `to_timestamp(col)` 或 `col::TIMESTAMP`

## DuckDB 写 SQLite 的支持范围

| 操作 | 支持 |
|---|---|
| CREATE TABLE / INSERT / UPDATE / DELETE | 支持 |
| CREATE OR REPLACE / CTAS | 支持 |
| ALTER TABLE（加列、改名） | 部分支持，失败时改用 sqlite3 CLI |
| 建索引、触发器、视图 | 建议用 sqlite3 CLI 透传 |
| PRAGMA（VACUUM、integrity_check 等） | 用 sqlite3 CLI |

用 sqlite3 CLI 透传原生 SQL：

```bash
sqlite3 DB_PATH "VACUUM;"
sqlite3 -header -column DB_PATH "SELECT name FROM sqlite_master WHERE type='table';"
```

## 性能与体积

- 批量写入：一条 `INSERT INTO t SELECT * FROM 'big.csv'` 远快于逐行 INSERT
- 库文件增大后执行 `sqlite3 DB_PATH "VACUUM;"` 回收空间
- 大分析查询建议把 SQLite 表先拉成 DuckDB 临时表再算（SQLite 行存逐行读慢）：
  `CREATE TEMP TABLE buf AS SELECT * FROM db.t;` 然后对 buf 做重计算

## 备份与安全

- 单文件即整库：`cp main.sqlite backups/main-$(date +%F).sqlite` 即可备份
- 批量修改前先备份；DuckDB 侧的错误 SQL 不太会损坏 SQLite 文件，但覆盖语义（CREATE OR REPLACE）会丢旧数据
- WAL 模式的库（存在 -wal/-shm 附属文件）复制时要连同附属文件一起拷，或先 `PRAGMA wal_checkpoint(TRUNCATE);`
- 密码/敏感列不要明文进 `_meta` 记录

## _meta 导入登记表（约定）

建库时创建：

```sql
CREATE TABLE IF NOT EXISTS _meta (
  table_name VARCHAR, source_file VARCHAR,
  row_count BIGINT, imported_at TIMESTAMP DEFAULT now()
);
```

每次导入后登记一行，用户问"库里有什么/数据哪来的"时直接查它。
