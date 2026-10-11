import fs from 'node:fs';
import path from 'node:path';

// OpenClaw SQLite/auth storage needs POSIX permissions. Windows bind mounts
// cannot supply those reliably: copy only the prepared seeds to a Linux volume.
const root = '/state';
if (fs.readdirSync(root).length !== 0) throw new Error('State volume is not empty; refusing to overwrite it.');
const files = ['openclaw.json'];
for (const agent of ['asia', 'developpement', 'recherche']) {
  files.push(`agents/${agent}/agent/auth-profiles.json`);
  files.push(`workspaces/${agent}/AGENTS.md`, `workspaces/${agent}/IDENTITY.md`);
}
for (const file of files) {
  if (!fs.statSync(path.join('/seed', file)).isFile()) throw new Error(`Missing seed: ${file}`);
}
for (const file of files) {
  const target = path.join(root, file);
  fs.mkdirSync(path.dirname(target), {recursive: true, mode: 0o700});
  fs.copyFileSync(path.join('/seed', file), target, fs.constants.COPYFILE_EXCL);
}
function protect(file) {
  const info = fs.lstatSync(file);
  if (info.isSymbolicLink()) throw new Error('Symlinks are not accepted in the initial state');
  fs.chownSync(file, 1000, 1000);
  fs.chmodSync(file, info.isDirectory() ? 0o700 : 0o600);
  if (info.isDirectory()) for (const child of fs.readdirSync(file)) protect(path.join(file, child));
}
protect(root);
console.log('Initialized a private Linux state volume for three agents.');
