import 'dart:async';

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

  String get start => locale == 'zh' ? '启动' : 'Start';
  String get stop => locale == 'zh' ? '停止' : 'Stop';
  String get status => locale == 'zh' ? '状态' : 'Status';

  String get tick => locale == 'zh' ? '刻' : 'Tick';
  String get think => locale == 'zh' ? '思考' : 'Think';
  String get action => locale == 'zh' ? '行动' : 'Action';
  String get spirit => locale == 'zh' ? '精神力' : 'Spirit';

  String get task => locale == 'zh' ? '任务' : 'Task';
  String get assignTask => locale == 'zh' ? '分配任务' : 'Assign Task';
  String get taskHint => locale == 'zh' ? '输入任务描述...' : 'Enter task description...';

  String get settings => locale == 'zh' ? '设置' : 'Settings';
  String get connection => locale == 'zh' ? '连接' : 'Connection';
  String get language => locale == 'zh' ? '语言' : 'Language';

  String get running => locale == 'zh' ? '运行中' : 'Running';
  String get stopped => locale == 'zh' ? '已停止' : 'Stopped';
  String get connected => locale == 'zh' ? '已连接' : 'Connected';
  String get disconnected => locale == 'zh' ? '未连接' : 'Disconnected';

  String get eventLog => locale == 'zh' ? '事件日志' : 'Event Log';
  String get chronicle => locale == 'zh' ? '编年史' : 'Chronicle';
  String get world => locale == 'zh' ? '世界' : 'World';
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

// 需要导入 BuildContext
import 'package:flutter/widgets.dart';