/**
 * Throw this from a service, validator or middleware to send an error response:
 *
 *   throw new HttpError(404, 'Job not found.');
 *
 * The error-handler middleware turns it into JSON. `details` may be a list
 * (used for validation errors, one entry per invalid field).
 */
export class HttpError extends Error {
  readonly status: number;
  readonly details: string | Array<string>;
  constructor(status: number, details: string | Array<string>) {
    super(Array.isArray(details) ? details.join(', ') : details);
    this.status = status;
    this.details = details;

  }
}
