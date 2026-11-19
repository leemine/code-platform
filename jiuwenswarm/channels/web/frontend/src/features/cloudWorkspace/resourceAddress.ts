const CLOUD_RESOURCE_PREFIX = /^cloud([sp])_([a-f0-9]{24})_/;

/** An address selects a transport; only the server can authorize the resource. */
export function isCloudResource(value: unknown): boolean {
  return typeof value === 'string' && CLOUD_RESOURCE_PREFIX.test(value);
}

export function isCloudSessionInProjectScope(sessionId: unknown, projectId: unknown): boolean {
  if (typeof sessionId !== 'string' || typeof projectId !== 'string') return false;
  const session = CLOUD_RESOURCE_PREFIX.exec(sessionId);
  const project = CLOUD_RESOURCE_PREFIX.exec(projectId);
  return session?.[1] === 's' && project?.[1] === 'p' && session[2] === project[2];
}
