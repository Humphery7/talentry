import type { Request, Response } from 'express';
import { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import * as applicationsService from '../services/applications.service.js';
import { parseApply } from '../validators/applications.validator.js';

export const applicationsRoutes = Router();

applicationsRoutes.post(
  '/',
  requireAuth,
  async (req: Request, res: Response) => {
    const { jobId } = parseApply(req.body);
    res.status(201).json(await applicationsService.apply(req.user!.id, jobId));
  },
);

applicationsRoutes.get(
  '/',
  requireAuth,
  async (req: Request, res: Response) => {
    res.json(await applicationsService.listForUser(req.user!.id));
  },
);
