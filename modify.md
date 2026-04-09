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

---

## 8. 更新记录（2026-04-09 13:08 EDT）

### 8.1 新增 Interview RedFlag 检索服务（MVP）

新增文件：
- `backend-python/app/services/interview_redflag_rag.py`

核心能力：
1. 支持红旗症状上下文输出：`RedFlagContext(red_flags, source_urls, source_mode)`。
2. 受控来源在线检索（白名单域名）+ LLM 结构化抽取。
3. 离线规则兜底与去重合并。

说明：
- 该服务不是 LangChain agent 自主联网 tool calling；是后端受控检索后再喂给 LLM。

### 8.2 CaseGenerator 接入红旗增强

修改文件：
- `backend-python/app/services/case_generator_service.py`

新增逻辑：
1. 初始化 `InterviewRedFlagRagService`。
2. 生成 case 后执行 `_enrich_red_flags(case_data, config)`：
   - 合并现有 `redFlags` 与检索到的红旗症状。
   - 自动补充 `mustAskItems` 的 ROS 红旗筛查问题（`critical: true`）。
   - 自动将 `critical` 数量补齐到至少 4 项（优先 HPC/ROS/PMH/DH）。

结果：
- `redFlags` 与 `mustAskItems.critical` 的一致性更强，病例结构更贴近临床安全思维。

### 8.3 按需求切换为“离线优先 + 定期更新离线库”

新增文件：
- `backend-python/data/redflags_offline.json`

策略调整：
1. 先匹配离线规则库。
2. 若匹配成功，直接返回离线结果，不触发联网。
3. 仅当离线未命中时，才走在线检索 + LLM 提取 + 离线兜底合并。

实现点：
- `interview_redflag_rag.py` 新增 `_load_offline_rules()`，从 `backend-python/data/redflags_offline.json` 加载规则。
- 保留内置默认规则（文件缺失/格式错误时回退）。

### 8.4 新增/更新测试

新增测试文件：
- `backend-python/tests/test_case_generator_redflag_rag.py`
- `backend-python/tests/test_interview_redflag_rag.py`

测试覆盖：
1. `CaseGenerator` 会合并 red flags、补齐 critical 下限、补充 ROS 筛查项。
2. 命中离线规则时短路在线检索（不联网）。

本次执行结果：
- `PYTHONPATH=. python3 -m unittest tests.test_interview_redflag_rag tests.test_case_generator_redflag_rag tests.test_interview_service -v`
- 结果：`OK`（7/7）

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

---

## 10. CPR 模块 RAG 改造记录（新增）

**记录时间（America/New_York）：2026-04-05 14:00 EDT**

### 10.1 目标
在 CPR 训练模块中加入“训练前指南检索 + 网页阅读 + LLM总结 + 评分对齐”能力：

1. 训练前触发指南预热。
2. 使用搜索工具定位 CPR 指南上下文。
3. 读取目标网页内容：
   - https://www.aclsmedicaltraining.com/blog/cpr-first-defibrillation-first
4. 让 LLM 总结 CPR 基本标准。
5. 将该标准注入评估规则，使 AI 可据此判断学徒 CPR 是否合规。

### 10.2 新增能力与业务逻辑

#### A. 新增 CPR Guideline RAG 服务
文件：`backend-python/app/services/cpr_guideline_rag.py`

核心流程：
1. `web_search`（实现为搜索 API 调用）获取相关结果。
2. `web_open`（实现为网页抓取 + HTML 转文本）读取目标网页正文。
3. 调用 LLM 产出结构化标准（JSON）：
   - `compression_rate_min`
   - `compression_rate_max`
   - `depth_cm_min`
   - `depth_cm_max`
   - `compression_fraction_min`
   - `full_recoil_required`
   - `minimize_interruptions`
   - `avoid_excessive_ventilation`
   - `defibrillation_guidance`
4. 结果缓存（TTL 默认 6 小时），避免频繁重复抓取与总结。
5. 若网络或 LLM 失败，自动回退到默认 CPR 标准（不中断主流程）。

#### B. CPR 评分接入 RAG 标准
文件：`backend-python/app/services/cpr_service.py`

改动点：
1. `CprService` 注入 `CprGuidelineRagService`。
2. 新增 `prepare_guidelines(config)`，支持“训练前预热”。
3. `evaluate(...)` 增加 `config` 参数并读取 RAG 标准。
4. 评分阈值动态化（由 RAG 标准驱动）：
   - 节律范围（rate min/max）
   - 深度映射阈值（由 cm 目标换算到 depthProxy 评分区间）
   - compression fraction 最低阈值
5. 反馈文本改为引用当前标准而非固定 100-120 / 60%。
6. 在 `feedback` 中附加指南来源信息：
   - `guidelineSummary`
   - `guidelineSource`
   - `guidelineTitle`

#### C. API 层扩展
文件：
- `backend-python/app/api/cpr_schemas.py`
- `backend-python/app/api/routes.py`

新增：
1. `CprEvaluateRequest` 增加可选 `config`（textProvider/textModel/textApiKey/textBaseUrl）。
2. 新增接口：`POST /api/cpr/guidelines/prepare`。

#### D. 前端训练前预热与评估透传
文件：
- `src/modules/cpr/hooks/useCprSession.ts`
- `src/modules/cpr/components/CprTrainingScreen.tsx`

改动：
1. `useCprSession` 新增参数 `aiConfig`。
2. 场景初始化时调用 `/api/cpr/guidelines/prepare`。
3. 最终评估请求 `/api/cpr/evaluate` 时透传 `aiConfig`，确保后端可用当前模型配置做总结。
4. 保留原有本地 fallback，不影响无网或后端异常时训练流程。

### 10.3 测试与验证

#### 新增测试
文件：`backend-python/tests/test_cpr_service_rag.py`

验证点：
1. 评分确实使用了 RAG 下发的节律区间（非硬编码）。
2. 反馈中包含 guideline source 与 summary。

#### 执行结果
1. `python3 -m compileall app tests`：通过。
2. `python3 -m unittest tests.test_interview_service tests.test_interview_chain_fallback tests.test_cpr_service_rag`：通过（8/8）。
3. `npm run build`：通过。

### 10.4 当前边界
1. 搜索实现目前使用通用搜索接口作为 tool，随后固定读取目标网页。
2. 仅单网页主来源；多来源交叉校验可作为下一步增强。
3. 指南标准用于评分与反馈，不直接改动摄像头动作识别算法。

### 10.5 后续建议
1. 在 CPR 评估 UI 展示 `guidelineSummary` 与 `guidelineSource`，提升可解释性。
2. 增加多站点证据融合（AHA/ERC/培训机构），并提供来源权重。
3. 将指南版本与抓取时间在后端持久化，便于审计与复现。

---

## 11. 随机案例生成 + CPR 评测滚动修复（2026-04-07 11:46 EDT）

### 11.1 新增功能：Open-Patients 随机案例生成

**背景：**
原有 Interview 模块只有 3 个固定 JSON 案例（case-zhang / case-li / case-wang），无法给学生提供多样化的训练素材。本次改造接入 Open-Patients 数据集，实现每次生成真正随机的完整案例。

**新增文件：**

#### `backend-python/app/services/case_generator_service.py`（新增）
核心服务，负责：
1. 调用 `OpenPatientsRagService.sample_case()` 从本地 180,142 条真实病例中随机抽取一条。
2. 将原始 `description` 连同用户指定的 `difficulty` 一起送入 LLM，使用结构化 prompt 生成完整 `PatientCase` JSON，包含：
   - 基本信息（name / age / gender / initialComplaint）
   - hiddenDetails（8 个子字段）
   - physicalExam（2-4 条查体发现）
   - correctDiagnosis / differentials / redFlags
   - mustAskItems（覆盖 HPC / PMH / DH / FH / SH / ROS / ICE / COMM 全部 8 个维度）
   - personality / speechPatterns
3. 解析 LLM 输出的 JSON，校验必填字段，补全缺省字段。
4. 注入唯一 `id`（`gen-{source_id}-{uuid}`），强制对齐 `difficulty`。
5. 任意环节失败均返回 `None`，由路由层抛出 503，不影响主流程。

**修改文件：**

#### `backend-python/app/api/routes.py`（修改）
- 新增 import：`Query`（from fastapi）、`AIConfigPayload`（from interview_schemas）、`CaseGeneratorService`。
- 新增路由：`POST /api/interview/case/random?difficulty=easy|medium|hard`
  - 请求体：`AIConfigPayload`（与 Interview 对话用同一配置）
  - 查询参数：`difficulty`（默认 `medium`）
  - 成功返回：完整 `PatientCase` JSON
  - 失败返回：503（数据集不可用或 LLM 错误）/ 400（其他异常）

#### `src/modules/interview/components/CaseSelector.tsx`（修改）
- 新增 props：`onGenerateRandom(difficulty) → Promise<void>`、`isGenerating: boolean`。
- 页面底部新增「Real-World Cases」区域：
  - 难度选择器（Easy / Medium / Hard 三色 pill）
  - **Generate Case** 按钮（loading 时显示 spinner + "Generating..." 文字）
  - 生成中显示提示文字。
- 新增 icon：`Shuffle`、`Loader2`（来自 lucide-react，无需新增依赖）。

#### `src/modules/interview/components/InterviewScreen.tsx`（修改）
- 新增状态：`isGeneratingCase: boolean`。
- 新增函数：`handleGenerateRandom(difficulty)`
  - POST `/api/interview/case/random?difficulty={difficulty}`，携带当前 `aiConfig` 作为请求体。
  - 成功后将返回的 `PatientCase` 写入 `currentCase` 并跳转至 Brief 预览页。
  - 失败时在选择页顶部显示可关闭的红色错误横幅。
- IDLE 界面改为 `flex-col`，在 `CaseSelector` 上方插入错误横幅。
- `CaseSelector` 调用新增两个 props 透传。

**使用流程：**
案例选择页 → 选择难度 → 点击 Generate Case → 后端随机抽取 + LLM 生成（约 5-20 秒）→ 自动进入 Brief 预览页 → 开始面试。

**依赖说明：**
`datasets==4.1.1` 已在 `requirements.txt` 中，无新增依赖。后端须使用 venv Python 启动（`./venv/bin/python3 -m uvicorn ...`）才能正确 import `datasets`。

---

### 11.2 Bug 修复：CPR 评测结果页面无法滚动

**文件：** `src/modules/cpr/components/CprTrainingScreen.tsx`（修改）

**问题：**
训练结束后评测结果容器 `div.lg:col-span-12` 没有设置高度上限和 overflow 属性，内容超出视口后无法用鼠标滚轮滚动查看。

**修复：**
在评测结果容器上添加 `overflow-y-auto overscroll-contain max-h-[calc(100dvh-7rem)]`，与训练活动列左列的滚动策略保持一致。
