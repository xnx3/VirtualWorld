import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'services/app_state.dart';
import 'services/websocket_service.dart';
import 'screens/home_screen.dart';
import 'screens/settings_screen.dart';
import 'core/theme/app_theme.dart';
import 'l10n/app_localizations.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 加载保存的设置
  final prefs = await SharedPreferences.getInstance();
  final savedLanguage = prefs.getString('language') ?? 'zh';
  final savedHost = prefs.getString('server_host') ?? WebSocketService.defaultHost;
  final savedPort = prefs.getInt('server_port') ?? WebSocketService.defaultPort;

  runApp(GenesisApp(
    initialLanguage: savedLanguage,
    initialHost: savedHost,
    initialPort: savedPort,
  ));
}

class GenesisApp extends StatelessWidget {
  final String initialLanguage;
  final String initialHost;
  final int initialPort;

  const GenesisApp({
    super.key,
    required this.initialLanguage,
    required this.initialHost,
    required this.initialPort,
  });

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => AppState()..setLanguage(initialLanguage),
        ),
        ChangeNotifierProvider(
          create: (_) => WebSocketService(host: initialHost, port: initialPort),
        ),
      ],
      child: Consumer<AppState>(
        builder: (context, appState, _) {
          return MaterialApp(
            title: 'Genesis',
            debugShowCheckedModeBanner: false,

            // 主题
            theme: AppTheme.darkTheme,
            darkTheme: AppTheme.darkTheme,
            themeMode: ThemeMode.dark,

            // 国际化
            locale: Locale(appState.language, ''),
            localizationsDelegates: const [
              AppLocalizationsDelegate(),
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: const [
              Locale('en', ''),
              Locale('zh', ''),
            ],

            // 路由
            home: const HomeScreen(),
            routes: {
              '/settings': (context) => const SettingsScreen(),
            },
          );
        },
      ),
    );
  }
}