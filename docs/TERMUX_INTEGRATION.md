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

## 安装方式对比

| 方式 | 安装时间 | 网络需求 | 适用场景 |
|------|---------|---------|---------|
| **快速安装** | ~1 分钟 | 仅需下载 bundle | 推荐，离线可用 |
| **完整安装** | 10-30 分钟 | 需下载依赖并编译 | 网络好，或无预构建 bundle |

### 快速安装（推荐）

使用预构建的 bundle 包，包含完整的 Python 虚拟环境和所有依赖，解压即用。

**前提条件**：
- Termux 已安装
- bundle 文件已准备好（`genesis-termux-bundle.tar.gz`）

**步骤**：

```bash
# 1. 授予存储权限
termux-setup-storage

# 2. 运行快速安装脚本
bash ~/storage/downloads/Genesis/quick_install.sh

# 3. 启动服务
cd ~/genesis
./start_genesis.sh
```

**选项参数**：
```bash
# 强制重新安装
bash ~/storage/downloads/Genesis/quick_install.sh --force

# 从网络下载 bundle
bash ~/storage/downloads/Genesis/quick_install.sh --from-url https://example.com/genesis-termux-bundle.tar.gz

# 指定 bundle 文件路径
bash ~/storage/downloads/Genesis/quick_install.sh --bundle /path/to/bundle.tar.gz
```

### 完整安装（备选）

从源码安装，需要编译依赖包。

```bash
# 1. 授予存储权限
termux-setup-storage

# 2. 运行完整安装脚本（需要 10-30 分钟）
bash ~/storage/downloads/Genesis/install.sh

# 3. 启动服务
cd ~/genesis
./start_genesis.sh
```

## 自动安装（Flutter 应用内）

在 Flutter 应用中，打开 **设置** 界面，按照 3 步流程操作：

### Step 1: 安装 Termux
- 应用会检测 Termux 是否已安装
- 点击"下载 Termux"跳转到 F-Droid 下载页面
- 安装 Termux 后返回应用

### Step 2: 一键安装 Genesis
- 点击"一键安装 Genesis"按钮
- 应用会自动将 Genesis 文件复制到共享存储目录
- 如果 APK 包含预构建 bundle，会一并复制

### Step 3: 在 Termux 中完成安装
- 打开 Termux 应用
- 运行 `termux-setup-storage` 授予存储权限
- 根据提示选择快速安装或完整安装：
  ```bash
  # 快速安装（推荐，约1分钟）
  bash ~/storage/downloads/Genesis/quick_install.sh

  # 或完整安装（约20分钟）
  bash ~/storage/downloads/Genesis/install.sh
  ```

### Step 4: 启动服务
- 在 Termux 中运行：
  ```bash
  cd ~/genesis
  ./start_genesis.sh
  ```
- 服务将在后台运行
- 返回 Flutter 应用，会自动连接 `ws://127.0.0.1:19842`

## 手动安装（开发/测试）

如果自动安装失败，可以手动操作：

### 1. 安装 Termux

从 F-Droid 安装（推荐，Google Play 版本已过时）：
- Termux: https://f-droid.org/packages/com.termux/

### 2. 获取 Genesis 文件

```bash
# 方法 A: 从 Git 克隆
pkg install git
git clone https://github.com/your-repo/VirtualWorld.git
cd VirtualWorld/termux
bash install.sh

# 方法 B: 从 Flutter 应用复制
# Flutter 应用会将文件复制到 ~/storage/downloads/Genesis/
termux-setup-storage
bash ~/storage/downloads/Genesis/install.sh
```

### 3. 配置 API 密钥

```bash
# 编辑配置文件
nano ~/genesis/config.yaml

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

## 文件结构

```
~/genesis/                          # Termux 主目录
├── genesis/                        # Python 后端源码
│   ├── main.py                     # 入口文件
│   ├── being/                      # 生命体模块
│   ├── world/                      # 世界模块
│   └── ...
├── venv/                           # Python 虚拟环境（快速安装）
├── data/                           # 数据目录
│   ├── genesis.log                 # 日志文件
│   └── chronicle/                  # 历史记录
├── config.yaml                     # 配置文件（需手动配置 API）
├── start_genesis.sh                # 启动脚本
├── install.sh                      # 完整安装脚本
├── quick_install.sh                # 快速安装脚本
└── bundle-info.json                # Bundle 信息（快速安装）
```

## 构建 Bundle（开发者）

如果需要自己构建预构建 bundle，在 ARM64 Termux 环境中运行：

```bash
# 进入项目目录
cd VirtualWorld/termux

# 运行构建脚本
bash build_bundle.sh

# 输出文件
# - genesis-termux-bundle.tar.gz (~30-50MB)
# - genesis-termux-bundle.tar.gz.sha256
```

**注意**：Bundle 必须在 ARM64 Termux 环境中构建，以确保 `.so` 文件兼容性。

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

### 快速安装失败

**Python 版本不兼容**：
```bash
# 检查 Python 版本
python3 --version

# 查看 bundle 需要的版本
cat ~/genesis/bundle-info.json

# 如果版本不匹配，使用完整安装
bash ~/storage/downloads/Genesis/install.sh
```

**Bundle 校验失败**：
```bash
# 手动校验 SHA256
sha256sum -c genesis-termux-bundle.tar.gz.sha256

# 如果校验失败，重新下载 bundle
```

**venv 损坏**：
```bash
# 删除 venv 并重新安装依赖
rm -rf ~/genesis/venv
cd ~/genesis
pip install -r requirements.txt
```

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
3. 在设置界面点击"刷新状态"按钮

### Termux RUN_COMMAND 权限问题

如果启动服务失败，可能需要手动授权：

1. 打开 Termux 应用
2. 运行 `termux-setup-storage` 授权存储访问
3. 返回 Flutter 应用重试

## API 配置

在 Flutter 应用设置界面，可以直接配置 LLM API：

1. 打开 **设置** → **LLM API 配置**
2. 选择预设提供商（OpenAI/DeepSeek/Claude/Ollama）或手动输入
3. 输入 **API Key**
4. 确认 **Model** 名称正确
5. 点击 **保存并验证**

应用会自动测试 API 连接，验证成功后配置将保存到 `~/genesis/config.yaml`。

### 支持的提供商

| 提供商 | Base URL | 默认模型 |
|--------|----------|----------|
| OpenAI | https://api.openai.com/v1 | gpt-4o-mini |
| DeepSeek | https://api.deepseek.com/v1 | deepseek-chat |
| Claude | https://api.anthropic.com/v1 | claude-3-haiku-20240307 |
| Ollama | http://localhost:11434/v1 | llama3 |

### 手动配置（备选）

如需手动编辑配置文件：

```bash
nano ~/genesis/config.yaml
```

配置格式：
```yaml
llm:
  base_url: "https://api.openai.com/v1"
  api_key: "your-api-key"
  model: "gpt-4o-mini"
  max_tokens: 4096
  temperature: 0.7
```
