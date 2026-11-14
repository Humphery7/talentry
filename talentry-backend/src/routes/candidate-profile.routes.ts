import type { Request, Response } from 'express';
import express, { Router } from 'express';
import { requireAuth } from '../middleware/auth.js';
import * as candidateProfileService from '../services/candidate-profile.service.js';
import { HttpError } from '../utils/http-error.js';
import { parseCandidateProfile } from '../validators/candidate-profile.validator.js';

export const candidateProfileRoutes = Router();

const CV_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/octet-stream',
];

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
// and encoded filename in headers. PDF and DOCX are both accepted; the bytes
// are kept so a DOCX upload can keep its own layout.
candidateProfileRoutes.put(
  '/cv',
  requireAuth,
  express.raw({ type: CV_TYPES, limit: '5mb' }),
  async (req: Request, res: Response) => {
    if (!Buffer.isBuffer(req.body) || req.body.length === 0) {
      throw new HttpError(400, 'Upload a PDF or DOCX, maximum of 5MB.');
    }
    let rawName = req.header('x-filename') ?? 'cv';
    try {
      rawName = decodeURIComponent(rawName);
    } catch {
      // Keep the raw header if it is not valid percent-encoding.
    }
    const filename = rawName.replace(/[^\w.\- ]+/g, '_').slice(0, 120) || 'cv';

    // Trust the bytes, not the header: browsers are inconsistent with DOCX.
    const isPdf = req.body.subarray(0, 5).toString('latin1') === '%PDF-';
    const isZip = req.body[0] === 0x50 && req.body[1] === 0x4b;
    if (!isPdf && !isZip) {
      throw new HttpError(400, 'Upload a PDF or DOCX, maximum of 5MB.');
    }
    const mime = isPdf
      ? candidateProfileService.PDF_MIME
      : candidateProfileService.DOCX_MIME;

    let text: string;
    try {
      text = isPdf
        ? await candidateProfileService.parsePDF(req.body)
        : await candidateProfileService.parseDocx(req.body);
    } catch {
      throw new HttpError(
        400,
        'Could not read that file. Try saving it again as PDF or DOCX.',
      );
    }
    if (!text.trim()) {
      throw new HttpError(
        400,
        'That file has no selectable text. Export it again as PDF or DOCX.',
      );
    }

    res.json(
      await candidateProfileService.saveCv(
        req.user!.id,
        filename,
        mime,
        text,
        req.body,
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
    // This is the extracted text the profile edits; the original file is kept
    // separately for layout-preserving DOCX applications.
    const name = cv.filename.replace(/\.[^.]+$/, '') || 'cv';
    res
      .type('text/plain')
      .set('Content-Disposition', `attachment; filename="${name}.txt"`)
      .send(cv.data);
  },
);
