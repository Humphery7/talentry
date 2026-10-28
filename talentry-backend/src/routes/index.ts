// Every URL prefix the API serves, in one place.
import { Router } from 'express';
import { agentApplicationsRoutes } from './agent-applications.routes.js';
import { applicationsRoutes } from './applications.routes.js';
import { authRoutes } from './auth.routes.js';
import { candidateProfileRoutes } from './candidate-profile.routes.js';
import { companiesRoutes } from './companies.routes.js';
import { interviewRoutes } from './interview.routes.js';
import { jobsRoutes } from './jobs.routes.js';
import { notificationsRoutes } from './notifications.routes.js';
import { recommendationsRoutes } from './recommendations.routes.js';

export const routes = Router();

routes.get('/', (_req, res) => {
  res.send('Hello World!');
});
routes.use('/auth', authRoutes);
routes.use('/jobs', jobsRoutes);
routes.use('/companies', companiesRoutes);
routes.use('/applications', applicationsRoutes);
routes.use('/agent-applications', agentApplicationsRoutes);
routes.use('/notifications', notificationsRoutes);
routes.use('/candidate-profile', candidateProfileRoutes);
routes.use('/recommendations', recommendationsRoutes);
routes.use('/interview', interviewRoutes);
