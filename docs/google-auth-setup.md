# Google sign-in setup

CoreAI uses Google Identity Services for browser sign-in and verifies Google ID tokens on the
FastAPI backend. The integration requires a Web application client ID. It does not use a Google
client secret, access token, or refresh token.

## Google Cloud configuration

1. Open Google Auth Platform in a Google Cloud project owned by CoreAI.
2. Configure the app name, CoreAI logo, support email, and developer contact.
3. Add `coreai.uz` as an authorized domain.
4. Choose the appropriate audience and add test users while the app remains in testing mode.
5. Create an OAuth client with application type **Web application**.
6. Add the JavaScript origins used by each environment:
   - `http://localhost:3000`
   - the staging chat origin
   - `https://chat.coreai.uz`
7. Copy the generated client ID. This flow uses the JavaScript callback API, so it does not require
   an OAuth redirect URI.

## CoreAI configuration

Add the Web client ID to the environment used by the backend:

```dotenv
GOOGLE_CLIENT_ID=000000000000-example.apps.googleusercontent.com
GOOGLE_PENDING_TTL_S=600
```

The Docker Compose configuration passes both variables to FastAPI. Restart the backend after
changing them:

```bash
docker compose up -d --build backend
```

The frontend reads the public client ID from `GET /api/auth/providers` at runtime. Google buttons
are shown only when the provider is enabled, so frontend images do not need an environment-specific
client ID baked into the JavaScript bundle.

## Verification

1. Open `http://localhost:3000/register` and confirm the Google button renders.
2. Sign in with an allowed Google test user.
3. For a new Google identity, confirm that CoreAI opens `/register/google` and requires legal
   acceptance before creating the account.
4. Complete optional onboarding and confirm the anonymous chat history remains attached.
5. Log out and confirm the same Google identity signs in without repeating registration.
6. Sign in to a password account, open `/account`, connect Google, and verify it appears under
   sign-in methods.
7. Confirm a Google-only account cannot disconnect its only sign-in method.

Production must use HTTPS with `COOKIE_SECURE=true`. Keep the list of authorized JavaScript origins
limited to origins that serve the CoreAI chat/API frontend.
