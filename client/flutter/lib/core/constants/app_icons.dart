/// 应用图标
class AppIcons {
  // 核心图标 (使用 emoji 或 Material Icons)
  static const String tick = '⏱️';
  static const String think = '💭';
  static const String speak = '💬';
  static const String teach = '📖';
  static const String learn = '📚';
  static const String create = '✨';
  static const String explore = '🔍';
  static const String compete = '⚔️';
  static const String meditate = '🧘';
  static const String buildShelter = '🏠';
  static const String move = '🚶';
  static const String perceive = '👁️';
  static const String deepThink = '🌀';

  // 事件图标
  static const String disaster = '⚡';
  static const String death = '💀';
  static const String birth = '🌟';
  static const String treasure = '💎';
  static const String spirit = '🔮';
  static const String priest = '⛩️';
  static const String vote = '🗳️';
  static const String hibernate = '😴';
  static const String wake = '☀️';
  static const String task = '📋';
  static const String knowledge = '🧠';
  static const String world = '🌍';
  static const String error = '❌';

  // 状态图标
  static const String running = '▶️';
  static const String stopped = '⏹️';
  static const String warning = '⚠️';
  static const String success = '✅';

  // 行动图标映射
  static String getActionIcon(String actionType) {
    switch (actionType) {
      case 'speak': return speak;
      case 'teach': return teach;
      case 'learn': return learn;
      case 'create': return create;
      case 'explore': return explore;
      case 'compete': return compete;
      case 'meditate': return meditate;
      case 'build_shelter': return buildShelter;
      case 'move': return move;
      case 'deep_think': return deepThink;
      default: return '▶';
    }
  }
}