// One search result: title, snippet, source + score + path. Long-press shares
// the file path (thin client — the engine never knows what the client does
// with a result; standing rule 2).

import {StyleSheet, Text, Pressable, Share, View} from 'react-native';
import {ThemeColors, monoFont, spacing, radius} from '../theme';
import type {SearchResult} from '../engineApi';

interface Props {
  result: SearchResult;
  colors: ThemeColors;
}

export function ResultRow({result, colors}: Props) {
  const styles = stylesFor(colors);
  const title = result.title || result.path.split('/').pop() || result.path;
  const score = result.score != null ? result.score.toFixed(2) : null;

  return (
    <Pressable
      style={styles.card}
      onLongPress={() => {
        void Share.share({message: result.path});
      }}>
      <Text style={styles.title} numberOfLines={2}>
        {title}
      </Text>
      <Text style={styles.snippet} numberOfLines={3}>
        {result.snippet}
      </Text>
      <View style={styles.meta}>
        <Text style={styles.source}>{result.source_id}</Text>
        {score != null && <Text style={styles.score}>{score}</Text>}
      </View>
      <Text style={styles.path} numberOfLines={1}>
        {result.path}
      </Text>
    </Pressable>
  );
}

const stylesFor = (c: ThemeColors) =>
  StyleSheet.create({
    card: {
      backgroundColor: c.card,
      borderRadius: radius.m,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.border,
      padding: spacing.m,
    },
    title: {color: c.text, fontSize: 16, fontWeight: '600'},
    snippet: {color: c.muted, fontSize: 13, lineHeight: 18, marginTop: spacing.xs},
    meta: {flexDirection: 'row', justifyContent: 'space-between', marginTop: spacing.s},
    source: {color: c.accent, fontSize: 12, fontWeight: '600'},
    score: {color: c.muted, fontSize: 12, fontVariant: ['tabular-nums']},
    path: {
      color: c.muted,
      fontFamily: monoFont,
      fontSize: 11,
      marginTop: spacing.xs,
    },
  });
