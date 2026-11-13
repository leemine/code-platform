import { useId, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../components/ui/Button/Button';
import { Input } from '../../components/ui/Input/Input';

/** One account form for the local dialog and cloud page; hosts own their session lifecycle. */
export function AccountLoginForm({ username, password, onUsername, onPassword, onSubmit, busy,
  registering = false, submitLabel, ids, children, footer }: {
  username: string; password: string; onUsername: (value: string) => void; onPassword: (value: string) => void;
  onSubmit: (event: FormEvent) => void; busy: boolean; registering?: boolean; submitLabel?: string;
  ids: { form: string; username: string; password: string; submit: string }; children?: ReactNode; footer?: ReactNode;
}) {
  const { t } = useTranslation();
  const id = useId();
  return <form onSubmit={onSubmit} data-testid={ids.form}>
    <label htmlFor={`${id}-username`} data-testid={`${ids.username}-label`}>{t('auth.username')}</label>
    <Input id={`${id}-username`} data-testid={ids.username} autoComplete="username" required
      value={username} onChange={onUsername} changeOnBlur={false} disabled={busy} />
    <label htmlFor={`${id}-password`} data-testid={`${ids.password}-label`}>{t('auth.password')}</label>
    <Input id={`${id}-password`} data-testid={ids.password} type="password" required
      autoComplete={registering ? 'new-password' : 'current-password'} value={password}
      onChange={onPassword} changeOnBlur={false} disabled={busy} />
    {children}
    <Button type="submit" variant="primary" loading={busy} disabled={!username || !password}
      data-testid={ids.submit}>{submitLabel || t(busy ? 'auth.loggingIn' : 'auth.login')}</Button>
    {footer}
  </form>;
}
