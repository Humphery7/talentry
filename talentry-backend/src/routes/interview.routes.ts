import type { Request, Response } from 'express';
import { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import * as interviewService from '../services/interview.service.js';
import {
  parseAnswer,
  parseAttemptId,
  parseItemId,
  parseJobIdQuery,
  parseStartAttempt,
} from '../validators/interview.validator.js';

export const interviewRoutes = Router();

interviewRoutes.post(
  '/attempts',
  requireAuth,
  async (req: Request, res: Response) => {
    const { jobId, newAttempt } = parseStartAttempt(req.body);
    res
      .status(201)
      .json(await interviewService.startAttempt(req.user!.id, jobId, newAttempt));
  },
);

interviewRoutes.get(
  '/attempts',
  requireAuth,
  async (req: Request, res: Response) => {
    const jobId = parseJobIdQuery(req.query.jobId);
    res.json(await interviewService.listAttempts(req.user!.id, jobId));
  },
);

interviewRoutes.get(
  '/attempts/:id/feedback',
  requireAuth,
  async (req: Request, res: Response) => {
    const attemptId = parseAttemptId(String(req.params.id));
    res.json(await interviewService.getFeedback(req.user!.id, attemptId));
  },
);

interviewRoutes.get(
  '/attempts/:id',
  requireAuth,
  async (req: Request, res: Response) => {
    const attemptId = parseAttemptId(String(req.params.id));
    res.json(await interviewService.getAttempt(req.user!.id, attemptId));
  },
);

interviewRoutes.put(
  '/attempts/:id/responses/:itemId',
  requireAuth,
  async (req: Request, res: Response) => {
    const attemptId = parseAttemptId(String(req.params.id));
    const itemId = parseItemId(String(req.params.itemId));
    const answer = parseAnswer(req.body);
    res.json(
      await interviewService.submitResponse(
        req.user!.id,
        attemptId,
        itemId,
        answer,
      ),
    );
  },
);
