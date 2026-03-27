# Flutter APK 使用说明

## 架构概述

Genesis Android 版本采用 **Flutter + Termux** 架构：

```
┌─────────────────────────────────────────────────────────────┐
│                     Android 设备                            │
│                                                             │
│  ┌─────────────────┐     WebSocket      ┌────────────────┐  │
│  │  Flutter 应用    │ ◄───────────────► │  Genesis 后端  │  │
│  │  (Genesis GUI)  │    ws://127.0.0.1   │  (Termux)     │  │
│  └─────────────────┘      :19842         └────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**重要说明**：
- APK 本身**不包含** Python 运行环境
- Python 后端运行在 **Termux** 应用中
- 用户需要同时安装 Flutter APK 和 Termux
- APK 可能是两种打包模式：
  - 预打包模式（内置 bundle，安装快）
  - 回退模式（不内置 bundle，首次安装较慢）

## 安装流程

### 方式一：快速安装（推荐）

使用预构建 Bundle，安装时间约 **1 分钟**。

1. 安装 Flutter APK
2. 安装 Termux（从 F-Droid）
3. 打开 Flutter 应用，进入设置
4. 点击"一键安装 Genesis"
5. 在 Termux 中执行：
   ```bash
   termux-setup-storage
   bash ~/storage/downloads/Genesis/quick_install.sh
   ```

### 方式二：完整安装

从源码安装，安装时间约 **20 分钟**。

```bash
termux-setup-storage
bash ~/storage/downloads/Genesis/install.sh
```

详细说明请参阅 [Termux 集成指南](./TERMUX_INTEGRATION.md)。

## 使用方法

1. 打开 Flutter 应用
2. 点击"启动服务"（或打开 Termux 运行 `./start_genesis.sh`）
3. 应用自动连接本地 Genesis 后端

## 技术说明

| 组件 | 说明 |
|------|------|
| Flutter APK | GUI 前端，提供用户界面 |
| Termux | Linux 环境，运行 Python 后端 |
| WebSocket | 前后端通信，端口 19842 |
| Genesis 后端 | Python 应用，硅基文明模拟 |

## 故障排查

### 服务无法启动？

1. 确认 Termux 已安装
2. 在 Termux 中检查：
   ```bash
   cd ~/genesis
   ./start_genesis.sh
   ```

### 连接失败？

1. 确认服务正在运行：`pgrep -f genesis.main`
2. 确认端口监听：`netstat -tlnp | grep 19842`
3. 在 Flutter 应用中点击"刷新状态"

### 安装失败？

参考 [Termux 集成指南](./TERMUX_INTEGRATION.md) 的故障排除章节。

## 相关文档

- [Termux 集成指南](./TERMUX_INTEGRATION.md) - 详细安装说明
- [Android APK 打包指南](./ANDROID_APK_BUILD.md) - 开发者构建指南
- [APK 打包实操 Runbook](./APK_BUILD_RUNBOOK.md) - 可直接照抄的打包步骤
- [Termux Bundle 部署](./TERMUX_BUNDLE_DEPLOY.md) - 快速部署方案
