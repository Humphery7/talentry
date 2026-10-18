// Every URL prefix the API serves, in one place.
import { Router } from 'express';
import { applicationsRoutes } from './applications.routes.js';
import { authRoutes } from './auth.routes.js';
import { companiesRoutes } from './companies.routes.js';
import { jobsRoutes } from './jobs.routes.js';

export const routes = Router();

routes.get('/', (_req, res) => {
  res.send('Hello World!');
});
routes.use('/auth', authRoutes);
routes.use('/jobs', jobsRoutes);
routes.use('/companies', companiesRoutes);
routes.use('/applications', applicationsRoutes);
