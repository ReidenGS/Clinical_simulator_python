# Clinical Simulator LangChain 重构设计文档

## 1. 目标
本次重构目标是：

1. **仅将 Interview 模块与 AI 编排层 LangChain 化**
2. **保留 CPR 现有实时规则/算法实现**，不为了框架统一而破坏实时性
3. **保持现有 FastAPI API 兼容**，前端无需大改或只需最小改动
4. 为后续扩展预留能力：
   - Prompt 模板管理
   - Structured Output
   - 多模型统一接入
   - LangSmith/Tracing
   - CPR Guideline RAG

---

## 2. 为什么这样改

## 2.1 当前项目现状
当前项目已经有较清晰的业务边界：
- 前端负责 UI、摄像头、MediaPipe、实时 tracking
- Python 后端负责业务逻辑、AI 编排、评分与流程控制

其中 Interview 模块已经明显具备以下 LangChain 化条件：
- 有稳定的 prompt 输入结构
- 有明显的结构化输出需求
- 有多 provider 模型抽象需求
- 有多步骤逻辑（生成 → 解析 → 更新状态 → 决策）
- 后续可能引入知识检索增强（RAG）

而 CPR 模块当前的主价值在：
- 前端实时姿态识别
- 峰值检测与统计特征提取
- 规则状态机与评分逻辑

这些内容更偏实时算法与业务规则，不适合强行 LangChain 化。

## 2.2 重构收益
- 将手写 prompt 拼接升级为 **PromptTemplate**
- 将手写 JSON 容错解析升级为 **Pydantic schema + structured output**
- 将模型调用抽象升级为 **LangChain model adapter**
- 为后续接入 **RAG / tools / tracing** 打基础
- 面试表达更强：
  - lightweight orchestration → standardized LLM workflow
  - raw parsing → schema-constrained output
  - custom provider wrapper → LangChain model abstraction

---

## 3. 本次重构范围

## 3.1 这次要改的
- `backend-python/app/services/ai_service.py`
- `backend-python/app/services/interview_service.py`
- `backend-python/app/services/interview_evaluate_service.py`
- `backend-python/requirements.txt`

新增：
- `backend-python/app/llm/` 目录
- Prompt 模板
- Structured output schemas
- LangChain model factory / chains

## 3.2 这次不改的
- CPR 前端 `usePoseDetection.ts`
- CPR 前端 `useCompressionAnalysis.ts`
- CPR 后端 `cpr_service.py` 核心规则
- 前端 Interview/CPR 页面结构
- API 路由路径与请求体格式

---

## 4. 重构后架构

## 4.1 总体结构

### 现状
Route -> Service -> raw SDK call / handwritten prompt / handwritten parse -> business logic

### 重构后
Route -> Service -> LangChain prompt / model / structured output -> business logic

也就是说，**LangChain 只替代 LLM orchestration 层，不替代核心业务规则层**。

---

## 5. 模块设计

## 5.1 新增目录设计
建议新增：

```text
backend-python/app/llm/
  __init__.py
  clients.py              # 模型工厂：OpenAI / Gemini
  prompts/
    __init__.py
    interview_prompts.py  # Interview prompt templates
    evaluation_prompts.py # Interview evaluation prompts
  schemas/
    __init__.py
    interview_outputs.py  # Pydantic structured outputs
  chains/
    __init__.py
    interview_chain.py    # patient response + extraction chain
    evaluation_chain.py   # evaluation chain
```

---

## 5.2 AI 编排层设计

### clients.py
职责：
- 根据 provider 构建 LangChain Chat Model
- 支持：
  - OpenAI
  - Gemini
- 支持动态覆盖：
  - api_key
  - base_url
  - model
  - temperature

输出统一为 LangChain chat model。

### 好处
- 取代 `AIService` 里 if/else 拼 SDK 调用的方式
- 后续接 LangSmith、fallback、retry 更方便

---

## 5.3 Prompt 模板设计

### interview_prompts.py
拆成两个模板函数：

1. `build_interview_messages(...)`
   - 负责 patient role + hidden facts + strict rules + extraction instructions
2. `build_extraction_instruction(...)`
   - 负责输出格式与 must-ask items 的要求

### evaluation_prompts.py
提供：
- `build_dimension_evaluation_prompt(...)`

### 好处
- prompt 可维护
- 可版本化
- 便于后续做 A/B test
- 便于面试说明 prompt modularization

---

## 5.4 Structured Output 设计

### interview_outputs.py
定义：
- `TopicCovered`
- `InterviewExtraction`
- `PatientTurnOutput`
- `DimensionEvaluationOutput`

其中：
- `PatientTurnOutput` 对应 Interview 响应链输出
- `DimensionEvaluationOutput` 对应 LLM 评分输出

### 好处
- 替代手写 safe_parse 为主路径
- 降低 JSON 漂移风险
- 更容易测试

### 注意
仍保留少量 fallback：
- 如果 structured output 失败，可回退到旧 parser 或默认值

---

## 5.5 Interview 链设计

### interview_chain.py
输入：
- case_data
- history
- student_input
- config

流程：
1. 构建 prompt messages
2. 创建对应 provider 的 chat model
3. 使用 structured output schema 执行
4. 返回 `PatientTurnOutput`

### Service 与 Chain 分工
- Chain：只管“拿到结构化 LLM 输出”
- Service：负责 coverage update、phase transition、decision logic

这样业务规则不会被 LangChain 侵入太深。

---

## 5.6 Evaluation 链设计

### evaluation_chain.py
输入：
- dimension
- session_state
- diagnosis
- case_data
- config

流程：
1. 构建维度评分 prompt
2. 调用对应模型
3. 解析为 `DimensionEvaluationOutput`
4. 返回 rawScore / feedback / evidence

### 保留原策略
- deterministic scoring 继续保留
- 仅把 LLM scoring 部分替换成 LangChain

---

## 6. API 兼容策略

本次不修改这些接口：
- `/api/ai/text`
- `/api/ai/json`
- `/api/interview/respond`
- `/api/interview/evaluate`

前端继续按原格式传：
- `caseData`
- `history`
- `studentInput`
- `sessionState`
- `config`

服务内部替换为 LangChain 实现，保证对前端透明。

---

## 7. CPR 模块处理策略

## 7.1 本次不 LangChain 化 CPR 主链路
原因：
- CPR 主链路是实时姿态检测与统计判断
- 这部分适合规则和算法，不适合 agent/chain
- LangChain 不能提升峰值检测、角度计算、实时状态推进性能

## 7.2 CPR 后续可扩展 RAG
可以增加一个 **Guideline Retrieval Layer**，用于：
- AHA / ERC / ILCOR 等 CPR/BLS 指南检索
- 自动生成更有依据的 feedback
- 给教练提示增加 guideline citation
- 面向国际化标准扩展训练内容

### 可能的数据源
- AHA CPR/BLS guideline summary
- ERC guidelines
- WHO / Red Cross 公开 CPR training materials
- 项目内部 rubric 和 guideline reference 文本

### 技术方案
- 文档加载：本地 markdown/pdf 抽取后文本化
- 切分：LangChain text splitter
- 向量化：OpenAI embeddings / Gemini embeddings（视后续支持）
- 向量库：FAISS / Chroma
- 检索：Retriever
- 使用位置：
  - CPR 训练后 feedback 增强
  - CPR 教练提示补充依据
  - 后续知识问答模块

### 注意
RAG 只作为 **解释增强层**，不直接替代实时 decision engine。

---

## 8. 依赖改造

新增依赖：
- `langchain`
- `langchain-openai`
- `langchain-google-genai`

保留：
- `fastapi`
- `uvicorn`
- `httpx`
- `python-dotenv`
- `pydantic`
- `openai`（可保留兼容 TTS）
- `google-genai`（可保留兼容 TTS）

---

## 9. 风险与应对

## 9.1 Structured output 并非 100% 稳定
**风险：** 模型偶发不按 schema 输出

**应对：**
- 保留 fallback parser / 默认值
- 在 service 层兜底

## 9.2 Gemini / OpenAI provider 能力差异
**风险：** 不同模型在 structured output 支持上表现不同

**应对：**
- OpenAI 优先走 with_structured_output
- Gemini 走 schema 或 JSON instruction + parser
- 在 model factory 统一抽象

## 9.3 过度框架化
**风险：** 把 LangChain 用到不适合的地方，增加复杂度

**应对：**
- 只替换 LLM orchestration
- CPR 规则和实时算法不动

---

## 10. 分阶段实施计划

## Phase 1（本次）
- 引入 LangChain 依赖
- 新增 `app/llm/` 结构
- 改造 `AIService`
- 改造 Interview respond 链
- 改造 Interview evaluate 的 LLM scoring 链
- 保持 API 不变

## Phase 2（后续）
- Prompt versioning
- LangSmith tracing
- 更强 fallback/retry
- 单元测试补齐

## Phase 3（后续）
- CPR guideline RAG
- Interview guideline RAG
- 可解释引用输出

---

## 11. 面试可讲版本

> 原始项目采用的是自定义 lightweight orchestration：手写 prompt、手写 provider adapter、手写 JSON parse。重构后，我把 Interview 模块和 AI 编排层升级到了 LangChain 架构，使用 PromptTemplate、model abstraction 和 structured output schema 替代原始实现，同时保留原有 coverage tracking、状态机和规则评分逻辑。这样既提升了可维护性，也为后续接入 RAG 和 tracing 留出了标准化接口。CPR 部分则继续保留现有实时规则与姿态算法，只在后续通过 guideline RAG 增强反馈解释，而不破坏实时链路。
