---
name: 功德值系统待改进
description: 功德值善行奖励使用随机数，需要改进为基于行为价值的计算
type: project
---

## 功德值善行奖励机制待改进

**状态**: 待改进（已设置 2026-03-28 提醒）

**问题位置**: `genesis/governance/merit.py:222-265`

**当前实现问题**:
- `award_for_teach()` 使用 `random.uniform(MERIT_TEACH_MIN, MERIT_TEACH_MAX)`
- `award_for_share_knowledge()` 使用随机数
- `award_for_build_shelter()` 使用随机数
- 没有考虑行为的实际价值

**改进方向**:
1. 基于知识复杂度计算功德值
2. 基于生灵的进化等级调整
3. 基于行为的影响力评估
4. 移除纯随机数计算

**相关方法**:
- `award_for_teach()`
- `award_for_share_knowledge()`
- `award_for_build_shelter()`
- `award_for_kindness()`

**Why**: 当前随机数方式无法体现功德值应有的"德行积累"含义
**How to apply**: 后续改进时应参考天道规则的功德值计算方式（impact_score × 0.9 + vote_ratio × 10 × 0.1）
