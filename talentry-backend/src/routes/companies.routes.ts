import type { Request, Response } from 'express';
import { Router } from 'express';
import * as companiesService from '../services/companies.service.js';
import { parseCompaniesQuery } from '../validators/companies.validator.js';

export const companiesRoutes = Router();

companiesRoutes.get('/', async (req: Request, res: Response) => {
  res.json(await companiesService.list(parseCompaniesQuery(req.query)));
});

companiesRoutes.get('/:slug', async (req: Request, res: Response) => {
  res.json(await companiesService.getOne(String(req.params.slug)));
});
