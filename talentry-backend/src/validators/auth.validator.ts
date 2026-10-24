import {
  requiredEmail,
  requiredString,
  throwIfInvalid,
  type Input,
} from './rules.js';

export interface SignupInput {
  name: string;
  email: string;
  password: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export function parseSignup(body: Input = {}): SignupInput {
  const errors: Array<string> = [];
  const input = {
    name: requiredString(body, 'name', errors, { notEmpty: true, max: 120 }),
    email: requiredEmail(body, 'email', errors),
    password: requiredString(body, 'password', errors, { min: 8, max: 128 }),
  };
  throwIfInvalid(errors);
  return input;
}

export function parseLogin(body: Input = {}): LoginInput {
  const errors: string[] = [];
  const input = {
    email: requiredEmail(body, 'email', errors),
    password: requiredString(body, 'password', errors, { min: 8, max: 128 }),
  };
  throwIfInvalid(errors);
  return input;
}
