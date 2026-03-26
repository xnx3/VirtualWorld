# Flutter APK 构建指南

本文档说明如何构建 Genesis Android APK。

## 环境要求

- **Java 17**（必需，Gradle 8.1.0 要求）
- **Flutter SDK 3.24+**
- **Android SDK**（通过 Flutter 自动管理）

## 快速构建

```bash
# 1. 进入 Flutter 项目目录
cd client/flutter

# 2. 获取依赖
flutter pub get

# 3. 检查环境
flutter doctor

# 4. 构建 Release APK
flutter build apk --release
```

## 输出位置

```
client/flutter/build/app/outputs/flutter-apk/app-release.apk
```

## Java 版本设置

如果系统默认 Java 版本不是 17：

```bash
# Linux/macOS
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk

# 或使用 flutter 强制指定
flutter config --jdk-dir /usr/lib/jvm/java-17-openjdk
```

## 详细文档

完整的 APK 打包指南，包括：
- Termux Bundle 嵌入
- 签名配置
- 故障排除

请参阅：[Android APK 打包指南](./ANDROID_APK_BUILD.md)

## 相关文档

- [Termux 集成指南](./TERMUX_INTEGRATION.md) - Termux 安装和使用
- [Termux Bundle 部署](./TERMUX_BUNDLE_DEPLOY.md) - 快速部署方案
