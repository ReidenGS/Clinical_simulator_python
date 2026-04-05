# Clinical Simulator Interview RAG 改造说明（modify）

## 1. 改造背景与目标

### 1.1 原始问题
当前 interview 模块中，病人扮演主要依赖结构化 case（`case-zhang/li/wang.json`）进行回答。虽然可控，但存在两个问题：

1. 语言表现相对模板化，缺少真实病例叙事风格。
2. 症状表达的细节层次有限，难以覆盖更多“真实病人会怎么说”的变体。

### 1.2 业务目标
引入一个轻量级 RAG（本地病例库增强）流程，在每次 interview 会话中：

1. 从 `data/open_patients` 随机抽取一个真实病例的 `description`。
2. 将该 `description` 做摘要（目前已升级为 **LLM 摘要优先**）。
3. 把摘要结果注入 patient system prompt，作为“真实表达锚点”。
4. 保持会话内一致性：同一会话只抽一次、只总结一次，后续轮次复用。

目标是让 AI 扮演病人更加自然、真实，同时不破坏既有教学逻辑（mustAskItems 覆盖率、阶段推进、coach 提示）。

---

## 2. 数据与现状确认

已确认数据源：

- 路径：`/Users/jackiewen/Documents/clinical_simulator_dev/data/open_patients`
- 训练 split：`train`
- 核心字段：`_id`、`description`
- 样本规模：`180142` 条（来自 `dataset_info.json`）

该数据集以 Hugging Face `datasets` 本地格式落盘（arrow + metadata）。

---

## 3. 整体方案（业务逻辑）

### 3.1 会话首轮（或 sessionState 为空）

当 `/api/interview/respond` 首次进入 `InterviewService.process_turn` 时：

1. 初始化 `sessionState`。
2. 若 `sessionState.ragCaseSummary` 为空：
   - 随机抽取一条 `open_patients` 病例。
   - 读取其 `description`。
   - 用当前 interview 配置的模型进行摘要（`textProvider/textModel/textApiKey/textBaseUrl`）。
   - 摘要失败时，回退到规则摘要。
   - 把结果写入：
     - `ragCaseId`
     - `ragCaseSummary`
   - 记录事件：`rag_case_selected`。

### 3.2 后续轮次

后续每一轮请求会携带前一轮 `sessionState` 回传；只要 `ragCaseSummary` 已存在，就**不再抽样、不再总结**，直接复用。

### 3.3 prompt 注入策略

构建 patient prompt 时，在 `CASE FACTS` 之后增加 `REAL-WORLD REFERENCE (RAG)` 区块：

- 将 `ragCaseSummary` 作为“表达和病程叙述风格”参考。
- 显式约束：
  - 不要逐句抄写。
  - 优先级顺序：
    1) 当前结构化 `CASE FACTS`
    2) 诊断一致性
    3) RAG 参考

这样可避免 RAG 反向污染主病例设定。

---

## 4. 代码改动清单

### 4.1 新增：OpenPatients RAG 服务

文件：
- `backend-python/app/services/open_patients_rag.py`

核心职责：

1. 加载本地 `open_patients` 数据集（`load_from_disk`）。
2. 随机抽样病例（最多尝试 8 次跳过空 description）。
3. 提供规则摘要（fallback）。
4. 支持加载失败安全降级（`_load_failed`）。

主要对象：

- `RetrievedCase`
  - `case_id`
  - `description`
  - `summary`（规则摘要）

说明：
- 这个 `summary` 现在是兜底值；主路径会优先使用 LLM 摘要。

---

### 4.2 修改：InterviewService 接入“抽样 + LLM摘要 + 状态持久化”

文件：
- `backend-python/app/services/interview_service.py`

新增/修改要点：

1. 新增服务依赖：
   - `self.rag_service = OpenPatientsRagService()`
   - `self.ai_service = None`（懒加载）

2. `create_initial_state` 新增字段：
   - `ragCaseId`
   - `ragCaseSummary`

3. 新增 `_get_ai_service()`：
   - 懒加载 `AIService`，避免测试环境缺依赖时报 ImportError。

4. 新增 `_summarize_rag_description()`：
   - 使用当前配置模型生成摘要。
   - 摘要约束：80-140词、纯文本、包含人口学+主诉病程+伴随症状+背景+说话风格。
   - 失败返回 `None`。

5. 新增 `_ensure_rag_context(state, config)`：
   - 若已有 `ragCaseSummary` 直接返回。
   - 否则抽样 + LLM摘要。
   - 若 LLM失败，使用 `rag_case.summary`（规则摘要）兜底。
   - 写入 state 并记录事件：
     - `summarySource = llm | heuristic_fallback`

6. `process_turn` 调整顺序：
   - 先 `next_state = ...`，再 `_ensure_rag_context`。
   - 把 `rag_case_summary` 传给 chain。

业务影响：
- 会话内病人“语言风格锚点”稳定，避免每轮随机导致人设漂移。
- 覆盖率计算、阶段推进逻辑保持不变。

---

### 4.3 修改：Interview chain 接受 rag summary

文件：
- `backend-python/app/llm/chains/interview_chain.py`

修改点：

1. `invoke(...)` 新增参数：`rag_case_summary: str | None = None`
2. 调用 `build_patient_turn_prompt(...)` 时透传该参数。

---

### 4.4 修改：Prompt 版本升级并注入 RAG 参考

文件：
- `backend-python/app/llm/prompts/interview_prompts.py`

修改点：

1. `INTERVIEW_PROMPT_VERSION` 从 `v2` 升级到 `v3-rag`。
2. `build_patient_turn_prompt(...)` 新增 `rag_case_summary` 参数。
3. 增加 `REAL-WORLD REFERENCE (RAG)` 片段。
4. 加入 `format_instructions` brace escaping（`safe_format_instructions`），避免结构化输出 schema 被模板引擎误解析。

---

### 4.5 修改：API schema 扩展 session 字段

文件：
- `backend-python/app/api/interview_schemas.py`

新增字段：

- `SessionStatePayload`：
  - `ragCaseId`
  - `ragCaseSummary`

另外补齐：
- `PatientCasePayload` 增加 `difficulty` 字段（与前端 case 对齐）。

---

### 4.6 修改：前端 SessionState 类型同步

文件：
- `src/modules/interview/types/session.ts`

新增：
- `ragCaseId?: string | null`
- `ragCaseSummary?: string | null`

事件类型补充：
- `'rag_case_selected'`

说明：
- 前端不需要额外业务代码即可透传 sessionState；类型补齐后可避免 TS 报错。

---

### 4.7 修改：依赖

文件：
- `backend-python/requirements.txt`

新增：
- `datasets==4.1.1`

用途：
- 支撑 `open_patients` 本地数据集加载。

---

### 4.8 修改：单测增强

文件：
- `backend-python/tests/test_interview_service.py`

新增测试能力：

1. mock `FakeRagService`（带 `description` + fallback summary）
2. mock `FakeAIService`（验证会调用 LLM 摘要）
3. 验证“会话内只总结一次、后续复用”：
   - 第一轮 `fake_ai.calls == 1`
   - 第二轮仍 `fake_ai.calls == 1`
   - `ragCaseSummary` 保持一致

---

## 5. 时序流程（端到端）

1. 前端调用 `/api/interview/respond`，带 `caseData/history/studentInput/sessionState/config`。
2. 后端 `InterviewService.process_turn`：
   - 初始化或复制 state
   - 确保 RAG 上下文（抽样+摘要）
   - 调用 `InterviewTurnChain.invoke(..., rag_case_summary=...)`
3. Prompt 构建时拼入 RAG 参考段。
4. LLM 生成 patientResponse + extraction。
5. 继续原有覆盖率与阶段判定。
6. 返回 `patientMessage + sessionState + decision`。

---

## 6. 失败与降级策略

### 6.1 数据集加载失败
- `OpenPatientsRagService` 将 `_load_failed` 标记为 `True`，后续快速返回 `None`，不阻断主流程。

### 6.2 LLM 摘要失败
- `_summarize_rag_description` 返回 `None`，自动回退到规则摘要。

### 6.3 依赖缺失（如测试环境无 httpx）
- `AIService` 懒加载；导入失败则不做 LLM 摘要，走 fallback，不影响主流程启动。

---

## 7. 验证结果

已执行：

1. `python3 -m compileall app` 通过
2. `python3 -m unittest tests.test_interview_service tests.test_interview_chain_fallback` 通过（7/7）

说明：
- 新增逻辑未破坏 interview 既有链路与 fallback 测试。

---

## 8. 当前实现边界与后续建议

### 8.1 当前边界
1. 抽样是纯随机，不按年龄/性别做检索过滤。
2. 摘要是“单条 description 压缩”，不是向量检索式 top-k 召回。
3. RAG 仅用于表达增强，不参与评分规则。

### 8.2 建议下一步
1. 增加 metadata 过滤（按年龄段、性别、主诉关键词）后再随机。
2. 增加“摘要长度/风格”配置开关（例如简短/标准/详细）。
3. 在日志中记录摘要 token 用量，做成本可观测。
4. 如要做标准 RAG，可将 `description` 向量化后按当前 case 检索 top-k 再融合摘要。

---

## 9. 结论

本次改造已经把 interview 从”仅结构化模板驱动”升级为”结构化病例 + 真实语料表达锚点”双轨模式，并采用 **LLM摘要优先、规则摘要兜底** 的稳态方案。

核心业务收益：

1. 病人对话更接近真实临床叙述。
2. 会话内一致性可控（不会每轮漂移）。
3. 与既有教学评估逻辑兼容，风险可控、可逐步迭代。

---

## 10. 后续补丁记录（Claude 辅助）

### 10.1 Bug 修复：未声明的 legacy fallback 常量（2026-04-05）

**文件：**
- `src/modules/interview/hooks/useInterviewSession.ts`
- `src/modules/interview/components/InterviewScreen.tsx`

**问题：**
`ENABLE_LEGACY_INTERVIEW_FALLBACK` 和 `ENABLE_LEGACY_INTERVIEW_EVALUATION` 两个常量被使用但从未声明，导致 `npm run build` TypeScript 编译失败。

**修复：**
在两个文件各自顶部（import 语句之后）添加声明，值均为 `false`，保持 Python 后端为主路径不变。

---

### 10.2 TTS 语音同步与稳定性改进（2026-04-05）

**文件：**
- `src/platform/audio/speechSynthesis.ts`
- `src/platform/audio/SpeechService.ts`

**问题：**
Gemini TTS 语音在同一会话内随机切换男女声，未正确依据病人的 gender 字段固定声音。浏览器原生 TTS fallback 也没有会话内缓存机制，导致每轮重新选音。

**修复：**
- `speechSynthesis.ts`：新增 `resolveGender()` 规范化函数和 `getGeminiVoiceName()` 映射函数（female→Kore，male→Puck）；OpenAI 映射为 nova/echo，Qwen 映射为 Cherry/Chelsie。
- `SpeechService.ts`：新增 `cachedNativeVoiceUri` 字段，选定浏览器原生音后在会话内复用，防止切换。同时将 `resolveGender` 和 `selectNativeVoice` 提取为私有方法，并加入 token 化的 gender 解析逻辑。

---

### 10.3 评估链路与错误处理改进（2026-04-05）

**文件：**
- `src/modules/interview/components/InterviewScreen.tsx`
- `backend-python/app/services/interview_evaluate_service.py`
- `backend-python/app/api/interview_schemas.py`

**问题与修复：**
1. 评估 API 报错时前端只显示原始 HTTP 文本，改为解析 FastAPI 的 `detail` 字段并将验证错误 `msg` 数组展平成可读字符串。
2. `PatientCasePayload` 缺少 `difficulty` 字段，与前端 case JSON 不一致；已补齐为 `Literal['easy', 'medium', 'hard']`。
3. `recommend_next_case` 在 `current_difficulty` 不在枚举范围内时会 `KeyError`；加入边界检查，不合法值直接返回 `None`。
4. `difficulty_cases` 取值由硬索引 `[0]` 改为 `.get('name')` 安全访问。
5. 评估时强制将非 OPENAI/GEMINI provider fallback 到 OpenAI（后续 10.5 中已升级为支持 QWEN，此处改动随之合并）。

---

### 10.4 算法优化（2026-04-05）

#### 10.4.1 `update_coverage` topic 匹配算法
**文件：** `backend-python/app/services/interview_service.py`

**原算法：** 用 `split(' ')[0]` 取第一个词做子串比较，存在误匹配（`history` 匹配 `history of smoking`）和漏匹配（`chest tightness` 匹配不到 `chest pain`）。

**新算法：** 提取去停用词后的 token 集合，取交集 / 较小集合大小 ≥ 50% 即视为匹配；`confidence ≥ 0.7` 时直接通过，不依赖字面匹配。新增 `_topic_tokens()` 和 `_topic_matches()` 静态方法。

#### 10.4.2 `recommend_next_case` 排除当前病例
**文件：** `backend-python/app/services/interview_evaluate_service.py`

**问题：** 同难度推荐永远取第一个，如果当前测试的就是第一个，会一直推荐自己。

**修复：** 新增 `current_case_name` 参数，从候选列表中过滤掉当前病例；仅当所有同难度病例都是当前病例时才 fallback 回原逻辑。

#### 10.4.3 RAG 摘要首句权重提升
**文件：** `backend-python/app/services/open_patients_rag.py`

**问题：** 原位置加成只有 idx=0 时 +2、idx=1 时 +1，医学文本首句通常包含最重要的人口学信息和主诉，权重太低。

**修复：** 改为 idx=0 时 +5、idx=1 时 +2、idx=2 时 +1 的递减策略。

---

### 10.5 QWEN 文字 provider 支持（2026-04-05）

**文件：**
- `backend-python/app/api/interview_schemas.py`
- `backend-python/app/llm/clients.py`
- `src/modules/interview/components/InterviewScreen.tsx`

**问题：**
`AIConfigPayload` 的 `textProvider` 只允许 `OPENAI` 或 `GEMINI`，前端选 QWEN 时后端直接返回 422。`LangChainModelFactory` 也没有 QWEN 分支。

**修复：**
- `interview_schemas.py`：`textProvider` 的 `Literal` 加入 `'QWEN'`。
- `clients.py`：新增 QWEN 分支，通过 Dashscope `compatible-mode/v1` 端点（OpenAI 兼容格式）接入 `ChatOpenAI`。
- `InterviewScreen.tsx`：移除强制 fallback 到 OpenAI 的 `evaluationConfig` 包装逻辑，三个 provider 现在均直接透传。

---

### 10.6 RAG 感知评分规则（2026-04-05）

**文件：**
- `backend-python/app/llm/prompts/evaluation_prompts.py`
- `backend-python/app/llm/chains/evaluation_chain.py`

**背景：**
RAG `ragCaseSummary` 已存储在 `sessionState` 中并随每次评估请求传入后端，但 `build_dimension_evaluation_prompt` 完全未使用它，评分对真实病例参考视而不见。

**方案：**
新增 `_RAG_AWARE_DIMENSIONS = {'clinical_reasoning', 'communication'}` 常量，仅对这两个维度在 prompt 中注入 RAG context 块：

- `clinical_reasoning`（临床推理）：注入 `REAL-WORLD PRESENTATION REFERENCE` 块，要求评估者判断学生是否追问了真实患者才会呈现的细节（时间线、伴随症状、背景因素）。
- `communication`（沟通能力）：注入 `REAL-WORLD EXPRESSION REFERENCE` 块，要求评估者判断学生是否适应了 RAG 驱动的口语化患者回复风格，以及是否展示出适当的情绪共情。

**刻意排除的维度：**
- `diagnostic_accuracy`：必须只基于正确诊断评分，引入 RAG 叙事会干扰判断。
- `safety`：必须只基于结构化红旗症状列表。
- `info_gathering` / `efficiency`：纯确定性算法，不走 LLM。

**其他：**
- `EVALUATION_PROMPT_VERSION` 从 `v2` 升级到 `v3-rag`。
- `evaluation_chain.py` 的 LangSmith metadata 新增 `rag_active` 字段，便于追踪哪些评估会话使用了 RAG 数据。
- `ragCaseSummary` 直接从 `session_state` 提取，无 API 或 schema 变更；当值为空时 prompt 与旧版完全一致，向后兼容。
