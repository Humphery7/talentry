import type { Request, Response } from 'express';
import { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import * as agentApplicationsService from '../services/agent-applications.service.js';
import {
  parseAgentApply,
  parseAnswers,
  parseApplicationId,
  parseDocument,
  parseDocumentKind,
  parseFieldEdit,
  parseQueueTop,
  parseRetry,
} from '../validators/agent-applications.validator.js';

export const agentApplicationsRoutes = Router();
agentApplicationsRoutes.use(requireAuth);

const id = (req: Request) => parseApplicationId(String(req.params.id));
const uid = (req: Request) => req.user!.id;

agentApplicationsRoutes.post('/', async (req: Request, res: Response) => {
  const { jobIds } = parseAgentApply(req.body);
  res.status(202).json(await agentApplicationsService.start(uid(req), jobIds));
});

agentApplicationsRoutes.post(
  '/queue-top',
  async (req: Request, res: Response) => {
    const { limit } = parseQueueTop(req.body);
    res
      .status(201)
      .json(await agentApplicationsService.queueTop(uid(req), limit));
  },
);

agentApplicationsRoutes.get('/', async (req: Request, res: Response) => {
  res.json(await agentApplicationsService.list(uid(req)));
});

agentApplicationsRoutes.get('/:id', async (req: Request, res: Response) => {
  res.json(await agentApplicationsService.get(uid(req), id(req)));
});

agentApplicationsRoutes.post(
  '/:id/answers',
  async (req: Request, res: Response) => {
    const { answers } = parseAnswers(req.body);
    res.json(await agentApplicationsService.answer(uid(req), id(req), answers));
  },
);

agentApplicationsRoutes.post(
  '/:id/resume',
  async (req: Request, res: Response) => {
    res.json(await agentApplicationsService.resume(uid(req), id(req)));
  },
);

agentApplicationsRoutes.post(
  '/:id/manual-complete',
  async (req: Request, res: Response) => {
    res.json(
      await agentApplicationsService.markSubmittedManually(uid(req), id(req)),
    );
  },
);

agentApplicationsRoutes.put(
  '/:id/fields',
  async (req: Request, res: Response) => {
    const { key, value } = parseFieldEdit(req.body);
    res.json(
      await agentApplicationsService.editField(uid(req), id(req), key, value),
    );
  },
);

agentApplicationsRoutes.put(
  '/:id/documents/:kind',
  async (req: Request, res: Response) => {
    const kind = parseDocumentKind(String(req.params.kind));
    const { content } = parseDocument(req.body);
    res.json(
      await agentApplicationsService.saveDocument(
        uid(req),
        id(req),
        kind,
        content,
      ),
    );
  },
);

agentApplicationsRoutes.post(
  '/:id/documents/:kind/regenerate',
  async (req: Request, res: Response) => {
    const kind = parseDocumentKind(String(req.params.kind));
    res.json(
      await agentApplicationsService.regenerate(uid(req), id(req), kind),
    );
  },
);

agentApplicationsRoutes.post(
  '/:id/approve',
  async (req: Request, res: Response) => {
    res.json(await agentApplicationsService.approve(uid(req), id(req)));
  },
);

agentApplicationsRoutes.post(
  '/:id/retry',
  async (req: Request, res: Response) => {
    const { confirmNotSubmitted } = parseRetry(req.body);
    res.json(
      await agentApplicationsService.retry(
        uid(req),
        id(req),
        confirmNotSubmitted,
      ),
    );
  },
);

agentApplicationsRoutes.post(
  '/:id/cancel',
  async (req: Request, res: Response) => {
    res.json(await agentApplicationsService.cancel(uid(req), id(req)));
  },
);
