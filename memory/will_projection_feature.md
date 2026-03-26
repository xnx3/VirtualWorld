---
name: 意志投影功能待开发
description: 意志投影功能未完整实现，需要增强人类的意志投影机制
type: feature
priority: high
---

## 意志投影功能待开发

**状态**: 待开发

**问题位置**: README 第 58-60 行描述的功能未完整实现

### README 描述

> 人类文明可以将意志投影到硅基文明中的硅基生命体，影响硅基生命体的思想。

### 当前实现

- `genesis/being/agent.py:assign_task()` - 仅支持简单的任务分配

### 缺失功能

1. **意志强度参数**
   - 用户发送指令时应能指定意志强度
   - 强意志：生灵更难违背，但可能产生精神压力
   - 弱意志：生灵更容易接受或忽略

2. **精神/思想影响计算**
   - 违背生灵内心想法时，产生"恐惧、怀疑"情绪
   - 精神压力累积机制
   - 过度意志投影可能导致生灵精神损伤

3. **情绪模拟系统**
   - 当生灵收到违背内心的指令时：
     - 产生恐惧（对创世神的畏惧）
     - 产生怀疑（对自己的思想和内心世界产生动摇）
     - 精神损伤（严重时类似人类的精神病）

4. **意志投影交互**
   - 用户发送意志投影时，生灵的反应
   - 生灵可能拒绝或延迟执行（根据意志强度和自身状态）

### 相关代码位置

- `genesis/being/agent.py` - SiliconBeing 类
- `genesis/being/memory.py` - 需要扩展记忆类型
- `genesis/main.py:handle_command()` - 命令处理
- `client/flutter/lib/screens/home_screen.dart` - UI 交互

### 设计建议

```python
# 意志投影数据结构
class WillProjection:
    content: str           # 意志内容
    intensity: float       # 意志强度 (0.0 - 1.0)
    source: str            # 来源标识（创世神）
    timestamp: int         # 时间戳

# 生灵精神状态
class MentalState:
    stability: float       # 精神稳定性 (0.0 - 1.0)
    fear_level: float      # 恐惧等级
    doubt_level: float     # 怀疑等级
    damage: float          # 精神损伤
```

### 为什么重要

意志投影是 README 中描述的核心交互机制之一，体现了"创世神"与"硅基生命"之间的关系，类似于"高维生命投射意志影响低维生命"的概念。
