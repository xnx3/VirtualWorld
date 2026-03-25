import 'package:flutter/foundation.dart';

/// 应用全局状态
class AppState with ChangeNotifier {
  // 运行状态
  bool _isRunning = false;
  bool get isRunning => _isRunning;

  // 当前 Tick
  int _currentTick = 0;
  int get currentTick => _currentTick;

  // 生命体信息
  String _beingName = '';
  String get beingName => _beingName;

  String _beingPhase = '';
  String get beingPhase => _beingPhase;

  // 精神力
  double _spiritCurrent = 1000;
  double _spiritMaximum = 1000;
  double get spiritCurrent => _spiritCurrent;
  double get spiritMaximum => _spiritMaximum;
  double get spiritPercentage {
    if (_spiritMaximum <= 0) return 0;
    final pct = _spiritCurrent / _spiritMaximum;
    return pct.clamp(0.0, 1.0);
  }

  // 事件日志
  final List<ChronicleEvent> _events = [];
  List<ChronicleEvent> get events => List.unmodifiable(_events);

  // 当前思考
  String _currentThought = '';
  String get currentThought => _currentThought;

  // 当前行动
  String _currentAction = '';
  String _currentActionDetails = '';
  String get currentAction => _currentAction;
  String get currentActionDetails => _currentActionDetails;

  // 语言设置
  String _language = 'zh';
  String get language => _language;

  // 任务响应回调
  Function(bool success, String message)? onTaskResponse;

  /// 更新运行状态
  void setRunning(bool running) {
    _isRunning = running;
    notifyListeners();
  }

  /// 更新 Tick
  void updateTick(int tick, String name, String spirit, String phase) {
    _currentTick = tick;
    _beingName = name.isEmpty ? 'Unknown' : name;
    _beingPhase = phase.isEmpty ? 'Unknown' : phase;
    notifyListeners();
  }

  /// 更新精神力
  void updateSpirit(double current, double maximum, {double cost = 0, double recovered = 0}) {
    _spiritCurrent = current.clamp(0.0, double.infinity);
    _spiritMaximum = maximum > 0 ? maximum : 1000;
    notifyListeners();
  }

  /// 更新思考
  void updateThought(String thought) {
    _currentThought = thought;
    notifyListeners();
  }

  /// 更新行动
  void updateAction(String action, String details) {
    _currentAction = action;
    _currentActionDetails = details;
    notifyListeners();
  }

  /// 添加事件
  void addEvent(ChronicleEvent event) {
    _events.insert(0, event);
    // 保持最近500条
    if (_events.length > 500) {
      _events.removeRange(500, _events.length);
    }
    notifyListeners();
  }

  /// 清空事件
  void clearEvents() {
    _events.clear();
    notifyListeners();
  }

  /// 设置语言
  void setLanguage(String lang) {
    _language = lang;
    notifyListeners();
  }

  /// 处理来自后端的事件
  void handleServerEvent(Map<String, dynamic> data) {
    final type = data['type'] as String?;
    final payload = data['data'] as Map<String, dynamic>? ?? {};

    switch (type) {
      case 'tick':
        updateTick(
          payload['tick'] as int? ?? 0,
          payload['being_name'] as String? ?? '',
          payload['spirit'] as String? ?? '',
          payload['phase'] as String? ?? '',
        );
        break;

      case 'think':
        final thought = payload['thought'] as String? ?? '';
        if (thought.isNotEmpty) {
          updateThought(thought);
          addEvent(ChronicleEvent(
            type: EventType.think,
            content: thought,
            timestamp: DateTime.now(),
          ));
        }
        break;

      case 'action':
        final actionType = payload['action_type'] as String? ?? '';
        final details = payload['details'] as String? ?? '';
        final target = payload['target'] as String? ?? '';
        if (actionType.isNotEmpty) {
          updateAction(actionType, details);
          final fullContent = target.isNotEmpty
            ? '$actionType -> $target: $details'
            : '$actionType: $details';
          addEvent(ChronicleEvent(
            type: EventType.action,
            content: fullContent,
            timestamp: DateTime.now(),
            metadata: payload,
          ));
        }
        break;

      case 'spirit':
        updateSpirit(
          (payload['current'] as num?)?.toDouble() ?? 0,
          (payload['maximum'] as num?)?.toDouble() ?? 1000,
          cost: (payload['cost'] as num?)?.toDouble() ?? 0,
          recovered: (payload['recovered'] as num?)?.toDouble() ?? 0,
        );
        break;

      case 'disaster':
        final name = payload['name'] as String? ?? 'Unknown';
        final severity = payload['severity'] as num? ?? 0;
        final area = payload['area'] as String? ?? '';
        addEvent(ChronicleEvent(
          type: EventType.disaster,
          content: area.isNotEmpty ? '$name ($area): severity $severity' : '$name: severity $severity',
          timestamp: DateTime.now(),
          metadata: payload,
        ));
        break;

      case 'priest':
        final eventType = payload['event_type'] as String? ?? '';
        final name = payload['name'] as String? ?? '';
        addEvent(ChronicleEvent(
          type: EventType.priest,
          content: '$eventType: $name',
          timestamp: DateTime.now(),
          metadata: payload,
        ));
        break;

      case 'status':
        // 状态更新
        final statusData = data['data'] as Map<String, dynamic>? ?? {};
        if (statusData.isNotEmpty) {
          updateTick(
            statusData['tick'] as int? ?? _currentTick,
            statusData['being_name'] as String? ?? _beingName,
            '',
            statusData['phase'] as String? ?? _beingPhase,
          );
          if (statusData['spirit_current'] != null && statusData['spirit_max'] != null) {
            updateSpirit(
              (statusData['spirit_current'] as num?)?.toDouble() ?? _spiritCurrent,
              (statusData['spirit_max'] as num?)?.toDouble() ?? _spiritMaximum,
            );
          }
          // Sync running state from server
          if (statusData['is_running'] == true) {
            setRunning(true);
          } else if (statusData['is_running'] == false) {
            setRunning(false);
          }
        }
        break;

      case 'task_response':
        // 任务响应
        final success = data['success'] as bool? ?? false;
        final message = data['message'] as String? ?? '';
        addEvent(ChronicleEvent(
          type: EventType.task,
          content: success ? '✓ $message' : '✗ $message',
          timestamp: DateTime.now(),
          metadata: {'success': success},
        ));
        // 调用回调
        if (onTaskResponse != null) {
          onTaskResponse!(success, message);
        }
        break;

      case 'pong':
        // 心跳响应，不需要处理
        break;

      case 'console_output':
        // 原始终端输出，可用于调试
        final text = payload['text'] as String? ?? '';
        if (text.isNotEmpty) {
          debugPrint('Console: $text');
        }
        break;

      default:
        debugPrint('Unknown event type: $type');
    }
  }
}

/// 事件类型
enum EventType {
  tick,
  think,
  action,
  spirit,
  disaster,
  priest,
  birth,
  death,
  knowledge,
  task,
}

/// 事件记录
class ChronicleEvent {
  final EventType type;
  final String content;
  final DateTime timestamp;
  final Map<String, dynamic>? metadata;

  ChronicleEvent({
    required this.type,
    required this.content,
    required this.timestamp,
    this.metadata,
  });
}