# Genesis Flutter App

跨平台 GUI 前端，用于 Genesis 硅基文明模拟器。

## 支持平台

- ✅ Android
- ✅ Windows
- ✅ macOS
- ✅ Linux
- ❌ iOS (暂不支持)

## 前置要求

1. **Flutter SDK** (3.0+)
   ```bash
   # 安装 Flutter: https://docs.flutter.dev/get-started/install
   flutter doctor
   ```

2. **Python 后端运行中**
   ```bash
   cd ../../../
   ./genesis.sh start --api
   ```

## 运行

```bash
# 获取依赖
flutter pub get

# 运行开发版本
flutter run

# 指定平台运行
flutter run -d windows
flutter run -d macos
flutter run -d linux
flutter run -d chrome  # Web (需要后端 CORS 配置)
```

## 构建

```bash
# Android APK
flutter build apk --release

# Windows
flutter build windows --release

# macOS
flutter build macos --release

# Linux
flutter build linux --release
```

## 项目结构

```
lib/
├── main.dart              # 应用入口
├── app.dart               # App 配置
├── core/
│   ├── theme/             # 主题
│   └── constants/         # 常量、图标
├── services/
│   ├── app_state.dart     # 全局状态
│   └── websocket_service.dart  # WebSocket 连接
├── screens/
│   ├── home_screen.dart   # 主界面
│   └── settings_screen.dart    # 设置
├── widgets/
│   ├── tick_card.dart     # Tick 卡片
│   ├── spirit_progress_bar.dart  # 精神力条
│   ├── think_bubble.dart  # 思考气泡
│   ├── action_card.dart   # 行动卡片
│   └── event_log_card.dart  # 事件日志
├── l10n/                  # 国际化
└── models/                # 数据模型
```

## 与 Python 后端通信

WebSocket 连接到 `ws://127.0.0.1:19842`

### 发送命令

```json
// 分配任务
{"type": "task", "task": "探索世界的意义"}

// 请求状态
{"type": "status"}

// 停止
{"type": "stop"}
```

### 接收事件

```json
// Tick 更新
{"type": "tick", "data": {"tick": 42, "being_name": "Luna", ...}}

// 思考
{"type": "think", "data": {"thought": "我在思考..."}}

// 行动
{"type": "action", "data": {"action_type": "explore", "details": "..."}}

// 精神力
{"type": "spirit", "data": {"current": 850, "maximum": 1000}}

// 灾害
{"type": "disaster", "data": {"name": "地震", "severity": 0.8}}
```

## Android 打包注意事项

1. 需要安装 Android SDK
2. 需要配置签名密钥（发布版本）
3. APK 约 35-50MB（包含 Flutter 引擎）

```bash
# 生成签名密钥
keytool -genkey -v -keystore genesis-release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias genesis

# 构建 APK
flutter build apk --release
```