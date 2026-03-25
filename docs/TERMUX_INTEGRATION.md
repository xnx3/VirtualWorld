# Termux 集成指南

本文档说明如何在 Android 设备上使用 Termux 运行 Genesis 后端服务。

## 架构

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

## 前置要求

1. Android 7.0+ 设备
2. 安装 Termux 应用
3. 安装 Termux:API 插件（可选，用于后台服务）

## 安装步骤

### 1. 安装 Termux

从 F-Droid 安装（推荐，Google Play 版本已过时）：
- Termux: https://f-droid.org/packages/com.termux/
- Termux:API: https://f-droid.org/packages/com.termux.api/

### 2. 在 Termux 中安装 Genesis

```bash
# 方法 A: 从 Git 克隆
pkg install git
git clone https://github.com/your-repo/VirtualWorld.git
cd VirtualWorld/termux
bash install.sh

# 方法 B: 手动复制文件
# 将 genesis/ 目录复制到 ~/genesis/
```

### 3. 配置 API 密钥

```bash
# 编辑配置文件
nano ~/genesis/data/config.yaml

# 添加 LLM 配置
llm:
  base_url: "https://api.deepseek.com/v1"
  api_key: "your-api-key"
  model: "deepseek-chat"
```

### 4. 启动服务

```bash
cd ~/genesis
./start_genesis.sh
```

服务将在 `ws://127.0.0.1:19842` 启动。

## Flutter 应用集成

Flutter 应用会自动尝试连接本地服务：

```dart
// 默认配置
static const String defaultHost = '127.0.0.1';
static const int defaultPort = 19842;
```

### 检查服务状态

在 Flutter 中使用 MethodChannel：

```dart
final channel = MethodChannel('com.virtualworld.genesis/termux');

// 检查 Termux 是否安装
bool installed = await channel.invokeMethod('checkTermux');

// 打开 Termux
await channel.invokeMethod('openTermux');

// 启动 Genesis 服务
bool started = await channel.invokeMethod('startGenesis');

// 检查服务是否运行
bool running = await channel.invokeMethod('checkServiceRunning');
```

## 后台运行

### 使用 Termux:Boot（开机自启）

1. 安装 Termux:Boot
2. 创建启动脚本：

```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/genesis.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/sh
cd ~/genesis
./start_genesis.sh
EOF
chmod +x ~/.termux/boot/genesis.sh
```

### 使用 nohup 后台运行

```bash
cd ~/genesis
nohup ./start_genesis.sh > genesis.log 2>&1 &
```

## 故障排除

### 服务无法启动

```bash
# 检查端口是否被占用
netstat -tlnp | grep 19842

# 检查进程
pgrep -f genesis.main

# 查看日志
tail -f ~/genesis/data/genesis.log
```

### 依赖安装失败

```bash
# 安装编译工具
pkg install build-essential libffi openssl rust

# 重新安装依赖
pip install --force-reinstall -r ~/genesis/requirements.txt
```

### WebSocket 连接失败

1. 确认服务正在运行：`pgrep -f genesis.main`
2. 确认端口监听：`netstat -tlnp | grep 19842`
3. 检查防火墙设置

## 文件结构

```
~/genesis/
├── genesis/          # Python 后端源码
├── data/             # 数据目录
│   ├── config.yaml   # 配置文件
│   ├── genesis.log   # 日志文件
│   └── chronicle/    # 历史记录
├── start_genesis.sh  # 启动脚本
└── requirements.txt  # Python 依赖
```
