const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { test } = require('node:test');
const { openRepositoryAuthorization } = require('../../jiuwenswarm/channels/desktop/electron/repository_authorization.cjs');

function launcher(installed) {
  const commands = [];
  let released = 0;
  function spawnProcess(command, args, options) {
    commands.push({ command, args, options });
    const child = new EventEmitter();
    child.unref = () => { released++; };
    queueMicrotask(() => child.emit(command === installed ? 'spawn' : 'error'));
    return child;
  }
  return { commands, spawnProcess, released: () => released };
}

test('Windows tries installed Google Chrome and passes only the official GitHub device page', async () => {
  const env = { LOCALAPPDATA: 'C:\\Users\\Work Swarm\\AppData\\Local', ProgramFiles: 'C:\\Program Files' };
  const chrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  const launch = launcher(chrome);
  assert.equal(await openRepositoryAuthorization('github', { platform: 'win32', env, spawnProcess: launch.spawnProcess }), true);
  assert.equal(launch.commands.length, 2);
  assert.match(launch.commands[0].command, /AppData\\Local\\Google/);
  assert.deepEqual(launch.commands[1], {
    command: chrome, args: ['--new-tab', 'https://github.com/login/device'],
    options: { detached: true, stdio: 'ignore' },
  });
  assert.equal(launch.released(), 1);
});

test('Chrome launch is scoped to GitHub and GitCode, and an unavailable Chrome is reported', async () => {
  const launch = launcher('google-chrome-stable');
  const options = { platform: 'linux', env: {}, spawnProcess: launch.spawnProcess };
  assert.equal(await openRepositoryAuthorization('https://github.com/login/device', options), false);
  assert.equal(launch.commands.length, 0);
  assert.equal(await openRepositoryAuthorization('gitcode', options), true);
  assert.deepEqual(launch.commands.at(-1).args, ['--new-tab', 'https://gitcode.com/setting/token-classic/create']);
  assert.equal(await openRepositoryAuthorization('github', { ...options, spawnProcess: launcher().spawnProcess }), false);
});
