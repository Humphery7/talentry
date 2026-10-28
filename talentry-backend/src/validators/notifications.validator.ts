import { HttpError } from '../utils/http-error.js';

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function parseNotificationIds(body: unknown): string[] | 'all' {
  const ids = (body as { ids?: unknown } | null)?.ids;
  if (ids === 'all') return ids;
  if (
    !Array.isArray(ids) ||
    ids.length > 100 ||
    !ids.every((id) => typeof id === 'string' && UUID.test(id))
  ) {
    throw new HttpError(
      400,
      'ids must be "all" or a list of notification ids.',
    );
  }
  return ids;
}
