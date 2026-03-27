# APK 打包实操 Runbook

本 Runbook 用于日常出包，目标是让任何人按步骤执行都能复现结果。

## 1. 术语

- `bundle`：`genesis-termux-bundle.tar.gz`，包含预装 Python 依赖的 Termux 部署包。
- `预打包 APK`：APK 内带 bundle，用户安装更快。
- `回退 APK`：APK 不带 bundle，Termux 运行 `install.sh` 在线安装依赖。

## 2. 目录约定

项目根目录：`/home/git/VirtualWorld`

关键脚本：

- `scripts/build_android_apk_with_bundle.sh`
- `termux/build_bundle.sh`

APK 输出目录：

- `client/flutter/build/app/outputs/flutter-apk/`

## 3. 环境准备

```bash
cd /home/git/VirtualWorld
export PATH=/opt/flutter/bin:$PATH
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
export PATH=$JAVA_HOME/bin:$PATH
```

建议先验证：

```bash
flutter --version
java -version
```

## 4. 回退模式出包（本机已验证）

适用于没有 bundle 文件，或只想快速出一个可安装 APK。

### Step 1: 执行构建

```bash
cd /home/git/VirtualWorld
bash scripts/build_android_apk_with_bundle.sh --skip-bundle-build --release
```

### Step 2: 检查产物

```bash
ls -lh client/flutter/build/app/outputs/flutter-apk/app-release.apk
sha256sum client/flutter/build/app/outputs/flutter-apk/app-release.apk
```

### Step 3: 检查关键 assets

```bash
unzip -l client/flutter/build/app/outputs/flutter-apk/app-release.apk \
  | grep -E "assets/(genesis/|install\.sh|quick_install\.sh|start_genesis\.sh|termux-.*\.apk|genesis-termux-bundle\.tar\.gz)"
```

预期：有 `quick_install.sh`/`install.sh`/`start_genesis.sh`，若没有 bundle 则不会出现 `genesis-termux-bundle.tar.gz`。

## 5. 预打包模式出包（发布推荐）

### Step 1: 在 ARM64 Termux 生成 bundle

> 这一步不能在普通 Linux x86_64 上完成。

```bash
cd /path/to/VirtualWorld
bash termux/build_bundle.sh --output-dir termux --cleanup
```

生成文件：

- `termux/genesis-termux-bundle.tar.gz`
- `termux/genesis-termux-bundle.tar.gz.sha256`

可选校验：

```bash
cd termux
sha256sum -c genesis-termux-bundle.tar.gz.sha256
```

### Step 2: 用 bundle 构建 release APK

```bash
cd /home/git/VirtualWorld
bash scripts/build_android_apk_with_bundle.sh \
  --bundle-file termux/genesis-termux-bundle.tar.gz \
  --release
```

### Step 3: 验证 bundle 已进入 APK

```bash
unzip -l client/flutter/build/app/outputs/flutter-apk/app-release.apk \
  | grep "assets/genesis-termux-bundle.tar.gz"
```

如果 grep 能命中，说明是预打包 APK。

## 6. 当前已验证构建记录

构建日期：`2026-03-27`

执行命令：

```bash
cd /home/git/VirtualWorld
export PATH=/opt/flutter/bin:$PATH
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
export PATH=$JAVA_HOME/bin:$PATH
bash scripts/build_android_apk_with_bundle.sh --skip-bundle-build --release
```

产物：

- 路径：`client/flutter/build/app/outputs/flutter-apk/app-release.apk`
- 大小：`92MB`
- SHA256：`f91e5b72b611d705e811a47d7fc93013bafb637bad7081392694ab98212a2fc5`

## 7. 常见问题

### 7.1 `pkg: command not found`

原因：在普通 Linux 环境运行了 `termux/build_bundle.sh`。

处理：改在 Android Termux（ARM64）执行该脚本。

### 7.2 构建失败但日志出现 `Already watching path`

这条通常是文件监听器告警，不一定导致失败。以 `Built ... app-release.apk` 是否出现为准。

### 7.3 没有 bundle 时是否可发布

可以发布，但属于回退模式。用户首次安装时间更长，依赖网络。

## 8. 发布前最小清单

- [ ] 选择模式（预打包 / 回退）
- [ ] 生成并校验 APK SHA256
- [ ] 验证 APK assets 内容符合预期
- [ ] 记录构建命令、日期、构建人
