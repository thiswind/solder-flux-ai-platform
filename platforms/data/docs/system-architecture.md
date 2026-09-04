# 云锡数据管理系统架构说明

## 1. 系统目标

云锡数据管理系统用于统一管理以下能力：

- 总体数据与详细数据的自动处理
- 有铅/无铅 Excel 的结构化提取
- 粒度分布、化学成分、质量指标的标准化存储
- 图片盘点与批次关联
- 数据问题复核
- 面向客户的可视化管理页面

## 2. 前后端职责划分

### 前端 `frontend/`

职责：

- 展示系统总览
- 手动触发数据处理任务
- 浏览结构化数据集
- 查看复核问题
- 查看数据源清单

技术栈：

- Vue 3
- Vite
- TypeScript
- Naive UI
- Vue Router
- Axios

### 后端 `backend/`

职责：

- 提供 REST API
- 管理 ETL 执行
- 连接 PostgreSQL
- 存储任务运行记录、数据集、复核问题、源文件清单
- 对接旧版 Excel 解析逻辑

技术栈：

- Python 3.9
- FastAPI
- SQLAlchemy
- Uvicorn
- PostgreSQL 16

## 3. 数据处理分层

### 3.1 原始层

来源目录：

- `excel/overall_data`
- `excel/specific_data`
- `image/`
- 外部图片盘

当前阶段默认只扫描 Excel 文本数据并建立 `source_file_inventory`。

说明：

- `image/` 与外部图片盘的扫描已暂时关闭
- 等文本数据链路稳定后，再恢复图片盘点与关联

### 3.2 解析层

当前阶段通过 `backend/app/services/legacy_etl.py` 复用旧版 ETL：

- `yunxi_data_platform`
- `excel/data_column.py`

这一步负责：

- 读取总体数据
- 读取详细数据
- 完成合并
- 输出结构化数据表
- 生成复核问题

### 3.3 标准层

后端将结构化结果落入数据库：

- `ingestion_runs`
- `source_file_inventory`
- `dataset_records`
- `review_issues`
- `system_artifacts`

其中 `dataset_records` 统一存放不同数据集的行级 JSON 数据，便于前端快速浏览和后续演化。

## 4. API 规划

当前 API：

- `GET /api/v1/health`
- `GET /api/v1/dashboard/overview`
- `GET /api/v1/dashboard/runs`
- `POST /api/v1/pipeline/run`
- `GET /api/v1/pipeline/datasets`
- `GET /api/v1/pipeline/datasets/{dataset_name}`
- `GET /api/v1/pipeline/review-issues`
- `GET /api/v1/pipeline/source-files`

后续扩展 API：

- 文件上传
- 数据集导出
- 人工复核回写
- 模板管理
- 权限与用户管理

## 5. 为什么客户不再直接看 Excel

中间 Excel 的问题：

- 表过多，客户难以理解
- 字段和来源不够直观
- 不适合作为系统主交互入口

新系统方式：

- 客户看页面
- 运营/数据管理员看复核问题页面
- 开发看后端数据集与日志
- Excel 退化为中间产物或导出产物，不再是主入口

## 6. 目录规划

- `backend/`: 新后端服务
- `frontend/`: 新前端管理台
- `docs/`: 架构与使用文档
- `yunxi_data_platform/`: 旧 ETL 核心兼容层
- `excel/`: 历史原始数据与旧脚本
- `image/`: 历史图片与旧脚本

## 7. 下一步建议

- 接入 PostgreSQL 实库并校验建表
- 将 `dataset_records` 逐步拆为更清晰的业务表
- 增加文件上传与增量处理
- 增加图片增量扫描与缺图诊断
- 将旧版 ETL 的提取逻辑进一步升级为模板识别 + 锚点搜索
