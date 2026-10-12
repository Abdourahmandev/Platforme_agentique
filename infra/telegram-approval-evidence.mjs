// A timeout is stored as decision=deny too. Only an explicit channel decision
// can qualify the operator-assisted test, and execution must agree with it.
export function approvalChecks(choice, evidence, status, rows) {
  if (!['deny', 'allow'].includes(choice)) throw Error('Invalid approval choice');
  const resolution = rows.find(row => row.terminal_reason === 'user' && row.resolver_kind === 'channel' &&
    row.status === (choice === 'deny' ? 'denied' : 'allowed') &&
    row.decision === (choice === 'deny' ? 'deny' : 'allow-once'));
  return {
    nativeChannelDecisionObserved: Boolean(resolution),
    singleToolCall: evidence.calls === 1,
    ...(choice === 'deny'
      ? {noExecution: evidence.completed === 0, taskSettled: !status.permissions.length && status.status === 'idle'}
      : {executedExactlyOnce: evidence.completed === 1, realOutput: evidence.outputMatches,
        taskSettled: status.completed === true && !status.permissions.length && status.status === 'idle'}),
  };
}
