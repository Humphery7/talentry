import type { NextFunction, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import { env } from '../config/env.js';
import { HttpError } from '../utils/http-error.js';

export interface AuthUser {
  id: string;
  email: string;
}

// Lets controllers read `req.user` with the right type.
declare module 'express-serve-static-core' {
  interface Request {
    user?: AuthUser;
  }
}

/** Protects a route: checks `Authorization: Bearer <jwt>` and sets `req.user`. */
export function requireAuth(req: Request, _res: Response, next: NextFunction) {
  const header = req.headers.authorization;
  const token = header?.startsWith('Bearer ') ? header.slice(7) : undefined;
  if (!token) throw new HttpError(401, 'Missing bearer token.');

  try {
    const payload = jwt.verify(token, env.jwtSecret) as {
      sub: string;
      email: string;
    };
    req.user = { id: payload.sub, email: payload.email };
  } catch {
    throw new HttpError(401, 'Invalid or expired token.');
  }
  next();
}
