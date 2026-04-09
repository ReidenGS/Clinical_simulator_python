# Clinical Simulator 修改记录索引

详细记录按日期拆分存放在 `modify/` 文件夹中。

## 目录

### 2026-04

| 文件 | 内容摘要 |
|------|---------|
| [before-2026-04-01.md](modify/2026-04/before-2026-04-01.md) | 项目初始架构设计：RAG 改造背景、数据确认、整体方案、代码改动清单、时序流程、降级策略、验证结果、实现边界与结论 |
| [2026-04-05.md](modify/2026-04/2026-04-05.md) | 后续补丁：legacy fallback 修复、TTS 语音同步、评估链路改进、算法优化（topic matching / RAG 摘要权重）、QWEN provider 支持、RAG 感知评分；CPR 模块 RAG 改造（guideline 检索 + 评分对齐） |
| [2026-04-07.md](modify/2026-04/2026-04-07.md) | Open-Patients 随机案例生成接口；CPR 评测结果页滚动 Bug 修复 |
| [2026-04-09.md](modify/2026-04/2026-04-09.md) | Interview RedFlag RAG 服务 + CaseGenerator 红旗增强；代码冗余优化；Interview 渐进式摘要记忆系统（后端文件存储 + session 联动删除） |

## 新增记录规范

每次改动在对应日期文件末尾追加，格式：

```
### N.X 改动标题（YYYY-MM-DD HH:MM EDT）

**文件：**
- `path/to/file.py`

**改动说明：**
...
```

如当天文件不存在，在对应月份文件夹下新建 `YYYY-MM-DD.md`。
