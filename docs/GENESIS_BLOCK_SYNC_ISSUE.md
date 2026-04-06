# Genesis 多节点同步问题：创世区块不一致

## 问题概述

当两个 Genesis 节点首次启动时，它们各自创建**不同的创世区块（Genesis Block）**，导致无法同步到同一条区块链。即使两个节点互相发现并连接，它们也只会认为"链已同步"（高度都是 0），但实际上是两条完全独立的链。

## 复现步骤

1. 启动本地 Genesis 节点（节点 A）：
   ```bash
   ./genesis.sh start
   ```
   - 节点 A 创建创世区块，hash=`141bb81b...`，proposer=`9aef78ca...`

2. 启动远程 Genesis 节点（节点 B），配置 `bootstrap_nodes` 指向节点 A 的 bootstrap 服务：
   ```bash
   ./genesis.sh start
   ```
   - 节点 B 连接到节点 A
   - 节点 B 创建**自己的**创世区块，hash=`1141c40d...`，proposer=`3ecf989a...`

3. 观察日志：
   ```
   [genesis.network.sync] INFO: Chain is up to date (local=0, best_peer=0)
   ```
   - 同步逻辑认为链已同步（高度都是 0）
   - 但两个节点的创世区块哈希完全不同

## 根本原因

### 1. 创世区块创建时机

在 `genesis/chain/chain.py` 的 `initialize()` 方法中：

```python
async def initialize(self, node_id: str) -> None:
    """Initialize storage and create the genesis block if the chain is empty."""
    self._node_id = node_id
    await self.storage.initialize()

    height = await self.storage.get_chain_height()
    if height < 0:  # 链为空时，立即创建创世区块
        genesis = Block.genesis_block(node_id)
        await self.storage.save_block(genesis)
        logger.info("Genesis block created by node %s", node_id)
```

**问题**：在 `initialize()` 调用时，节点还没有机会从其他节点同步创世区块。

### 2. 同步逻辑的判断缺陷

在 `genesis/network/sync.py` 的 `sync_chain()` 方法中：

```python
async def sync_chain(self, blockchain: Any) -> bool:
    # ...
    local_height = await blockchain.get_chain_height()
    remote_height = peers[0].chain_height

    if remote_height <= local_height:
        logger.info(
            "Chain is up to date (local=%d, best_peer=%d)",
            local_height,
            remote_height,
        )
        return False  # 不会同步
```

**问题**：只比较高度，不比较创世区块哈希。当两边高度都是 0 时，认为"已同步"。

### 3. 启动顺序问题

在 `genesis/main.py` 的 `start()` 方法中：

```python
# 1. 加载配置
# 2. 初始化身份
# 3. 初始化区块链 ← 此时创建创世区块
# 4. 启动 P2P 网络
# 5. 同步链 ← 此时创世区块已经存在，不会同步
```

**问题**：区块链初始化在网络启动之前，导致无法在创建创世区块前同步。

## 期望行为

新节点应该：
1. 先连接到已有的主网节点
2. 从主网获取创世区块
3. 使用相同的创世区块初始化本地链
4. 然后同步后续区块

## 可能的解决方案

### 方案 A：延迟创世区块创建（推荐）

修改启动顺序，在同步阶段处理创世区块：

1. 初始化时，如果链为空，先标记为"待同步"状态
2. 启动 P2P 网络
3. 尝试从 peer 获取创世区块
4. 如果有 peer，使用 peer 的创世区块
5. 如果没有 peer（首次启动或允许本地创世），再创建自己的创世区块

**涉及文件**：
- `genesis/chain/chain.py` - 修改 `initialize()` 方法
- `genesis/main.py` - 修改启动顺序
- `genesis/network/sync.py` - 添加创世区块同步逻辑

### 方案 B：创世区块哈希验证

在同步时验证创世区块哈希：

1. 同步时，如果本地高度为 0，检查 peer 的创世区块哈希
2. 如果哈希不同，询问用户或自动采用"更早"的创世区块
3. 删除本地创世区块，替换为 peer 的创世区块

**问题**：替换创世区块会使本地签名无效，需要重新处理。

### 方案 C：配置共享创世区块

允许通过配置文件指定创世区块：

1. 导出主网创世区块到 JSON 文件
2. 新节点启动时读取该文件
3. 如果配置了创世区块，使用配置的区块

**问题**：需要手动配置，不够自动化。

## 相关代码位置

| 文件 | 行号 | 说明 |
|------|------|------|
| `genesis/chain/chain.py` | 31-40 | 创世区块创建逻辑 |
| `genesis/network/sync.py` | 62-71 | 同步判断逻辑 |
| `genesis/main.py` | 680-760 | 启动流程 |
| `genesis/chain/block.py` | `genesis_block()` | 创世区块生成 |

## 测试验证

修复后，应该满足以下条件：

1. 两个新启动的节点，后启动的节点应该使用先启动节点的创世区块
2. 创世区块哈希应该一致
3. 两个节点应该能够同步后续产生的区块
4. 当没有其他节点时，应该允许创建新的创世区块（`allow_local_bootstrap=true`）

## 补充信息

- 创世区块包含 `proposer` 字段，是创建者节点 ID
- 创世区块哈希由区块内容计算得出
- 当前配置 `allow_local_bootstrap=true` 只是允许在没有 peer 时创建创世区块，但不能解决"两边都有创世区块但不同"的问题
