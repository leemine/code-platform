/** An address selects a transport; only the server can authorize the resource. */
export function isCloudResource(value: unknown): boolean {
  return typeof value === 'string' && /^cloud[sp]_[a-f0-9]{24}_/.test(value);
}
