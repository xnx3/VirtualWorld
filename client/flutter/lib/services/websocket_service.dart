import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// WebSocket 服务 - 连接 Python 后端
class WebSocketService with ChangeNotifier {
  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  bool _isConnected = false;
  bool _isDisposed = false;
  bool _isConnecting = false;
  String _serverUrl;
  int _serverPort;
  String? _lastError;

  // 预设服务器配置 - APK 内置 Genesis 后端，连接本地
  static const String defaultHost = '127.0.0.1';
  static const int defaultPort = 19842;

  // 重连配置
  int _reconnectAttempts = 0;
  static const int _maxReconnectAttempts = 10;
  Timer? _reconnectTimer;

  // 事件流控制器
  final _eventController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get events => _eventController.stream;

  // 连接状态变化流 - 用于通知 UI 重连成功
  final _connectionStateController = StreamController<bool>.broadcast();
  Stream<bool> get connectionChanges => _connectionStateController.stream;

  // 状态
  bool get isConnected => _isConnected;
  bool get isConnecting => _isConnecting;
  bool get isReconnecting => _reconnectTimer != null;
  String get serverUrl => _serverUrl;
  int get serverPort => _serverPort;
  String? get lastError => _lastError;

  /// 构造函数 - 接收初始配置
  WebSocketService({String? host, int? port})
      : _serverUrl = host ?? defaultHost,
        _serverPort = port ?? defaultPort;

  /// 更新服务器配置
  void updateServerConfig(String url, int port) {
    _serverUrl = url;
    _serverPort = port;
  }

  /// 连接到后端
  Future<bool> connect({String? host, int? port}) async {
    // 如果已连接，直接返回
    if (_isConnected) return true;
    if (_isDisposed) return false;

    // 取消任何现有的重连计时器
    _reconnectTimer?.cancel();
    _reconnectTimer = null;

    // 更新服务器配置
    if (host != null) _serverUrl = host;
    if (port != null) _serverPort = port;

    // 检查服务器地址是否有效
    if (_serverUrl.isEmpty) {
      _lastError = '服务器地址未配置';
      notifyListeners();
      return false;
    }

    _isConnecting = true;
    _lastError = null;
    notifyListeners();

    try {
      final uri = Uri.parse('ws://$_serverUrl:$_serverPort');
      _channel = WebSocketChannel.connect(uri);

      // 等待连接建立，设置超时
      await _channel!.ready.timeout(const Duration(seconds: 10));

      // 取消之前的订阅
      await _subscription?.cancel();

      // 监听消息
      _subscription = _channel!.stream.listen(
        _handleMessage,
        onError: _handleError,
        onDone: _handleDisconnect,
      );

      _isConnected = true;
      _isConnecting = false;
      _reconnectAttempts = 0;
      _lastError = null;

      // 通知连接状态变化
      _connectionStateController.add(true);
      notifyListeners();

      debugPrint('WebSocket connected to $uri');
      return true;
    } catch (e) {
      debugPrint('WebSocket connection failed: $e');
      _isConnected = false;
      _isConnecting = false;
      _lastError = _generateFriendlyError(e.toString());
      _scheduleReconnect();
      notifyListeners();
      return false;
    }
  }

  /// 生成友好的错误消息
  String _generateFriendlyError(String error) {
    if (error.contains('Connection refused') ||
        error.contains('SocketException') ||
        error.contains('Failed host lookup')) {
      return '无法连接到本地 Genesis 服务\n\n'
          '请检查:\n'
          '1. Genesis 服务是否已启动\n'
          '2. 应用是否正常运行';
    }
    if (error.contains('timed out') || error.contains('TimeoutException')) {
      return '连接超时\n请检查服务状态';
    }
    if (error.contains('No address associated')) {
      return '无法解析服务器地址';
    }
    return '连接失败: $error';
  }

  /// 安排重连
  void _scheduleReconnect() {
    if (_isDisposed) return;

    _reconnectTimer?.cancel();

    if (_reconnectAttempts < _maxReconnectAttempts) {
      final delay = Duration(seconds: 1 << _reconnectAttempts.clamp(0, 4));
      debugPrint('Scheduling reconnect in ${delay.inSeconds}s (attempt ${_reconnectAttempts + 1}/$_maxReconnectAttempts)');

      _reconnectTimer = Timer(delay, () async {
        _reconnectAttempts++;
        final success = await connect();
        if (!success && _reconnectAttempts >= _maxReconnectAttempts) {
          _lastError = '重连失败，已达到最大重试次数\n请检查服务器状态后手动重试';
          notifyListeners();
        }
      });
    } else {
      _lastError = '连接失败\n请检查服务器状态后点击重试';
      notifyListeners();
    }
  }

  /// 手动重试连接（用户点击重试按钮）
  Future<bool> retryConnect() async {
    _reconnectAttempts = 0;  // 重置重连计数
    return await connect();
  }

  /// 断开连接
  void disconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
    _isConnected = false;
    _isConnecting = false;
    notifyListeners();
  }

  /// 发送命令
  void sendCommand(String type, Map<String, dynamic> data) {
    final channel = _channel;
    if (!_isConnected || channel == null) {
      debugPrint('WebSocket not connected, cannot send command');
      return;
    }

    final message = jsonEncode({'type': type, ...data});
    channel.sink.add(message);
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
      if (_eventController.isClosed) return;
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
    _isConnecting = false;
    _lastError = '连接错误: $error';
    _connectionStateController.add(false);
    notifyListeners();
    _scheduleReconnect();
  }

  /// 处理断开连接
  void _handleDisconnect() {
    debugPrint('WebSocket disconnected');
    _isConnected = false;
    _isConnecting = false;
    _lastError = '与服务器的连接已断开';
    _connectionStateController.add(false);
    notifyListeners();
    _scheduleReconnect();
  }

  @override
  void dispose() {
    _isDisposed = true;
    _reconnectTimer?.cancel();
    disconnect();
    if (!_eventController.isClosed) {
      _eventController.close();
    }
    if (!_connectionStateController.isClosed) {
      _connectionStateController.close();
    }
    super.dispose();
  }
}