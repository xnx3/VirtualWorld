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

## 自动安装（推荐）

在 Flutter 应用中，打开 **设置** 界面，按照 3 步流程操作：

### Step 1: 安装 Termux
- 应用会检测 Termux 是否已安装
- 点击"下载 Termux"跳转到 F-Droid 下载页面
- 安装 Termux 后返回应用

### Step 2: 一键安装 Genesis
- 点击"一键安装 Genesis"按钮
- 应用会自动将 Genesis 文件复制到 Termux 目录
- 等待安装完成（约 10-30 秒）

### Step 3: 启动服务
- 点击"启动服务"按钮
- 服务将在后台运行
- 返回主界面，应用会自动连接 `ws://127.0.0.1:19842`

## 手动安装（备选）

如果自动安装失败，可以手动操作：

### 1. 安装 Termux

从 F-Droid 安装（推荐，Google Play 版本已过时）：
- Termux: https://f-droid.org/packages/com.termux/

### 2. 在 Termux 中安装 Genesis

```bash
# 方法 A: 从 Git 克隆
pkg install git
git clone https://github.com/your-repo/VirtualWorld.git
cd VirtualWorld/termux
bash install.sh

# 方法 B: 从 APK assets 复制
# Genesis 文件位于 /data/data/com.termux/files/home/genesis/
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

## 文件结构

```
~/genesis/                          # Termux 主目录
├── genesis/                        # Python 后端源码
│   ├── main.py                     # 入口文件
│   ├── being/                      # 生命体模块
│   ├── world/                      # 世界模块
│   └── ...
├── data/                           # 数据目录
│   ├── config.yaml                 # 配置文件（需手动配置 API）
│   ├── genesis.log                 # 日志文件
│   └── chronicle/                  # 历史记录
├── start_genesis.sh                # 启动脚本
└── install.sh                      # 安装依赖脚本
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

应用会自动测试 API 连接，验证成功后配置将保存到 Termux 的 `config.yaml`。

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
nano ~/genesis/data/config.yaml
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
