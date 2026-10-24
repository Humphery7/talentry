import type { Request, Response } from 'express';
import { Router } from 'express';
import * as client from 'openid-client';
import { oidc_env } from '../config/env.js';
import { requireAuth } from '../middleware/auth.js';
import * as authService from '../services/auth.service.js';
import { getOidcConfig } from '../services/openid.service.js';
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

// The exact URL Google sends the browser back to. It must be listed in the
// Google Cloud console, and must be the same value we send in both requests.
function callbackUrl(req: Request) {
  return (
    oidc_env.redirect_url ??
    `${req.protocol}://${req.get('host')}/auth/google/callback`
  );
}

// Step 1: send the browser to Google.
authRoutes.get('/google/login', async (req: Request, res: Response) => {
  const config = await getOidcConfig();

  const codeVerifier = client.randomPKCECodeVerifier();
  const codeChallenge = await client.calculatePKCECodeChallenge(codeVerifier);
  const state = client.randomState();
  const nonce = client.randomNonce();

  // Remember the one-time values so the callback can prove the response is ours.
  req.session.oidc = { codeVerifier, state, nonce };

  const url = client.buildAuthorizationUrl(config, {
    redirect_uri: callbackUrl(req),
    scope: 'openid email profile',
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    state,
    nonce,
  });
  res.redirect(url.href);
});

// Step 2: Google sends the browser back here with a code we exchange for the user.
authRoutes.get('/google/callback', async (req: Request, res: Response) => {
  const saved = req.session.oidc;
  if (!saved) {
    return res.status(400).send('Login session expired, please try again.');
  }

  try {
    const config = await getOidcConfig();
    const currentUrl = new URL(req.originalUrl, callbackUrl(req));

    const tokens = await client.authorizationCodeGrant(config, currentUrl, {
      pkceCodeVerifier: saved.codeVerifier,
      expectedState: saved.state,
      expectedNonce: saved.nonce,
    });

    const claims = tokens.claims();
    const { user, accessToken } = await authService.loginWithGoogle({
      name: claims?.name as string | undefined,
      email: claims?.email as string | undefined,
    });

    // The handshake is done, so drop the short-lived session and hand the
    // browser our normal JWT. It travels in the URL hash, which is not sent to
    // any server, and the frontend saves it and cleans the address bar.
    const params = new URLSearchParams({
      token: accessToken,
      name: user.name,
      email: user.email,
    });
    req.session.destroy(() =>
      res.redirect(`${oidc_env.frontend_url}/jobs#${params}`),
    );
  } catch (err) {
    console.error('Google login failed:', err);
    req.session.destroy(() =>
      res.redirect(`${oidc_env.frontend_url}/?auth=login#error=google`),
    );
  }
});
