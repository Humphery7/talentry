import type { Request, Response } from 'express';
import { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import * as aiSettingsService from '../services/ai-settings.service.js';
import { HttpError } from '../utils/http-error.js';

export const aiSettingsRoutes = Router();

// The browser only ever sees `{ configured, hint, updatedAt }`. The key itself
// is write-only: it goes in, and nothing ever reads it back out.
aiSettingsRoutes.get(
  '/',
  requireAuth,
  async (req: Request, res: Response) => {
    res.json(await aiSettingsService.get(req.user!.id));
  },
);

aiSettingsRoutes.put(
  '/',
  requireAuth,
  async (req: Request, res: Response) => {
    const apiKey = (req.body as { apiKey?: unknown } | undefined)?.apiKey;
    if (typeof apiKey !== 'string' || !apiKey.trim()) {
      throw new HttpError(400, 'Enter your Gemini API key.');
    }
    res.json(await aiSettingsService.save(req.user!.id, apiKey));
  },
);

aiSettingsRoutes.delete(
  '/',
  requireAuth,
  async (req: Request, res: Response) => {
    res.json(await aiSettingsService.remove(req.user!.id));
  },
);
