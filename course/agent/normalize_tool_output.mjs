// Remove one known, non-fatal OpenClaw launcher warning only when the tool itself
// explicitly completed successfully. Otherwise annotate without removing output.
// Keep raw logs and all genuine errors intact.
export function normalizeToolMessage(message) {
  if (message.role !== 'tool' || typeof message.content !== 'string') return message;
  const warning = /^\/bin\/(?:ba)?sh: (?:line )?1: cannot create \/proc\/self\/oom_score_adj: Permission denied\r?\n/;
  if (!warning.test(message.content)) return message;
  const content = message.content.replace(warning, '');
  try {
    const event = JSON.parse(content);
    if (event.completed === true && 'result' in event && !('error' in event)) {
      return {...message, content};
    }
  } catch { /* Preserve non-JSON output and explain the launcher warning below. */ }
  return {...message, content:
    'Launcher diagnostic: the following oom_score_adj warning alone is non-fatal; '
    + 'the requested command can still run. Check subsequent output and exit status. '
    + 'Any other error below remains a real error.\n' + message.content};
}
