# Deploy CareerOps to Google Cloud Run

This puts your own CareerOps online behind Google sign-in that only your account can pass.

```text
                 Google sign-in (your email only)
                              |
Browser --> Cloud Run service "careerops"  (FastAPI UI/API + Chromium apply agent)
                 |         |            \
                 |         |             +--> Secret Manager (keys)
                 |         +--> Cloud Storage bucket mounted at /data (resumes, PDFs, screenshots)
                 +--> PostgreSQL (Neon free tier, or Cloud SQL)
                              ^
Cloud Scheduler (every 15 min) --> Cloud Run job "careerops-discovery" (job scan)
```

The web app scales to zero when you're not using it, and the discovery job runs for a minute or two every 15 minutes, so day-to-day usage stays small. Set a budget alert anyway (step 9).

Commands are for **PowerShell on Windows**. You need the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) and a Google Cloud project with billing enabled.

## 1. Set your variables

```powershell
$PROJECT = "your-project-id"
$REGION  = "us-west1"                       # Oregon, closest to Seattle
$BUCKET  = "$PROJECT-careerops-data"
$SA      = "careerops-run@$PROJECT.iam.gserviceaccount.com"
$IMAGE   = "$REGION-docker.pkg.dev/$PROJECT/careerops/app:latest"

gcloud auth login
gcloud config set project $PROJECT
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com
```

## 2. Database

**Neon (free tier, easiest):** create a project at neon.tech and copy its connection string. Change the start from `postgresql://` to `postgresql+psycopg://` and keep `?sslmode=require`:

```text
postgresql+psycopg://USER:PASSWORD@ep-xxxx.us-west-2.aws.neon.tech/neondb?sslmode=require
```

CareerOps creates its tables on first start.

*Cloud SQL instead:* create a PostgreSQL instance, add `--add-cloudsql-instances PROJECT:REGION:INSTANCE` to the deploy commands below, and use `postgresql+psycopg://USER:PASSWORD@/DB?host=/cloudsql/PROJECT:REGION:INSTANCE`.

## 3. Storage bucket and service account

```powershell
gcloud storage buckets create gs://$BUCKET --location=$REGION --uniform-bucket-level-access
gcloud iam service-accounts create careerops-run --display-name "CareerOps Cloud Run"
gcloud storage buckets add-iam-policy-binding gs://$BUCKET --member "serviceAccount:$SA" --role roles/storage.objectUser
gcloud projects add-iam-policy-binding $PROJECT --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor
gcloud artifacts repositories create careerops --repository-format=docker --location=$REGION
```

## 4. Google sign-in client

In the Cloud Console, open **Google Auth Platform**:

1. **Branding:** app name `CareerOps`, your email as support contact.
2. **Audience:** *External*, leave it in **Testing**, and add your Gmail address as a test user. CareerOps only asks for `openid email`, so no Google verification is needed.
3. **Clients → Create client → Web application.** Leave the redirect URI empty for now (you add it in step 7). Copy the **client ID** and **client secret**.

## 5. Secrets

In **Security → Secret Manager → Create secret**, create one secret per value. Pasting values in the Console keeps them out of your shell history.

| Secret name | Value |
|---|---|
| `careerops-database-url` | the connection string from step 2 |
| `careerops-secret-key` | output of `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `careerops-google-client-secret` | the client secret from step 4 |
| `careerops-openai-api-key` | your OpenAI key (optional; leave out with `LLM_PROVIDER: local`) |
| `careerops-alert-ingest-token` | another random value, if you use the alert-email endpoint |

Other keys from `.env` (Adzuna, USAJOBS, IMAP, Telegram, Slack) work the same way. Add a secret, then add it to the `--set-secrets` list below as `ENV_NAME=secret-name:latest`.

## 6. Settings file, build, deploy

```powershell
Copy-Item deploy/gcp/env.example.yaml deploy/gcp/env.yaml
notepad deploy/gcp/env.yaml        # set GOOGLE_CLIENT_ID and ALLOWED_EMAILS; leave BASE_URL for now

$SECRETS = "DATABASE_URL=careerops-database-url:latest,SECRET_KEY=careerops-secret-key:latest,GOOGLE_CLIENT_SECRET=careerops-google-client-secret:latest,OPENAI_API_KEY=careerops-openai-api-key:latest"

gcloud builds submit --tag $IMAGE

gcloud run deploy careerops --image $IMAGE --region $REGION --service-account $SA `
  --execution-environment gen2 --memory 2Gi --cpu 2 --timeout 900 --concurrency 4 --max-instances 2 `
  --allow-unauthenticated `
  --env-vars-file deploy/gcp/env.yaml --set-secrets $SECRETS `
  --add-volume "name=data,type=cloud-storage,bucket=$BUCKET" --add-volume-mount "volume=data,mount-path=/data"
```

`--allow-unauthenticated` only lets requests reach the container. CareerOps's own Google sign-in then turns away anyone who isn't on `ALLOWED_EMAILS`, and the app refuses to start at all if `AUTH_MODE` is not `google` in production. `--memory 2Gi` is for Chromium, and `--timeout 900` gives the apply agent up to 15 minutes per run.

## 7. Connect the sign-in redirect

```powershell
$URL = gcloud run services describe careerops --region $REGION --format "value(status.url)"
$URL
```

1. In **Google Auth Platform → Clients → your client**, add the authorized redirect URI `$URL/auth/callback`, for example `https://careerops-123456789.us-west1.run.app/auth/callback`.
2. Put the same `$URL` as `BASE_URL` in `deploy/gcp/env.yaml`, then apply it:

```powershell
gcloud run services update careerops --region $REGION --env-vars-file deploy/gcp/env.yaml
```

Open `$URL` and sign in with Google. You should land on the dashboard with your email shown in the sidebar.

## 8. Job discovery every 15 minutes

```powershell
gcloud run jobs create careerops-discovery --image $IMAGE --region $REGION --service-account $SA `
  --command python --args="-m,careerops.workers.discovery" `
  --memory 2Gi --cpu 1 --task-timeout 15m --max-retries 0 `
  --env-vars-file deploy/gcp/env.yaml --set-secrets $SECRETS `
  --add-volume "name=data,type=cloud-storage,bucket=$BUCKET" --add-volume-mount "volume=data,mount-path=/data"

gcloud run jobs add-iam-policy-binding careerops-discovery --region $REGION --member "serviceAccount:$SA" --role roles/run.invoker

gcloud scheduler jobs create http careerops-discovery-15m --location $REGION --schedule "*/15 * * * *" `
  --uri "https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/careerops-discovery:run" `
  --http-method POST --oauth-service-account-email $SA

gcloud run jobs execute careerops-discovery --region $REGION --wait    # one run now, to check it works
```

## 9. Budget alert

In **Billing → Budgets & alerts**, create a budget for the project with email alerts, so an unexpected loop or traffic spike can't surprise you.

## Updating after code changes

```powershell
git pull
gcloud builds submit --tag $IMAGE
gcloud run deploy careerops --image $IMAGE --region $REGION
gcloud run jobs update careerops-discovery --image $IMAGE --region $REGION
```

## Notes

- **Your data starts empty.** Upload your master resume and verify your work-authorization answers on `/profile` in the hosted copy. To move your local database instead, `pg_dump` the local Postgres (port 5433) and restore it into Neon.
- **Scripts and the MCP server** can call the API with `Authorization: Bearer <API_TOKEN>`. Add a `careerops-api-token` secret (32+ random characters) mapped to `API_TOKEN`.
- **Logs:** `gcloud run services logs read careerops --region $REGION` and `gcloud run jobs executions list --job careerops-discovery --region $REGION`.
- **Friends later:** keep `ALLOWED_EMAILS` to yourself. Each person can deploy their own copy with this guide; a shared multi-user version is a separate piece of work.
