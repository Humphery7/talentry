// Tiny hand-written validation helpers.
//
// Each helper checks ONE field. If the field is invalid it adds a readable
// message to the `errors` list; after checking every field, call
// `throwIfInvalid(errors)` once to respond with a single 400 listing all problems.
//
// Only fields a validator explicitly reads are returned, so unknown fields in
// a request body or query string are simply ignored.
import { HttpError } from '../utils/http-error.js';

export type Input = Record<string, unknown>;

export function throwIfInvalid(errors: string[]) {
  if (errors.length) throw new HttpError(400, errors);
}

/** A required string with optional length limits. */
export function requiredString(
  input: Input,
  field: string,
  errors: string[],
  { min = 0, max = Infinity, notEmpty = false } = {},
): string {
  const value = input[field];
  if (typeof value !== 'string') {
    errors.push(`${field} must be a string`);
    return '';
  }
  if (notEmpty && value === '') errors.push(`${field} should not be empty`);
  else if (value.length < min)
    errors.push(`${field} must be longer than or equal to ${min} characters`);
  else if (value.length > max)
    errors.push(`${field} must be shorter than or equal to ${max} characters`);
  return value;
}

/** A required string that must look like an email address. */
export function requiredEmail(
  input: Input,
  field: string,
  errors: string[],
  max = 255,
): string {
  const value = input[field];
  if (typeof value !== 'string' || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
    errors.push(`${field} must be an email`);
    return '';
  }
  if (value.length > max)
    errors.push(`${field} must be shorter than or equal to ${max} characters`);
  return value;
}

/** A required whole number (used for JSON bodies, where numbers are real numbers). */
export function requiredInteger(
  input: Input,
  field: string,
  errors: string[],
  { min = -Infinity } = {},
): number {
  const value = input[field];
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    errors.push(`${field} must be an integer number`);
    return 0;
  }
  if (value < min) errors.push(`${field} must not be less than ${min}`);
  return value;
}

/** An optional string (query strings are always strings). */
export function optionalString(
  input: Input,
  field: string,
  errors: string[],
): string | undefined {
  const value = input[field];
  if (value === undefined) return undefined;
  if (typeof value !== 'string') {
    errors.push(`${field} must be a string`);
    return undefined;
  }
  return value;
}

/** An optional number read from a query string like `?lo=50`. */
export function optionalNumber(
  input: Input,
  field: string,
  errors: string[],
  { integer = false, min = -Infinity, max = Infinity } = {},
): number | undefined {
  const raw = input[field];
  if (raw === undefined) return undefined;
  const value = Number(raw);
  if (integer ? !Number.isInteger(value) : !Number.isFinite(value)) {
    errors.push(
      integer
        ? `${field} must be an integer number`
        : `${field} must be a number conforming to the specified constraints`,
    );
    return undefined;
  }
  if (value < min) errors.push(`${field} must not be less than ${min}`);
  else if (value > max) errors.push(`${field} must not be greater than ${max}`);
  return value;
}

/** An optional string that must be one of a fixed list of values. */
export function optionalOneOf<T extends string>(
  input: Input,
  field: string,
  errors: string[],
  allowed: readonly T[],
): T | undefined {
  const value = input[field];
  if (value === undefined) return undefined;
  if (typeof value !== 'string' || !allowed.includes(value as T)) {
    errors.push(
      `${field} must be one of the following values: ${allowed.join(', ')}`,
    );
    return undefined;
  }
  return value as T;
}
