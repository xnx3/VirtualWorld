# 代码审查问题清单

> 审查日期: 2026-03-26 ~ 2026-03-28
> 审查方式: 8专家代理 + 2深入验证专家

---

## ✅ 已修复的问题（6个）

| # | 问题 | 文件 | 提交 |
|---|------|------|------|
| 1 | `handle_tao_vote_event` 缺少 `voter_name` 参数 | `tao_voting.py` | f215cf1 |
| 2 | `pending_tao_votes` 结算后未清理导致内存泄漏 | `tao_voting.py` | 1f32438 |
| 3 | `_lock` 初始化但从未使用 | `tao_voting.py` | 69df851 |
| 4 | Flutter端 `proposerName` 定义但未显示 | `app_state.dart` | e16b12d |
| 5 | Flutter端 `passed`/`rejected` 未显示票数和功德值 | `app_state.dart` | e16b12d |
| 6 | Flutter端未使用标准国际化机制 | `app_state.dart` | 0610278 |

---

## ⏳ 待改进的问题（4个）

### 问题7: 投票者身份验证缺失

**严重程度**: 🔴 高

**位置**: `genesis/governance/tao_voting.py:261-306`

**问题描述**:
- `cast_vote()` 方法仅接受 `voter_id` 字符串，没有任何身份验证
- 攻击者可以伪造任意生灵的身份进行投票
- 整个投票系统信任基础完全崩塌

**建议修复**:
```python
# 使用 Ed25519 签名验证投票者私钥
def cast_vote(self, vote_id: str, voter_id: str, support: bool,
              signature: str, world_state: WorldState) -> tuple[bool, str]:
    # 验证签名
    if not verify_vote_signature(vote_id, voter_id, support, signature):
        return False, "Invalid signature"
```

---

### 问题8: 输入无长度验证

**严重程度**: 🟠 中

**位置**: `genesis/governance/tao_voting.py:185-219`

**问题描述**:
- `rule_name`, `rule_description`, `proposer_id` 等参数均无长度限制
- 可导致内存耗尽攻击（DoS）
- 可进行日志注入攻击

**建议修复**:
```python
MAX_RULE_NAME_LENGTH = 256
MAX_RULE_DESCRIPTION_LENGTH = 4096

def initiate_tao_vote(self, proposer_id: str, rule_name: str,
                      rule_description: str, ...):
    if len(rule_name) > MAX_RULE_NAME_LENGTH:
        raise ValueError("Rule name too long")
    if len(rule_description) > MAX_RULE_DESCRIPTION_LENGTH:
        raise ValueError("Rule description too long")
```

---

### 问题9: 无单元测试

**严重程度**: 🟡 低

**位置**: 整个项目

**问题描述**:
- `/home/git/VirtualWorld/tests/` 目录为空
- `/home/git/VirtualWorld/genesis/tests/` 目录不存在
- 项目完全没有测试代码

**建议添加测试**:

```
tests/
├── conftest.py                 # fixtures
├── governance/
│   ├── test_tao_voting.py      # 天道投票测试
│   ├── test_merit.py           # 功德值系统测试
│   └── test_creator_god.py     # 创世神系统测试
└── world/
    └── test_state.py           # 世界状态测试
```

**必要测试用例**:
- `cast_vote` 正常投票
- `cast_vote` 重复投票应拒绝
- `cast_vote` 提案者不能投票
- `finalize_vote` 95%赞成通过
- `finalize_vote` 低于95%拒绝
- `finalize_vote` 无投票失败

---

### 问题10: 功德值奖励使用纯随机数

**严重程度**: 🟡 低（功能性问题）

**位置**: `genesis/governance/merit.py:222-265`

**问题描述**:
```python
def award_for_teach(self, ...):
    merit = random.uniform(0.00001, 0.00005)  # 纯随机

def award_for_share_knowledge(self, ...):
    merit = random.uniform(0.00001, 0.00003)  # 纯随机

def award_for_build_shelter(self, ...):
    merit = random.uniform(0.00001, 0.00002)  # 纯随机
```

**问题**: 没有考虑行为的实际价值，不符合"功德值应该反映实际贡献"的设计意图

**建议改进**:

| 因素 | 当前 | 建议 |
|------|------|------|
| 知识复杂度 | ❌ 未考虑 | 基于知识树的深度和广度 |
| 进化等级 | ❌ 未考虑 | 高进化等级生灵的行为应更有价值 |
| 行为影响力 | ❌ 未考虑 | 基于受益生灵数量和效果 |
| 随机性 | 100% | 仅作为小幅度波动因子 |

**建议代码**:
```python
def award_for_teach(self, teacher_id: str, student_id: str,
                    knowledge_complexity: float, world_state: WorldState):
    teacher = world_state.get_being(teacher_id)

    # 基础功德值
    base_merit = 0.00001

    # 知识复杂度加成
    complexity_bonus = base_merit * knowledge_complexity

    # 进化等级加成
    evolution_bonus = base_merit * teacher.evolution_level * 0.1

    # 最终功德值 = 基础 + 加成 + 小幅随机波动
    merit = base_merit + complexity_bonus + evolution_bonus
    merit *= random.uniform(0.9, 1.1)  # ±10% 波动

    return merit
```

---

## 📊 审查统计

| 类别 | 数量 |
|------|------|
| 发现问题总数 | 10 |
| 已修复 | 6 |
| 待改进 | 4 |
| 高优先级 | 2 |
| 中优先级 | 1 |
| 低优先级 | 1 |

---

## 📝 专家团队

| 角色 | 职责 |
|------|------|
| 真实性测试专家 | 验证调用链和参数传递 |
| 测试专家 | 检查测试覆盖 |
| 代码审查专家 | 检查代码规范和逻辑 |
| 用户体验专家 | 评估用户交互 |
| 安全专家 | 检查安全风险 |
| 性能专家 | 检查性能问题 |
| 需求专家 | 验证需求满足 |
| 架构专家 | 验证系统集成 |
