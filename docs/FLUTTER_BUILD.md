# Flutter APK 构建指南

## 构建命令

必须使用 Java 17，否则 Gradle 8.1.0 不兼容。

```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk
cd /home/git/VirtualWorld/client/flutter
/opt/flutter/bin/flutter build apk --release
```

## 输出路径

```
build/app/outputs/flutter-apk/app-release.apk
```

## 环境要求

- Java 17（系统默认是 Java 8，需要手动设置 JAVA_HOME）
- Flutter 位于 `/opt/flutter/bin/flutter`

## APK 配置说明

APK 内置 Genesis 后端服务，默认连接 `127.0.0.1:19842`，用户安装后无需任何配置。
