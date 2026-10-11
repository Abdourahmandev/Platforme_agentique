// Check tracked content, including the index before the first commit. Never print matched values.
import { execFileSync } from 'node:child_process';

const files = execFileSync('git', ['ls-files', '-z'], { encoding: 'utf8' }).split('\0').filter(Boolean);
const forbiddenPath = /(^|\/)(node_modules|dist|venv|\.venv|__pycache__|backups)(\/|$)|(^|\/)(config\.local\.json|auth\.json|server-secret\.json|database\.json|runtime-private\.json|gateway-test-device\.json|recovery-key\.txt|speech-secret\.txt|\.env(?:\..*)?)$|(?:\.env|\.token|\.key|\.pem|\.p12|\.sqlite(?:-.*)?|\.db(?:-.*)?|\.dump|\.jsonl|\.aes|\.log|\.pyc)$|credentials[^/]*\.json$/i;
const patterns = [
  /\bAIza[0-9A-Za-z_-]{35}\b/,
  /\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b/,
  /\bsk-(?:asia-)?[A-Za-z0-9_-]{20,}\b/,
  /\b\d{8,12}:[A-Za-z0-9_-]{35}\b/,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
  /postgres(?:ql)?:\/\/[^\s:/]+:[^\s@]+@/,
];
const failures = [];
for (const file of files) {
  if (forbiddenPath.test(file) && !file.endsWith('/.env.example') && file !== '.env.example') failures.push(`${file}: forbidden file`);
  const content = execFileSync('git', ['show', `:${file}`], { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 });
  if (patterns.some(pattern => pattern.test(content))) failures.push(`${file}: possible credential`);
}
if (!files.length) failures.push('No tracked files to check');
if (failures.length) {
  console.error(failures.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`${files.length} tracked files checked; no forbidden files or recognized credentials.`);
}
