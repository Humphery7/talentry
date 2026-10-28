import type { Request, Response } from 'express';
import { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import * as notificationsService from '../services/notifications.service.js';
import { parseNotificationIds } from '../validators/notifications.validator.js';

export const notificationsRoutes = Router();
notificationsRoutes.use(requireAuth);

notificationsRoutes.get('/', async (req: Request, res: Response) => {
  res.json(await notificationsService.list(req.user!.id));
});

notificationsRoutes.post('/read', async (req: Request, res: Response) => {
  const ids = parseNotificationIds(req.body);
  res.json(await notificationsService.markRead(req.user!.id, ids));
});
