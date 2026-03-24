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
  double get spiritPercentage => _spiritMaximum > 0 ? _spiritCurrent / _spiritMaximum : 0;

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

  /// 更新运行状态
  void setRunning(bool running) {
    _isRunning = running;
    notifyListeners();
  }

  /// 更新 Tick
  void updateTick(int tick, String name, String spirit, String phase) {
    _currentTick = tick;
    _beingName = name;
    _beingPhase = phase;
    notifyListeners();
  }

  /// 更新精神力
  void updateSpirit(double current, double maximum, {double cost = 0, double recovered = 0}) {
    _spiritCurrent = current;
    _spiritMaximum = maximum;
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
        updateThought(thought);
        addEvent(ChronicleEvent(
          type: EventType.think,
          content: thought,
          timestamp: DateTime.now(),
        ));
        break;

      case 'action':
        final actionType = payload['action_type'] as String? ?? '';
        final details = payload['details'] as String? ?? '';
        updateAction(actionType, details);
        addEvent(ChronicleEvent(
          type: EventType.action,
          content: '$actionType: $details',
          timestamp: DateTime.now(),
          metadata: payload,
        ));
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
        addEvent(ChronicleEvent(
          type: EventType.disaster,
          content: '${payload['name']}: severity ${payload['severity']}',
          timestamp: DateTime.now(),
          metadata: payload,
        ));
        break;

      case 'priest':
        addEvent(ChronicleEvent(
          type: EventType.priest,
          content: '${payload['event_type']}: ${payload['name']}',
          timestamp: DateTime.now(),
          metadata: payload,
        ));
        break;

      case 'console_output':
        // 原始终端输出，可用于调试
        debugPrint('Console: ${payload['text']}');
        break;
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