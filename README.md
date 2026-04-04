# Clinical Simulator

Clinical Simulator 是一个面向临床训练的交互式练习平台，结合了：
- **Clinical Interview（问诊训练）**
- **CPR Training（心肺复苏训练）**
- AI 驱动的实时反馈
- 训练后结构化评估

项目当前采用 **React/TypeScript 前端 + Python 后端** 的混合架构，并正在持续完成核心业务逻辑的 Python 化。

---

## 当前项目状态

当前仓库是 **Clinical Simulator 的主工作仓库**。

它包含：
- 完整的 React / TypeScript 前端
- Python 后端迁移代码（`backend-python/`）
- 根目录 Python 服务入口（`app.py`）
- 前端构建产物承载方式（`dist/`）

### Python 化进度

简要状态如下：
- **Interview 模块**：主流程已基本迁移到 Python 后端
- **CPR 模块**：目前为混合架构，实时感知留在前端，决策与评估已迁入 Python

详细说明见：
- `PROJECT_PYTHON_MIGRATION_PROGRESS.md`
- `backend-python/MIGRATION_STATUS.md`

---

## 功能概览

### 1. Clinical Interview
用于练习临床问诊、病史采集、推理与诊断表达。

支持：
- 多个病例难度层级
- 文本或语音交互
- AI 患者自然回复
- 问诊覆盖度追踪
- 诊断提交与结构化评分
- 多维度反馈与能力等级评估

### 2. CPR Training
用于练习 CPR / BLS 流程与节奏、动作规范。

支持：
- 多难度 CPR 场景
- 摄像头姿态识别
- 压胸计数与节奏跟踪
- CPR 流程引导
- 实时动作反馈
- 训练后评分与建议

---

## 项目结构

```text
.
├─ src/                            # React / TypeScript 前端
│  ├─ app/                         # 应用壳层与共享 UI
│  ├─ modules/interview/           # 问诊模块
│  ├─ modules/cpr/                 # CPR 模块
│  └─ platform/                    # 音频、AI、存储、类型等平台层
├─ backend-python/                 # FastAPI 后端（迁移主目录）
│  ├─ app/api/                     # API schema 与路由
│  ├─ app/services/                # 业务服务层
│  ├─ app/llm/                     # LangChain / LLM 编排层
│  ├─ tests/                       # 后端测试
│  ├─ README.md
│  └─ MIGRATION_STATUS.md
├─ app.py                          # 根目录 Python 服务入口
├─ dist/                           # 前端构建产物
├─ package.json                    # 前端与联调脚本
├─ requirements.txt                # 根目录 Python 运行依赖
└─ PROJECT_PYTHON_MIGRATION_PROGRESS.md
```

---

## 启动方式

项目目前推荐两种启动方式：

## 方式 A：开发模式（前后端分开跑）
适合本地开发、调试和迭代。

### 1）启动 Python 后端
```bash
cd backend-python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

也可以在仓库根目录直接运行：

```bash
npm run dev:backend
```

### 2）启动前端
在仓库根目录另开一个终端：

```bash
npm install
npm run dev
```

默认前端开发地址：
- `http://127.0.0.1:3000`
- 或 `http://localhost:3000`

---

## 方式 B：生产式运行（前端构建后由 Python 承载）
适合部署或本地模拟生产环境。

### 1）安装依赖
```bash
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2）构建前端
```bash
npm run build
```

### 3）启动服务
```bash
npm start
```

默认由根目录 `app.py` 使用 Uvicorn 提供服务。

如果需要自定义端口：

```bash
PORT=3000 npm start
```

---

## 环境变量

### 根目录 Python 服务
常见依赖：
- `OPENAI_API_KEY`
- `GEMINI_API_KEY`
- `DASHSCOPE_API_KEY`
- `APP_URL`
- `RENDER_EXTERNAL_URL`
- `NODE_ENV`

### `backend-python/` 后端
请参考：
- `backend-python/.env.example`
- `backend-python/README.md`

常见项包括：
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `QWEN_API_KEY`
- `QWEN_BASE_URL`
- `LANGCHAIN_MAX_RETRIES`
- `LANGCHAIN_RETRY_BACKOFF_SECONDS`
- `LANGSMITH_TRACING`
- `LANGSMITH_PROJECT`

---

## 测试

### 后端测试
```bash
cd backend-python
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

---

## 当前架构说明

### 前端负责
- UI 与用户交互
- 摄像头 / 麦克风 / 浏览器语音能力
- CPR 实时姿态/压胸相关的即时反馈
- 训练过程展示与结果渲染

### Python 后端负责
- Interview 主流程业务逻辑
- AI 网关能力
- CPR 决策与评估
- 逐步承接更多核心业务逻辑

---

## 文档说明

当前推荐优先阅读：
- `PROJECT_PYTHON_MIGRATION_PROGRESS.md`：项目 Python 化进度总览
- `backend-python/MIGRATION_STATUS.md`：后端迁移状态细节
- `backend-python/README.md`：后端开发与接口说明

旧的阶段性 plan 文档已不再作为当前主说明。

---

## 相关链接

- Feishu 文档：<https://my.feishu.cn/docx/R0DrdkDcqoJnxgx6RlxcudOyn3c?from=from_copylink>
- Web Demo：<https://clinical-simulator-zrwk.onrender.com/>
