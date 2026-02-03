# GateReady AWS Deployment (S3 + CloudFront + API Gateway + Lambda + DynamoDB)

This guide documents a serverless AWS deployment for GateReady:

- **Frontend**: S3 (origin) + CloudFront (CDN)
- **Backend**: API Gateway + Lambda
- **Database**: DynamoDB
- **Auth**: JWT (issued by Lambda; validated by Lambda or API Gateway Authorizer)

---

## 1) Frontend (React) on S3 + CloudFront

### Build the frontend

```powershell
cd frontend
npm install
npm run build
```

This produces a `frontend/dist/` folder.

### Create S3 bucket

- Create an S3 bucket (e.g., `gateready-frontend-prod`)
- Disable public access (recommended)
- Upload `frontend/dist/` contents to the bucket

### CloudFront distribution

- Origin: the S3 bucket
- Enable **Origin Access Control (OAC)** or **OAI**
- Viewer protocol policy: **Redirect HTTP to HTTPS**
- Cache: default settings are fine for static files

### Custom domain (optional)

- Request certificate in ACM
- Attach to CloudFront
- Update DNS (Route 53 or your provider)

---

## 2) Backend on API Gateway + Lambda

### Lambda function

You can deploy a single Lambda with FastAPI using Mangum or package each route as its own Lambda.

**Recommended (single Lambda):**
- Create a Lambda function (Python runtime)
- Use Mangum to wrap FastAPI
- Package dependencies (zip or container)

**Runtime env vars:**

```
MONGODB_URI=
MONGODB_DB_NAME=booking_assistant
MONGODB_BOOKINGS_COLLECTION=bookings
MONGODB_USERS_COLLECTION=users
MONGODB_FLIGHT_INFO_COLLECTION=flight_info
JWT_SECRET=
JWT_REFRESH_SECRET=
ACCESS_TOKEN_TTL_MINUTES=15
REFRESH_TOKEN_TTL_DAYS=7
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
```

### API Gateway

- Create HTTP API (or REST API)
- Integrate with Lambda (proxy integration)
- Enable CORS:
  - Allow origin: your CloudFront domain
  - Allow headers: `Authorization`, `Content-Type`
  - Allow methods: `GET,POST,OPTIONS`

---

## 2b) Strands Session Memory on S3 (optional)

If you move the agent layer to **Strands Agents SDK**, you can persist chat sessions in S3 with
`S3SessionManager`. This stores conversation history per user/session.

Example (from Strands docs):

```python
from strands import Agent
from strands.session.s3_session_manager import S3SessionManager
import boto3

boto_session = boto3.Session(region_name="us-west-2")

session_manager = S3SessionManager(
    session_id="user-456",
    bucket="my-agent-sessions",
    prefix="production/",
    boto_session=boto_session,
    region_name="us-west-2"
)

agent = Agent(session_manager=session_manager)
agent("Hello!")
```

Operational notes:

- Use **S3 bucket** dedicated to session data.
- Set `session_id` to the authenticated `user_id`.
- Ensure Lambda has S3 read/write permissions.
- Session management is not supported in the TypeScript SDK.

---

## 3) DynamoDB Schema (if replacing MongoDB)

### Table: `Bookings`

- Partition key: `user_id` (string)
- Sort key: `date` (string, ISO timestamp)
- Attributes: `flight_number`, `origin`, `destination`, `status`

### Table: `FlightInfo`

- Partition key: `flight_number` (string)
- Attribute: `details_text`

### Table: `Users`

- Partition key: `user_id` (string)
- Attributes: `username`, `password_hash`

---

## 4) API Mapping (example)

- `POST /login` → Lambda → issue JWT
- `POST /refresh` → Lambda → refresh JWT
- `POST /logout` → Lambda → revoke refresh + clear memory
- `POST /chat` → Lambda → Strands/LangGraph agent
- `GET /bookings` → Lambda → DynamoDB query
- `GET /bookings/latest` → Lambda → DynamoDB query (desc sort)
- `GET /bookings/flight/{flight_number}` → Lambda → DynamoDB get
- `GET /flight-info/{flight_number}` → Lambda → DynamoDB get

---

## 5) CloudFront → API Gateway

Frontend should call the API Gateway URL. Example in frontend:

```
VITE_API_BASE=https://<api-id>.execute-api.<region>.amazonaws.com
```

---

## 6) Observability (optional)

- Enable CloudWatch logs for Lambda
- Add request IDs to responses
- Use API Gateway access logs

---

## 7) Notes

- Keep secrets in **Lambda environment variables** or AWS Secrets Manager.
- Use **OAC/OAI** to keep S3 private.
- Add API Gateway Authorizer if you want JWT validation at the edge.
