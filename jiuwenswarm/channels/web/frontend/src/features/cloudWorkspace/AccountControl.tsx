import { useEffect, useState } from 'react';
import { UserRound } from 'lucide-react';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '../../components/ui/DropdownMenu/DropdownMenu';
import './cloudWorkspace.css';

/** Shared account presentation; each host retains its own authentication lifecycle. */
export function AccountControl({ authenticated, username, loginLabel, logoutLabel, onLogin, onLogout, actionsDisabled = false,
  prefix, triggerTestId, logoutTestId }: {
  authenticated: boolean; username?: string; loginLabel: string; logoutLabel: string;
  onLogin?: () => void; onLogout: () => void; actionsDisabled?: boolean;
  prefix: string; triggerTestId: string; logoutTestId: string;
}) {
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [authenticated, username]);
  const label = authenticated ? username || '?' : loginLabel;
  const initials = Array.from((username?.trim() || '?').toUpperCase()).slice(0, 2).join('');
  return <div className="cloud-workspace-account" data-testid={prefix} title={label}>
    {authenticated ? <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger className="cloud-workspace-avatar" aria-label={label} data-testid={triggerTestId}>
        {initials}
      </DropdownMenuTrigger>
      <DropdownMenuContent side="right" align="end" data-testid={`${prefix}-menu`}>
        <p className="cloud-workspace-account-name" data-testid={`${prefix}-name`}>{username}</p>
        <DropdownMenuItem disabled={actionsDisabled} onSelect={onLogout} data-testid={logoutTestId}>{logoutLabel}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu> : <button type="button" className="cloud-workspace-avatar" aria-label={loginLabel}
      onClick={onLogin} data-testid={triggerTestId}><UserRound size={16} aria-hidden="true" /></button>}
  </div>;
}
