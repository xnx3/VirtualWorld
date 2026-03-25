import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';
import '../services/app_state.dart';

/// 事件日志卡片
class EventLogCard extends StatelessWidget {
  final ChronicleEvent event;

  const EventLogCard({super.key, required this.event});

  IconData get eventIcon {
    switch (event.type) {
      case EventType.think:
        return Icons.psychology;
      case EventType.action:
        return Icons.directions_run;
      case EventType.disaster:
        return Icons.warning;
      case EventType.priest:
        return Icons.account_balance;
      case EventType.birth:
        return Icons.child_care;
      case EventType.death:
        return Icons.dangerous;
      case EventType.knowledge:
        return Icons.lightbulb;
      case EventType.task:
        return Icons.assignment;
      default:
        return Icons.circle;
    }
  }

  Color get eventColor {
    switch (event.type) {
      case EventType.think:
        return AppTheme.thinkColor;
      case EventType.action:
        return AppTheme.actionColor;
      case EventType.disaster:
        return AppTheme.disasterColor;
      case EventType.priest:
        return AppTheme.priestColor;
      case EventType.birth:
        return Colors.green;
      case EventType.death:
        return Colors.red;
      case EventType.knowledge:
        return AppTheme.knowledgeColor;
      case EventType.task:
        return Colors.blue;
      default:
        return Colors.white54;
    }
  }

  @override
  Widget build(BuildContext context) {
    final content = event.content.isEmpty ? 'No content' : event.content;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white54,
        borderRadius: BorderRadius.circular(8),
        border: Border(left: BorderSide(color: eventColor, width: 3)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(eventIcon, color: eventColor, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  content,
                  style: const TextStyle(fontSize: 13),
                ),
                const SizedBox(height: 4),
                Text(
                  _formatTime(event.timestamp),
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.white.withOpacity(0.5),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _formatTime(DateTime time) {
    return '${time.hour.toString().padLeft(2, '0')}:'
        '${time.minute.toString().padLeft(2, '0')}:'
        '${time.second.toString().padLeft(2, '0')}';
  }
}