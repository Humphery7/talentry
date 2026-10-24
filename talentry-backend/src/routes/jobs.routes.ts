import type { Request, Response } from 'express';
import { Router } from 'express';
import * as jobsService from '../services/jobs.service.js';
import { parseJobId, parseJobsQuery } from '../validators/jobs.validator.js';

export const jobsRoutes = Router();

jobsRoutes.get('/', async (req: Request, res: Response) => {
  res.json(await jobsService.list(parseJobsQuery(req.query)));
});

// Must stay before `/:id`, otherwise Express treats "facets" as an id.
jobsRoutes.get('/facets', async (_req: Request, res: Response) => {
  res.json(await jobsService.facets());
});

jobsRoutes.get('/:id', async (req: Request, res: Response) => {
  res.json(await jobsService.getOne(parseJobId(String(req.params.id))));
});

