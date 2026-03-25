# Flutter APK 使用说明

## 安装后直接使用

APK 已内置默认服务器配置：
- **服务器地址**: `192.168.31.250`
- **端口**: `19842`

安装后即可直接使用，无需手动配置。

## 连接要求

1. **同一局域网**：手机需连接到 `192.168.31.x` 网段的 WiFi
2. **服务器运行**：确保 Genesis 后端服务已启动

## 故障排查

### 无法连接？

1. 检查手机是否连接到正确的 WiFi（192.168.31.x 网段）
2. 检查服务器是否运行：`./genesis.sh status`
3. 检查网络是否可达：在手机浏览器访问 `http://192.168.31.250:19842`

### 需要修改服务器地址？

进入 设置 页面，修改服务器地址后点击连接。

## 相关文件

- `client/flutter/lib/services/websocket_service.dart` - WebSocket 连接逻辑
- `client/flutter/lib/screens/settings_screen.dart` - 服务器设置界面
