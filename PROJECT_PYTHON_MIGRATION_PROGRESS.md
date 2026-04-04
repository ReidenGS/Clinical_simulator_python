# Clinical Simulator Python 化进度

本文档用于取代之前分散的阶段性 plan，集中说明当前仓库里 **Clinical Simulator 项目的 Python 化迁移进度**、当前架构、已完成事项和下一步建议。

## 一句话结论

项目目前已经进入 **“前端保留交互层 + Python 后端承接核心业务逻辑”** 的阶段。

- **Interview 模块**：主流程已基本 Python 化，前端主要负责 UI、语音和展示。
- **CPR 模块**：目前是 **混合架构**，实时姿态识别与本地响应仍在前端，决策与评估已迁到 Python。
- **部署入口**：仓库根目录使用 `app.py` 统一承载静态前端和部分服务；`backend-python/` 保留完整 FastAPI 业务后端。

---

## 当前架构概览

```text
根目录
├─ src/                  # React + TypeScript 前端
├─ backend-python/       # FastAPI 后端（核心业务逻辑迁移主战场）
├─ app.py                # 根目录 Python 服务入口，用于生产式启动/静态资源承载
├─ dist/                 # 前端构建产物
├─ package.json          # 前端与联调脚本
└─ requirements.txt      # 根目录 Python 运行依赖
```

### 当前职责分工

#### 前端（React / TypeScript）
负责：
- 页面与交互
- 摄像头 / 麦克风 / 浏览器语音能力
- CPR 实时感知与即时 UI 反馈
- 本地会话展示、结果渲染、流程承载

#### Python 后端（FastAPI）
负责：
- Interview 业务主流程
- AI 文本/JSON 能力网关
- CPR 的决策与评估逻辑
- 逐步承接更多核心业务逻辑

---

## Interview 模块 Python 化进度

### 已完成

以下能力已经迁移到 Python 后端主路径：

- `/api/interview/respond`
  - 患者回复生成
  - 提取结果解析
  - 会话状态更新
  - 决策生成

- `/api/interview/evaluate`
  - 评分
  - 反馈生成
  - 能力等级映射
  - 下一案例建议

- 共用 AI 网关
  - `/api/ai/text`
  - `/api/ai/json`

### 当前状态判断

**Interview 可以视为“主流程已 Python 化完成”**。

前端在 Interview 中的主要角色已经缩减为：
- UI 展示
- 语音输入/输出
- 局部状态呈现
- 进度与提示的显示逻辑

### 已做的工程化强化

后端已经加入：
- LangChain model factory
- prompt version 标记
- structured output 优先
- parser fallback
- retry / backoff 机制
- 用于 LangSmith 的 metadata / tags 预留
- 单元测试覆盖关键 fallback 和服务逻辑

### 结论

Interview 模块已经从“前端主导”切换到 **“后端主导，前端展示”**。

---

## CPR 模块 Python 化进度

### 已完成

以下 CPR 能力已迁移到 Python：

- `/api/cpr/runtime/ingest`
- `/api/cpr/runtime/action`
- `/api/cpr/decide`
- `/api/cpr/evaluate`

对应承接内容包括：
- 运行时状态推进
- 阶段切换
- 通气确认
- 周期恢复
- 决策输出
- 评估与反馈输出

### 仍保留在前端

由于 CPR 对实时性要求高，以下能力仍保留在前端：
- 姿态识别
- 压胸检测
- 实时观察事件采集
- 本地即时响应
- 摄像头相关实时交互

### 当前状态判断

**CPR 目前是“部分 Python 化 / 混合架构”**，还不能算完全后端化。

这是合理的，因为：
- 浏览器侧更适合处理摄像头与高频反馈
- 后端更适合承接状态决策、评估、规则逻辑

### 结论

CPR 已完成 **第一阶段 Python 化**，但仍需要保留前端实时链路，短期内不适合强行做“纯后端化”。

---

## 当前仓库里 Python 相关入口

### 1. 根目录 `app.py`
用途：
- 生产式承载前端静态资源
- 提供部分 Python 服务接口
- 作为整仓库的统一启动入口之一

### 2. `backend-python/app/main.py`
用途：
- 完整 FastAPI 业务后端入口
- Interview / CPR 迁移中的核心 API 都在这里演进

---

## 当前项目成熟度判断

### 已经比较稳定的部分
- 前端主界面和训练流程
- Interview 后端主路径
- CPR 后端决策/评估路径
- Python 方向的总体迁移策略

### 还需要继续整理的部分
- 文档分散，历史 plan 太多
- 根目录 `app.py` 与 `backend-python/` 的职责容易让人困惑
- 部分旧说明仍带有阶段性措辞
- CPR 的前后端边界还需要继续固化

---

## 建议的后续工作顺序

### 优先级 1：文档统一
- 用当前这份文档作为 Python 化进度总说明
- 删除旧的阶段性 plan
- 让 README 只保留“当前事实”，不再混杂旧阶段计划

### 优先级 2：启动路径统一
明确区分两种开发方式：
1. **前后端分开开发**：Vite + FastAPI
2. **生产式启动**：构建前端后由 Python 服务承载

### 优先级 3：继续清理 CPR 边界
继续保持：
- 前端负责实时感知
- Python 后端负责业务规则、决策、评估

除非后续有充分收益，否则不建议把摄像头实时链路硬搬到后端。

### 优先级 4：收口旧 fallback / 旧文档
在确认稳定后：
- 清理无效 fallback
- 清理陈旧说明
- 收敛历史阶段文档

---

## 当前建议结论

如果用一句话描述当前项目：

> Clinical Simulator 已经不是“准备做 Python 化”，而是已经完成了 **核心业务逻辑向 Python 后端迁移的主体工作**；其中 Interview 基本完成主路径迁移，CPR 则处于有意保留实时前端能力的混合阶段。

这也是当前仓库最适合对外和对内说明的状态。
