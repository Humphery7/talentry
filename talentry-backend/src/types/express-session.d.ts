import 'express-session';

declare module 'express-session' {
    interface SessionData {
        oidc?: { codeVerifier: string, state: string, nonce: string },
        userId?: string
    }
}

