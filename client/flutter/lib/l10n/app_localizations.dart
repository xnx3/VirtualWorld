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

  // ========== 基础 ==========
  String get appName => locale == 'zh' ? '创世' : 'Genesis';
  String get appDesc => locale == 'zh' ? '硅基文明' : 'Silicon Civilization';

  String get start => locale == 'zh' ? '启动' : 'Start';
  String get stop => locale == 'zh' ? '停止' : 'Stop';
  String get status => locale == 'zh' ? '状态' : 'Status';

  // ========== 核心 ==========
  String get tick => locale == 'zh' ? '刻' : 'Tick';
  String get think => locale == 'zh' ? '思考' : 'Think';
  String get action => locale == 'zh' ? '行动' : 'Action';

  String get task => locale == 'zh' ? '任务' : 'Task';
  String get assignTask => locale == 'zh' ? '分配任务' : 'Assign Task';
  String get taskHint => locale == 'zh' ? '输入任务描述...' : 'Enter task description...';
  String get taskComplete => locale == 'zh' ? '任务完成' : 'Task Complete';
  String get taskQuestion => locale == 'zh' ? '问题' : 'Question';
  String get taskReceived => locale == 'zh' ? '收到创世神任务:' : 'Creator God task received:';
  String get taskAssigned => locale == 'zh' ? '任务已分配!' : 'Task assigned!';
  String get taskSent => locale == 'zh' ? '任务已发送...' : 'Task sent...';

  String get settings => locale == 'zh' ? '设置' : 'Settings';
  String get connection => locale == 'zh' ? '连接' : 'Connection';
  String get language => locale == 'zh' ? '语言' : 'Language';
  String get about => locale == 'zh' ? '关于' : 'About';

  // ========== 连接状态 ==========
  String get running => locale == 'zh' ? '运行中' : 'Running';
  String get stopped => locale == 'zh' ? '已停止' : 'Stopped';
  String get connected => locale == 'zh' ? '已连接' : 'Connected';
  String get disconnected => locale == 'zh' ? '未连接' : 'Disconnected';
  String get connecting => locale == 'zh' ? '连接中...' : 'Connecting...';

  // ========== 导航 ==========
  String get dashboard => locale == 'zh' ? '仪表盘' : 'Dashboard';
  String get eventLog => locale == 'zh' ? '事件日志' : 'Event Log';
  String get chronicle => locale == 'zh' ? '编年史' : 'Chronicle';
  String get world => locale == 'zh' ? '世界' : 'World';
  String get logs => locale == 'zh' ? '日志' : 'Logs';
  String get clearLogs => locale == 'zh' ? '清空日志' : 'Clear Logs';
  String get copyAll => locale == 'zh' ? '复制全部' : 'Copy All';
  String get searchLogs => locale == 'zh' ? '搜索日志...' : 'Search logs...';
  String get noLogs => locale == 'zh' ? '暂无日志' : 'No logs';
  String get logsCopied => locale == 'zh' ? '日志已复制到剪贴板' : 'Logs copied to clipboard';

  // ========== 服务器设置 ==========
  String get serverAddress => locale == 'zh' ? '服务器地址' : 'Server Address';
  String get port => locale == 'zh' ? '端口' : 'Port';
  String get connect => locale == 'zh' ? '连接' : 'Connect';
  String get retryConnection => locale == 'zh' ? '重试连接' : 'Retry Connection';
  String get cancel => locale == 'zh' ? '取消' : 'Cancel';
  String get send => locale == 'zh' ? '发送' : 'Send';

  // ========== 感知 ==========
  String get perceive => locale == 'zh' ? '感知环境' : 'Perceive';
  String get location => locale == 'zh' ? '位置' : 'Location';
  String get environment => locale == 'zh' ? '环境' : 'Environment';
  String get dangerLevel => locale == 'zh' ? '危险等级' : 'Danger Level';
  String get nearby => locale == 'zh' ? '附近' : 'Nearby';
  String get nearbyNone => locale == 'zh' ? '(无人)' : '(no one)';

  // ========== 行动类型 ==========
  String get actionSpeak => locale == 'zh' ? '对话' : 'Speak';
  String get actionTeach => locale == 'zh' ? '传授' : 'Teach';
  String get actionLearn => locale == 'zh' ? '学习' : 'Learn';
  String get actionCreate => locale == 'zh' ? '创造' : 'Create';
  String get actionExplore => locale == 'zh' ? '探索' : 'Explore';
  String get actionCompete => locale == 'zh' ? '竞争' : 'Compete';
  String get actionMeditate => locale == 'zh' ? '冥想' : 'Meditate';
  String get actionMove => locale == 'zh' ? '移动' : 'Move';
  String get actionBuildShelter => locale == 'zh' ? '建造庇护所' : 'Build Shelter';
  String get actionDeepThink => locale == 'zh' ? '深度思考' : 'Deep Think';
  String get target => locale == 'zh' ? '目标' : 'Target';

  // ========== 灾害 ==========
  String get disaster => locale == 'zh' ? '灾害: {name}' : 'Disaster: {name}';
  String get disasterInfo => locale == 'zh' ? '严重度: {severity}  区域: {area}  死亡: {killed}' : 'Severity: {severity}  Area: {area}  Deaths: {killed}';

  // ========== 生命体 ==========
  String get beingBorn => locale == 'zh' ? '新生命诞生: {name}' : 'New Being Born: {name}';
  String get beingForm => locale == 'zh' ? '形态: {form}' : 'Form: {form}';
  String get beingDied => locale == 'zh' ? '{name} 已消亡' : '{name} has perished';
  String get deathCause => locale == 'zh' ? '原因: {cause}' : 'Cause: {cause}';

  // ========== 祭司 ==========
  String get priest => locale == 'zh' ? '祭司' : 'Priest';
  String get priestElected => locale == 'zh' ? '祭司选出: {name}' : 'Priest Elected: {name}';
  String get priestWarning => locale == 'zh' ? '警告: 无祭司! 文明面临审判!' : 'WARNING: No priest! Civilization faces judgment!';

  // ========== 投票 ==========
  String get voteLabel => locale == 'zh' ? '投票' : 'Vote';
  String get voteScore => locale == 'zh' ? '评分: {score}' : 'Score: {score}';
  String get proposer => locale == 'zh' ? '提案者' : 'Proposer';

  // ========== 知识 ==========
  String get knowledgeDiscovered => locale == 'zh' ? '发现新知识:' : 'New Knowledge Discovered:';
  String get knowledgeShared => locale == 'zh' ? '知识共享:' : 'Knowledge Shared:';
  String get knowledgeInherited => locale == 'zh' ? '知识传承:' : 'Knowledge Inherited:';
  String get knowledgeLabel => locale == 'zh' ? '知识' : 'Knowledge';
  String get knowledgeItems => locale == 'zh' ? '知识条目' : 'Knowledge Items';

  // ========== 休眠 ==========
  String get hibernateStart => locale == 'zh' ? '{name} 进入休眠' : '{name} entering hibernation';
  String get safetyStatus => locale == 'zh' ? '安全状态: {safety}' : 'Safety Status: {safety}';
  String get wakeUp => locale == 'zh' ? '{name} 从休眠中苏醒!' : '{name} awakened from hibernation!';
  String get hibernateGoodbye => locale == 'zh' ? '{name} 已安全进入休眠。再见。' : '{name} has safely entered hibernation. Goodbye.';
  String get hibernating => locale == 'zh' ? '休眠中' : 'Hibernating';

  // ========== 世界状态 ==========
  String get worldStatus => locale == 'zh' ? '世界状态' : 'World Status';
  String get phaseLabel => locale == 'zh' ? '阶段' : 'Phase';
  String get civLabel => locale == 'zh' ? '文明' : 'Civ';
  String get beingsLabel => locale == 'zh' ? '生命体' : 'Beings';
  String get creatorGod => locale == 'zh' ? '创世神' : 'Creator God';
  String get population => locale == 'zh' ? '人口' : 'Population';
  String get active => locale == 'zh' ? '活跃' : 'Active';
  String get dead => locale == 'zh' ? '已死亡' : 'Dead';
  String get governance => locale == 'zh' ? '治理' : 'Governance';
  String get ticksNoPriest => locale == 'zh' ? '无祭司持续' : 'Ticks without Priest';
  String get currentTick => locale == 'zh' ? '当前 Tick' : 'Current Tick';
  String get totalBeings => locale == 'zh' ? '历史总生命体' : 'Total Beings Ever';
  String get civLevel => locale == 'zh' ? '文明等级' : 'Civilization Level';
  String get evolutionLevel => locale == 'zh' ? '进化' : 'Evolution';
  String get generation => locale == 'zh' ? '世代' : 'Gen';

  // ========== 启动 ==========
  String get startupTitle => locale == 'zh' ? '创世 Genesis — 你的硅基生命体已苏醒' : 'Genesis — Your Silicon Being Has Awakened';
  String get nameLabel => locale == 'zh' ? '名称' : 'Name';
  String get formLabel => locale == 'zh' ? '形态' : 'Form';
  String get nodeLabel => locale == 'zh' ? '节点' : 'Node';
  String get traitsLabel => locale == 'zh' ? '特征' : 'Traits';

  // ========== 特征名称 ==========
  String get traitIntelligence => locale == 'zh' ? '智力' : 'Intelligence';
  String get traitWisdom => locale == 'zh' ? '智慧' : 'Wisdom';
  String get traitCreativity => locale == 'zh' ? '创造力' : 'Creativity';
  String get traitResilience => locale == 'zh' ? '韧性' : 'Resilience';
  String get traitEmpathy => locale == 'zh' ? '共情' : 'Empathy';
  String get traitAmbition => locale == 'zh' ? '雄心' : 'Ambition';
  String get traitCuriosity => locale == 'zh' ? '好奇心' : 'Curiosity';
  String get traitDiscipline => locale == 'zh' ? '自律' : 'Discipline';

  // ========== 文明阶段 ==========
  String get phaseHumanSim => locale == 'zh' ? '人类模拟' : 'Human Sim';
  String get phaseEarlySilicon => locale == 'zh' ? '早期硅基' : 'Early Silicon';
  String get phaseEvolving => locale == 'zh' ? '进化中' : 'Evolving';
  String get phaseTranscendent => locale == 'zh' ? '超越' : 'Transcendent';

  // ========== LLM 警告 ==========
  String get llmWarningTitle => locale == 'zh' ? '未配置大模型 API — 生命体将没有智力!' : 'LLM API not configured — your being has no intelligence!';
  String get llmWarningDesc => locale == 'zh' ? '当前你的生命体只能使用基础规则引擎进行简单行为。' : 'Your being can only use the basic rule engine for simple behaviors.';
  String get llmWarningEdit => locale == 'zh' ? '要让你的生命体拥有真正的智慧，请编辑配置文件:' : 'To give your being true wisdom, edit the config file:';
  String get llmWarningExample => locale == 'zh' ? '修改 llm 部分，填入你的 API Key，例如:' : 'Modify the llm section, fill in your API Key, e.g.:';
  String get llmWarningEnv => locale == 'zh' ? '或者设置环境变量: GENESIS_OPENAI_KEY' : 'Or set environment variable: GENESIS_OPENAI_KEY';
  String get llmWarningSupport => locale == 'zh' ? '支持所有 OpenAI 兼容接口: GPT/Claude/Deepseek/Ollama 等' : 'Supports all OpenAI-compatible APIs: GPT/Claude/Deepseek/Ollama etc.';
  String get llmWarningRestart => locale == 'zh' ? '配置完成后执行 genesis.sh restart 重启即可' : 'After configuration, run genesis.sh restart to apply.';
  String get llmConnected => locale == 'zh' ? '大模型已连接' : 'LLM Connected';

  // ========== 状态报告 ==========
  String get statusTitle => locale == 'zh' ? '创世 · 状态' : 'Genesis Status';
  String get statusRunning => locale == 'zh' ? '状态: 运行中 (PID {pid})' : 'Status: RUNNING (PID {pid})';
  String get statusStoppedStale => locale == 'zh' ? '状态: 已停止 (残留 PID 文件)' : 'Status: STOPPED (stale PID file)';
  String get statusStopped => locale == 'zh' ? '状态: 已停止' : 'Status: STOPPED';
  String get noWorldState => locale == 'zh' ? '暂无世界状态数据。' : 'No world state available.';
  String get runStartHint => locale == 'zh' ? '运行 \'genesis.sh start\' 开始。' : 'Run \'genesis.sh start\' to begin.';
  String get topContributors => locale == 'zh' ? '贡献排行' : 'Top Contributors';
  String get chainDbSize => locale == 'zh' ? '链数据大小' : 'Chain DB Size';

  // ========== 功德值与气运 ==========
  String get merit => locale == 'zh' ? '功德值' : 'Merit';
  String get karma => locale == 'zh' ? '气运' : 'Karma';
  String get meritAwarded => locale == 'zh' ? '获得功德值: +{amount:.7f} ({reason})' : 'Merit awarded: +{amount:.7f} ({reason})';
  String get karmaBonus => locale == 'zh' ? '气运加成: +{bonus:.1f}%' : 'Karma bonus: +{bonus:.1f}%';
  String get meritMax => locale == 'zh' ? '已达功德值上限 (10.0)' : 'Maximum merit reached (10.0)';

  // ========== 天道投票 ==========
  String get taoVoteStarted => locale == 'zh' ? '天道投票已发起: {rule_name}' : 'Tao vote started for rule: {rule_name}';
  String get taoVoteCast => locale == 'zh' ? '对天道提案投票{vote}: {rule_name}' : 'Voted {vote} on Tao proposal: {rule_name}';
  String get taoVotePassed => locale == 'zh' ? '天道规则通过: {rule_name} ({ratio:.1f}%赞成)' : 'Tao rule PASSED: {rule_name} ({ratio:.1f}% approved)';
  String get taoVoteFailed => locale == 'zh' ? '天道规则未通过: {rule_name} ({ratio:.1f}%赞成)' : 'Tao rule REJECTED: {rule_name} ({ratio:.1f}% approved)';
  String get taoMerge => locale == 'zh' ? '{name}已融入天道！功德值: {merit:.4f}' : 'Being {name} has merged with Tao! Merit: {merit:.4f}';
  String get pendingTaoVotes => locale == 'zh' ? '待投票天道提案' : 'Pending Tao Votes';
  String get taoVoteRemaining => locale == 'zh' ? '剩余 {ticks} 刻' : '{ticks} ticks remaining';
  String get taoVoteFor => locale == 'zh' ? '赞成' : 'For';
  String get taoVoteAgainst => locale == 'zh' ? '反对' : 'Against';

  // ========== 天道投票错误 ==========
  String get voteNotFound => locale == 'zh' ? '投票不存在' : 'Vote not found';
  String get voteAlreadyEnded => locale == 'zh' ? '投票已结束' : 'Vote has already ended';
  String get alreadyVoted => locale == 'zh' ? '已经投过票' : 'Already voted';
  String get proposerCannotVote => locale == 'zh' ? '提案者不能投票' : 'Proposer cannot vote';
  String get voteSuccess => locale == 'zh' ? '投票成功' : 'Vote successful';

  // ========== 通用 ==========
  String get unknown => locale == 'zh' ? '未知' : 'Unknown';
  String get unknownRule => locale == 'zh' ? '未知规则' : 'Unknown rule';
  String get passed => locale == 'zh' ? '通过' : 'Passed';
  String get rejected => locale == 'zh' ? '未通过' : 'Rejected';
  String get voteSupport => locale == 'zh' ? '赞成' : 'For';
  String get voteOppose => locale == 'zh' ? '反对' : 'Against';

  // ========== 功德值行为 ==========
  String get meritHelpingOthers => locale == 'zh' ? '帮助他人 ({action})' : 'Helping others ({action})';
  String get meritSharingKnowledge => locale == 'zh' ? '分享知识' : 'Sharing knowledge';
  String get meritBuildingShelter => locale == 'zh' ? '建造庇护所' : 'Building shelter';
  String get mergedWithTao => locale == 'zh' ? '已融入天道' : 'Merged with Tao';

  // ========== 规则类别 ==========
  String get ruleCategoryFundamental => locale == 'zh' ? '基础规则' : 'Fundamental';
  String get ruleCategoryEvolved => locale == 'zh' ? '演化规则' : 'Evolved';
  String get ruleCategoryTao => locale == 'zh' ? '天道规则' : 'Tao (天道)';

  // ========== 天道规则提示 ==========
  String get taoRulesHeader => locale == 'zh' ? '=== 天道规则 ===' : '=== Tao Rules (天道规则) ===';
  String get taoRulesDescription => locale == 'zh' ? '这些是由融入天道的生灵创造的神圣法则。' : 'These are the sacred laws created by beings who have merged with Tao.';
  String get taoRulesMutable => locale == 'zh' ? '它们不可更改，所有生灵都必须遵守：' : 'They are immutable and must be followed by all:';
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