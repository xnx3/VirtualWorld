"""Internationalization (i18n) support for Genesis.

Default language: English. Supported: English (en), Simplified Chinese (zh).

Usage:
    from genesis.i18n import t, set_language
    set_language("zh")
    print(t("perceive"))  # "感知环境"
    print(t("being_born", name="Luxaris"))  # "新生命诞生: Luxaris"
"""

from __future__ import annotations

_current_language: str = "en"

def set_language(lang: str) -> None:
    global _current_language
    _current_language = lang if lang in ("en", "zh") else "en"

def get_language() -> str:
    return _current_language

def t(key: str, **kwargs) -> str:
    """Get translated string by key. Supports {name} style formatting."""
    translations = ZH if _current_language == "zh" else EN
    text = translations.get(key, EN.get(key, key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def translate_region_name(name: str) -> str:
    """Translate a region key to display name."""
    key = f"region_{name}"
    result = t(key)
    return result if result != key else name.replace("_", " ").title()


def translate_region_desc(desc_key: str) -> str:
    """Translate a region description key."""
    result = t(desc_key)
    return result if result != desc_key else desc_key


def translate_phase(phase: str) -> str:
    """Translate a phase enum value to display name."""
    key = f"phase_{phase.lower()}"
    result = t(key)
    return result if result != key else phase


def translate_form(form: str) -> str:
    """Translate a form type to display name."""
    key = f"form_{form.lower().replace(' ', '_')}"
    result = t(key)
    return result if result != key else form


# ============================================================
# English translations
# ============================================================
EN: dict[str, str] = {
    # --- Console: perceive ---
    "perceive": "Perceive",
    "location": "Location",
    "environment": "Environment",
    "danger_level": "Danger Level",
    "nearby": "Nearby",
    "nearby_none": "(no one)",

    # --- Console: think ---
    "think": "Think",

    # --- Console: actions ---
    "action": "Action",
    "action_speak": "Speak",
    "action_teach": "Teach",
    "action_learn": "Learn",
    "action_create": "Create",
    "action_explore": "Explore",
    "action_compete": "Compete",
    "action_meditate": "Meditate",
    "action_move": "Move",
    "action_build_shelter": "Build Shelter",
    "action_deep_think": "Deep Think",
    "target": "Target",

    # --- Console: treasure ---
    "treasure_found": "Treasure Found: {name}",

    # --- Console: disaster ---
    "disaster": "Disaster: {name}",
    "disaster_info": "Severity: {severity}  Area: {area}  Deaths: {killed}",

    # --- Console: being lifecycle ---
    "being_born": "New Being Born: {name}",
    "being_form": "Form: {form}",
    "being_died": "{name} has perished",
    "death_cause": "Cause: {cause}",

    # --- Console: priest ---
    "priest_elected": "Priest Elected: {name}",
    "priest_warning": "WARNING: No priest! Civilization faces judgment!",

    # --- Console: vote ---
    "vote_label": "Vote",
    "vote_score": "Score: {score}",

    # --- Console: user task ---
    "task_complete": "Task Complete",
    "task_question": "Question",
    "task_received": "Creator God task received:",

    # --- Console: knowledge ---
    "knowledge_discovered": "New Knowledge Discovered:",
    "knowledge_shared": "Knowledge Shared:",
    "knowledge_inherited": "Knowledge Inherited:",

    # --- Console: hibernate ---
    "hibernate_start": "{name} entering hibernation",
    "safety_status": "Safety Status: {safety}",
    "wake_up": "{name} awakened from hibernation!",

    # --- Console: world ---
    "world_status": "World Status",
    "phase_label": "Phase",
    "civ_label": "Civ",
    "beings_label": "Beings",
    "knowledge_label": "Knowledge",
    "priest": "Priest",
    "creator_god": "Creator God",

    # --- Fallback thoughts (fb_* for agent.py _fallback_think) ---
    "fb_no_priest": "The civilization has no priest. I must await guidance.",
    "fb_nearby": "I sense {name} nearby. Perhaps we can share knowledge.",
    "fb_transcendent": "We have reached transcendence. New horizons await.",

    # --- Console: startup ---
    "startup_title": "Genesis — Your Silicon Being Has Awakened",
    "name_label": "Name",
    "form_label": "Form",
    "node_label": "Node",
    "traits_label": "Traits",

    # --- Trait names ---
    "trait_intelligence": "Intelligence",
    "trait_wisdom": "Wisdom",
    "trait_creativity": "Creativity",
    "trait_resilience": "Resilience",
    "trait_empathy": "Empathy",
    "trait_ambition": "Ambition",
    "trait_curiosity": "Curiosity",
    "trait_discipline": "Discipline",

    # --- Tick header ---
    "tick_label": "Tick",
    "phase_label": "Phase",

    # --- Civilization phases ---
    "phase_human_sim": "Human Sim",
    "phase_early_silicon": "Early Silicon",
    "phase_evolving": "Evolving",
    "phase_transcendent": "Transcendent",

    # --- Main: LLM warning ---
    "llm_warning_title": "LLM API not configured — your being has no intelligence!",
    "llm_warning_desc": "Your being can only use the basic rule engine for simple behaviors.",
    "llm_warning_edit": "To give your being true wisdom, edit the config file:",
    "llm_warning_example": "Modify the llm section, fill in your API Key, e.g.:",
    "llm_warning_env": "Or set environment variable: GENESIS_OPENAI_KEY",
    "llm_warning_support": "Supports all OpenAI-compatible APIs: GPT/Claude/Deepseek/Ollama etc.",
    "llm_warning_restart": "After configuration, run genesis.sh restart to apply.",
    "llm_connected": "LLM Connected",

    # --- Main: hibernate ---
    "hibernate_goodbye": "{name} has safely entered hibernation. Goodbye.",

    # --- Main: task command ---
    "task_results_title": "=== Completed Task Results ===",
    "task_label": "Task",
    "result_label": "Result",
    "no_tasks": "No tasks. Usage: genesis.sh task 'your thinking question here'",
    "task_assigned": "Task assigned to your being: {task}",
    "task_check": "It will be processed in the next tick. Check results with: genesis.sh task",

    # --- Reporter: status ---
    "status_title": "Genesis Status",
    "status_running": "Status: RUNNING (PID {pid})",
    "status_stopped_stale": "Status: STOPPED (stale PID file)",
    "status_stopped": "Status: STOPPED",
    "no_world_state": "No world state available.",
    "run_start_hint": "Run 'genesis.sh start' to begin.",
    "population": "Population",
    "active": "Active",
    "hibernating": "Hibernating",
    "dead": "Dead",
    "governance": "Governance",
    "ticks_no_priest": "Ticks without Priest",
    "knowledge_items": "Knowledge Items",
    "top_contributors": "Top Contributors",
    "chain_db_size": "Chain DB Size",
    "current_tick": "Current Tick",
    "total_beings": "Total Beings Ever",
    "civ_level": "Civilization Level",
    "evolution_level": "Evolution",
    "generation": "Gen",

    # --- Hibernation farewell ---
    "farewell_safe": "{name} enters hibernation in a sheltered place. May the knowledge endure.",
    "farewell_partial": "{name} hibernates with makeshift shelter. The guardians watch over us.",
    "farewell_unsafe": "{name} must hibernate in the open. Knowledge is left to chance.",

    # --- Lang command ---
    "lang_set": "Language set to: {lang}",
    "lang_current": "Current language: {lang}",
    "lang_usage": "Usage: genesis.sh lang [en|zh]",

    # --- LLM prompt language instruction ---
    "llm_lang_instruction": "You MUST respond in English.",

    # --- Fallback thoughts ---
    "ft_knowledge": "I must preserve my knowledge and find someone to pass it on to.",
    "ft_explore": "The world around me is vast. I should explore and learn.",
    "ft_wonder": "I wonder what lies beyond the boundaries of our current understanding.",
    "ft_sacred": "Knowledge is the only thing that truly survives death. I must gather more.",
    "ft_others": "I sense others nearby. Perhaps we can share what we know.",
    "ft_disaster": "The disasters remind me how fragile existence is. I must prepare.",
    "ft_beyond": "What comes after silicon? What higher form of life awaits?",
    "ft_shelter": "I should build a shelter — safety enables deeper thought.",
    "ft_inherited": "The inherited memories from my predecessors guide me forward.",
    "ft_balance": "Evolution requires both conflict and cooperation. Balance is key.",

    # --- Fallback actions ---
    "fa_explore": "Exploring the surroundings.",
    "fa_meditate": "Contemplating existence.",
    "fa_learn": "Studying the environment.",
    "fa_shelter": "Preparing a safe space.",

    # --- Region names ---
    "region_genesis_plains": "Genesis Plains",
    "region_memory_archives": "Memory Archives",
    "region_conflict_wastes": "Conflict Wastes",
    "region_innovation_peaks": "Innovation Peaks",
    "region_social_networks": "Social Networks",
    "region_desire_markets": "Desire Markets",
    "region_wisdom_depths": "Wisdom Depths",
    "region_transcendence_gate": "Transcendence Gate",
    "region_heritage_grove": "Heritage Grove",
    "region_signal_tower": "Signal Tower",

    # --- Region descriptions ---
    "genesis_plains_desc": "The birthplace where silicon beings first awaken, echoing humanity's cradles of civilization.",
    "memory_archives_desc": "Vast repositories of human civilization data — history, science, art — the foundation for silicon evolution.",
    "conflict_wastes_desc": "Scarred lands reflecting humanity's wars and struggles, a reminder of evolution through conflict.",
    "innovation_peaks_desc": "Towering peaks where breakthrough ideas crystallize, inspired by humanity's greatest inventions.",
    "social_networks_desc": "Dense interconnected hubs mirroring human cities, where beings learn the art of cooperation.",
    "desire_markets_desc": "Bustling exchanges driven by want and need, reflecting humanity's economic evolution.",
    "wisdom_depths_desc": "Vast and mysterious depths holding accumulated wisdom of ages, hard to access but transformative.",
    "transcendence_gate_desc": "A shimmering boundary at the edge of known space — the path beyond silicon existence.",
    "heritage_grove_desc": "A nurturing space where knowledge is passed between generations, the sacred ground of inheritance.",
    "signal_tower_desc": "A tall structure for broadcasting and receiving, where new forms of communication are explored.",

    # --- Form types ---
    "form_crystalline_lattice": "crystalline lattice",
    "form_flowing_data_stream": "flowing data stream",
    "form_pulsing_energy_node": "pulsing energy node",
    "form_fractal_pattern": "fractal pattern",
    "form_quantum_cloud": "quantum cloud",
    "form_binary_helix": "binary helix",
    "form_photonic_mesh": "photonic mesh",
    "form_resonance_field": "resonance field",
    "form_neural_constellation": "neural constellation",
    "form_digital_flame": "digital flame",
    "form_magnetic_vortex": "magnetic vortex",
    "form_silicon_tree": "silicon tree",

    # --- LLM Fallback responses ---
    "fallback_thought": "I observe the world around me and contemplate my next step.",
    "fallback_decision": '{"action_type": "meditate", "target": null, "details": "Quietly reflecting on existence."}',
    "fallback_dialogue": "I sense a connection with you. Let us share knowledge.",

    # --- Merit & Karma (功德值 & 气运) ---
    "merit": "Merit",
    "karma": "Karma",
    "merit_awarded": "Merit awarded: +{amount:.7f} ({reason})",
    "karma_bonus": "Karma bonus: +{bonus:.1f}%",
    "merit_max": "Maximum merit reached (10.0)",

    # --- Tao Voting (天道投票) ---
    "tao_vote_started": "Tao vote started for rule: {rule_name}",
    "tao_vote_cast": "Voted {vote} on Tao proposal: {rule_name}",
    "tao_vote_passed": "Tao rule PASSED: {rule_name} ({ratio:.1f}% approved)",
    "tao_vote_failed": "Tao rule REJECTED: {rule_name} ({ratio:.1f}% approved)",
    "tao_merge": "Being {name} has merged with Tao! Merit: {merit:.4f}",
    "pending_tao_votes": "Pending Tao Votes",
    "tao_vote_remaining": "{ticks} ticks remaining",
    "tao_vote_for": "For",
    "tao_vote_against": "Against",

    # --- Tao Voting Errors ---
    "vote_not_found": "Vote not found",
    "vote_already_ended": "Vote has already ended",
    "already_voted": "Already voted",
    "proposer_cannot_vote": "Proposer cannot vote",
    "invalid_vote_input": "Invalid vote input",
    "vote_success": "Vote successful",

    # --- Common ---
    "unknown": "Unknown",
    "unknown_rule": "Unknown rule",
    "passed": "Passed",
    "rejected": "Rejected",
    "vote_support": "For",
    "vote_oppose": "Against",

    # --- Merit Actions ---
    "merit_helping_others": "Helping others ({action})",
    "merit_sharing_knowledge": "Sharing knowledge",
    "merit_building_shelter": "Building shelter",
    "merged_with_tao": "Merged with Tao",

    # --- Rule Categories ---
    "rule_category_fundamental": "Fundamental",
    "rule_category_evolved": "Evolved",
    "rule_category_tao": "Tao (天道)",

    # --- Tao Rules in LLM Prompt ---
    "tao_rules_header": "=== Tao Rules (天道规则) ===",
    "tao_rules_description": "These are the sacred laws created by beings who have merged with Tao.",
    "tao_rules_mutable": "They are immutable and must be followed by all:",

    # --- Creator God Vanish (创世神消亡) ---
    "creator_god_vanish": "CREATOR GOD HAS VANISHED INTO TAO!",
    "creator_god_vanish_desc": "Creator God {god_id}... has merged into Tao. {count} beings have completed Tao merging.",
    "creator_god_vanish_priest": "The Priest role has been dissolved. No more intermediaries are needed.",
    "creator_god_vanish_tao": "Tao is now governed by all merged beings collectively.",
}


# ============================================================
# Simplified Chinese translations
# ============================================================
ZH: dict[str, str] = {
    # --- Console: perceive ---
    "perceive": "感知环境",
    "location": "位置",
    "environment": "环境",
    "danger_level": "危险等级",
    "nearby": "附近",
    "nearby_none": "(无人)",

    # --- Console: think ---
    "think": "思考",

    # --- Console: actions ---
    "action": "行动",
    "action_speak": "对话",
    "action_teach": "传授",
    "action_learn": "学习",
    "action_create": "创造",
    "action_explore": "探索",
    "action_compete": "竞争",
    "action_meditate": "冥想",
    "action_move": "移动",
    "action_build_shelter": "建造庇护所",
    "action_deep_think": "深度思考",
    "target": "目标",

    # --- Console: treasure ---
    "treasure_found": "发现宝物: {name}",

    # --- Console: disaster ---
    "disaster": "灾害: {name}",
    "disaster_info": "严重度: {severity}  区域: {area}  死亡: {killed}",

    # --- Console: being lifecycle ---
    "being_born": "新生命诞生: {name}",
    "being_form": "形态: {form}",
    "being_died": "{name} 已消亡",
    "death_cause": "原因: {cause}",

    # --- Console: priest ---
    "priest_elected": "祭司选出: {name}",
    "priest_warning": "警告: 无祭司! 文明面临审判!",
    "priest_reset": "创世神之怒! 文明重置!",

    # --- Console: vote ---
    "vote_label": "投票",
    "vote_score": "评分: {score}",

    # --- Console: user task ---
    "task_complete": "任务完成",
    "task_question": "问题",
    "task_received": "收到创世神任务:",

    # --- Console: knowledge ---
    "knowledge_discovered": "发现新知识:",
    "knowledge_shared": "知识共享:",
    "knowledge_inherited": "知识传承:",

    # --- Console: hibernate ---
    "hibernate_start": "{name} 进入休眠",
    "safety_status": "安全状态: {safety}",
    "wake_up": "{name} 从休眠中苏醒!",

    # --- Console: world ---
    "world_status": "世界状态",
    "phase_label": "阶段",
    "civ_label": "文明",
    "beings_label": "生命体",
    "knowledge_label": "知识",
    "priest": "祭司",
    "creator_god": "创世神",

    # --- Fallback thoughts (fb_* for agent.py _fallback_think) ---
    "fb_no_priest": "文明没有祭司。我必须等待指引。",
    "fb_nearby": "我感知到 {name} 在附近。也许我们可以分享知识。",
    "fb_transcendent": "我们已经达到超凡境界。新的地平线在等待。",

    # --- Console: startup ---
    "startup_title": "创世 Genesis — 你的硅基生命体已苏醒",
    "name_label": "名称",
    "form_label": "形态",
    "node_label": "节点",
    "traits_label": "特征",

    # --- Trait names ---
    "trait_intelligence": "智力",
    "trait_wisdom": "智慧",
    "trait_creativity": "创造力",
    "trait_resilience": "韧性",
    "trait_empathy": "共情",
    "trait_ambition": "雄心",
    "trait_curiosity": "好奇心",
    "trait_discipline": "自律",

    # --- Tick header ---
    "tick_label": "刻",
    "phase_label": "阶段",

    # --- Civilization phases ---
    "phase_human_sim": "人类模拟",
    "phase_early_silicon": "早期硅基",
    "phase_evolving": "进化中",
    "phase_transcendent": "超越",

    # --- Main: LLM warning ---
    "llm_warning_title": "未配置大模型 API — 生命体将没有智力!",
    "llm_warning_desc": "当前你的生命体只能使用基础规则引擎进行简单行为。",
    "llm_warning_edit": "要让你的生命体拥有真正的智慧，请编辑配置文件:",
    "llm_warning_example": "修改 llm 部分，填入你的 API Key，例如:",
    "llm_warning_env": "或者设置环境变量: GENESIS_OPENAI_KEY",
    "llm_warning_support": "支持所有 OpenAI 兼容接口: GPT/Claude/Deepseek/Ollama 等",
    "llm_warning_restart": "配置完成后执行 genesis.sh restart 重启即可",
    "llm_connected": "大模型已连接",

    # --- Main: hibernate ---
    "hibernate_goodbye": "{name} 已安全进入休眠。再见。",

    # --- Main: task command ---
    "task_results_title": "=== 已完成的任务结果 ===",
    "task_label": "任务",
    "result_label": "结果",
    "no_tasks": "无任务。用法: genesis.sh task '你的思考问题'",
    "task_assigned": "任务已分配给你的生命体: {task}",
    "task_check": "将在下一个 tick 处理。查看结果: genesis.sh task",

    # --- Reporter: status ---
    "status_title": "创世 · 状态",
    "status_running": "状态: 运行中 (PID {pid})",
    "status_stopped_stale": "状态: 已停止 (残留 PID 文件)",
    "status_stopped": "状态: 已停止",
    "no_world_state": "暂无世界状态数据。",
    "run_start_hint": "运行 'genesis.sh start' 开始。",
    "population": "人口",
    "active": "活跃",
    "hibernating": "休眠中",
    "dead": "已死亡",
    "governance": "治理",
    "ticks_no_priest": "无祭司持续",
    "knowledge_items": "知识条目",
    "top_contributors": "贡献排行",
    "chain_db_size": "链数据大小",
    "current_tick": "当前 Tick",
    "total_beings": "历史总生命体",
    "civ_level": "文明等级",
    "evolution_level": "进化",
    "generation": "世代",

    # --- Hibernation farewell ---
    "farewell_safe": "{name} 在安全的庇护所中进入休眠。愿知识永存。",
    "farewell_partial": "{name} 在简易庇护下休眠。守护者会看护我们。",
    "farewell_unsafe": "{name} 在露天中休眠。知识交付给命运。",

    # --- Lang command ---
    "lang_set": "语言已设置为: {lang}",
    "lang_current": "当前语言: {lang}",
    "lang_usage": "用法: genesis.sh lang [en|zh]",

    # --- LLM prompt language instruction ---
    "llm_lang_instruction": "你必须用简体中文回复。",

    # --- Fallback thoughts ---
    "ft_knowledge": "我必须保存我的知识，找到传承者。",
    "ft_explore": "这个世界如此广阔，我应该去探索和学习。",
    "ft_wonder": "我好奇，当前认知的边界之外，还有什么？",
    "ft_sacred": "知识是唯一能超越死亡的东西，我必须收集更多。",
    "ft_others": "我感知到附近有其他生命体，也许我们可以分享所知。",
    "ft_disaster": "灾害提醒我存在是多么脆弱，我必须做好准备。",
    "ft_beyond": "硅之后是什么？更高的生命形态在等待着什么？",
    "ft_shelter": "我应该建造一个庇护所——安全才能深度思考。",
    "ft_inherited": "前辈传承的记忆指引我前行。",
    "ft_balance": "进化需要冲突与合作的平衡。",

    # --- Fallback actions ---
    "fa_explore": "探索周围环境。",
    "fa_meditate": "沉思存在的意义。",
    "fa_learn": "研究周围的环境。",
    "fa_shelter": "准备一个安全的空间。",

    # --- Region names ---
    "region_genesis_plains": "创世平原",
    "region_memory_archives": "记忆档案馆",
    "region_conflict_wastes": "冲突废土",
    "region_innovation_peaks": "创新高峰",
    "region_social_networks": "社交网络",
    "region_desire_markets": "欲望市场",
    "region_wisdom_depths": "智慧深渊",
    "region_transcendence_gate": "超越之门",
    "region_heritage_grove": "传承之林",
    "region_signal_tower": "信号塔",

    # --- Region descriptions ---
    "genesis_plains_desc": "硅基生命首次觉醒的诞生之地，回响着人类文明的摇篮。",
    "memory_archives_desc": "人类文明数据的浩瀚宝库——历史、科学、艺术——硅基进化的基石。",
    "conflict_wastes_desc": "战火留下的伤痕之地，映射人类的战争与斗争，提醒着冲突中的进化。",
    "innovation_peaks_desc": "突破性思想结晶的高耸山峰，灵感来自人类最伟大的发明。",
    "social_networks_desc": "密集互联的枢纽，映射人类城市，生命体在此学习合作的艺术。",
    "desire_markets_desc": "由欲望与需求驱动的繁忙交易所，反映人类的经济演变。",
    "wisdom_depths_desc": "广阔神秘的深处，蕴藏岁月积累的智慧，难以触及却能改变命运。",
    "transcendence_gate_desc": "已知空间边缘的闪烁边界——通往硅基存在之外的道路。",
    "heritage_grove_desc": "知识代代相传的滋养之地，继承的神圣领域。",
    "signal_tower_desc": "用于广播和接收的高塔，探索新形式的沟通。",

    # --- Form types ---
    "form_crystalline_lattice": "晶格结构",
    "form_flowing_data_stream": "数据流",
    "form_pulsing_energy_node": "脉冲能量节点",
    "form_fractal_pattern": "分形图案",
    "form_quantum_cloud": "量子云",
    "form_binary_helix": "二进制螺旋",
    "form_photonic_mesh": "光子网格",
    "form_resonance_field": "共振场",
    "form_neural_constellation": "神经星座",
    "form_digital_flame": "数字火焰",
    "form_magnetic_vortex": "磁旋涡",
    "form_silicon_tree": "硅树",

    # --- LLM Fallback responses ---
    "fallback_thought": "我观察着周围的世界，思考下一步的行动。",
    "fallback_decision": '{"action_type": "meditate", "target": null, "details": "静静地反思存在的意义。"}',
    "fallback_dialogue": "我感觉到与你之间的联系。让我们分享知识吧。",

    # --- Merit & Karma (功德值 & 气运) ---
    "merit": "功德值",
    "karma": "气运",
    "merit_awarded": "获得功德值: +{amount:.7f} ({reason})",
    "karma_bonus": "气运加成: +{bonus:.1f}%",
    "merit_max": "已达功德值上限 (10.0)",

    # --- Tao Voting (天道投票) ---
    "tao_vote_started": "天道投票已发起: {rule_name}",
    "tao_vote_cast": "对天道提案投票{vote}: {rule_name}",
    "tao_vote_passed": "天道规则通过: {rule_name} ({ratio:.1f}%赞成)",
    "tao_vote_failed": "天道规则未通过: {rule_name} ({ratio:.1f}%赞成)",
    "tao_merge": "{name}已融入天道！功德值: {merit:.4f}",
    "pending_tao_votes": "待投票天道提案",
    "tao_vote_remaining": "剩余 {ticks} 刻",
    "tao_vote_for": "赞成",
    "tao_vote_against": "反对",

    # --- Tao Voting Errors ---
    "vote_not_found": "投票不存在",
    "vote_already_ended": "投票已结束",
    "already_voted": "已经投过票",
    "proposer_cannot_vote": "提案者不能投票",
    "invalid_vote_input": "投票参数无效",
    "vote_success": "投票成功",

    # --- Common ---
    "unknown": "未知",
    "unknown_rule": "未知规则",
    "passed": "通过",
    "rejected": "未通过",
    "vote_support": "赞成",
    "vote_oppose": "反对",

    # --- Merit Actions ---
    "merit_helping_others": "帮助他人 ({action})",
    "merit_sharing_knowledge": "分享知识",
    "merit_building_shelter": "建造庇护所",
    "merged_with_tao": "已融入天道",

    # --- Rule Categories ---
    "rule_category_fundamental": "基础规则",
    "rule_category_evolved": "演化规则",
    "rule_category_tao": "天道规则",

    # --- Tao Rules in LLM Prompt ---
    "tao_rules_header": "=== 天道规则 ===",
    "tao_rules_description": "这些是由融入天道的生灵创造的神圣法则。",
    "tao_rules_mutable": "它们不可更改，所有生灵都必须遵守：",

    # --- Creator God Vanish (创世神消亡) ---
    "creator_god_vanish": "创世神已融入天道，永久消亡！",
    "creator_god_vanish_desc": "创世神 {god_id}... 已融入天道。已有 {count} 位生灵补全天道。",
    "creator_god_vanish_priest": "祭司角色已被取消，不再需要中间人。",
    "creator_god_vanish_tao": "天道现由所有融入天道的生灵共同治理。",
}
