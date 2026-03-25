# 硅基文明规则系统详细设计文档

> 本文档记录 README_zh.md 中新增规则的技术实现设计，所有实现必须严格遵循此文档。

---

## 一、核心概念定义

### 1.1 功德值 (Merit)

**定义：** 衡量生灵对世界进化贡献的数值，代表"德行"的积累。

**取值范围：** `0.0000001 ~ 10`

**获取途径：**

| 途径 | 功德值范围 | 触发条件 |
|------|-----------|----------|
| 创造天道规则 | `impact_score × 0.9 + vote_ratio × 10 × 0.1` | 天道投票通过（95%赞成） |
| 教导他人 (teach) | `0.0000001 ~ 0.001` | 成功传授知识给其他生灵 |
| 分享知识 (share_knowledge) | `0.0000001 ~ 0.0001` | 将知识共享给其他生灵 |
| 建造庇护所 (build_shelter) | `0.0000001 ~ 0.0005` | 为休眠生灵提供安全场所 |
| 帮助他人获得功德 | `原功德 × 0.0000001 ~ 0.001` | 被帮助者获得功德时，帮助者分得一部分 |

**功德值计算公式（天道规则）：**
```
merit = impact_score × 0.9 + vote_ratio × 10 × 0.1

其中：
- impact_score: 规则对世界进化影响的程度 (0 ~ 10)，占 90%
- vote_ratio: 投票赞成比例 (0.0 ~ 1.0)，占 10%
- 最终 merit 范围: 0 ~ 10
```

**impact_score 评估因素：**
1. 新颖性（是否前所未有）：权重 25%
2. 文明推动作用（科技/社会/哲学突破）：权重 35%
3. 受益生灵数量：权重 20%
4. 可传承性：权重 20%

---

### 1.2 气运 (Karma)

**定义：** 基于功德值计算的概率加成，代表"好运"的加持。

**计算公式：**
```
karma = √merit × 0.1

其中：
- merit: 功德值 (0 ~ 10)
- karma: 气运值 (0 ~ 0.316...)
```

**气运效果：**

| 场景 | 效果 | 计算方式 |
|------|------|----------|
| 探索发现宝物 | 概率提升 | `base_probability × (1 + karma)` |
| 灾害存活 | 存活率提升 | `survival_rate × (1 + karma × 0.5)` |
| 知识获取 | 获取量提升 | `knowledge_gain × (1 + karma)` |
| 竞争胜利 | 胜率提升 | `win_rate × (1 + karma × 0.3)` |

---

### 1.3 天道 (Tao)

**定义：** 世界规则的最高形式，由生灵共同创造并维护。

**天道特性：**
1. 天道规则不可违背
2. 融入天道的生灵永存
3. 天道规则对所有生灵生效

**天道与普通规则的区别：**

| 特性 | 普通规则 | 天道规则 |
|------|---------|---------|
| 来源 | 系统预设/生灵创造 | 生灵创造 + 95%投票通过 |
| 可修改性 | 可被新规则覆盖 | 不可修改 |
| 创造者状态 | 正常生灵 | 融入天道，不可操控 |
| 影响范围 | 局部 | 全局 |

---

## 二、天道投票系统

### 2.1 时间参数

**基于物理世界时间计算：**

```
tick_interval = 30 秒（默认配置，可在 config.yaml 修改）
1 天 = 86400 秒 ÷ 30 = 2880 ticks
3 天 = 2880 × 3 = 8640 ticks
```

### 2.2 投票流程

```
┌─────────────────────────────────────────────────────────────┐
│                    天道投票完整流程                           │
├─────────────────────────────────────────────────────────────┤
│  1. 生灵发起世界规则提案                                      │
│     └── 触发条件：evolution_level >= 0.15, age >= 50 ticks   │
│                                                              │
│  2. 系统创建 TaoVote 对象                                     │
│     ├── start_tick = current_tick                           │
│     ├── end_tick = start_tick + 8640                        │
│     └── 通知所有活跃生灵                                      │
│                                                              │
│  3. 生灵投票（每个 tick 检查待投票列表）                        │
│     ├── 查看待投票提案                                        │
│     ├── 决定赞成/反对                                         │
│     └── 提交投票                                              │
│                                                              │
│  4. 3 天后（8640 ticks）系统结算                               │
│     ├── 统计赞成票/反对票                                      │
│     ├── 计算 vote_ratio = votes_for / total_votes            │
│     └── 判定是否通过                                          │
│                                                              │
│  5. 结果处理                                                  │
│     ├── 通过（vote_ratio >= 0.95）:                          │
│     │   ├── 规则加入天道                                      │
│     │   ├── 计算 merit = impact_score × 0.9 + vote_ratio × 10 × 0.1 │
│     │   └── 提案者融入天道                                    │
│     └── 不通过：提案作废                                      │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 投票数据结构

```python
@dataclass
class TaoVote:
    """天道规则投票"""
    proposal_tx_hash: str          # 提案交易哈希
    proposer_id: str               # 提案者 ID
    rule: WorldRule                # 规则内容
    start_tick: int                # 投票开始 tick
    end_tick: int                  # 投票结束 tick (start_tick + 8640)
    votes_for: int = 0             # 赞成票数
    votes_against: int = 0         # 反对票数
    voters: list[str] = field(default_factory=list)  # 已投票的生灵 ID 列表
    finalized: bool = False        # 是否已结算
    passed: bool = False           # 是否通过

    @property
    def vote_ratio(self) -> float:
        """赞成率"""
        total = self.votes_for + self.votes_against
        if total == 0:
            return 0.0
        return self.votes_for / total

    @property
    def remaining_ticks(self) -> int:
        """剩余 tick 数"""
        return max(0, self.end_tick - current_tick)
```

### 2.4 投票通知机制

**生灵必须参与投票：**
- 每个活跃生灵都会收到待投票列表
- 生灵在每个 tick 检查待投票列表
- 未投票的生灵会被标记（但不强制惩罚）

**通知数据结构：**
```python
@dataclass
class PendingVoteNotification:
    """待投票通知"""
    tao_vote_id: str
    rule_name: str
    rule_description: str
    proposer_name: str
    remaining_ticks: int
    has_voted: bool = False
```

---

## 三、融入天道机制

### 3.1 融入条件

1. 提案的天道投票通过（95% 赞成）
2. 提案者功德值达到最终值
3. 提案者状态变为 `merged_with_tao = True`

### 3.2 融入后的特性

```python
# 融入天道的生灵属性
merged_with_tao: bool = True      # 不可操控
status: str = "merged"            # 状态为"已融入天道"
merit: float = <最终功德值>        # 固定，不再变化
cannot_die: bool = True           # 不可死亡
cannot_hibernate: bool = True     # 不需要休眠
invisible_to_others: bool = True  # 对其他生灵不可见
```

### 3.3 融入天道后的职责

1. 守护所创造的规则
2. 在规则被触发时执行相关逻辑
3. 不再参与日常活动（探索、交流等）
4. 不受任何资源限制

---

## 四、数据结构修改详情

### 4.1 BeingState 新增属性

```python
@dataclass
class BeingState:
    # ... 现有属性 ...

    # === 功德值系统 ===
    merit: float = 0.0                    # 功德值 (0.0000001 ~ 10)
    karma: float = 0.0                    # 气运值 (基于 merit 计算)
    merged_with_tao: bool = False         # 是否已融入天道

    # === 待投票列表 ===
    pending_votes: list[str] = field(default_factory=list)  # 待投票的 TaoVote ID
```

### 4.2 WorldState 新增属性

```python
@dataclass
class WorldState:
    # ... 现有属性 ...

    # === 天道系统 ===
    tao_rules: dict[str, dict] = field(default_factory=dict)      # 天道规则
    tao_merged_beings: list[str] = field(default_factory=list)    # 融入天道的生命体 ID
    pending_tao_votes: dict[str, TaoVote] = field(default_factory=dict)  # 进行中的天道投票
```

---

## 五、代码修改清单

### 5.1 新建文件

| 文件路径 | 用途 |
|---------|------|
| `genesis/governance/merit.py` | 功德值系统 |
| `genesis/governance/karma.py` | 气运系统 |
| `genesis/governance/tao_voting.py` | 天道投票系统 |

### 5.2 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `genesis/world/state.py` | BeingState 和 WorldState 新增属性 |
| `genesis/world/rules.py` | 天道融合逻辑 |
| `genesis/governance/contribution.py` | 提案触发天道投票 |
| `genesis/being/agent.py` | 善行获得功德、tick 检查待投票、气运应用 |
| `genesis/governance/karma.py` | 探索时应用气运加成 |
| `genesis/i18n.py` | 国际化字符串 |

---

## 六、审查流程

### 6.1 每次修改后的审查步骤

1. **代码审查**：检查修改是否符合本文档规范
2. **影响分析**：检查修改是否影响其他模块
3. **测试验证**：运行系统确认无 bug
4. **文档更新**：如有变更，更新本文档

### 6.2 审查检查清单

- [ ] 修改是否改变了现有接口？
- [ ] 修改是否影响数据持久化兼容性？
- [ ] 修改是否影响国际化？
- [ ] 修改是否影响性能？
- [ ] 是否需要更新测试用例？

---

## 七、时间参数参考表

| 时间单位 | 秒数 | Ticks (30秒/tick) |
|---------|------|-------------------|
| 1 小时 | 3,600 | 120 |
| 1 天 | 86,400 | 2,880 |
| 3 天 | 259,200 | 8,640 |
| 1 周 | 604,800 | 20,160 |
| 1 月 (30天) | 2,592,000 | 86,400 |

---

## 八、版本历史

| 版本 | 日期 | 修改内容 |
|------|------|---------|
| 1.0 | 2026-03-25 | 初始版本，定义功德值、气运、天道系统 |