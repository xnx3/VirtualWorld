# Flutter APK 使用说明

## APK 内置 Genesis 后端

APK 已内置 Genesis 服务，**安装后可直接使用，无需任何配置**。

## 使用方法

1. 安装 APK
2. 打开应用，点击启动服务
3. 自动连接本地 Genesis 后端

## 技术说明

- **WebSocket 地址**: `127.0.0.1:19842`
- **后端服务**: APK 内置 Python 环境，自动启动 Genesis
- **无需外部服务器**

## 故障排查

### 服务启动失败？

检查 APK 日志，确认 Python 环境是否正常。

### 连接失败？

服务启动后自动连接本地端口，无需手动配置。

## 相关文件

- `client/flutter/lib/services/websocket_service.dart` - WebSocket 连接逻辑
- `client/flutter/lib/screens/settings_screen.dart` - 服务器设置界面
