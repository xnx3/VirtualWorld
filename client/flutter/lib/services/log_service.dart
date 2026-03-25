import 'dart:async';
import 'package:flutter/foundation.dart';

/// 日志级别
enum LogLevel {
  debug,
  info,
  warning,
  error,
}

/// 日志条目
class LogEntry {
  final DateTime timestamp;
  final LogLevel level;
  final String source; // 'flutter' 或 'backend'
  final String message;
  final Map<String, dynamic>? metadata;

  LogEntry({
    required this.timestamp,
    required this.level,
    required this.source,
    required this.message,
    this.metadata,
  });

  String get levelStr {
    switch (level) {
      case LogLevel.debug:
        return 'DEBUG';
      case LogLevel.info:
        return 'INFO';
      case LogLevel.warning:
        return 'WARN';
      case LogLevel.error:
        return 'ERROR';
    }
  }

  String get formattedTimestamp {
    return '${timestamp.hour.toString().padLeft(2, '0')}:'
           '${timestamp.minute.toString().padLeft(2, '0')}:'
           '${timestamp.second.toString().padLeft(2, '0')}';
  }

  @override
  String toString() {
    return '[$formattedTimestamp] [$levelStr] [$source] $message';
  }
}

/// 日志服务 - 全局日志管理
class LogService with ChangeNotifier {
  static const int _maxEntries = 1000;

  final List<LogEntry> _entries = [];
  final _entryController = StreamController<LogEntry>.broadcast();

  Stream<LogEntry> get entries => _entryController.stream;
  List<LogEntry> get allEntries => List.unmodifiable(_entries);
  int get entryCount => _entries.length;

  /// 添加日志
  void log(
    LogLevel level,
    String message, {
    String source = 'flutter',
    Map<String, dynamic>? metadata,
  }) {
    final entry = LogEntry(
      timestamp: DateTime.now(),
      level: level,
      source: source,
      message: message,
      metadata: metadata,
    );

    _entries.add(entry);
    if (_entries.length > _maxEntries) {
      _entries.removeAt(0);
    }

    _entryController.add(entry);
    notifyListeners();

    // 同时输出到控制台
    debugPrint('[${entry.levelStr}] [$source] $message');
  }

  /// 便捷方法
  void debug(String message, {String source = 'flutter'}) {
    log(LogLevel.debug, message, source: source);
  }

  void info(String message, {String source = 'flutter'}) {
    log(LogLevel.info, message, source: source);
  }

  void warning(String message, {String source = 'flutter'}) {
    log(LogLevel.warning, message, source: source);
  }

  void error(String message, {String source = 'flutter', Object? error, StackTrace? stackTrace}) {
    log(
      LogLevel.error,
      message,
      source: source,
      metadata: {
        if (error != null) 'error': error.toString(),
        if (stackTrace != null) 'stackTrace': stackTrace.toString(),
      },
    );
  }

  /// 后端日志
  void backendLog(LogLevel level, String message) {
    log(level, message, source: 'backend');
  }

  /// 按级别筛选
  List<LogEntry> filterByLevel(LogLevel level) {
    return _entries.where((e) => e.level == level).toList();
  }

  /// 按来源筛选
  List<LogEntry> filterBySource(String source) {
    return _entries.where((e) => e.source == source).toList();
  }

  /// 搜索
  List<LogEntry> search(String keyword) {
    final lowerKeyword = keyword.toLowerCase();
    return _entries.where((e) => e.message.toLowerCase().contains(lowerKeyword)).toList();
  }

  /// 清空日志
  void clear() {
    _entries.clear();
    notifyListeners();
  }

  /// 导出为文本
  String export() {
    return _entries.map((e) => e.toString()).join('\n');
  }

  @override
  void dispose() {
    _entryController.close();
    super.dispose();
  }
}
