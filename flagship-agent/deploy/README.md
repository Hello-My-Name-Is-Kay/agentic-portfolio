# Deploying to Amazon Bedrock AgentCore Runtime

The agent runs on **AgentCore Runtime** (HTTP protocol, ARM64/Graviton). Conversation state is checkpointed to
**AgentCore Memory**, every message is screened by **Bedrock Guardrails**, and intent is classified by **Claude on
Bedrock**. The mock booking API runs beside the agent on localhost (demo only): its data resets whenever AgentCore
recycles the session's microVM, while the conversation itself stays in AgentCore Memory for 7 days.

```
client ──SigV4──▶ AgentCore Runtime (microVM per session)
                    ├─ ApplyGuardrail ── Bedrock Guardrails (v1, pinned)
                    ├─ LangGraph agent ── Claude Haiku 4.5 (Converse, EU inference profile)
                    │    └─ checkpoints ── AgentCore Memory (7-day expiry)
                    └─ mock booking API (127.0.0.1:8000)
```

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage ARM64 image, non-root user, port 8080 |
| `start.sh` | Starts the booking API, then `agent-agentcore` (`exec`, so SIGTERM reaches it) |
| `buildspec.yml` | AWS CodeBuild on a native ARM machine: build, check architecture, push to ECR |
| `iam/*.json` | Least-privilege roles with `${ACCOUNT_ID}`/`${REGION}` placeholders (`envsubst`) |
| `main.py`, `build_code_zip.sh` | Alternative: AgentCore *direct code* deployment (zip of ARM64 wheels, no Docker) |

## One-time setup

Region `eu-north-1`. Replace the IDs with your own.

```bash
export REGION=eu-north-1 ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export BUCKET=flagship-agent-build-${ACCOUNT_ID} GUARDRAIL_ID=<guardrail id> MEMORY_ID=<memory id>
REPO=${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/flagship-agent

aws ecr create-repository --repository-name flagship-agent --image-scanning-configuration scanOnPush=true
aws s3api create-bucket --bucket $BUCKET --create-bucket-configuration LocationConstraint=$REGION
aws bedrock-agentcore-control create-memory --name flagship_agent_memory --event-expiry-duration 7

aws iam create-role --role-name flagship-agent-codebuild --assume-role-policy-document "$(envsubst < iam/codebuild-trust.json)"
aws iam put-role-policy --role-name flagship-agent-codebuild --policy-name build --policy-document "$(envsubst < iam/codebuild-policy.json)"
aws iam create-role --role-name flagship-agent-runtime --assume-role-policy-document "$(envsubst < iam/runtime-trust.json)"
aws iam put-role-policy --role-name flagship-agent-runtime --policy-name runtime --policy-document "$(envsubst < iam/runtime-policy.json)"

aws codebuild create-project --name flagship-agent-image \
  --source "type=S3,location=${BUCKET}/source/flagship-agent.zip,buildspec=flagship-agent/deploy/buildspec.yml" \
  --artifacts type=NO_ARTIFACTS --service-role "arn:aws:iam::${ACCOUNT_ID}:role/flagship-agent-codebuild" \
  --environment "type=ARM_CONTAINER,image=aws/codebuild/amazonlinux-aarch64-standard:3.0,computeType=BUILD_GENERAL1_SMALL,privilegedMode=true,environmentVariables=[{name=ECR_REPOSITORY_URI,value=${REPO}},{name=IMAGE_TAG,value=v0.4.2}]"
```

In zsh, write `${ACCOUNT_ID}:role`, not `$ACCOUNT_ID:role`: `:r` is a zsh modifier and silently corrupts the ARN.

## Build and deploy

```bash
# from the repository root: upload source (flagship-agent/ and mock-booking-api/), build the image natively on ARM
aws s3 cp source.zip s3://$BUCKET/source/flagship-agent.zip
aws codebuild start-build --project-name flagship-agent-image

aws bedrock-agentcore-control create-agent-runtime --agent-runtime-name flagship_agent \
  --agent-runtime-artifact "{\"containerConfiguration\":{\"containerUri\":\"${REPO}:v0.4.2\"}}" \
  --role-arn "arn:aws:iam::${ACCOUNT_ID}:role/flagship-agent-runtime" \
  --network-configuration '{"networkMode":"PUBLIC"}' --protocol-configuration '{"serverProtocol":"HTTP"}' \
  --environment-variables "{\"AGENT_LLM\":\"bedrock\",\"AGENT_AWS_REGION\":\"${REGION}\",\"AGENT_GUARDRAIL_ID\":\"${GUARDRAIL_ID}\",\"AGENT_GUARDRAIL_VERSION\":\"1\",\"AGENT_MEMORY_ID\":\"${MEMORY_ID}\"}"
```

Callers are authenticated by AgentCore with IAM (SigV4). No secrets are passed as environment variables.

## Monitoring

The guardrail fails open, so a misconfiguration would silently let messages through unscreened. A metric filter on
the runtime log group counts `guardrail.unavailable` warnings, and an alarm fires on the first one:

```bash
aws logs put-metric-filter --log-group-name /aws/bedrock-agentcore/runtimes/<runtime id>-DEFAULT \
  --filter-name guardrail-unavailable --filter-pattern '"guardrail.unavailable"' \
  --metric-transformations metricName=GuardrailUnavailable,metricNamespace=FlagshipAgent,metricValue=1,defaultValue=0
aws cloudwatch put-metric-alarm --alarm-name flagship-agent-guardrail-unavailable --namespace FlagshipAgent \
  --metric-name GuardrailUnavailable --statistic Sum --period 300 --evaluation-periods 1 --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold --treat-missing-data notBreaching
```

Logs record message lengths only, never content, and keep 7 days.

## Invoke

```bash
SESSION=demo-$(date +%s)-conversation-0001     # 33+ characters; one session = one conversation
aws bedrock-agentcore invoke-agent-runtime --agent-runtime-arn <runtime arn> --runtime-session-id $SESSION \
  --payload '{"prompt": "I need to cancel R-00001"}' --cli-binary-format raw-in-base64-out /dev/stdout
```

## Tear down

```bash
aws cloudwatch delete-alarms --alarm-names flagship-agent-guardrail-unavailable
aws bedrock-agentcore-control delete-agent-runtime --agent-runtime-id <runtime id>
aws bedrock-agentcore-control delete-memory --memory-id $MEMORY_ID
aws codebuild delete-project --name flagship-agent-image
aws ecr delete-repository --repository-name flagship-agent --force
aws s3 rm s3://$BUCKET --recursive && aws s3api delete-bucket --bucket $BUCKET
for r in flagship-agent-runtime flagship-agent-codebuild; do
  aws iam delete-role-policy --role-name $r --policy-name $([ $r = flagship-agent-runtime ] && echo runtime || echo build)
  aws iam delete-role --role-name $r
done
```
