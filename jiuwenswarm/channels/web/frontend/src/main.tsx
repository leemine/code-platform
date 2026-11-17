import './i18n';
import ReactDOM from 'react-dom/client';
import type { ReactNode } from 'react';
import { A2UIProvider } from '@a2ui/react';
import type { A2UIClientEventMessage } from '@a2ui/react';
import { injectStyles } from '@a2ui/react/styles';
import App from './App.tsx'
import { CloudWorkspaceGate } from './features/cloudWorkspace/CloudWorkspaceGate'
import { LocalCloudAccount } from './features/cloudWorkspace/LocalCloudAccount'
import { ShareImageExportRunner } from './features/shareImageExport'
import { openSourceSettingsPageDefinition } from './features/settings/registry/openSourceDefinition'
import type { SettingsRequest } from './features/settings/services/settingsContract'
import { dispatchA2UIAction } from './features/a2ui/actionBridge';
import { installDesktopLocalFilesBridge } from './features/workspace/localFilePicker';
import { getApiBase, getWsBase } from './utils/env';
import './styles/foundation.css'
import './styles/themes/default/light.css'
import './index.css'
import './features/a2ui/a2ui.css'

// Durable desktop drop bridge — must exist before ChatPanel mounts / effect cleanup.
installDesktopLocalFilesBridge();

function flagA2UIIconFontAvailability() {
  if (typeof document === 'undefined' || !('fonts' in document)) {
    return
  }

  const fonts = document.fonts
  const hasMaterialSymbols =
    fonts.check('20px "Material Symbols Outlined"') ||
    fonts.check('20px "Google Symbols"')

  document.documentElement.classList.toggle(
    'a2ui-material-symbols-unavailable',
    !hasMaterialSymbols
  )
}

injectStyles();
flagA2UIIconFontAvailability()
void document.fonts?.ready.then(flagA2UIIconFontAvailability)

function handleA2UIAction(message: A2UIClientEventMessage) {
  void dispatchA2UIAction(message);
}

function resolveOpenSourceSettingsRequest(request: SettingsRequest): SettingsRequest {
  return request
}

const runnerQuery = new URLSearchParams(window.location.search)
const browserRunner = window.location.pathname === '/share-export-runner' && runnerQuery.get('client') === '1'
const runnerSessionId = window.location.pathname === '/share-export-runner'
  ? runnerQuery.get('session_id')?.trim() || null
  : null
const runnerJobId = window.location.pathname === '/share-export-runner'
  ? runnerQuery.get('job_id')?.trim() || null
  : null
const localDesktop = import.meta.env.VITE_WORKSWARM_LOCAL_DESKTOP === 'true'
  && window.jiuwenDesktop?.isElectron === true
  && window.location.hostname === '127.0.0.1'
  && !getApiBase()
  && !getWsBase()

function renderWorkspace(sidebarFooter?: ReactNode, capabilities?: { shareExportDisabledReason: string }) {
  return <App
    shareExportDisabledReason={capabilities?.shareExportDisabledReason}
    sidebarFooter={sidebarFooter}
    settingsPageDefinition={openSourceSettingsPageDefinition}
    resolveSettingsRequest={resolveOpenSourceSettingsRequest}
  />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <A2UIProvider onAction={handleA2UIAction}>
    {browserRunner || runnerJobId || runnerSessionId ? (
      <ShareImageExportRunner
        jobId={runnerJobId}
        sessionId={runnerSessionId}
        locale={runnerQuery.get('locale')}
        client={browserRunner}
      />
    ) : localDesktop ? (
      renderWorkspace(<LocalCloudAccount waitForGateway />)
    ) : (
      <CloudWorkspaceGate>{renderWorkspace}</CloudWorkspaceGate>
    )}
  </A2UIProvider>,
)
