import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// WebSocket 服务 - 连接 Python 后端
class WebSocketService with ChangeNotifier {
  WebSocketChannel? _channel;
  bool _isConnected = false;
  String _serverUrl = '127.0.0.1';
  int _serverPort = 19842;

  // 事件流控制器
  final _eventController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get events => _eventController.stream;

  // 状态
  bool get isConnected => _isConnected;

  /// 连接到后端
  Future<bool> connect({String? host, int? port}) async {
    if (_isConnected) return true;

    _serverUrl = host ?? _serverUrl;
    _serverPort = port ?? _serverPort;

    try {
      final uri = Uri.parse('ws://$_serverUrl:$_serverPort');
      _channel = WebSocketChannel.connect(uri);

      // 等待连接建立
      await _channel!.ready;

      // 监听消息
      _channel!.stream.listen(
        _handleMessage,
        onError: _handleError,
        onDone: _handleDisconnect,
      );

      _isConnected = true;
      notifyListeners();
      debugPrint('WebSocket connected to $uri');
      return true;
    } catch (e) {
      debugPrint('WebSocket connection failed: $e');
      _isConnected = false;
      return false;
    }
  }

  /// 断开连接
  void disconnect() {
    _channel?.sink.close();
    _channel = null;
    _isConnected = false;
    notifyListeners();
  }

  /// 发送命令
  void sendCommand(String type, Map<String, dynamic> data) {
    if (!_isConnected || _channel == null) {
      debugPrint('WebSocket not connected, cannot send command');
      return;
    }

    final message = jsonEncode({'type': type, ...data});
    _channel!.sink.add(message);
  }

  /// 分配任务
  void sendTask(String task) {
    sendCommand('task', {'task': task});
  }

  /// 请求停止
  void sendStop() {
    sendCommand('stop', {});
  }

  /// 请求状态
  void requestStatus() {
    sendCommand('status', {});
  }

  /// 处理收到的消息
  void _handleMessage(dynamic message) {
    try {
      final data = jsonDecode(message as String) as Map<String, dynamic>;
      _eventController.add(data);
    } catch (e) {
      debugPrint('Failed to parse message: $e');
    }
  }

  /// 处理错误
  void _handleError(dynamic error) {
    debugPrint('WebSocket error: $error');
    _isConnected = false;
    notifyListeners();
  }

  /// 处理断开连接
  void _handleDisconnect() {
    debugPrint('WebSocket disconnected');
    _isConnected = false;
    notifyListeners();
  }

  @override
  void dispose() {
    disconnect();
    _eventController.close();
    super.dispose();
  }
}