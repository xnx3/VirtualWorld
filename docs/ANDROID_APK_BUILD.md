# Android APK 打包指南

本文档是 Genesis Android 打包的统一入口，覆盖两种模式：

1. `预打包模式`：APK 内含 `genesis-termux-bundle.tar.gz`，Termux 安装最快。
2. `回退模式`：APK 不含 bundle，Termux 首次安装时在线安装依赖。

---

## 1. 构建模式对比

| 模式 | 是否内置 bundle | 构建环境要求 | 用户首次安装耗时 | 推荐场景 |
|------|------------------|--------------|------------------|---------|
| 预打包模式 | 是 | 需要先生成 ARM64 Termux bundle | 约 1 分钟 | 正式发布、离线分发 |
| 回退模式 | 否 | 任意可构建 Flutter APK 的机器 | 约 10-30 分钟 | 开发联调、无 bundle 时临时出包 |

---

## 2. 前置条件

### 2.1 必需软件

1. Java 17
2. Flutter SDK（建议 3.24+）
3. Android SDK（由 Flutter 管理）

示例（Linux）：

```bash
export PATH=/opt/flutter/bin:$PATH
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
export PATH=$JAVA_HOME/bin:$PATH
```

### 2.2 项目准备

```bash
cd /path/to/VirtualWorld/client/flutter
flutter pub get
```

---

## 3. 一键打包脚本（推荐）

统一使用：

```bash
scripts/build_android_apk_with_bundle.sh
```

常用参数：

- `--bundle-file PATH`：使用现成 `genesis-termux-bundle.tar.gz`
- `--skip-bundle-build`：跳过 bundle 构建（回退模式）
- `--release`：Release 构建（默认）
- `--debug`：Debug 构建
- `--split-per-abi`：按 ABI 拆分

脚本产物目录：

```text
client/flutter/build/app/outputs/flutter-apk/
```

---

## 4. 预打包模式（推荐发布）

### Step 1: 在 ARM64 Termux 生成 bundle

> 注意：此步骤必须在 Android Termux（ARM64）中执行。
> 普通 Linux/x86_64 环境没有 `pkg`，无法直接生成可用 Termux bundle。

```bash
cd /path/to/VirtualWorld
bash termux/build_bundle.sh --output-dir termux --cleanup
```

成功后应得到：

1. `termux/genesis-termux-bundle.tar.gz`
2. `termux/genesis-termux-bundle.tar.gz.sha256`

可选校验：

```bash
cd termux
sha256sum -c genesis-termux-bundle.tar.gz.sha256
```

### Step 2: 在构建机打包 APK

```bash
cd /path/to/VirtualWorld
bash scripts/build_android_apk_with_bundle.sh \
  --bundle-file termux/genesis-termux-bundle.tar.gz \
  --release
```

### Step 3: 校验 APK 内资源

```bash
unzip -l client/flutter/build/app/outputs/flutter-apk/app-release.apk \
  | grep -E "assets/(genesis-termux-bundle\.tar\.gz|quick_install\.sh|install\.sh|start_genesis\.sh|termux-.*\.apk)"
```

若输出含 `assets/genesis-termux-bundle.tar.gz`，说明预打包成功。

---

## 5. 回退模式（当前机器可直接构建）

当你没有 bundle 文件时，直接构建回退模式 APK：

```bash
cd /path/to/VirtualWorld
bash scripts/build_android_apk_with_bundle.sh --skip-bundle-build --release
```

脚本会提示：

```text
Warning: bundle not found, APK will fallback to full install mode
```

这不是构建失败，而是表示 APK 不含预制 bundle。

---

## 6. 当前仓库实测流程（2026-03-27）

本仓库在 `x86_64 Linux` 环境中，已验证以下流程成功：

```bash
cd /home/git/VirtualWorld
export PATH=/opt/flutter/bin:$PATH
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
export PATH=$JAVA_HOME/bin:$PATH
bash scripts/build_android_apk_with_bundle.sh --skip-bundle-build --release
```

构建结果：

1. APK 路径：`client/flutter/build/app/outputs/flutter-apk/app-release.apk`
2. 体积：约 92MB
3. SHA256：`f91e5b72b611d705e811a47d7fc93013bafb637bad7081392694ab98212a2fc5`

---

## 7. 常见失败与解决

### 7.1 `pkg: command not found`

触发场景：在普通 Linux 机器上执行 `termux/build_bundle.sh`。

原因：`pkg` 是 Termux 包管理器，不存在于普通 Linux。

处理：

1. 在 Android Termux（ARM64）中先生成 bundle；或
2. 改用 `--skip-bundle-build` 打回退模式 APK。

### 7.2 Java/Kotlin 编译异常

先清理再构建：

```bash
cd client/flutter/android && ./gradlew clean
cd ..
flutter clean
flutter pub get
flutter build apk --release
```

### 7.3 Flutter 依赖不一致

```bash
cd client/flutter
flutter pub get
flutter pub outdated
```

---

## 8. 发布前检查

- [ ] 使用 `--release` 构建
- [ ] 校验 APK SHA256
- [ ] 检查 assets 中是否包含预期文件（bundle/脚本/termux apk）
- [ ] 记录构建命令与构建时间
- [ ] 如需上架，配置正式签名（keystore）

---

## 9. 相关文档

- [Termux Bundle 部署](./TERMUX_BUNDLE_DEPLOY.md)
- [Termux 集成指南](./TERMUX_INTEGRATION.md)
- [Flutter APK 使用说明](./APK_DEBUG.md)
