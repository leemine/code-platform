import { useEffect, useRef, useState } from 'react';
import {
  localCloudModelSyncRequest,
  onLocalCloudAccountChange,
  type LocalCloudModelSyncOperation,
  type LocalCloudModelSyncStatus,
} from '../../../cloudWorkspace/localCloudAccountClient';

export function useCloudModelSync() {
  const [status, setStatus] = useState<LocalCloudModelSyncStatus | null>(null);
  const [busyModel, setBusyModel] = useState<string | null>(null);
  const generation = useRef(0);
  const renderedGeneration = generation.current;

  useEffect(() => {
    function reload() {
      const current = ++generation.current;
      setStatus(null);
      setBusyModel(null);
      void localCloudModelSyncRequest().then(
        value => { if (current === generation.current) setStatus(value); },
        () => { /* Keep the switch unavailable until the account status is confirmed. */ },
      );
    }
    const off = onLocalCloudAccountChange(reload);
    reload();
    return () => {
      generation.current++;
      off();
    };
  }, []);

  async function sync(operation: LocalCloudModelSyncOperation) {
    const scope = status?.scope;
    if (!scope || renderedGeneration !== generation.current) return undefined;
    setBusyModel(operation.model_id);
    try {
      const next = await localCloudModelSyncRequest({ ...operation, scope });
      if (renderedGeneration !== generation.current) return undefined;
      if (next?.scope !== scope) throw new Error('Cloud account changed');
      setStatus(next);
      if (operation.operation === 'refresh' || operation.enabled) {
        window.dispatchEvent(new Event('jiuwenswarm-cloud-catalog-refresh'));
      }
      return next;
    } catch (error) {
      if (renderedGeneration === generation.current) throw error;
      return undefined;
    } finally {
      if (renderedGeneration === generation.current) setBusyModel(null);
    }
  }

  return { status, busyModel, sync };
}
