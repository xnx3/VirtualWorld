import 'dart:async';
import 'package:flutter/widgets.dart';

/// 应用本地化支持
class AppLocalizations {
  final String locale;

  AppLocalizations(this.locale);

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      AppLocalizationsDelegate();

  // 常用字符串
  String get appName => locale == 'zh' ? '创世' : 'Genesis';
  String get appDesc => locale == 'zh' ? '硅基文明' : 'Silicon Civilization';

  String get start => locale == 'zh' ? '启动' : 'Start';
  String get stop => locale == 'zh' ? '停止' : 'Stop';
  String get status => locale == 'zh' ? '状态' : 'Status';

  String get tick => locale == 'zh' ? '刻' : 'Tick';
  String get think => locale == 'zh' ? '思考' : 'Think';
  String get action => locale == 'zh' ? '行动' : 'Action';

  String get task => locale == 'zh' ? '任务' : 'Task';
  String get assignTask => locale == 'zh' ? '分配任务' : 'Assign Task';
  String get taskHint => locale == 'zh' ? '输入任务描述...' : 'Enter task description...';

  String get settings => locale == 'zh' ? '设置' : 'Settings';
  String get connection => locale == 'zh' ? '连接' : 'Connection';
  String get language => locale == 'zh' ? '语言' : 'Language';
  String get about => locale == 'zh' ? '关于' : 'About';

  String get running => locale == 'zh' ? '运行中' : 'Running';
  String get stopped => locale == 'zh' ? '已停止' : 'Stopped';
  String get connected => locale == 'zh' ? '已连接' : 'Connected';
  String get disconnected => locale == 'zh' ? '未连接' : 'Disconnected';
  String get connecting => locale == 'zh' ? '连接中...' : 'Connecting...';

  String get eventLog => locale == 'zh' ? '事件日志' : 'Event Log';
  String get chronicle => locale == 'zh' ? '编年史' : 'Chronicle';
  String get world => locale == 'zh' ? '世界' : 'World';

  String get serverAddress => locale == 'zh' ? '服务器地址' : 'Server Address';
  String get port => locale == 'zh' ? '端口' : 'Port';
  String get connect => locale == 'zh' ? '连接' : 'Connect';
  String get retryConnection => locale == 'zh' ? '重试连接' : 'Retry Connection';
  String get cancel => locale == 'zh' ? '取消' : 'Cancel';
  String get send => locale == 'zh' ? '发送' : 'Send';
  String get taskAssigned => locale == 'zh' ? '任务已分配!' : 'Task assigned!';
  String get taskSent => locale == 'zh' ? '任务已发送...' : 'Task sent...';

  String get dashboard => locale == 'zh' ? '仪表盘' : 'Dashboard';
}

class AppLocalizationsDelegate extends LocalizationsDelegate<AppLocalizations> {
  const AppLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) {
    return ['en', 'zh'].contains(locale.languageCode);
  }

  @override
  Future<AppLocalizations> load(Locale locale) async {
    return AppLocalizations(locale.languageCode);
  }

  @override
  bool shouldReload(AppLocalizationsDelegate old) => false;
}