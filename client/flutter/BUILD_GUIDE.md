# Genesis 跨平台打包指南

本文档说明如何在本地构建 Genesis App 的各平台版本。

---

## 前置要求

### 通用要求
- **Flutter SDK 3.0+**: [安装指南](https://docs.flutter.dev/get-started/install)
- **Git**: 用于克隆仓库

### Android 打包额外要求
- **Android Studio** 或 **Android SDK Command-line Tools**
- **Java JDK 11+**
- 环境变量:
  - `ANDROID_HOME` 或 `ANDROID_SDK_ROOT` 指向 Android SDK 目录

### Windows 打包额外要求
- Visual Studio 2022 (带 Desktop development with C++)

### macOS 打包额外要求
- Xcode 15+
- CocoaPods

---

## 快速开始

### 1. 克隆仓库

```bash
git clone <your-repo-url>
cd VirtualWorld/client/flutter
```

### 2. 安装依赖

```bash
flutter pub get
```

### 3. 运行开发版本

```bash
flutter run
```

---

## Android APK 构建

### 方式一：使用构建脚本（推荐）

```bash
cd client/flutter
./build_apk.sh
```

### 方式二：手动构建

```bash
# 1. 接受 Android 许可
flutter doctor --android-licenses

# 2. 构建 APK
flutter build apk --release

# 3. 输出位置
# build/app/outputs/flutter-apk/app-release.apk
```

### 安装到设备

```bash
# 通过 ADB 安装
adb install build/app/outputs/flutter-apk/app-release.apk

# 或直接将 APK 文件传输到手机安装
```

### 签名配置（发布版本）

创建签名密钥：

```bash
keytool -genkey -v -keystore genesis-release.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias genesis
```

创建 `android/key.properties`:

```properties
storePassword=<your-store-password>
keyPassword=<your-key-password>
keyAlias=genesis
storeFile=../genesis-release.jks
```

修改 `android/app/build.gradle`:

```gradle
// 在 android {} 之前添加
def keystoreProperties = new Properties()
def keystorePropertiesFile = rootProject.file('key.properties')
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
}

android {
    ...
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

---

## Windows 构建

```bash
flutter build windows --release
```

输出位置: `build\windows\x64\runner\Release\`

创建安装包（使用 Inno Setup 或 NSIS）

---

## macOS 构建

```bash
# 1. 安装 CocoaPods 依赖
cd macos
pod install
cd ..

# 2. 构建
flutter build macos --release
```

输出位置: `build/macos/Build/Products/Release/genesis_app.app`

创建 DMG:

```bash
hdiutil create -volname "Genesis" \
  -srcfolder build/macos/Build/Products/Release/genesis_app.app \
  -ov -format UDZO genesis.dmg
```

---

## Linux 构建

```bash
# 安装依赖 (Ubuntu/Debian)
sudo apt-get install clang cmake ninja-build pkg-config libgtk-3-dev

# 构建
flutter build linux --release
```

输出位置: `build/linux/x64/release/bundle/`

创建 AppImage:

```bash
# 使用 appimage-builder 或 linuxdeploy
```

---

## 项目结构

```
client/flutter/
├── android/                 # Android 平台配置
│   ├── app/
│   │   ├── build.gradle     # App 级构建配置
│   │   └── src/main/
│   │       ├── AndroidManifest.xml
│   │       └── kotlin/      # Kotlin 原生代码
│   ├── build.gradle         # 项目级构建配置
│   └── gradle.properties
├── ios/                     # iOS 平台配置（暂不支持）
├── linux/                   # Linux 平台配置
├── macos/                   # macOS 平台配置
├── windows/                 # Windows 平台配置
├── lib/                     # Dart 源代码
│   ├── main.dart
│   ├── core/
│   ├── services/
│   ├── screens/
│   ├── widgets/
│   └── l10n/
├── assets/                  # 静态资源
├── pubspec.yaml             # 项目配置
├── build_apk.sh             # APK 构建脚本
└── BUILD_GUIDE.md           # 本文档
```

---

## 连接到 Python 后端

### 1. 启动后端（带 API）

```bash
cd ../../../
./genesis.sh start --api
```

后端将在 `ws://127.0.0.1:19842` 提供 WebSocket 服务。

### 2. 修改连接地址

如果后端不在本地，编辑 `lib/services/websocket_service.dart`:

```dart
String _serverUrl = 'your-server-ip';  // 修改为后端 IP
int _serverPort = 19842;
```

### 3. 手机连接

如果手机和电脑在同一 WiFi：

1. 查看电脑 IP: `ipconfig` (Windows) 或 `ifconfig` (macOS/Linux)
2. 在 App 设置中修改服务器地址为电脑 IP
3. 确保防火墙允许 19842 端口

---

## 常见问题

### Q: Flutter 命令找不到
A: 确保 Flutter SDK 已添加到 PATH：
```bash
export PATH="$PATH:/path/to/flutter/bin"
```

### Q: Android SDK 未找到
A: 设置环境变量：
```bash
export ANDROID_HOME=/path/to/android/sdk
export PATH="$PATH:$ANDROID_HOME/tools:$ANDROID_HOME/platform-tools"
```

### Q: 构建失败，提示 Gradle 错误
A: 尝试清理：
```bash
flutter clean
flutter pub get
flutter build apk
```

### Q: APK 体积太大
A: 使用 split APK：
```bash
flutter build apk --split-per-abi
```

---

## 预计 APK 大小

| 架构 | 大小 |
|------|------|
| arm64-v8a | ~25MB |
| armeabi-v7a | ~23MB |
| x86_64 | ~26MB |
| 通用 APK | ~50MB |