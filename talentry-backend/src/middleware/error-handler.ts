import { STATUS_CODES } from 'node:http';
import type { NextFunction, Request, Response } from 'express';
import { HttpError } from '../utils/http-error.js';

/**
 * The single place where errors become responses. Every error body looks like
 * `{ message, error, statusCode }`, which is what the frontend already expects.
 */
export function errorHandler(
  err: unknown,
  _req: Request,
  res: Response,
  _next: NextFunction,
) {
  // Errors we threw on purpose (validation, 401, 404, ...).
  if (err instanceof HttpError) {
    return sendError(res, err.status, err.details);
  }

  // Errors raised by Express itself, e.g. malformed JSON or a body that is too large.
  const status = (err as { status?: number })?.status;
  if (typeof status === 'number' && status >= 400 && status < 500) {
    return sendError(res, status, (err as Error).message);
  }

  // Anything else is a bug or an outage: log it, but don't leak details.
  console.error(err);
  sendError(res, 500, 'Internal server error');
}

function sendError(res: Response, status: number, message: string | string[]) {
  res
    .status(status)
    .json({ message, error: STATUS_CODES[status], statusCode: status });
}
