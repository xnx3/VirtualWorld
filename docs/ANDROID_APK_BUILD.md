# Android APK 打包指南

本文档详细说明如何在任何电脑上使用 Claude Code 进行 Genesis Android APK 打包。

## 前提条件

### 必需软件

1. **Java 17**（Android 构建必需）
   ```bash
   # Ubuntu/Debian
   sudo apt install openjdk-17-jdk

   # macOS
   brew install openjdk@17

   # 验证
   java -version  # 应显示 17.x.x
   ```

2. **Flutter SDK 3.24+**
   ```bash
   # 下载 Flutter SDK
   git clone https://github.com/flutter/flutter.git -b stable ~/flutter

   # 添加到 PATH
   export PATH="$PATH:~/flutter/bin"

   # 验证
   flutter doctor
   ```

3. **Android SDK**（通过 Flutter 自动管理）

### 项目依赖

```bash
# 进入 Flutter 项目目录
cd client/flutter

# 获取依赖
flutter pub get
```

## 构建流程

### 1. 检查环境

```bash
cd client/flutter
flutter doctor
```

确保输出中 Android toolchain 和 Java 版本正常。

### 2. 构建 APK

```bash
cd client/flutter

# 构建 Release APK
flutter build apk --release

# 输出位置
# build/app/outputs/flutter-apk/app-release.apk
```

### 3. 构建结果

构建完成后，APK 位于：
```
client/flutter/build/app/outputs/flutter-apk/app-release.apk
```

## Termux Bundle 打包（可选）

如果需要预构建 Termux bundle 以实现快速安装：

### 方式一：本地构建（需要 ARM64 设备）

在 ARM64 Android 设备的 Termux 中：

```bash
# 克隆项目
git clone https://github.com/xnx3/Genesis.git
cd Genesis/termux

# 运行构建脚本
bash build_bundle.sh

# 输出文件
# ~/genesis-termux-bundle.tar.gz
# ~/genesis-termux-bundle.tar.gz.sha256
```

### 方式二：将 Bundle 嵌入 APK

构建好 bundle 后，将其放入 Flutter assets：

```bash
# 复制 bundle 到 assets 目录
cp genesis-termux-bundle.tar.gz client/flutter/android/app/src/main/assets/
cp genesis-termux-bundle.tar.gz.sha256 client/flutter/android/app/src/main/assets/

# 重新构建 APK
cd client/flutter
flutter build apk --release
```

APK 会自动包含 bundle 文件，Flutter 应用安装时会将其复制到共享存储供 Termux 使用。

## Termux APK 内置（推荐）

**目标**：用户只需安装一个 APK，无需手动下载 Termux。

### Step 1: 下载 Termux APK

从 F-Droid 下载最新版 Termux APK：

```bash
# 下载地址
# https://f-droid.org/packages/com.termux/

# 使用 wget 下载
wget -O termux/termux-app.apk https://f-droid.org/repo/com.termux_1020.apk

# 或手动下载后放入 termux/ 目录
```

### Step 2: 将 Termux APK 放入项目

```
termux/termux-app.apk  ← Termux APK 文件
```

### Step 3: 构建 APK

```bash
cd client/flutter
flutter build apk --release
```

构建时会自动将 Termux APK 复制到 assets 中。

### Step 4: 用户安装流程

用户安装 Genesis APK 后：

1. 打开应用
2. 提示"需要安装 Termux" → 点击"安装"
3. 系统提示"允许安装未知应用" → 允许
4. Termux 安装完成 → 返回 Genesis
5. 点击"一键安装 Genesis" → 完成

**详细实现** 请参阅 [Termux 内置方案](./TERMUX_BUNDLED_APK.md)。

### APK 大小估算

| 组件 | 大小 |
|------|------|
| Flutter 应用 | ~15 MB |
| Genesis 源码 | ~1 MB |
| Termux APK | ~30 MB |
| Genesis Bundle | ~30-50 MB |
| **总计** | **~80-100 MB** |

## 打包前检查清单

- [ ] Java 版本为 17
- [ ] Flutter 版本 >= 3.24
- [ ] `flutter pub get` 已执行
- [ ] 代码已提交（无未提交修改）
- [ ] 版本号已更新（如需要）

## 版本号管理

版本号位于 `client/flutter/pubspec.yaml`：

```yaml
version: 1.0.0+1
# 格式: version.name+build.number
# 例如: 1.2.3+10 表示版本 1.2.3，构建号 10
```

更新版本号后重新构建即可。

## 常见问题

### Java 版本错误

```
Execution failed for task ':app:compileDebugKotlin'.
> Kotlin could not find the required JDK tools in the Java installation
```

解决方案：确保 JAVA_HOME 指向 JDK 17：
```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
```

### Gradle 构建失败

```bash
cd client/flutter/android
./gradlew clean
cd ..
flutter clean
flutter pub get
flutter build apk --release
```

### 签名问题

Release APK 默认使用 debug 签名。正式发布需要配置签名：

1. 创建 keystore：
   ```bash
   keytool -genkey -v -keystore genesis-release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias genesis
   ```

2. 创建 `client/flutter/android/key.properties`：
   ```properties
   storePassword=<密码>
   keyPassword=<密码>
   keyAlias=genesis
   storeFile=<keystore文件路径>
   ```

3. 修改 `client/flutter/android/app/build.gradle`：
   ```groovy
   def keystoreProperties = new Properties()
   def keystorePropertiesFile = rootProject.file('key.properties')
   if (keystorePropertiesFile.exists()) {
       keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
   }

   android {
       signingConfigs {
           release {
               keyAlias keystoreProperties['keyAlias']
               keyPassword keystoreProperties['keyPassword']
               storeFile keystoreProperties['storeFile'] ? file(keystoreProperties['storeFile']) : null
               storePassword keystoreProperties['storePassword']
           }
       }
       buildTypes {
           release {
               signingConfig signingConfigs.release
           }
       }
   }
   ```

## 相关文档

- [Termux 集成指南](./TERMUX_INTEGRATION.md) - Termux 安装和使用
- [Termux Bundle 部署](./TERMUX_BUNDLE_DEPLOY.md) - Bundle 详细设计文档
- [Termux 内置方案](./TERMUX_BUNDLED_APK.md) - Termux APK 内置实现细节

## 自动化构建（CI/CD）

项目包含 GitHub Actions 工作流，可自动构建：

- `.github/workflows/build-termux-bundle.yml` - 构建 Termux bundle
- `.github/workflows/test-scripts.yml` - 测试脚本语法

推送标签触发自动构建：
```bash
git tag v1.0.0
git push origin v1.0.0
```
