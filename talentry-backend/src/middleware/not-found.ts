import type { Request, Response } from 'express';

/** Runs when no route matched. */
export function notFound(req: Request, res: Response) {
  res.status(404).json({
    message: `Cannot ${req.method} ${req.path}`,
    error: 'Not Found',
    statusCode: 404,
  });
}
