import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'services/app_state.dart';
import 'services/websocket_service.dart';
import 'screens/home_screen.dart';
import 'screens/settings_screen.dart';
import 'core/theme/app_theme.dart';
import 'l10n/app_localizations.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const GenesisApp());
}

class GenesisApp extends StatelessWidget {
  const GenesisApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppState()),
        Provider(create: (_) => WebSocketService()),
      ],
      child: MaterialApp(
        title: 'Genesis',
        debugShowCheckedModeBanner: false,

        // 主题
        theme: AppTheme.darkTheme,
        darkTheme: AppTheme.darkTheme,
        themeMode: ThemeMode.dark,

        // 国际化
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
      ),
    );
  }
}