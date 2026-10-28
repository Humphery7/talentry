import type { Request, Response } from 'express';
import { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import * as recommendationsService from '../services/recommendations.service.js';

export const recommendationsRoutes = Router();

recommendationsRoutes.get(
  '/',
  requireAuth,
  async (req: Request, res: Response) => {
    res.json(await recommendationsService.get(req.user!.id));
  },
);

recommendationsRoutes.post(
  '/refresh',
  requireAuth,
  async (req: Request, res: Response) => {
    res.json(await recommendationsService.refresh(req.user!.id));
  },
);
