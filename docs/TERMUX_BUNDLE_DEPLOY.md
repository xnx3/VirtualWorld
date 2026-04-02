# Termux 预制部署方案 — 类 Docker 镜像式一键部署

## 背景

当前 Termux 安装流程需要用户手动执行 `install.sh`，该脚本会：
1. `pkg update` + 安装 python3、build-essential、rust 等系统包
2. `pip install` 安装 7 个 Python 依赖（其中 `cryptography` 和 `msgpack` 含 C/Rust 扩展，编译耗时长）
3. 复制 Genesis 源码到 `~/genesis`

整个过程在手机上可能需要 **10-30 分钟**，且容易因网络或编译问题失败。

**目标**：像 Docker 镜像一样，预制好整个运行环境，Termux 安装后解压即用。

---

## 当前架构分析

### 项目结构
```
VirtualWorld/
├── genesis/              # Python 后端（纯 Python，无原生代码）
│   ├── main.py           # 主入口 (python3 -m genesis.main)
│   ├── api/              # WebSocket API 服务
│   ├── being/            # 硅基生命逻辑
│   ├── chain/            # 区块链
│   ├── chronicle/        # 编年史日志
│   ├── governance/       # 治理系统
│   ├── network/          # P2P 网络
│   ├── node/             # 节点配置/身份
│   ├── utils/            # 工具函数
│   └── world/            # 世界状态
├── termux/
│   ├── install.sh        # 当前完整安装脚本（慢）
│   └── start_genesis.sh  # 启动脚本
├── client/flutter/       # Flutter 前端
├── requirements.txt      # Python 依赖
├── config.yaml.example   # 配置模板
└── genesis.sh            # 桌面端启动脚本
```

### 当前安装流程
```
Flutter App → 复制文件到共享存储 → 用户打开 Termux → 运行 install.sh
                                                         ↓
                                              pkg update (~2min)
                                              pkg install python3/rust/build-essential (~5min)
                                              pip install cryptography/msgpack/... (~10min)
                                              复制 Genesis 源码 (~1s)
                                                         ↓
                                                    安装完成 (~20min)
```

### Python 依赖分析

| 包名 | 版本要求 | 是否含原生扩展 | 打包风险 |
|------|---------|--------------|---------|
| `openai` | >=1.0.0 | 否（纯 Python） | 低 |
| `cryptography` | >=41.0.0 | **是（Rust + C）** | **高** — 编译需要 rust/gcc |
| `msgpack` | >=1.0.0 | **是（C 扩展）** | **中** — 有纯 Python 回退 |
| `pyyaml` | >=6.0 | 可选 C 扩展 | 低 |
| `aiosqlite` | >=0.19.0 | 否 | 低 |
| `zeroconf` | >=0.80.0 | 否 | 低 |
| `websockets` | >=12.0 | 否 | 低 |

**关键瓶颈**：`cryptography` 包的编译是安装耗时的主要原因，需要 Rust 编译器和 C 工具链。

### Flutter 端集成现状

- `GenesisInstaller.kt`：将 APK assets 中的 Genesis 文件复制到共享存储 `/Download/Genesis/`
- `MainActivity.kt`：通过 Termux `RUN_COMMAND` API 启动/停止服务
- `build.gradle`：构建时将 `genesis/`、`termux/` 脚本、`config.yaml.example` 复制到 APK assets
- 安装状态通过 SharedPreferences 标记，不验证 Termux 内实际文件

---

## 方案设计：预构建 Bundle 快速部署

### 核心思路

在 ARM64 Termux 环境中预先完成所有安装步骤，将完整的 `~/genesis` 目录（含 venv 和所有依赖）打包为压缩包。用户只需解压即可运行。

### 新流程
```
Flutter App → 复制 bundle + quick_install.sh 到共享存储 → 用户打开 Termux → 运行 quick_install.sh
                                                                                    ↓
                                                                         pkg install python3 (~1min)
                                                                         解压 bundle (~10s)
                                                                         验证完整性 (~1s)
                                                                                    ↓
                                                                               安装完成 (~1min)
```

### 文件变更清单

#### 新建文件

| 文件 | 用途 |
|------|------|
| `termux/build_bundle.sh` | 在 Termux 中运行，构建预制 bundle |
| `termux/quick_install.sh` | 用户端一键快速部署脚本 |

#### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `termux/start_genesis.sh` | 支持 venv Python；修复 `pyyaml` import 检查 bug（`pyyaml` → `yaml`） |
| `client/flutter/android/app/build.gradle` | 添加 `quick_install.sh` 到 APK assets 复制任务 |
| `client/flutter/android/.../GenesisInstaller.kt` | 新增 bundle 安装路径，复制 bundle 文件 |
| `docs/TERMUX_INTEGRATION.md` | 添加快速部署说明 |

#### 保留不变

| 文件 | 原因 |
|------|------|
| `termux/install.sh` | 作为备用完整安装方式，网络环境好时仍可使用 |

---

## 详细实现

### 1. `termux/build_bundle.sh` — 打包脚本

**运行环境**：ARM64 Termux（真机或 CI Docker）

**功能**：
```bash
# 步骤概要
1. 确保系统依赖已安装（python3, build-essential, rust）
2. 创建临时构建目录 /tmp/genesis-build/
3. 复制 genesis/ 源码（排除 __pycache__）
4. 复制 config.yaml.example
5. 复制 start_genesis.sh, quick_install.sh
6. 创建 Python venv 并安装所有 requirements.txt 依赖
7. 清理 venv 中的 pip cache、__pycache__、.dist-info 中的大文件
8. 记录 Python 版本、架构信息到 bundle-info.json
9. 打包为 genesis-termux-bundle.tar.gz
10. 生成 SHA256 校验文件
```

**输出**：
- `genesis-termux-bundle.tar.gz`（预计 30-50MB）
- `genesis-termux-bundle.tar.gz.sha256`
- `bundle-info.json`（Python 版本、CPU 架构、构建时间）

### 2. `termux/quick_install.sh` — 快速部署脚本

**运行环境**：用户的 Termux

**功能**：
```bash
# 步骤概要
1. 检查/安装 python3（仅此一个系统包，不需要 rust/build-essential）
2. 查找 bundle 文件（优先共享存储，其次当前目录）
3. 校验 SHA256（如有校验文件）
4. 解压到 ~/genesis/
5. 验证 venv Python 可用
6. 验证关键依赖可 import
7. 如果 venv Python 版本与系统不匹配，自动重建 venv
8. 创建 data/ 目录，复制默认 config.yaml
9. 显示启动指引
```

**关键设计**：
- Python 版本兼容性检查：bundle 中的 venv 绑定了特定 Python 版本（如 3.11），如果用户 Termux 的 Python 版本不同，需要回退到 pip install
- 提供 `--force` 参数强制重新安装
- 提供 `--from-url <url>` 参数支持从网络下载 bundle

### 3. `termux/start_genesis.sh` 修改

**变更点**：
```bash
# 优先使用 venv Python
if [ -f "$GENESIS_DIR/venv/bin/python3" ]; then
    PYTHON="$GENESIS_DIR/venv/bin/python3"
else
    PYTHON="python3"
fi

# 修复依赖检查：pyyaml → yaml
local deps_import=("openai" "websockets" "aiosqlite" "yaml" "msgpack" "cryptography" "zeroconf")
```

### 4. Flutter 端集成修改

#### `build.gradle` 变更
```groovy
def generatedRuntimeAssetsDir = file("$buildDir/generated/runtime-assets/main")

task copyTermuxScripts(type: Copy) {
    from "${repoRootDir}/termux"
    into generatedRuntimeAssetsDir
    include 'start_genesis.sh'
    include 'install.sh'
    include 'quick_install.sh'
}

preBuild.dependsOn copyTermuxScripts
```

#### `GenesisInstaller.kt` 变更
- `install()` 方法中新增复制 `quick_install.sh`
- 如果 APK assets 中包含 `genesis-termux-bundle.tar.gz`，一并复制到共享存储
- 更新安装指引文本，优先推荐 `quick_install.sh`

---

## Bundle 分发策略

### 方案 A：随 APK 分发（推荐初期）

**优点**：离线可用，用户体验最简单
**缺点**：APK 体积增大 30-50MB

实现：
- `build.gradle` 添加 bundle 文件到 assets
- `GenesisInstaller.kt` 复制 bundle 到共享存储
- `quick_install.sh` 从共享存储读取 bundle

### 方案 B：网络下载

**优点**：APK 体积不变
**缺点**：需要网络，需要托管服务

实现：
- Bundle 托管在 GitHub Releases
- `quick_install.sh` 支持 `--from-url` 下载
- Flutter 端提供下载进度 UI

### 方案 C：混合方式（推荐长期）

- APK 内置 Genesis 源码（当前已有）
- Bundle 从网络按需下载
- `quick_install.sh` 智能选择：有 bundle 用 bundle，没有则回退到 `install.sh` 完整安装

---

## 注意事项与限制

### 架构绑定
- Bundle 中的 `.so` 文件（cryptography、msgpack）与 CPU 架构绑定
- 当前仅需支持 `arm64-v8a`（现代 Android 手机主流架构）
- 如需支持其他架构，需分别构建不同 bundle

### Python 版本绑定
- venv 中的 `.so` 文件与 Python 小版本绑定（如 cpython-311）
- 如果 Termux 更新了 Python 版本（如 3.11 → 3.12），旧 bundle 可能不兼容
- `quick_install.sh` 需要检测版本匹配，不匹配时回退到完整安装

### 路径绑定
- Termux 的 home 目录固定为 `/data/data/com.termux/files/home`
- venv 中的 shebang 和路径引用可能包含绝对路径
- 解压后可能需要修复 venv 中的路径（`--relocatable` 或 sed 替换）

### 已知 Bug 修复
- `start_genesis.sh` 第 36 行：`pyyaml` 应改为 `yaml`（Python import 名称）
- 当前脚本每次启动都会误判 pyyaml 未安装并尝试 pip install

---

## 验证计划

1. **构建验证**：在 ARM64 Termux 中运行 `build_bundle.sh`，确认生成 bundle
2. **部署验证**：在全新 Termux 中运行 `quick_install.sh`，确认解压成功
3. **运行验证**：执行 `start_genesis.sh`，确认服务正常启动
4. **连接验证**：Flutter 客户端连接 `ws://127.0.0.1:19842`，确认通信正常
5. **版本兼容验证**：在不同 Python 版本的 Termux 中测试回退逻辑
6. **Flutter 集成验证**：构建 APK，测试完整安装流程

---

## 时间线建议

1. **Phase 1**：创建 `build_bundle.sh` + `quick_install.sh` + 修复 `start_genesis.sh` ✅ **已完成**
2. **Phase 2**：更新 Flutter 端集成（build.gradle + GenesisInstaller.kt）✅ **已完成**
3. **Phase 3**：更新文档，在真机上端到端测试 ✅ **文档已更新**
4. **Phase 4**：（可选）设置 CI 自动构建 bundle

---

## 实现状态

| 阶段 | 任务 | 状态 |
|------|------|------|
| Phase 1 | `termux/build_bundle.sh` | ✅ 已完成 |
| Phase 1 | `termux/quick_install.sh` | ✅ 已完成 |
| Phase 1 | `termux/start_genesis.sh` 修复 | ✅ 已完成 |
| Phase 2 | `build.gradle` 更新 | ✅ 已完成 |
| Phase 2 | `GenesisInstaller.kt` 更新 | ✅ 已完成 |
| Phase 3 | `TERMUX_INTEGRATION.md` 更新 | ✅ 已完成 |
| Phase 3 | 真机端到端测试 | ⏳ 待测试 |
| Phase 4 | CI 自动构建 | ✅ 已完成 |

---

## CI 自动构建

项目使用 GitHub Actions 自动构建 Termux bundle。

### 触发方式

**方式 1：推送标签**
```bash
git tag v1.0.0
git push origin v1.0.0
```

**方式 2：手动触发**
1. 进入 GitHub Actions 页面
2. 选择 "Build Termux Bundle" 工作流
3. 点击 "Run workflow"
4. 可选填写版本号

### 构建流程

1. 在 ARM64 Docker 容器中运行（使用 `termux/termux-docker` 官方镜像）
2. 安装 Python 和编译依赖（rust, build-essential）
3. 创建虚拟环境并安装所有依赖
4. 打包为 `genesis-termux-bundle.tar.gz`
5. 生成 SHA256 校验文件
6. 上传为 Artifact（保留 30 天）
7. 如果是标签触发，自动创建 GitHub Release

### 输出文件

- `genesis-termux-bundle.tar.gz` - Bundle 包
- `genesis-termux-bundle.tar.gz.sha256` - SHA256 校验
- `bundle-info.json` - 构建元信息

### CI 工作流文件

| 文件 | 用途 |
|------|------|
| `.github/workflows/build-termux-bundle.yml` | 构建 Termux bundle |
| `.github/workflows/test-scripts.yml` | 测试脚本语法和 Flutter 构建 |

---

## 使用说明

### 构建 Bundle（开发者）

在 ARM64 Termux 环境中执行：

```bash
cd /path/to/VirtualWorld/termux
bash build_bundle.sh
```

输出文件：
- `~/genesis-termux-bundle.tar.gz` - Bundle 包（约 30-50MB）
- `~/genesis-termux-bundle.tar.gz.sha256` - SHA256 校验文件

### 分发 Bundle

**方案 A：随 APK 分发**

1. 将 bundle 文件放入仓库根目录下的 `termux/`
2. 重新构建 APK
3. Android 构建会自动复制 bundle 到临时原生 assets，Flutter 应用再把它复制到共享存储

**方案 B：网络下载**

1. 将 bundle 上传到 GitHub Releases 或其他托管服务
2. 用户运行：`quick_install.sh --from-url <bundle-url>`

### 用户快速安装

```bash
# 授予存储权限
termux-setup-storage

# 快速安装
bash ~/storage/downloads/Genesis/quick_install.sh
```

---

## 完整打包流程（开发者指南）

本节详细说明从源码到最终 APK 的完整打包流程，供其他开发者参考。

### 步骤 1：准备 Termux Bundle（可选但推荐）

Bundle 包含预编译的 Python 依赖，可大幅减少用户安装时间。

**在 ARM64 Android 设备上（Termux 环境）：**

```bash
# 1. 安装 Termux（从 F-Droid）
# 下载地址：https://f-droid.org/packages/com.termux/

# 2. 在 Termux 中克隆项目
pkg install git
git clone https://github.com/xnx3/Genesis.git
cd Genesis

# 3. 运行构建脚本
cd termux
bash build_bundle.sh

# 4. 等待构建完成（约 10-20 分钟）
# 输出文件位于 ~/ 目录：
# - genesis-termux-bundle.tar.gz
# - genesis-termux-bundle.tar.gz.sha256

# 5. 将 bundle 复制到共享存储
cp ~/genesis-termux-bundle.tar.gz* ~/storage/downloads/
```

**将 Bundle 嵌入 APK：**

```bash
# 在开发电脑上
# 1. 从设备获取 bundle（通过 adb 或其他方式）
adb pull /sdcard/Download/genesis-termux-bundle.tar.gz termux/
adb pull /sdcard/Download/genesis-termux-bundle.tar.gz.sha256 termux/

# 2. 或手动复制到 termux 目录
cp genesis-termux-bundle.tar.gz termux/
cp genesis-termux-bundle.tar.gz.sha256 termux/
```

### 步骤 2：构建 Flutter APK

**环境要求：**
- Java 17
- Flutter SDK 3.24+

```bash
# 1. 进入 Flutter 项目目录
cd client/flutter

# 2. 获取依赖
flutter pub get

# 3. 检查环境
flutter doctor

# 4. 构建 Release APK
flutter build apk --release

# 5. APK 输出位置
# build/app/outputs/flutter-apk/app-release.apk
```

### 步骤 3：测试 APK

```bash
# 安装到连接的设备
flutter install

# 或手动安装
adb install build/app/outputs/flutter-apk/app-release.apk
```

### 步骤 4：分发 APK

APK 可通过以下方式分发：

1. **GitHub Releases**：上传到项目的 Releases 页面
2. **直接分发**：发送 APK 文件给用户
3. **应用商店**：如需上架商店，需配置签名

### 无 Bundle 的情况

如果不嵌入 bundle，用户仍可使用完整安装：

```bash
# 在 Termux 中
termux-setup-storage
bash ~/storage/downloads/Genesis/install.sh
```

完整安装需要 10-30 分钟，但不需要额外准备工作。

### 文件依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                      APK 构建流程                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  genesis/                    ──┐                            │
│  requirements.txt            ──┼──► APK assets (必须)       │
│  config.yaml.example         ──┤                            │
│  termux/*.sh                 ──┘                            │
│                                                             │
│  genesis-termux-bundle.tar.gz ───► APK assets (可选)        │
│  genesis-termux-bundle.tar.gz.sha256                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      安装流程                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Flutter App                                                │
│       │                                                     │
│       ▼                                                     │
│  复制 assets 到共享存储 (~/storage/downloads/Genesis/)      │
│       │                                                     │
│       ▼                                                     │
│  用户在 Termux 中执行                                        │
│       │                                                     │
│       ├──► quick_install.sh (有 bundle，约1分钟)            │
│       │         │                                           │
│       │         ▼                                           │
│       │    解压 bundle → 完成                                │
│       │                                                     │
│       └──► install.sh (无 bundle，约20分钟)                  │
│                 │                                           │
│                 ▼                                           │
│            pip install → 完成                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 故障排除

**Bundle 构建失败：**
- 确保 Termux 是最新版本
- 确保有足够存储空间（约 500MB）
- 检查网络连接（需要下载依赖）

**APK 构建失败：**
- 检查 Java 版本是否为 17
- 运行 `flutter clean` 后重试
- 检查 `flutter doctor` 输出

**用户安装失败：**
- 确认已运行 `termux-setup-storage`
- 检查存储空间是否充足
- 尝试使用完整安装 (`install.sh`)
