import type { Request, Response } from 'express';
import { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import * as authService from '../services/auth.service.js';
import { parseLogin, parseSignup } from '../validators/auth.validator.js';

export const authRoutes = Router();

authRoutes.post('/signup', async (req: Request, res: Response) => {
  const { name, email, password } = parseSignup(req.body);
  res.status(201).json(await authService.signup(name, email, password));
});

authRoutes.post('/login', async (req: Request, res: Response) => {
  const { email, password } = parseLogin(req.body);
  res.json(await authService.login(email, password));
});

authRoutes.get('/profile', requireAuth, async (req: Request, res: Response) => {
  res.json(await authService.getProfile(req.user!.id));
});
