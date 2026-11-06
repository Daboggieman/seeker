// Source filter chips — "All" plus one chip per indexed source; multi-select
// maps directly to POST /v1/search filters.source_id (docs 03).

import {ScrollView, StyleSheet, Text, Pressable} from 'react-native';
import {ThemeColors, spacing, radius} from '../theme';
import type {SourceRecord} from '../engineApi';

interface Props {
  sources: SourceRecord[];
  selected: ReadonlySet<string>;
  onToggle: (sourceId: string) => void;
  colors: ThemeColors;
}

export function SourceFilter({sources, selected, onToggle, colors}: Props) {
  const styles = stylesFor(colors);
  if (sources.length === 0) {
    return null;
  }
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
      style={styles.wrap}>
      <Chip
        label="All"
        active={selected.size === 0}
        onPress={() => sources.forEach((s) => selected.has(s.id) && onToggle(s.id))}
        colors={colors}
      />
      {sources.map((s) => (
        <Chip
          key={s.id}
          label={s.id}
          active={selected.has(s.id)}
          onPress={() => onToggle(s.id)}
          colors={colors}
        />
      ))}
    </ScrollView>
  );
}

function Chip({
  label,
  active,
  onPress,
  colors,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  colors: ThemeColors;
}) {
  const styles = stylesFor(colors);
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{selected: active}}
      style={[styles.chip, active && styles.chipActive]}>
      <Text style={[styles.chipText, active && styles.chipTextActive]} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
}

const stylesFor = (c: ThemeColors) =>
  StyleSheet.create({
    wrap: {flexGrow: 0},
    row: {flexDirection: 'row', gap: spacing.s, paddingHorizontal: spacing.l, paddingVertical: spacing.s},
    chip: {
      borderRadius: radius.m,
      backgroundColor: c.chipBg,
      paddingVertical: 6,
      paddingHorizontal: spacing.m,
      maxWidth: 220,
    },
    chipActive: {backgroundColor: c.accentSoft, borderColor: c.accent, borderWidth: 1},
    chipText: {color: c.muted, fontSize: 13},
    chipTextActive: {color: c.accent, fontWeight: '600'},
  });
