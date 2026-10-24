import type { Request, Response } from 'express';
import express, { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import * as candidateProfileService from '../services/candidate-profile.service.js';
import { HttpError } from '../utils/http-error.js';
import { parseCandidateProfile } from '../validators/candidate-profile.validator.js';

export const candidateProfileRoutes = Router();

const CV_TYPES = ['application/pdf'];

candidateProfileRoutes.get(
  '/',
  requireAuth,
  async (req: Request, res: Response) => {
    res.json(await candidateProfileService.get(req.user!.id));
  },
);

candidateProfileRoutes.put(
  '/',
  requireAuth,
  async (req: Request, res: Response) => {
    const input = parseCandidateProfile(req.body);
    res.json(await candidateProfileService.save(req.user!.id, input));
  },
);

// The browser sends the file raw (no multipart parser needed) with its type
// and encoded filename in headers.
candidateProfileRoutes.put(
  '/cv',
  requireAuth,
  express.raw({ type: CV_TYPES, limit: '5mb' }),
  async (req: Request, res: Response) => {
    if (!Buffer.isBuffer(req.body) || req.body.length === 0) {
      throw new HttpError(400, 'Upload a PDF, maximum of 5MB.');
    }
    let rawName = req.header('x-filename') ?? 'cv';
    try {
      rawName = decodeURIComponent(rawName);
    } catch {
      // Keep the raw header if it is not valid percent-encoding.
    }
    const filename = rawName.replace(/[^\w.\- ]+/g, '_').slice(0, 120) || 'cv';
    const mime = req.header('content-type') ?? 'application/octet-stream';
    const pdfparse = await candidateProfileService.parsePDF(req.body);
    res.json(
      await candidateProfileService.saveCv(
        req.user!.id,
        filename,
        mime,
        pdfparse,
      ),
    );
  },
);

candidateProfileRoutes.get(
  '/cv',
  requireAuth,
  async (req: Request, res: Response) => {
    const cv = await candidateProfileService.getCv(req.user!.id);
    if (!cv) throw new HttpError(404, 'No CV uploaded.');
    // Only the extracted text is stored, so this is not the original PDF.
    const name = cv.filename.replace(/\.[^.]+$/, '') || 'cv';
    res
      .type('text/plain')
      .set('Content-Disposition', `attachment; filename="${name}.txt"`)
      .send(cv.data);
  },
);
