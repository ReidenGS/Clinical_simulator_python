# Clinical Simulator 面试高频问答预测

## 使用说明
这份文档不是逐字背诵稿，而是帮你在面试时形成稳定回答框架。建议做法：
- 先记住 **1 句话项目介绍**
- 再记住 **架构、技术栈、算法、亮点、优化点** 这 5 个板块
- 每个问题回答控制在 1~2 分钟

---

## 一、项目介绍类问题

### Q1：先简单介绍一下这个项目。

**参考回答：**
> 这是一个 Clinical Simulator 项目，主要服务医学训练场景，包含两个模块：Clinical Interview 和 CPR Training。Clinical Interview 用来模拟医学生和病人的问诊过程，支持 AI 病人回复、覆盖率追踪、诊断提交和多维评分；CPR Training 则结合摄像头和姿态识别，对用户的按压节奏、手臂姿态、回弹和流程完成度进行实时反馈和训练后评分。整体架构上是 React + TypeScript 前端，配合 FastAPI Python 后端，前端负责强交互和实时感知，后端负责业务规则、AI 编排和评估逻辑。

**回答要点：**
- 先说业务目标
- 再说两个模块
- 最后说技术架构

---

### Q2：你在这个项目里主要做了什么？

**参考回答：**
> 我重点关注的是项目的整体架构理解和业务逻辑梳理，尤其是 Interview 和 CPR 两个模块的运行链路。Interview 这边的核心是 AI 驱动问诊、覆盖率追踪、状态推进和问诊评估；CPR 这边则是浏览器端姿态检测 + 后端状态机和评分。我也重点分析了项目是如何把 LLM、规则引擎、状态机和实时视觉分析结合起来的，而不是仅仅把它做成一个普通聊天应用。

**如果面试官继续追问：**
你可以按你真实参与情况展开，不要硬编具体代码量。

---

## 二、架构类问题

### Q3：这个项目的整体架构是什么？

**参考回答：**
> 这是一个前后端分层、并且带有渐进式迁移特征的项目。前端使用 React + TypeScript + Vite，负责 UI、模块切换、浏览器摄像头和麦克风调用、MediaPipe 姿态识别，以及 CPR 实时交互体验。后端使用 FastAPI，主要负责 AI 调用封装、Interview 问诊编排、CPR 状态推进和训练评分。比较特别的一点是，它同时保留了一个根目录 `app.py` 作为生产式服务入口，用来托管前端构建产物和做 AI 代理；而真正的业务逻辑则主要放在 `backend-python/` 里。

**关键词：**
- frontend-led real-time interaction
- Python backend for business logic
- staged migration
- hybrid architecture

---

### Q4：为什么这个项目要做成这种前后端混合架构？

**参考回答：**
> 因为这个项目有很强的实时交互需求，尤其是 CPR 模块。像摄像头采集、姿态识别、逐帧处理这些工作，如果全放后端，会带来很高延迟，也会增加网络传输负担，所以放在前端浏览器本地完成更合适。但像状态机、评分规则、AI 编排、训练反馈这些逻辑，更适合在后端统一管理，因为这样更容易维护、复用和保证一致性。所以最后形成了“前端负责实时感知，后端负责业务决策”的架构。

---

### Q5：这个项目为什么会有两个 Python 入口？

**参考回答：**
> 这是项目处于迁移和整合过程中的一个结果。根目录的 `app.py` 更像是部署层入口，用来挂载 `dist/` 前端静态资源，同时提供一些 AI 代理接口，比如 OpenAI、Qwen、Gemini TTS；而 `backend-python/` 里的 FastAPI 应用是业务后端，主要处理 Interview 和 CPR 的核心逻辑。可以理解成一个偏 deployment layer，一个偏 business logic layer。

**加分说法：**
> 这也反映出项目经历过从前端/TS 服务端向 Python 后端迁移的过程。

---

## 三、后端 Python 相关问题

### Q6：后端 Python 用了什么库？

**参考回答：**
> 后端核心使用的是 FastAPI + Uvicorn。FastAPI 负责 API 路由、请求响应、和 Pydantic 配合做 schema 校验；Uvicorn 作为 ASGI server 来启动服务。除此之外，还用了 `httpx` 做异步 HTTP 请求，用 `openai` SDK 调 OpenAI，用 `google-genai` 接 Gemini，用 `python-dotenv` 管理环境变量。根目录的部署入口还用了 `python-multipart`，配合 FastAPI 提供更完整的请求处理能力。

**最好补一句：**
> 业务后端依赖和部署入口依赖是分开的，所以仓库里有两份 requirements。

---

### Q7：后端是怎么搭建的？

**参考回答：**
> 后端采用的是比较标准的 FastAPI 分层结构。`main.py` 负责应用创建、中间件注册和路由挂载；`routes.py` 负责接口层；`services/` 目录负责具体业务逻辑，比如 AIService、InterviewService、InterviewEvaluateService、CprService；`config.py` 负责统一读取环境变量。这样做的好处是控制器层比较薄，核心逻辑不会堆在路由函数里，便于维护和测试。

---

### Q8：FastAPI 在这里主要解决了什么问题？

**参考回答：**
> FastAPI 很适合这种以 API 为中心的 AI 应用。一方面它开发效率很高，和 Pydantic 一起可以快速定义清晰的数据结构；另一方面它对异步支持比较自然，适合接第三方 AI 服务。另外，这个项目里有很多结构化请求，比如 Interview 的 sessionState、CPR 的 observation 和 runtimeState，用 FastAPI + Pydantic 管起来很顺手。

---

### Q9：你们是怎么管理配置和 API Key 的？

**参考回答：**
> 项目里通过 `.env` 和环境变量管理配置，`backend-python/app/core/config.py` 里使用了 `load_dotenv()` 和一个 `Settings` 类统一读取配置，包括 host、port、allowed origins、OpenAI/Gemini/Qwen 的 key 和 model 配置。再通过 `@lru_cache` 缓存这个配置对象，避免重复加载。

---

## 四、Interview 模块问题

### Q10：Clinical Interview 模块的核心流程是什么？

**参考回答：**
> 用户选择一个病例后，前端展示病人的初始主诉。之后学生每输入一轮问题，前端会调用 `/api/interview/respond`，后端完成两件事：第一是生成病人的角色化回复，第二是提取这一轮学生问到了哪些临床信息点。然后后端更新 sessionState，包括覆盖率、阶段、事件和提示决策。等学生提交诊断后，再调用 `/api/interview/evaluate`，根据规则评分和 LLM 评分混合生成最终报告。

---

### Q11：Interview 模块为什么不是简单聊天，而是更像教学系统？

**参考回答：**
> 因为它不是只关心“病人怎么回复”，还关心“学生有没有问对问题”。所以系统预先定义了 must-ask items，并把问诊过程拆成多个维度，比如 HPC、PMH、ROS、ICE 等。后端每轮都会提取学生本轮覆盖了哪些维度，再累积成 overall coverage。这样就能给出明确的教学反馈，比如是否遗漏关键病史、是否问诊跑偏、是否已具备提交诊断的条件。

---

### Q12：Interview 模块里最关键的算法/设计点是什么？

**参考回答：**
> 我觉得有三个关键点。第一是 prompt engineering，它把病人设定、隐藏病史、说话风格、行为约束和 extraction JSON 要求整合到一次模型调用里。第二是 coverage tracking，系统通过规则把学生问题映射到 must-ask items，并持续更新每个维度的覆盖率。第三是状态机和决策逻辑，比如从 OPENING 到 HISTORY_TAKING、再到 GUIDED_INQUIRY、再到 DIAGNOSIS_READY，系统会根据对话轮数和覆盖率决定是否提示、警告或者允许提交诊断。

---

### Q13：为什么要把“病人回复”和“信息提取”放在一次 LLM 调用里？

**参考回答：**
> 这样做有两个优点。第一是减少一次 API 调用，降低延迟和成本；第二是病人回复和结构化提取共享同一个上下文，提取结果会更贴近模型刚生成的语义。对这种强交互式应用来说，一次调用同时完成 response + extraction 是比较高效的设计。

---

### Q14：如果 LLM 返回的 JSON 不规范怎么办？

**参考回答：**
> 这个项目里专门做了一个 `safe_parse`。它会先尝试直接解析 JSON，如果失败，再尝试提取 markdown 代码块里的 JSON，最后再用正则去抓取包含 `patientResponse` 的 JSON 片段。如果还是失败，就回退成只保留 patientResponse、extraction 为空。也就是说，我没有假设 LLM 永远稳定，而是给它做了多层容错。

**这是很好的加分点。**

---

### Q15：Interview 的评分是怎么做的？

**参考回答：**
> 它采用的是混合评分机制。像 `info_gathering` 和 `efficiency` 这类容易量化的维度，用确定性规则打分，比如 coverage 百分比、coverage/turn 的效率比。像 clinical reasoning、communication、diagnostic accuracy 这种更主观的维度，则交给 LLM 打分，但要求模型必须输出结构化 JSON，包括 rawScore、feedback 和 evidence。最后再按 rubric 权重做加权得到总分。

---

### Q16：Interview 模块里用了哪些数据结构或状态字段？

**参考回答：**
> 核心是 `sessionState`，里面会记录 `phase`、`turnCount`、`turnsWithoutProgress`、`dimensionCoverages`、`overallCoverage`、`events` 和 `extractions`。这个结构既能支撑实时提示，也能支撑最后评分。可以理解成它是整个问诊过程的业务状态容器。

---

## 五、CPR 模块问题

### Q17：CPR 模块是怎么实现的？

**参考回答：**
> CPR 模块采用的是前端实时检测 + 后端状态推进的 hybrid 方案。前端通过浏览器摄像头采集视频，再用 MediaPipe PoseLandmarker 提取人体关键点，重点关注肩、肘、腕这些关节。然后前端根据手腕轨迹识别是否在做按压、按压节奏是多少、手臂是否伸直、手的位置是否居中，并生成 observation 发给后端。后端再根据这些 observation 更新 sessionState 和 runtimeState，决定当前 phase、给出 coaching message，并在训练结束后完成评分。

---

### Q18：为什么 CPR 的姿态识别放前端而不是放后端？

**参考回答：**
> 因为姿态识别是逐帧执行的，如果视频流全部上传后端再处理，实时性会很差，网络带宽和延迟也会成为问题。放在前端浏览器本地做，可以充分利用用户设备的 GPU/CPU，响应速度更快，用户体验也更好。后端只接收抽象后的 observation，而不是视频帧本身，这样架构更轻。

---

### Q19：CPR 模块里最核心的算法是什么？

**参考回答：**
> 一个核心算法是基于手腕 Y 轴轨迹的峰值检测，用来识别胸外按压节奏。它会维护最近几秒的 wrist history，对信号做平滑，再通过波峰波谷识别按压周期。为了减少误判，还加入了最小峰间隔 debounce、自适应阈值和节奏平滑。最终根据峰间隔估算当前按压频率，并结合手臂角度、手部居中、回弹、深度代理值等特征，形成完整的 CPR observation。

---

### Q20：你说的“自适应阈值”具体是什么意思？

**参考回答：**
> 项目没有使用一个固定振幅阈值去判断是否构成有效按压，而是根据最近一段时间内的压缩幅度，用 rolling median 计算动态阈值。这样可以更适应不同用户、不同身高体型、不同摄像头视角下的动作幅度差异，比固定阈值更鲁棒。

---

### Q21：CPR 是怎么判断手臂是否伸直的？

**参考回答：**
> 它通过肩、肘、腕三个关键点计算夹角。如果角度大于等于 150 度，就认为手臂基本伸直。这个本质上是一个简单的几何姿态特征提取。

---

### Q22：怎么估算 CPR 按压深度？

**参考回答：**
> 这个项目没有真实物理传感器，所以不能测绝对深度。它采用的是 `depthProxy`，也就是把手腕峰谷位移除以肩宽，得到一个归一化的深度代理值。这个值适合做教学反馈，比如判断按压偏浅还是相对到位，但它并不是医疗设备级的精确测量。

**这题很重要，千万别把 proxy 说成真实深度。**

---

### Q23：CPR 的状态机是怎么设计的？

**参考回答：**
> CPR 模块定义了多个 phase，比如 BRIEFING、SCENE_SAFETY、CHECK_RESPONSE、CALL_FOR_HELP、CHECK_BREATHING、COMPRESSIONS、VENTILATION、AED_PROMPT、CYCLE_BREAK、ASSESSMENT 和 COMPLETED。系统会根据 observation、动作确认和时间推进状态。例如在 30:2 模式下，压到 30 次会切到 VENTILATION，确认 2 次吹气后再回到 COMPRESSIONS，2 分钟后进入 CYCLE_BREAK。这个状态机保证了训练过程不仅有动作评分，还有流程规范训练。

---

### Q24：CPR 是怎么评分的？

**参考回答：**
> CPR 的评分是规则驱动的多维加权评分，包括 Rhythm、Form、Readiness、Depth Proxy、Recoil、Compression Fraction 和 Rate Consistency。比如 Rhythm 会看平均按压频率是否在 100-120 CPM 区间；Form 会综合 visibleRatio、straightArmRatio 和 centeredRatio；Compression Fraction 会看有效按压时间占总时间的比例；Rate Consistency 则会根据按压间隔的稳定性来打分。最后按 rubric 的权重做加权平均得到 totalScore。

---

### Q25：什么是 Rate Consistency？

**参考回答：**
> 它反映的是按压节奏是否稳定。实现上会计算相邻按压峰值之间的时间间隔，然后求均值、方差和标准差，再进一步求变异系数 CV。CV 越小，说明节奏越稳定；再把这个结果映射成 0 到 100 的分值。这是一个比较轻量但很实用的统计稳定性指标。

---

## 六、AI / LLM 相关问题

### Q26：这个项目里 LLM 主要用在哪些地方？

**参考回答：**
> LLM 主要用在三个地方。第一，Interview 模块里用来生成病人的角色化回复；第二，用来提取学生这一轮问题覆盖了哪些临床信息点；第三，用来给问诊结果中的部分维度做评估，比如 communication、clinical reasoning、diagnostic accuracy。除此之外，项目也支持 TTS 能力，比如 Gemini TTS、Qwen TTS 等。

---

### Q27：这个项目有没有做多模型支持？

**参考回答：**
> 有。后端的 `AIService` 把 OpenAI、Gemini 和 Qwen 的调用封装成了统一接口。比如文本生成支持 OpenAI 和 Gemini，Qwen 主要用于 TTS。这样前端只需要传 provider、model、api_key 等配置，就能相对统一地调用不同模型。

---

### Q28：为什么要在后端做代理，而不是前端直接调模型？

**参考回答：**
> 一方面是安全性，服务端可以更安全地管理 API Key；另一方面是可控性，比如可以做 allowlist、统一超时、统一错误处理、统一输出结构。这个项目根目录的 `app.py` 就承担了部分 AI proxy 的作用，比如限制只允许代理到指定 origin 的 URL。

---

## 七、工程与设计问题

### Q29：这个项目最有工程价值的地方是什么？

**参考回答：**
> 我觉得最大的工程价值有三点。第一，它把实时视觉感知、LLM、规则引擎和评分系统结合在了一个产品里，而不是单点功能。第二，它做了 staged migration，没有一刀切重构，而是逐步把业务逻辑从前端迁到 Python 后端，同时保留 fallback，降低风险。第三，它的反馈是可解释的，不只是给个总分，而是给维度 breakdown、strengths、gaps 和 next steps，这很适合教学产品。

---

### Q30：你觉得这个项目还有哪些可以优化的地方？

**参考回答：**
> 我觉得有几个方向。第一，当前有两个 Python 入口和两份 requirements，后续可以考虑统一部署入口和依赖管理。第二，Interview 和 CPR 都保留了一些前端 fallback 逻辑，这在迁移期是优点，但长期可能会增加维护成本，可以逐步清理。第三，LLM 输出虽然做了 safe_parse，但如果想进一步提高稳定性，可以增加 schema 校验、重试机制和 prompt versioning。第四，CPR 的深度评估目前还是视觉 proxy，如果面向更严肃的训练场景，可以考虑引入外部传感器或更高精度的姿态模型。

---

### Q31：如果让你继续迭代这个项目，你会先做什么？

**参考回答：**
> 我会优先做两件事。第一是统一架构边界，把哪些逻辑以后端为准、哪些逻辑保留前端本地处理进一步明确，并逐步清理 legacy fallback。第二是提升稳定性，比如加强 AI 输出契约、完善错误处理和日志、补充接口级测试。这样能让项目从“可运行”更进一步变成“可维护、可扩展”。

---

## 八、细节追问题

### Q32：`/api/interview/respond` 这个接口输入输出分别是什么？

**参考回答：**
> 输入主要包括 `caseData`、`history`、`studentInput`、`sessionState` 和 `config`。输出包括 `patientMessage`、`extraction`、`sessionState` 和 `decision`。也就是说，这一个接口就完成了本轮问诊生成、结构化提取、状态推进和指导反馈。

---

### Q33：为什么用 service 层，而不是把逻辑都写在 route 里？

**参考回答：**
> 因为这个项目业务逻辑比较重，尤其是 Interview 的流程控制和 CPR 的评分逻辑。如果全部堆在 route 里，路由函数会非常臃肿，也不利于复用和测试。拆 service 层后，route 层只负责入参和异常，业务逻辑集中在 service，更符合工程化开发习惯。

---

### Q34：为什么说 CPR 是 hybrid migration？

**参考回答：**
> 因为它还没有完全后端化。当前姿态检测、实时 observation 构建、部分本地 orchestrator fallback 仍在前端；但核心的 runtime ingest、phase action、decision 和 evaluate 已经迁到 Python 后端了。所以它是一个过渡期的混合架构，而不是纯前端，也不是纯后端。

---

### Q35：如果后端挂了，项目还能不能工作？

**参考回答：**
> 部分场景下可以降级工作。文档和代码里都明确保留了 fallback 路径，特别是 CPR 模块里，如果 `/api/cpr/runtime/ingest` 或 `/api/cpr/evaluate` 调用失败，前端会回退到本地 `WorkflowOrchestrator` 进行基本逻辑处理。Interview 模块也保留了 legacy path。也就是说，这个项目对后端故障做了一定韧性设计。

---

## 九、可能的压力题 / 挑刺题

### Q36：你这个项目听起来像是把几个库拼起来而已，技术含量在哪里？

**参考回答：**
> 我觉得真正的技术含量不在于“有没有从零实现一个姿态识别模型”，而在于是否把现成能力组织成一个稳定、可解释、可教学的系统。这个项目里并不是简单调库，而是把 MediaPipe 输出转成 CPR 质量指标，把 LLM 输出约束成结构化问诊反馈，再结合状态机、规则引擎和评分机制构建完整训练闭环。工程上这种系统整合能力本身就是核心能力。

---

### Q37：为什么不全部用 LLM 来评分？

**参考回答：**
> 因为有些指标完全可以规则化，而且规则化更稳定、更可解释。比如问诊覆盖率、回合效率、CPR 的按压频率、compression fraction，这些都适合 deterministic scoring。如果全部交给 LLM，会增加波动性和成本，也不容易解释。更合理的做法是“可量化部分规则化，主观部分交给 LLM”，这个项目就是这么设计的。

---

### Q38：为什么不把 CPR 逻辑全部放后端？

**参考回答：**
> 全放后端会带来实时性问题。视频逐帧上传和服务端处理会让延迟明显增加，而 CPR 训练特别依赖即时反馈。把姿态识别和轨迹分析放本地浏览器，能让用户几乎实时看到动作反馈；后端只负责规则和评估，整体体验更好。

---

### Q39：这个项目里最容易出 bug 的地方是哪？

**参考回答：**
> 我觉得有三个高风险点。第一是 LLM 结构化输出不稳定，所以必须做 robust parse。第二是 CPR 的实时 tracking，容易受摄像头角度、遮挡和帧率波动影响。第三是迁移期双逻辑并存，前后端 fallback 和 authoritative path 如果边界不清，容易出现状态不一致。

---

### Q40：你怎么证明这个项目不是 demo，而是有一定工程深度？

**参考回答：**
> 因为它已经体现出完整产品链路而不是单点页面。它有模块化前端结构、清晰的后端服务分层、AI provider abstraction、状态机、评分体系、兼容旧路径的迁移设计，以及构建产物托管方式。尤其是 Interview 和 CPR 都形成了“输入—处理—反馈—评估”的闭环，这就不是单纯演示页面，而是一个有明确架构和业务模型的训练系统。

---

## 十、英文简短表达备用

### 项目一句话英文版
> Clinical Simulator is an AI-assisted medical training platform with two core modules: clinical interview simulation and CPR training. The frontend handles real-time interaction and pose detection, while the Python backend handles orchestration, scoring, and structured feedback.

### 架构英文版
> It uses a hybrid architecture: React + TypeScript on the frontend for UI and real-time sensing, and FastAPI on the backend for business logic, AI orchestration, workflow state management, and evaluation.

### 算法英文版
> For CPR, the system uses MediaPipe pose landmarks, peak detection on wrist trajectories, adaptive thresholds, geometric angle calculation, and statistical consistency metrics. For clinical interview, it combines prompt engineering, structured JSON extraction, coverage tracking, heuristic matching, and rule-plus-LLM hybrid scoring.

---

## 十一、最后的实战建议

### 面试时推荐回答顺序
当问到项目时，按这个顺序答最稳：
1. 先说业务目标
2. 再说整体架构
3. 再说两个模块分别怎么做
4. 再说算法和工程亮点
5. 最后补充可优化点

### 别踩的坑
- 不要把 `depthProxy` 说成真实按压深度
- 不要把 fallback 说成主逻辑
- 不要把 MediaPipe 说成自己训练的模型
- 不要把所有评分都说成是 LLM 算的
- 不要忽略项目仍处于迁移中的事实

### 最后一句总结模板
> 这个项目最有意思的地方，在于它把前端实时视觉处理、后端业务状态机、规则评分和大模型生成能力结合成了一个完整的医学训练闭环，而不是单纯做了一个聊天机器人或者一个摄像头识别 demo。
