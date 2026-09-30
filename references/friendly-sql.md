# DuckDB Friendly SQL 速查（data-desk 版）

生成 SQL 时优先使用以下 DuckDB 惯用法，代码更短、更不易错。

## 紧凑子句
- **FROM-first**：`FROM table WHERE x > 10`（省略 `SELECT *`）
- **GROUP BY ALL / ORDER BY ALL**：自动按非聚合列分组 / 按所有列排序
- **SELECT * EXCLUDE (a, b)**：通配符中剔除列
- **SELECT * REPLACE (expr AS col)**：原位替换某列
- **UNION ALL BY NAME**：按列名合并不同结构的表
- **LIMIT 10%**：按百分比取样
- **尾逗号合法**：SELECT 列表末尾可带逗号

## 常用特性
- `count()` 不必写 `count(*)`
- **列别名复用**：WHERE / GROUP BY / HAVING 可直接用 SELECT 里定义的别名
- `COLUMNS('err_.*')`：正则批量操作列，支持 lambda
- `count() FILTER (WHERE x > 10)`：条件聚合
- `DESCRIBE t` / `SUMMARIZE t`：结构 / 统计画像
- `PIVOT / UNPIVOT`：宽长表互转
- `SET VARIABLE x = ...` + `getvariable('x')`：SQL 内变量

## 文件直查与导入
- `FROM 'file.csv'`、`FROM 'data/*.parquet'`（支持 glob）
- CSV 自动检测表头与分隔符；显式控制：`read_csv('f', delim=';', encoding='utf-8', header=true)`
- JSON：`read_json('f', format='array')`；NDJSON：`read_json('f', format='newline_delimited')`
- Excel：`read_xlsx('f', header=true)`（需 excel 扩展）

## 表达式
- 点号链式：`col.trim().lower()`
- 列表推导：`[x*2 FOR x IN list_col]`
- 切片与负索引：`col[1:3]`、`col[-1]`
- `format('{} -> {}', a, b)`
- STRUCT：`{'a': 1}.a`、`s.*` 展开

## JOIN
- `ASOF JOIN`：按时间就近匹配
- `POSITIONAL JOIN`：按行号对齐
- `LATERAL`：子查询引用前表

## 写入
- `CREATE OR REPLACE TABLE`：免 DROP
- `CREATE TABLE t AS SELECT ...`（CTAS）
- `INSERT INTO t BY NAME`：按列名插入
- `INSERT OR IGNORE / OR REPLACE INTO`：upsert
