import type { Request, Response } from 'express';
import { Router } from 'express';
import * as jobsService from '../services/jobs.service.js';
import { parseJobId, parseJobsQuery } from '../validators/jobs.validator.js';

export const jobsRoutes = Router();

jobsRoutes.get('/', async (req: Request, res: Response) => {
  res.json(await jobsService.list(parseJobsQuery(req.query)));
});

jobsRoutes.get('/:id', async (req: Request, res: Response) => {
  res.json(await jobsService.getOne(parseJobId(String(req.params.id))));
});
