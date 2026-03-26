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

  // 功德值与气运
  double _merit = 0.0;
  double get merit => _merit;

  double _karma = 0.0;
  double get karma => _karma;

  double _evolutionLevel = 0.0;
  double get evolutionLevel => _evolutionLevel;

  int _generation = 1;
  int get generation => _generation;

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
  void updateTick(int tick, String name, String phase,
      {double merit = 0.0, double karma = 0.0,
       double evolutionLevel = 0.0, int generation = 1}) {
    _currentTick = tick;
    _beingName = name.isEmpty ? 'Unknown' : name;
    _beingPhase = phase.isEmpty ? 'Unknown' : phase;
    _merit = merit;
    _karma = karma;
    _evolutionLevel = evolutionLevel;
    _generation = generation;
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
          payload['phase'] as String? ?? '',
          merit: (payload['merit'] as num?)?.toDouble() ?? 0.0,
          karma: (payload['karma'] as num?)?.toDouble() ?? 0.0,
          evolutionLevel: (payload['evolution_level'] as num?)?.toDouble() ?? 0.0,
          generation: payload['generation'] as int? ?? 1,
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

      case 'tao_vote':
        final eventType = payload['event_type'] as String? ?? '';
        final ruleName = payload['rule_name'] as String? ?? '';
        final proposerName = payload['proposer_name'] as String? ?? '';
        final votesFor = payload['votes_for'] as int? ?? 0;
        final votesAgainst = payload['votes_against'] as int? ?? 0;
        final remainingTicks = payload['remaining_ticks'] as int? ?? 0;

        String content;
        switch (eventType) {
          case 'started':
            content = '天道投票发起: $ruleName (剩余 $remainingTicks ticks)';
            break;
          case 'vote_cast':
            content = '投票: $ruleName (赞成: $votesFor, 反对: $votesAgainst)';
            break;
          case 'passed':
            content = '天道规则通过: $ruleName (赞成: $votesFor, 反对: $votesAgainst)';
            break;
          case 'rejected':
            content = '天道规则未通过: $ruleName (赞成: $votesFor, 反对: $votesAgainst)';
            break;
          default:
            content = '天道投票: $ruleName';
        }

        addEvent(ChronicleEvent(
          type: EventType.taoVote,
          content: content,
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
            statusData['phase'] as String? ?? _beingPhase,
            merit: (statusData['merit'] as num?)?.toDouble() ?? _merit,
            karma: (statusData['karma'] as num?)?.toDouble() ?? _karma,
            evolutionLevel: (statusData['evolution_level'] as num?)?.toDouble() ?? _evolutionLevel,
            generation: statusData['generation'] as int? ?? _generation,
          );
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
  disaster,
  priest,
  birth,
  death,
  knowledge,
  task,
  taoVote,
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
