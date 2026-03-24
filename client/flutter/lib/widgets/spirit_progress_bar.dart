import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';

/// 精神力进度条
class SpiritProgressBar extends StatelessWidget {
  final double current;
  final double maximum;
  final double? cost;
  final double? recovered;

  const SpiritProgressBar({
    super.key,
    required this.current,
    required this.maximum,
    this.cost,
    this.recovered,
  });

  double get percentage => maximum > 0 ? current / maximum : 0;

  Color get barColor {
    if (percentage >= 0.6) return AppTheme.spiritHigh;
    if (percentage >= 0.3) return AppTheme.spiritMedium;
    if (percentage >= 0.1) return AppTheme.spiritLow;
    return AppTheme.spiritExhausted;
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Text('🔮 ', style: TextStyle(fontSize: 18)),
                Text(
                  'Spirit',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                const Spacer(),
                Text(
                  '${current.toInt()}/${maximum.toInt()}',
                  style: TextStyle(
                    color: barColor,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: percentage,
                backgroundColor: Colors.white12,
                valueColor: AlwaysStoppedAnimation(barColor),
                minHeight: 8,
              ),
            ),
            if (cost != null && cost! > 0 || recovered != null && recovered! > 0)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Row(
                  children: [
                    if (cost != null && cost! > 0)
                      Text(
                        '-${cost!.toInt()}',
                        style: const TextStyle(
                          color: AppTheme.spiritExhausted,
                          fontSize: 12,
                        ),
                      ),
                    if (recovered != null && recovered! > 0) ...[
                      if (cost != null && cost! > 0) const SizedBox(width: 8),
                      Text(
                        '+${recovered!.toInt()}',
                        style: const TextStyle(
                          color: AppTheme.spiritHigh,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}