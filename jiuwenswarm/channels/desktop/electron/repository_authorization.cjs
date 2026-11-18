const { spawn } = require('node:child_process');
const path = require('node:path');

const authorizationUrls = new Map([
  ['github', 'https://github.com/login/device'],
  ['gitcode', 'https://gitcode.com/setting/token-classic/create'],
]);

function chromeExecutables(platform, env) {
  if (platform === 'win32') {
    return [
      ...[env.LOCALAPPDATA, env.ProgramFiles, env['ProgramFiles(x86)'], env.ProgramW6432]
        .filter(Boolean)
        .map(base => path.win32.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe')),
      'chrome.exe',
    ];
  }
  if (platform === 'darwin') {
    const executable = 'Google Chrome.app/Contents/MacOS/Google Chrome';
    return [
      path.posix.join('/Applications', executable),
      ...(env.HOME ? [path.posix.join(env.HOME, 'Applications', executable)] : []),
    ];
  }
  if (platform === 'linux') return ['google-chrome', 'google-chrome-stable'];
  return [];
}

async function openRepositoryAuthorization(provider, {
  platform = process.platform, env = process.env, spawnProcess = spawn,
} = {}) {
  const url = authorizationUrls.get(provider);
  if (!url) return false;
  for (const executable of new Set(chromeExecutables(platform, env))) {
    const opened = await new Promise(resolve => {
      const chrome = spawnProcess(executable, ['--new-tab', url], { detached: true, stdio: 'ignore' });
      chrome.once('error', () => resolve(false));
      chrome.once('spawn', () => {
        chrome.unref();
        resolve(true);
      });
    });
    if (opened) return true;
  }
  return false;
}

module.exports = { openRepositoryAuthorization };
