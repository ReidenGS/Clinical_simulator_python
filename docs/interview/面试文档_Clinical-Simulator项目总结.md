# Clinical Simulator 项目面试文档

## 1. 项目一句话介绍
Clinical Simulator 是一个 **面向医学训练的交互式模拟平台**，目前包含两个核心模块：
- **Clinical Interview（临床问诊）**：模拟医学生与病人的对话问诊、病史采集、诊断提交与评分反馈。
- **CPR Training（心肺复苏训练）**：基于摄像头 + MediaPipe 姿态识别，对用户的 CPR 动作进行实时追踪、节奏判断、动作纠错和训练后评分。

它的核心特点是：**前端负责强交互和实时感知，Python 后端负责 AI 调用、业务编排、评分与决策逻辑**。

---

## 2. 项目整体架构

这个项目本质上是一个 **前后端分层 + 渐进式迁移** 的架构。

### 2.1 总体分层

#### 前端层（React + TypeScript + Vite）
职责：
- 页面展示与交互
- 模块切换（Interview / CPR）
- 摄像头调用、麦克风、浏览器语音播放
- MediaPipe 姿态检测
- CPR 实时动作分析
- 调用 Python 后端接口

#### 后端层（FastAPI + Python）
职责：
- AI 文本/JSON 生成网关
- Interview 问诊编排逻辑
- Interview 评分逻辑
- CPR 状态推进、动作判断、评分逻辑
- TTS 代理/封装

#### 部署层
项目里实际上有 **两套 Python 入口**：

1. **根目录 `app.py`**
   - 用于生产式部署
   - 功能：
     - 提供 `/health`
     - 提供 OpenAI / Qwen / Gemini TTS 代理接口
     - 挂载 `dist/` 静态资源
     - 做 SPA fallback（所有前端路由回到 `index.html`）
   - 作用类似：**前后端一体部署时的 Web Server + AI Proxy**

2. **`backend-python/app/main.py`**
   - 是业务逻辑主后端
   - 用 FastAPI 暴露 Interview / CPR 的核心 API
   - 用于开发期、迁移期、以及未来业务后端主体

所以面试时可以这样说：

> 这个项目不是“传统前端 + 传统数据库后台”的模式，而是一个以交互训练为核心的 AI 教学系统。前端承担了实时感知和用户体验，Python 后端承担业务规则、AI 编排与评估，部署时又保留了一个根级 Python 服务做静态资源托管和 AI 代理。

---

## 3. 目录结构与职责划分

### 3.1 根目录关键文件
- `README.md`：项目总说明
- `package.json`：前端构建和启动脚本
- `app.py`：生产式 Python 服务入口
- `requirements.txt`：根目录 Python 依赖（给 `app.py` 用）
- `dist/`：前端构建产物
- `backend-python/`：Python 业务后端
- `src/`：React 前端源码

### 3.2 前端源码结构
- `src/app/`：应用外壳、头部、模块选择、设置面板
- `src/modules/interview/`：临床问诊模块
- `src/modules/cpr/`：CPR 训练模块
- `src/platform/`：AI、音频、公共类型等平台能力

### 3.3 Python 后端结构
- `backend-python/app/main.py`：FastAPI 应用启动入口
- `backend-python/app/api/routes.py`：路由层
- `backend-python/app/core/config.py`：配置读取
- `backend-python/app/services/ai_service.py`：AI 服务封装
- `backend-python/app/services/interview_service.py`：问诊运行时逻辑
- `backend-python/app/services/interview_evaluate_service.py`：问诊评分逻辑
- `backend-python/app/services/cpr_service.py`：CPR 运行态 + 评分逻辑

---

## 4. 前端技术栈与搭建方式

### 4.1 前端使用的主要库
从 `package.json` 看，前端主要依赖有：

- `react` / `react-dom`
  - UI 组件开发
- `vite`
  - 前端开发服务器与打包器
- `typescript`
  - 类型系统
- `@vitejs/plugin-react`
  - React 的 Vite 插件
- `@mediapipe/tasks-vision`
  - CPR 模块的姿态识别核心库
- `@google/genai`
  - 前端可接 Gemini 的能力（兼容/调用链一部分）
- `openai`
  - 前端/平台层对 OpenAI 能力接入
- `motion`
  - 动画
- `lucide-react`
  - 图标
- `clsx`、`tailwind-merge`
  - className 管理
- `cors`、`express`、`tsx`
  - 项目历史遗留/兼容依赖，当前主后端已迁移到 Python，`server.ts.bak` 说明原来有 TS 服务端方案

### 4.2 前端运行方式
开发模式：
```bash
npm install
npm run dev
```

其中：
- `vite --host 0.0.0.0 --port 3000`
- 默认前端运行在 `3000`

构建与生产启动：
```bash
npm run build
npm start
```

这里的 `npm start` 实际执行的是：
```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-3000}
```
说明生产环境不是 Node 在提供页面，而是 **Python + Uvicorn 在托管前端构建产物**。

---

## 5. 后端 Python 用了什么库

项目里有两份 Python 依赖，分别对应两个运行入口。

### 5.1 根目录 `requirements.txt`
用于根目录 `app.py`：
- `fastapi==0.115.0`
- `uvicorn[standard]==0.30.6`
- `python-multipart==0.0.9`
- `httpx==0.28.1`
- `google-genai==1.45.0`

### 5.2 `backend-python/requirements.txt`
用于业务后端：
- `fastapi==0.116.1`
- `uvicorn[standard]==0.35.0`
- `httpx==0.28.1`
- `python-dotenv==1.1.1`
- `pydantic==2.11.7`
- `openai==1.99.9`
- `google-genai==1.45.0`

### 5.3 这些库分别做什么

#### 1）FastAPI
作用：
- 构建 REST API
- 定义路由
- 自动处理请求/响应
- 与 Pydantic 一起做数据校验

典型代码：
- `FastAPI(...)`
- `@router.post(...)`
- `HTTPException`
- `JSONResponse`
- `CORSMiddleware`

#### 2）Uvicorn
作用：
- ASGI 服务启动器
- 用来跑 FastAPI

典型启动：
```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 3）Pydantic
作用：
- 请求体 schema 校验
- 类型转换
- 数据序列化

比如在路由里：
- `payload.model_dump(...)`

#### 4）httpx
作用：
- 异步 HTTP 调用
- 代理请求到 OpenAI / Qwen 等外部 API

典型用法：
- `httpx.AsyncClient(timeout=120.0)`
- `await client.post(...)`

#### 5）openai
作用：
- 后端调用 OpenAI 大模型
- 用于文本生成 / JSON 结构化输出

典型用法：
- `OpenAI(...)`
- `client.chat.completions.create(...)`

#### 6）google-genai
作用：
- 后端调用 Gemini 模型
- 文本生成 / JSON 输出 / Gemini TTS

典型用法：
- `genai.Client(...)`
- `client.models.generate_content(...)`

#### 7）python-dotenv
作用：
- 从 `.env` 读取环境变量
- 管理 API Key、host、port、allowed origins 等配置

---

## 6. 后端是怎么搭建的

## 6.1 配置层
在 `backend-python/app/core/config.py` 中：
- 用 `load_dotenv()` 加载环境变量
- 用 `Settings` 类统一管理配置
- 用 `@lru_cache` 缓存配置实例

读取的配置包括：
- `HOST`
- `PORT`
- `ALLOWED_ORIGINS`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `QWEN_API_KEY`
- `QWEN_BASE_URL`
- `QWEN_TTS_MODEL`

这是很典型的 **配置集中管理** 方案。

## 6.2 主应用层
`backend-python/app/main.py` 做了三件事：
1. `app = FastAPI(...)`
2. 加 CORS 中间件
3. `app.include_router(router)` 注册所有 API

说明架构上用了比较标准的：
- main.py 做应用装配
- routes.py 做路由
- services.py 做业务逻辑

## 6.3 路由层
`backend-python/app/api/routes.py` 提供的核心接口：

### 通用 AI 接口
- `GET /api/health`
- `POST /api/ai/text`
- `POST /api/ai/json`
- `POST /api/tts/qwen`

### Interview 模块
- `POST /api/interview/respond`
- `POST /api/interview/evaluate`

### CPR 模块
- `POST /api/cpr/runtime/ingest`
- `POST /api/cpr/runtime/action`
- `POST /api/cpr/ingest`（兼容旧接口）
- `POST /api/cpr/decide`
- `POST /api/cpr/evaluate`

## 6.4 服务层
服务层把核心业务拆成：
- `AIService`：统一封装 OpenAI / Gemini / Qwen
- `InterviewService`：问诊单轮处理
- `InterviewEvaluateService`：问诊评分
- `CprService`：CPR 实时状态机 + 评分

这是典型的 **Controller / Service 分层**。

---

## 7. Interview 模块的业务逻辑

Interview 模块是一个 **AI 驱动的临床问诊模拟系统**。

### 7.1 运行流程
1. 前端选择病例
2. 学生输入问题
3. 前端调用 `/api/interview/respond`
4. 后端生成“病人回复 + 本轮问诊提取结果”
5. 后端更新 sessionState
6. 后端判断是否给提示/红旗/允许提交诊断
7. 最终前端调用 `/api/interview/evaluate` 做评分

### 7.2 核心算法/机制

#### 1）Prompt Engineering
后端会拼一个很长的 system prompt，其中包含：
- 病人基本信息
- 正确诊断
- 主诉、病程、诱因、既往史等 hidden details
- 性格与说话风格
- 不可泄露隐藏信息等约束
- 要求模型额外输出 extraction JSON

也就是说，一次大模型调用同时完成两件事：
- **扮演病人回复**
- **结构化分析学生这一轮问了什么**

这是一种很实用的 **response + structured extraction 合并调用** 设计，减少调用次数。

#### 2）安全解析 `safe_parse`
LLM 可能返回：
- 纯 JSON
- markdown 包裹的 JSON
- 混杂文本

所以代码中用了：
- `json.loads(...)`
- `re.findall(...)`
- `re.search(...)`

去尽量容错解析。

这在面试里可以说成：

> 我没有假设 LLM 永远稳定返回标准 JSON，而是加了多层 fallback，提高鲁棒性。

#### 3）覆盖率追踪（Coverage Tracking）
系统预先定义 `mustAskItems`，按维度划分：
- HPC
- PMH
- DH
- FH
- SH
- ROS
- ICE
- COMM

每轮问诊后，会根据 extraction 更新哪些点被覆盖了。

核心逻辑：
- 按维度记录 coveredItems
- 算每个维度的 percentage
- 算 overallCoverage

这是一个 **规则驱动的进度追踪器**。

#### 4）相似匹配与阈值策略
更新 coverage 时，并不是完全字符串精确匹配，而是用了轻量规则：
- 首词相似
- mustAskItems 与提取项互相包含
- `confidence >= 0.6 / 0.7` 也可判定有效

这是一个 **启发式匹配算法**，不是复杂 NLP，但足够支撑教学场景。

#### 5）阶段状态机（Phase Transition）
问诊过程被拆成：
- `OPENING`
- `HISTORY_TAKING`
- `GUIDED_INQUIRY`
- `DIAGNOSIS_READY`

推进逻辑依据：
- 已对话轮数 `turnCount`
- `overallCoverage`
- 若干维度是否达到 60%

这其实是一个 **有限状态机 FSM**。

#### 6）教练提示决策器（Decision Engine）
系统会根据状态自动决定是否给 coaching：
- 连续 3 轮无进展 → `HINT_NEEDED`
- 问偏了 + 无进展 → `RISK_BRANCH`
- 10 轮后仍有关键缺口 → `RED_FLAG`
- 覆盖率足够 → `PHASE_ADVANCE`

本质上是 **规则引擎 + 教学反馈系统**。

### 7.3 Interview 评分逻辑
评分分两类：

#### 确定性评分（Deterministic Scoring）
比如：
- `info_gathering`
- `efficiency`

例如效率分数：
- `ratio = coverage / turns`
- ratio 越高，说明问得越有效率

#### LLM 评分（LLM-based Scoring）
比如：
- clinical reasoning
- diagnostic accuracy
- communication
- safety

做法：
- 把 sessionState、覆盖率、诊断结果等打包进 prompt
- 让 LLM 返回 JSON：`rawScore / feedback / evidence`

这是 **规则评分 + LLM 评分混合架构**。

### 7.4 Interview 模块面试亮点
可以重点讲：
- 不是单纯聊天机器人，而是一个有 **教学目标** 的问诊模拟器
- 有 **可解释的覆盖率追踪**
- 有 **状态机驱动的问诊阶段推进**
- 有 **规则 + LLM 混合评分体系**
- 有 **容错 JSON 解析** 提高稳定性

---

## 8. CPR 模块的业务逻辑

CPR 模块是一个 **浏览器端实时姿态追踪 + Python 后端决策与评分** 的混合系统。

### 8.1 CPR 整体流程
1. 浏览器打开摄像头
2. MediaPipe PoseLandmarker 实时输出人体关键点
3. 前端根据手腕轨迹识别按压节奏
4. 前端把 observation 发给 `/api/cpr/runtime/ingest`
5. 后端更新 sessionState/runtimeState
6. 后端返回 decision（该提示快一点、慢一点、手没摆正等）
7. 训练完成后调用 `/api/cpr/evaluate`
8. 返回分项评分和训练建议

### 8.2 为什么 CPR 采用前后端混合架构
因为 CPR 有很强的实时性：
- 视频帧处理要在浏览器本地完成
- 姿态检测不能每帧都发服务器处理
- 但评分规则、状态推进、流程控制适合后端统一维护

因此它采用：
- **前端：实时感知**
- **后端：规则决策、状态权威化、评估汇总**

这是这个项目架构上非常合理的一点。

### 8.3 CPR 前端关键算法

#### 1）姿态检测
使用：
- `@mediapipe/tasks-vision`
- `PoseLandmarker`
- 33 个 body landmarks

前端 `usePoseDetection.ts` 完成：
- 模型加载
- 优先 GPU，失败时回退 CPU
- `requestAnimationFrame` 持续处理视频帧
- 在 canvas 画出骨架

#### 2）压胸峰值检测（Peak Detection）
`useCompressionAnalysis.ts` 是 CPR 的核心算法之一。

它做了这些事：
- 取左右手腕位置
- 计算平均 wrist 坐标
- 构建一段时间窗口内的 wrist Y 历史
- 做平滑（局部窗口平均）
- 检测波峰/波谷
- 根据峰间时间间隔估算 compression rate

关键策略包括：
- `MIN_INTER_PEAK_MS = 300`
  - 最小峰间隔，做 debounce，防止抖动误判
- `ROLLING_MEDIAN_WINDOW = 10`
  - 用最近压缩幅度的中位数构造自适应阈值
- `WRIST_VISIBILITY_THRESHOLD = 0.5`
  - 手腕可见性阈值
- `RECENT_INTERVALS_FOR_RATE = 3`
  - 用最近几个峰间间隔算频率

这说明算法不是简单阈值判断，而是用了 **动态阈值 + 去噪 + 节奏平滑**。

#### 3）手臂角度检测
通过肩、肘、腕三点计算夹角：
- `calculateAngle(...)`
- 角度 >= 150° 认为手臂比较直

这是一个典型的 **几何姿态特征提取**。

#### 4）手部居中判断
- 计算双肩中点 `shoulderCenterX`
- 比较手腕平均 X 与中点偏差
- 偏差 < 0.1 判定 handsCentered

#### 5）回弹检测（Recoil Detection）
通过：
- 峰值前的 valleyY 作为基线
- 当前 wrist Y 距离基线足够近，则认为回弹完成

这里用了 `RECOIL_TOLERANCE = 0.25`。

#### 6）深度代理值（Depth Proxy）
不是直接测真实胸廓按压深度，而是通过：
- 峰谷位移 / 肩宽
- 得到一个归一化深度代理值 `depthProxy`

这是一种 **视觉近似估计**，适合教学反馈，但不是医学级测量。

### 8.4 CPR 后端逻辑

#### 1）状态维护
后端 `CprService.ingest()` 会维护：
- observation 窗口
- 当前 phase
- 当前 rate / 平均 rate / 最大 rate
- visibleRatio / straightArmRatio / centeredRatio
- compressionFraction
- rateConsistency
- recoilRatio
- depthProxyAverage
- cycleHistory

#### 2）有限状态机
CPR 里定义了多个 phase：
- `BRIEFING`
- `SCENE_SAFETY`
- `CHECK_RESPONSE`
- `CALL_FOR_HELP`
- `CHECK_BREATHING`
- `COMPRESSIONS`
- `VENTILATION`
- `AED_PROMPT`
- `CYCLE_BREAK`
- `ASSESSMENT`
- `COMPLETED`

这也是一个 **流程型有限状态机**。

#### 3）30:2 流程支持
对于 `CONVENTIONAL_30_2` 模式：
- 按压达到 30 次后切到 `VENTILATION`
- 确认 2 次吹气后回到 `COMPRESSIONS`
- 2 分钟后进入 `CYCLE_BREAK`

#### 4）一致性指标 Rate Consistency
后端根据按压峰间隔计算：
- 均值
- 方差
- 标准差
- 变异系数 CV

公式思想：
- CV 越小，节奏越稳定
- 最终换算成 0-100 分

这一点很适合面试说，因为它体现了简单但有效的统计建模。

### 8.5 CPR 评分算法
最终分项包括：
- Rhythm
- Form
- Readiness
- Depth Proxy
- Recoil
- Compression Fraction
- Rate Consistency

其中：

#### Rhythm
根据平均 rate 是否偏离 100-120 CPM 目标区间评分。

#### Form
由以下比率加权组成：
- visibleRatio * 35
- straightArmRatio * 35
- centeredRatio * 30

#### Readiness
根据 checklist 完成度计算。

#### Depth Proxy
根据深度代理值落在哪个区间评分。

#### Recoil
根据 recoilRatio 评分。

#### Compression Fraction
按压有效时间 / 总时间，低于 0.6 会扣分。

#### Rate Consistency
根据节奏稳定性评分。

最后按 rubric 权重做加权平均得到 totalScore。

---

## 9. 这个项目涉及到的核心算法/设计思想

## 9.1 前端/实时侧
- 姿态识别（MediaPipe Pose）
- 几何角度计算
- 峰值检测
- 平滑滤波
- 动态阈值
- 防抖 debounce
- 局部时间窗口统计
- requestAnimationFrame 实时处理

## 9.2 后端/业务侧
- 有限状态机 FSM
- 规则引擎
- 启发式字符串匹配
- 覆盖率计算
- checklist 完成度评分
- 加权评分模型
- 统计稳定性指标（变异系数 CV）
- Prompt Engineering
- LLM 结构化输出（JSON）
- 容错解析

---

## 10. API 设计思路

### 10.1 Interview API
- `/api/interview/respond`
  - 输入：caseData、history、studentInput、sessionState、config
  - 输出：patientMessage、extraction、sessionState、decision

- `/api/interview/evaluate`
  - 输入：sessionState、diagnosis、caseData、rubricConfig、config
  - 输出：rubricResult、feedbackReport

### 10.2 CPR API
- `/api/cpr/runtime/ingest`
  - 输入：observation、scenario、state
  - 输出：sessionState、runtimeState、decision

- `/api/cpr/runtime/action`
  - 用于显式动作，如：
    - advance_phase
    - confirm_ventilation
    - confirm_phase_advance

- `/api/cpr/evaluate`
  - 输入：sessionState、scenario、rubric
  - 输出：evaluation、feedback

### 10.3 通用 AI API
- `/api/ai/text`
- `/api/ai/json`
- `/api/tts/qwen`

这说明作者做了一个 **AI provider abstraction**，把不同模型统一封装在后端服务层里。

---

## 11. 项目亮点与可讲的工程价值

### 11.1 亮点一：业务和交互拆得很清楚
- 前端做实时感知与用户体验
- 后端做规则、评估、AI 编排
- 这是适合多模态训练场景的正确架构

### 11.2 亮点二：Interview 和 CPR 都有“可解释反馈”
不是单纯给个总分，而是：
- 维度覆盖率
- 阶段推进
- 教练提示
- strengths / gaps / nextSteps

### 11.3 亮点三：迁移架构很稳
不是一次性把全部逻辑重写到 Python，而是：
- Interview 先迁后端
- CPR 先做 backend-assisted hybrid
- 前端保留 fallback

这是典型的 **渐进式重构 / 低风险迁移**。

### 11.4 亮点四：LLM 不是无约束聊天，而是嵌入业务流程
LLM 在项目里承担：
- 病人角色模拟
- 问题覆盖提取
- 多维评价

但最终结果又被：
- 规则校验
- 状态机
- 打分机制
- fallback 策略

所约束，这比“直接调一个模型聊天”要成熟很多。

---

## 12. 如果面试官问“这个项目是怎么搭起来的”，建议回答

可以按下面这个顺序说：

### 简洁版
> 这个项目是 React + TypeScript 前端，配合 FastAPI Python 后端构建的。前端主要负责页面交互、摄像头、姿态识别和实时训练体验；后端负责 AI 模型调用、问诊编排、CPR 决策状态机和训练后评分。部署时，前端先用 Vite 打包成 dist，再由根目录的 Python `app.py` 统一托管静态资源和代理 AI 接口。业务后端则放在 `backend-python/` 里，用 FastAPI 分模块管理 Interview 和 CPR 的核心逻辑。

### 展开版
> 前端用 React + TypeScript + Vite 做模块化开发，Interview 和 CPR 两个模块分别拆到 `src/modules` 下。CPR 由于需要实时处理视频流，所以姿态识别和压胸检测放在浏览器端，使用 MediaPipe PoseLandmarker 和自定义峰值检测逻辑。后端用 FastAPI，按 route/service 分层，把 AI 调用、业务状态机、评分逻辑放在 Python 里。Interview 基本已经迁到后端，CPR 目前是 hybrid 架构：实时 tracking 在前端，状态推进和评估由后端统一返回。

---

## 13. 风险点 / 可优化点

面试时如果被问“你觉得还能怎么优化”，可以答：

### 1）依赖和入口有双份
- 根目录 `app.py` 和 `backend-python/` 是两个 Python 服务面
- `requirements.txt` 也有两份
- 后续可以进一步统一依赖和部署入口

### 2）遗留代码还在
文档里明确提到：
- Interview 的 TS 旧逻辑仍有 fallback
- CPR 也保留本地 orchestrator fallback

这说明项目在迁移中，优点是安全，缺点是代码会有一定历史包袱。

### 3）CPR 深度估计是 proxy
- `depthProxy` 是视觉近似，不是医疗设备级测量
- 适合教学，不适合医学合规场景

### 4）LLM 输出的稳定性仍需约束
虽然做了 safe_parse 和结构化输出，但如果要更强稳定性，可以进一步：
- schema 强校验
- retry
- prompt versioning
- structured output contract test

---

## 14. 面试时可以主动强调的关键词

建议你在表达时多用这些词：
- hybrid architecture
- staged migration
- frontend-led real-time sensing
- backend authoritative decision engine
- finite state machine
- rule-based evaluation
- heuristic matching
- prompt engineering
- structured JSON output
- fallback strategy
- robustness
- explainable feedback

---

## 15. 最后给你的 30 秒项目介绍模板

> 我做的是一个 Clinical Simulator 项目，主要用于医学训练，包含临床问诊和 CPR 训练两个模块。整体技术架构是 React + TypeScript 前端配合 FastAPI 后端。前端负责强交互、摄像头和姿态识别，后端负责 AI 编排、状态机、评分和反馈。临床问诊模块里，我把病人回复生成、问诊覆盖项提取、阶段推进和最终评分都做了结构化设计；CPR 模块里，我结合 MediaPipe 做姿态检测，用峰值检测和节奏分析来识别按压质量，再由后端统一做流程控制和训练评估。这个项目比较有特点的地方在于，它不是单纯调 LLM，而是把 LLM、规则引擎、状态机和实时视觉分析结合在了一起。
